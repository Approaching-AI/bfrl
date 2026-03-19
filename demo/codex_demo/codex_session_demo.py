from __future__ import annotations

import argparse
import json
import math
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


TERMINAL_RESPONSE_STATES = {"completed", "failed", "cancelled", "incomplete"}
CODEX_APP_SERVER_TURN_TIMEOUT_SECONDS = 600

SESSION_INSTRUCTIONS = """You are the control loop for a Codex-style coding session.

Work in short tool-using turns:
1. Read the supplied task.
2. Use tools to inspect relevant project files before answering.
3. If useful, persist a concise learning note with append_daily_note.
4. Finish with a short summary of what happened in this session.

Stay grounded in the provided workspace. Do not invent file contents.
"""


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class TaskSpec:
    id: str
    title: str
    goal: str
    memory_paths: list[str] = field(default_factory=list)
    extra_context: str = ""
    system_prompt: str = ""
    system_prompt_path: str = ""
    allow_file_edits: bool = False

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "TaskSpec":
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            goal=str(payload["goal"]),
            memory_paths=[str(path) for path in payload.get("memory_paths", [])],
            extra_context=str(payload.get("extra_context", "")),
            system_prompt=str(payload.get("system_prompt", "")),
            system_prompt_path=str(payload.get("system_prompt_path", "")),
            allow_file_edits=bool(payload.get("allow_file_edits", False)),
        )


@dataclass
class FunctionCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str


@dataclass
class TurnResult:
    response_id: str
    status: str
    output_text: str
    function_calls: list[FunctionCall]
    carryover_items: list[dict[str, Any]]
    model_name: str | None
    usage: dict[str, Any] | None
    captured: dict[str, Any] | None
    raw_response: dict[str, Any]


@dataclass
class SessionContext:
    session_id: str
    workspace_root: Path
    notes_dir: Path
    logs_dir: Path
    task: TaskSpec
    adapter_name: str
    session_style: str
    max_turns: int
    turn_index: int = 0
    previous_response_id: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)


class DemoError(RuntimeError):
    pass


@dataclass
class ShellResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str


@dataclass
class RemoteTurn:
    assistant_message: str
    client_command: str | None
    done: bool


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def default_codex_auth_path() -> Path:
    return Path.home() / ".codex" / "auth.json"


def relative_to_workspace(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_workspace_path(workspace_root: Path, requested_path: str) -> Path:
    candidate = (workspace_root / requested_path).resolve()
    root = workspace_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise DemoError(f"Path escapes workspace: {requested_path}")
    return candidate


def load_task(task_path: Path) -> TaskSpec:
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    return TaskSpec.from_json(payload)


def resolve_task_system_prompt(task: TaskSpec, workspace_root: Path) -> str:
    inline_prompt = task.system_prompt.strip()
    if inline_prompt:
        return inline_prompt
    prompt_path = task.system_prompt_path.strip()
    if not prompt_path:
        return ""
    target = resolve_workspace_path(workspace_root, prompt_path)
    if not target.exists():
        raise DemoError(f"System prompt file not found: {prompt_path}")
    if not target.is_file():
        raise DemoError(f"System prompt path is not a file: {prompt_path}")
    return target.read_text(encoding="utf-8")


def session_instructions(task: TaskSpec, workspace_root: Path) -> str:
    custom_prompt = resolve_task_system_prompt(task, workspace_root).strip()
    if not custom_prompt:
        return SESSION_INSTRUCTIONS
    return "\n\n".join(
        [
            custom_prompt,
            "Execution defaults:",
            "- Stay grounded in the provided workspace.",
            "- Do not invent file contents.",
            "- Prefer inspecting relevant files before making claims.",
        ]
    )


def format_task_prompt(task: TaskSpec) -> str:
    sections = [
        f"Task id: {task.id}",
        f"Title: {task.title}",
        f"Goal: {task.goal}",
    ]
    if task.memory_paths:
        sections.append("Suggested starting files:\n- " + "\n- ".join(task.memory_paths))
    if task.extra_context:
        sections.append(f"Extra context: {task.extra_context}")
    sections.append(
        "Please inspect the workspace with tools before answering. "
        "If you discover something reusable, save a concise daily note."
    )
    return "\n\n".join(sections)


def format_command_proxy_prompt(task: TaskSpec) -> str:
    sections = [
        "You are operating in controller/client command-proxy mode.",
        "You may not directly read files or run local commands yourself.",
        "If you need evidence, request exactly one client command at a time.",
        "",
        f"Task id: {task.id}",
        f"Title: {task.title}",
        f"Goal: {task.goal}",
    ]
    if task.memory_paths:
        sections.append("Suggested starting files:\n- " + "\n- ".join(task.memory_paths))
    if task.extra_context:
        sections.append(f"Extra context: {task.extra_context}")
    return "\n".join(sections)


def format_codex_trace_prompt(task: TaskSpec, workspace_root: Path) -> str:
    custom_prompt = resolve_task_system_prompt(task, workspace_root).strip()
    sections = []
    if custom_prompt:
        sections.extend(
            [
                "System prompt:",
                custom_prompt,
                "",
            ]
        )
    sections.extend(
        [
            "This is a Codex session task.",
            "Do only the work needed for this task.",
            "Do not broaden the task.",
            "You may create or modify files if the task requires it." if task.allow_file_edits else "Do not create or modify files.",
            "",
            f"Task id: {task.id}",
            f"Title: {task.title}",
            f"Goal: {task.goal}",
        ]
    )
    if task.memory_paths:
        sections.append("Read the requested files, then return a very short summary.")
        sections.append("Read exactly these files first:")
        sections.extend(f"- {path}" for path in task.memory_paths)
    else:
        sections.append("If the task does not require files, answer directly with the minimum necessary text.")
    if task.extra_context:
        sections.extend(["", f"Extra context: {task.extra_context}"])
    sections.append("")
    sections.append("Output requirement:")
    if task.memory_paths:
        sections.extend(
            [
                "- 2 to 4 short sentences",
                "- stay strictly within the requested files and task goal",
            ]
        )
    else:
        sections.extend(
            [
                "- 1 short sentence if possible",
                "- answer the task directly and then stop",
            ]
        )
    return "\n".join(sections)


def format_codex_minimal_prompt(task: TaskSpec) -> str:
    goal = task.goal.strip()
    if goal:
        if not task.memory_paths and not task.extra_context and len(goal) <= 80:
            return f"Reply with exactly this text: {goal}"
        return goal
    title = task.title.strip()
    if title:
        return title
    return task.id


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def task_only_usage(task_prompt: str, final_text: str) -> dict[str, Any]:
    input_bytes = len(task_prompt.encode("utf-8"))
    output_bytes = len(final_text.encode("utf-8"))
    input_tokens = estimate_text_tokens(task_prompt)
    output_tokens = estimate_text_tokens(final_text)
    return {
        "input_bytes": input_bytes,
        "input_tokens_estimate": input_tokens,
        "output_bytes": output_bytes,
        "output_tokens_estimate": output_tokens,
        "total_tokens_estimate": input_tokens + output_tokens,
        "note": "Local estimate for only the task prompt and final answer. It excludes Codex-injected system/developer/context prompts.",
    }


def summarize_codex_session_file(session_path: str | None) -> dict[str, Any] | None:
    if not session_path:
        return None

    path = Path(session_path)
    if not path.exists():
        return None

    base_instructions_chars = 0
    developer_chars = 0
    environment_chars = 0
    task_prompt_chars = 0
    other_user_chars = 0

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = obj.get("payload", {})
        if obj.get("type") == "session_meta":
            base = payload.get("base_instructions", {}).get("text", "")
            if isinstance(base, str):
                base_instructions_chars = len(base)
            continue

        if obj.get("type") != "response_item" or payload.get("type") != "message":
            continue

        role = payload.get("role")
        chunks: list[str] = []
        for item in payload.get("content", []):
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
        joined = "\n".join(chunks)

        if role == "developer":
            developer_chars += len(joined)
            continue
        if role != "user":
            continue
        if joined.startswith("<environment_context>"):
            environment_chars += len(joined)
            continue
        if joined.startswith("<turn_aborted>"):
            other_user_chars += len(joined)
            continue
        task_prompt_chars += len(joined)

    total_overhead_chars = base_instructions_chars + developer_chars + environment_chars + other_user_chars
    return {
        "base_instructions_chars": base_instructions_chars,
        "developer_chars": developer_chars,
        "environment_chars": environment_chars,
        "other_user_chars": other_user_chars,
        "task_prompt_chars": task_prompt_chars,
        "overhead_chars": total_overhead_chars,
    }


def extract_message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if "text" in part and isinstance(part["text"], str):
            chunks.append(part["text"])
            continue
        if isinstance(part.get("text"), dict):
            maybe_text = part["text"].get("value")
            if isinstance(maybe_text, str):
                chunks.append(maybe_text)
    return "".join(chunks)


def next_daily_note_path(notes_dir: Path) -> Path:
    ensure_directory(notes_dir)
    prefix = datetime.now().strftime("%Y-%m-%d")
    existing = sorted(notes_dir.glob(f"{prefix}-*.md"))
    next_index = len(existing) + 1
    return notes_dir / f"{prefix}-{next_index:02d}.md"


def mock_usage(note: str) -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "note": note,
    }


def merge_usage_trees(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        existing = merged.get(key)
        if isinstance(value, dict):
            child = existing if isinstance(existing, dict) else {}
            merged[key] = merge_usage_trees(child, value)
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            previous = existing if isinstance(existing, (int, float)) and not isinstance(existing, bool) else 0
            merged[key] = previous + value
            continue
        if key not in merged:
            merged[key] = value
    return merged


def record_usage(state: dict[str, Any], usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    state["usage_summary"] = merge_usage_trees(state.get("usage_summary", {}), usage)


class ToolRegistry:
    def __init__(self, session: SessionContext) -> None:
        self.session = session
        self._tools: dict[str, tuple[dict[str, Any], Any]] = {
            "read_text_file": (
                {
                    "type": "function",
                    "name": "read_text_file",
                    "description": "Read a UTF-8 text file from the current workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path relative to the workspace root.",
                            },
                            "max_chars": {
                                "type": "integer",
                                "description": "Maximum number of characters to return.",
                                "default": 4000,
                            },
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
                self.read_text_file,
            ),
            "append_daily_note": (
                {
                    "type": "function",
                    "name": "append_daily_note",
                    "description": "Create a new markdown note in the configured daily notes directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Markdown heading for the note.",
                            },
                            "body": {
                                "type": "string",
                                "description": "Markdown body for the note.",
                            },
                        },
                        "required": ["title", "body"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
                self.append_daily_note,
            ),
            "list_memory_files": (
                {
                    "type": "function",
                    "name": "list_memory_files",
                    "description": "List markdown files under memory/ or another workspace-relative directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Directory relative to the workspace root.",
                                "default": "memory",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of files to return.",
                                "default": 20,
                            },
                        },
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
                self.list_memory_files,
            ),
        }

    def definitions(self) -> list[dict[str, Any]]:
        return [definition for definition, _handler in self._tools.values()]

    def execute(self, call: FunctionCall) -> dict[str, Any]:
        if call.name not in self._tools:
            raise DemoError(f"Unknown tool: {call.name}")
        _definition, handler = self._tools[call.name]
        return handler(**call.arguments)

    def read_text_file(self, path: str, max_chars: int = 4000) -> dict[str, Any]:
        if max_chars <= 0:
            raise DemoError("max_chars must be positive")
        target = resolve_workspace_path(self.session.workspace_root, path)
        if not target.exists():
            raise DemoError(f"File not found: {path}")
        if not target.is_file():
            raise DemoError(f"Not a file: {path}")

        text = target.read_text(encoding="utf-8", errors="replace")
        excerpt = text[:max_chars]
        result = {
            "path": relative_to_workspace(self.session.workspace_root, target),
            "characters_returned": len(excerpt),
            "truncated": len(text) > len(excerpt),
            "content": excerpt,
        }
        self.session.state.setdefault("read_paths", []).append(result["path"])
        return result

    def append_daily_note(self, title: str, body: str) -> dict[str, Any]:
        note_path = next_daily_note_path(self.session.notes_dir)
        note = "\n".join(
            [
                f"# {title}",
                "",
                f"- task_id: {self.session.task.id}",
                f"- session_id: {self.session.session_id}",
                f"- created_at: {iso_now()}",
                "",
                body.strip(),
                "",
            ]
        )
        note_path.write_text(note, encoding="utf-8")
        rel_path = relative_to_workspace(self.session.workspace_root, note_path)
        self.session.state["daily_note_path"] = rel_path
        return {"note_path": rel_path}

    def list_memory_files(self, directory: str = "memory", limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(limit, 200))
        target = resolve_workspace_path(self.session.workspace_root, directory)
        if not target.exists():
            raise DemoError(f"Directory not found: {directory}")
        if not target.is_dir():
            raise DemoError(f"Not a directory: {directory}")

        files = [
            relative_to_workspace(self.session.workspace_root, path)
            for path in sorted(target.rglob("*.md"))[:limit]
        ]
        return {"directory": relative_to_workspace(self.session.workspace_root, target), "files": files}


class MockModelAdapter:
    name = "mock"

    def create_turn(
        self,
        session: SessionContext,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> TurnResult:
        _ = input_items
        _ = tools
        session.turn_index += 1
        response_id = f"mock_resp_{session.turn_index}"
        read_paths = session.state.get("read_paths", [])
        target_paths = session.task.memory_paths
        note_path = session.state.get("daily_note_path")

        if len(read_paths) < len(target_paths):
            next_path = target_paths[len(read_paths)]
            call = FunctionCall(
                call_id=f"mock_call_{session.turn_index}",
                name="read_text_file",
                arguments={"path": next_path, "max_chars": 2500},
                raw_arguments=json.dumps({"path": next_path, "max_chars": 2500}, ensure_ascii=False),
            )
            return TurnResult(
                response_id=response_id,
                status="completed",
                output_text="",
                function_calls=[call],
                carryover_items=[],
                model_name="mock-local",
                usage=mock_usage("No API call was made. This turn was produced by the local mock adapter."),
                captured=None,
                raw_response={"id": response_id, "status": "completed", "mode": "mock"},
            )

        if not note_path:
            summary_lines = [
                "This note was created by the mock Codex session demo.",
                "",
                f"Task goal: {session.task.goal}",
                "",
                "Files inspected:",
            ]
            for path in read_paths:
                summary_lines.append(f"- {path}")
            if session.task.extra_context:
                summary_lines.extend(["", f"Extra context: {session.task.extra_context}"])
            call = FunctionCall(
                call_id=f"mock_call_{session.turn_index}",
                name="append_daily_note",
                arguments={
                    "title": f"Demo session note for {session.task.id}",
                    "body": "\n".join(summary_lines),
                },
                raw_arguments=json.dumps(
                    {
                        "title": f"Demo session note for {session.task.id}",
                        "body": "\n".join(summary_lines),
                    },
                    ensure_ascii=False,
                ),
            )
            return TurnResult(
                response_id=response_id,
                status="completed",
                output_text="",
                function_calls=[call],
                carryover_items=[],
                model_name="mock-local",
                usage=mock_usage("No API call was made. This turn was produced by the local mock adapter."),
                captured=None,
                raw_response={"id": response_id, "status": "completed", "mode": "mock"},
            )

        output_text = "\n".join(
            [
                f"Session completed for task `{session.task.id}`.",
                f"- inspected_files: {len(read_paths)}",
                f"- daily_note: {note_path}",
                "- next customization point: swap the mock adapter for the OpenAI Responses adapter.",
            ]
        )
        return TurnResult(
            response_id=response_id,
            status="completed",
            output_text=output_text,
            function_calls=[],
            carryover_items=[],
            model_name="mock-local",
            usage=mock_usage("No API call was made. This turn was produced by the local mock adapter."),
            captured=None,
            raw_response={"id": response_id, "status": "completed", "mode": "mock"},
        )


class MockCommandProxyDriver:
    def __init__(self, shell_name: str) -> None:
        self.shell_name = shell_name

    def create_turn(self, session: SessionContext) -> RemoteTurn:
        read_paths = session.state.get("proxy_read_paths", [])
        target_paths = session.task.memory_paths
        note_path = session.state.get("daily_note_path")

        if len(read_paths) < len(target_paths):
            next_path = target_paths[len(read_paths)]
            return RemoteTurn(
                assistant_message=f"I need the controller to inspect `{next_path}` on the target client.",
                client_command=build_file_read_command(next_path, self.shell_name),
                done=False,
            )

        if not note_path:
            return RemoteTurn(
                assistant_message="The controller has enough evidence. Persist a concise note, then conclude.",
                client_command=None,
                done=False,
            )

        return RemoteTurn(
            assistant_message=(
                f"Task `{session.task.id}` is complete. "
                f"The controller collected remote evidence and wrote `{note_path}`."
            ),
            client_command=None,
            done=True,
        )


class OpenAIResponsesAdapter:
    name = "openai"

    def __init__(
        self,
        api_token: str,
        model: str,
        background: bool,
        poll_interval_seconds: float,
        reasoning_effort: str | None,
        auth_source: str,
    ) -> None:
        self.api_token = api_token
        self.model = model
        self.background = background
        self.poll_interval_seconds = poll_interval_seconds
        self.reasoning_effort = reasoning_effort
        self.auth_source = auth_source

    def create_turn(
        self,
        session: SessionContext,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> TurnResult:
        session.turn_index += 1
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": session_instructions(session.task, session.workspace_root),
            "input": input_items,
            "tools": tools,
        }
        if session.previous_response_id:
            payload["previous_response_id"] = session.previous_response_id
        if self.background:
            payload["background"] = True
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}

        response = self._request("POST", "/responses", payload)
        if self.background:
            while response.get("status") in {"queued", "in_progress"}:
                time.sleep(self.poll_interval_seconds)
                response = self._request("GET", f"/responses/{response['id']}")

        return self._parse_response(response)

    def _parse_response(self, response: dict[str, Any]) -> TurnResult:
        function_calls: list[FunctionCall] = []
        carryover_items: list[dict[str, Any]] = []
        messages: list[str] = []

        for item in response.get("output", []):
            item_type = item.get("type")
            if item_type == "function_call":
                raw_arguments = item.get("arguments", "{}")
                try:
                    parsed_arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise DemoError(f"Invalid tool arguments returned by model: {raw_arguments}") from exc
                function_calls.append(
                    FunctionCall(
                        call_id=str(item["call_id"]),
                        name=str(item["name"]),
                        arguments=parsed_arguments,
                        raw_arguments=raw_arguments,
                    )
                )
                continue
            if item_type == "message":
                text = extract_message_text(item)
                if text:
                    messages.append(text)
                continue
            carryover_items.append(item)

        output_text = response.get("output_text") or "\n".join(messages)
        return TurnResult(
            response_id=str(response["id"]),
            status=str(response.get("status", "completed")),
            output_text=output_text,
            function_calls=function_calls,
            carryover_items=carryover_items,
            model_name=response.get("model"),
            usage=response.get("usage"),
            captured=None,
            raw_response=response,
        )

    def _request(self, method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"https://api.openai.com/v1{endpoint}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise DemoError(f"OpenAI API request failed ({exc.code}): {details}") from exc
        except urllib.error.URLError as exc:
            raise DemoError(f"OpenAI API request failed: {exc}") from exc


class CodexCLIAdapter:
    name = "codex"

    def __init__(self, model: str, workspace_root: Path, prompt_mode: str) -> None:
        self.model = model
        self.workspace_root = workspace_root
        self.prompt_mode = prompt_mode

    def create_turn(
        self,
        session: SessionContext,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> TurnResult:
        _ = tools
        session.turn_index += 1
        _ = input_items
        can_use_minimal = (
            self.prompt_mode == "minimal"
            and not session.task.allow_file_edits
            and not session.task.system_prompt.strip()
            and not session.task.system_prompt_path.strip()
        )
        if can_use_minimal:
            prompt = format_codex_minimal_prompt(session.task)
        else:
            prompt = format_codex_trace_prompt(session.task, session.workspace_root)
        session.state["prompt_text"] = prompt
        session.state["codex_prompt_mode"] = self.prompt_mode

        driver = CodexAppServerDriver(
            model=self.model,
            workspace_root=self.workspace_root,
            allow_file_edits=session.task.allow_file_edits,
        )
        try:
            driver.start()
            thread_info = driver.start_thread()
            turn_info = driver.run_turn(prompt)
        finally:
            driver.close()

        final_text = turn_info.get("final_answer") or ""
        if not final_text:
            raise DemoError("codex app-server completed without a final answer.")

        captured = {
            "thread_id": thread_info["thread_id"],
            "thread_path": thread_info.get("thread_path"),
            "turn_id": turn_info["turn_id"],
            "commands": turn_info["commands"],
            "usage": turn_info.get("usage"),
            "stderr": turn_info.get("stderr_lines", []),
        }
        prompt_breakdown = summarize_codex_session_file(thread_info.get("thread_path"))
        if prompt_breakdown is not None:
            captured["prompt_breakdown"] = prompt_breakdown
        return TurnResult(
            response_id=thread_info["thread_id"],
            status="completed",
            output_text=final_text,
            function_calls=[],
            carryover_items=[],
            model_name=thread_info.get("model") or self.model,
            usage=turn_info.get("usage"),
            captured=captured,
            raw_response={
                "thread": thread_info,
                "turn": turn_info,
            },
        )


class CodexAppServerDriver:
    def __init__(self, model: str, workspace_root: Path, allow_file_edits: bool) -> None:
        self.model = model
        self.workspace_root = workspace_root
        self.allow_file_edits = allow_file_edits
        self.process: subprocess.Popen[str] | None = None
        self.messages: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.thread_id: str | None = None

    def start(self) -> None:
        command = [
            "cmd.exe",
            "/c",
            "codex",
            "-m",
            self.model,
            "app-server",
            "--listen",
            "stdio://",
        ]
        self.process = subprocess.Popen(
            command,
            cwd=self.workspace_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._pump_stream(self.process.stdout, "stdout")
        self._pump_stream(self.process.stderr, "stderr")
        self._initialize()

    def close(self) -> None:
        if not self.process:
            return
        try:
            self.process.kill()
        except Exception:
            pass
        try:
            self.process.wait(timeout=5)
        except Exception:
            pass

    def start_thread(self) -> dict[str, Any]:
        approval_policy = "never" if self.allow_file_edits else "untrusted"
        response = self._request(
            2,
            "thread/start",
            {
                "cwd": str(self.workspace_root),
                "approvalPolicy": approval_policy,
                "sandbox": "workspace-write" if self.allow_file_edits else "read-only",
                "ephemeral": False,
                "experimentalRawEvents": False,
                "persistExtendedHistory": True,
            },
        )
        result = response.get("result", {})
        thread = result.get("thread", {})
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise DemoError("codex app-server thread/start did not return a thread id.")
        self.thread_id = thread_id
        return {
            "thread_id": thread_id,
            "thread_path": thread.get("path"),
            "model": result.get("model"),
            "raw": response,
        }

    def run_turn(self, prompt: str) -> dict[str, Any]:
        if not self.thread_id:
            raise DemoError("Thread must be started before run_turn.")
        approval_policy = "never" if self.allow_file_edits else "untrusted"

        response = self._request(
            3,
            "turn/start",
            {
                "threadId": self.thread_id,
                "input": [
                    {
                        "type": "text",
                        "text": prompt,
                        "text_elements": [],
                    }
                ],
                "approvalPolicy": approval_policy,
                "sandboxPolicy": (
                    {
                        "type": "workspaceWrite",
                        "networkAccess": False,
                    }
                    if self.allow_file_edits
                    else {
                        "type": "readOnly",
                        "access": {"type": "fullAccess"},
                        "networkAccess": False,
                    }
                ),
            },
        )
        turn = response.get("result", {}).get("turn", {})
        turn_id = turn.get("id")
        if not isinstance(turn_id, str) or not turn_id:
            raise DemoError("codex app-server turn/start did not return a turn id.")

        final_answer = ""
        usage: dict[str, Any] | None = None
        stderr_lines: list[str] = []
        commands: dict[str, dict[str, Any]] = {}
        events: list[dict[str, Any]] = []
        while True:
            channel, envelope = self._read_message(timeout=CODEX_APP_SERVER_TURN_TIMEOUT_SECONDS)
            if channel == "stderr":
                stderr_lines.append(envelope)
                continue

            obj = self._parse_json(envelope)
            if obj is None:
                continue
            events.append(obj)
            method = obj.get("method")
            if method == "thread/tokenUsage/updated":
                params = obj.get("params", {})
                token_usage = params.get("tokenUsage", {})
                total = token_usage.get("total")
                if isinstance(total, dict):
                    usage = {
                        "input_tokens": total.get("inputTokens"),
                        "cached_input_tokens": total.get("cachedInputTokens"),
                        "output_tokens": total.get("outputTokens"),
                        "reasoning_output_tokens": total.get("reasoningOutputTokens"),
                        "total_tokens": total.get("totalTokens"),
                    }
                continue

            if method in {"item/started", "item/completed"}:
                params = obj.get("params", {})
                if params.get("turnId") != turn_id:
                    continue
                item = params.get("item", {})
                item_type = item.get("type")
                if item_type == "agentMessage" and item.get("phase") == "final_answer":
                    text = item.get("text")
                    if isinstance(text, str):
                        final_answer = text
                if item_type == "commandExecution":
                    command_id = item.get("id")
                    if not isinstance(command_id, str):
                        continue
                    command_state = commands.setdefault(command_id, {"id": command_id})
                    command_state.update(
                        {
                            "command": item.get("command"),
                            "cwd": item.get("cwd"),
                            "status": item.get("status"),
                            "exit_code": item.get("exitCode"),
                            "duration_ms": item.get("durationMs"),
                            "aggregated_output": item.get("aggregatedOutput"),
                        }
                    )
                continue

            if method == "turn/completed":
                params = obj.get("params", {})
                completed_turn = params.get("turn", {})
                if completed_turn.get("id") == turn_id:
                    break

        return {
            "turn_id": turn_id,
            "final_answer": final_answer,
            "usage": usage,
            "commands": list(commands.values()),
            "stderr_lines": stderr_lines,
            "events": events,
        }

    def _initialize(self) -> None:
        self._request(
            1,
            "initialize",
            {
                "clientInfo": {
                    "name": "codex-session-demo",
                    "title": "codex-session-demo",
                    "version": "0.1",
                },
                "capabilities": {
                    "experimentalApi": True,
                },
            },
        )
        self._send({"method": "initialized"})

    def _pump_stream(self, pipe: Any, name: str) -> None:
        def _worker() -> None:
            if pipe is None:
                return
            for line in pipe:
                self.messages.put((name, line.rstrip("\n")))
            self.messages.put((name, "<EOF>"))

        threading.Thread(target=_worker, daemon=True).start()

    def _send(self, obj: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise DemoError("codex app-server stdin is not available.")
        self.process.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _request(self, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            channel, envelope = self._read_message(timeout=60)
            if channel == "stderr":
                continue
            obj = self._parse_json(envelope)
            if obj is None:
                continue
            if obj.get("id") == request_id and not obj.get("method"):
                if obj.get("error"):
                    raise DemoError(f"codex app-server {method} failed: {obj['error']}")
                return obj

    def _read_message(self, timeout: float) -> tuple[str, str]:
        if not self.process:
            raise DemoError("codex app-server process is not running.")
        try:
            channel, envelope = self.messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise DemoError("Timed out waiting for codex app-server event.") from exc
        if envelope == "<EOF>":
            raise DemoError("codex app-server exited unexpectedly.")
        return channel, envelope

    @staticmethod
    def _parse_json(raw_line: str) -> dict[str, Any] | None:
        try:
            return json.loads(raw_line)
        except json.JSONDecodeError:
            return None


def resolve_openai_auth_token(args: argparse.Namespace) -> tuple[str, str]:
    if args.api_key:
        return args.api_key, "cli --api-key"

    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        return env_key, "environment OPENAI_API_KEY"

    auth_path = Path(args.auth_file).expanduser().resolve()
    if auth_path.exists():
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
        file_key = payload.get("OPENAI_API_KEY")
        if isinstance(file_key, str) and file_key.strip():
            return file_key.strip(), f"{auth_path}::OPENAI_API_KEY"

        tokens = payload.get("tokens")
        if isinstance(tokens, dict):
            access_token = tokens.get("access_token")
            if isinstance(access_token, str) and access_token.strip():
                return access_token.strip(), f"{auth_path}::tokens.access_token"

    raise DemoError(
        "No auth token found. Checked --api-key, OPENAI_API_KEY, and "
        f"{auth_path}."
    )


def build_adapter(args: argparse.Namespace) -> MockModelAdapter | OpenAIResponsesAdapter | CodexCLIAdapter:
    if args.mode == "mock":
        return MockModelAdapter()
    if args.mode == "codex":
        return CodexCLIAdapter(
            model=args.model,
            workspace_root=Path(args.workspace_root).resolve(),
            prompt_mode=args.codex_prompt_mode,
        )

    api_token, auth_source = resolve_openai_auth_token(args)
    return OpenAIResponsesAdapter(
        api_token=api_token,
        model=args.model,
        background=args.background,
        poll_interval_seconds=args.poll_interval,
        reasoning_effort=args.reasoning_effort,
        auth_source=auth_source,
    )


class ShellCommandRunner:
    def __init__(self, shell_name: str, workspace_root: Path) -> None:
        self.shell_name = shell_name
        self.workspace_root = workspace_root

    def run(self, command: str) -> ShellResult:
        started_at = iso_now()
        completed = subprocess.run(
            self._shell_command(command),
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return ShellResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            started_at=started_at,
            finished_at=iso_now(),
        )

    def _shell_command(self, command: str) -> list[str]:
        if self.shell_name == "powershell":
            return ["powershell.exe", "-NoProfile", "-Command", command]
        if self.shell_name == "cmd":
            return ["cmd.exe", "/C", command]
        if self.shell_name == "bash":
            return ["bash", "-lc", command]
        if self.shell_name == "sh":
            return ["sh", "-lc", command]
        raise DemoError(f"Unsupported shell: {self.shell_name}")


def build_file_read_command(path: str, shell_name: str) -> str:
    if shell_name == "powershell":
        quoted = path.replace("'", "''")
        return f"Get-Content -Path '{quoted}' -Encoding utf8 -TotalCount 80"
    if shell_name == "cmd":
        return f'type "{path}"'
    if shell_name in {"bash", "sh"}:
        return f"sed -n '1,80p' {shlex.quote(path)}"
        raise DemoError(f"Unsupported shell for file read command: {shell_name}")


def present_usage(
    usage_view: str,
    raw_usage: dict[str, Any] | None,
    task_prompt: str,
    final_text: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if usage_view == "raw":
        return raw_usage, None

    task_usage = task_only_usage(task_prompt, final_text)
    if raw_usage is None:
        return task_usage, None
    return task_usage, raw_usage


def run_session(
    session: SessionContext,
    adapter: MockModelAdapter | OpenAIResponsesAdapter | CodexCLIAdapter,
) -> dict[str, Any]:
    if session.session_style == "command-proxy":
        return run_command_proxy_session(session, adapter)

    tools = ToolRegistry(session)
    initial_prompt = format_task_prompt(session.task)
    session.state.setdefault("prompt_text", initial_prompt)
    input_items: list[dict[str, Any]] = [{"role": "user", "content": initial_prompt}]
    final_text = ""

    while session.turn_index < session.max_turns:
        turn = adapter.create_turn(session=session, input_items=input_items, tools=tools.definitions())
        session.previous_response_id = turn.response_id
        if turn.model_name:
            session.state["model"] = turn.model_name
        record_usage(session.state, turn.usage)

        turn_record: dict[str, Any] = {
            "timestamp": iso_now(),
            "turn_index": session.turn_index,
            "response_id": turn.response_id,
            "model": turn.model_name,
            "status": turn.status,
            "output_text": turn.output_text,
            "usage": turn.usage,
            "function_calls": [],
        }
        if turn.captured is not None:
            turn_record["captured"] = turn.captured

        if turn.function_calls:
            tool_outputs: list[dict[str, Any]] = []
            for call in turn.function_calls:
                output: dict[str, Any]
                try:
                    output = tools.execute(call)
                except Exception as exc:  # noqa: BLE001 - demo should log tool failures verbosely.
                    output = {"error": str(exc)}

                turn_record["function_calls"].append(
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "output": output,
                    }
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(output, ensure_ascii=False),
                    }
                )

            session.trace.append(turn_record)
            input_items = turn.carryover_items + tool_outputs
            continue

        final_text = turn.output_text
        session.trace.append(turn_record)
        break
    else:
        raise DemoError(f"Session exceeded max_turns={session.max_turns}")

    log_path = write_session_log(session, final_text)
    selected_usage, raw_usage = present_usage(
        usage_view=str(session.state.get("usage_view", "raw")),
        raw_usage=session.state.get("usage_summary"),
        task_prompt=str(session.state.get("prompt_text", "")),
        final_text=final_text,
    )
    result = {
        "task_id": session.task.id,
        "session_id": session.session_id,
        "adapter": adapter.name,
        "session_style": session.session_style,
        "model": session.state.get("model"),
        "usage_mode": session.state.get("usage_view"),
        "usage": selected_usage,
        "captured": session.trace[-1].get("captured") if session.trace else None,
        "turns": session.turn_index,
        "final_text": final_text,
        "log_path": relative_to_workspace(session.workspace_root, log_path),
        "daily_note_path": session.state.get("daily_note_path"),
    }
    if raw_usage is not None:
        result["raw_usage"] = raw_usage
    return result

def run_command_proxy_session(
    session: SessionContext,
    adapter: MockModelAdapter | OpenAIResponsesAdapter | CodexCLIAdapter,
) -> dict[str, Any]:
    if adapter.name != "mock":
        raise DemoError("command-proxy mode currently supports --mode mock only.")

    driver = MockCommandProxyDriver(shell_name=session.state["shell_name"])
    runner = ShellCommandRunner(
        shell_name=session.state["shell_name"],
        workspace_root=session.workspace_root,
    )
    tools = ToolRegistry(session)
    final_text = ""
    session.state["model"] = "mock-local-command-proxy"
    session.state["usage_summary"] = mock_usage(
        "No API call was made. Command-proxy mode is currently implemented as a local mock controller."
    )

    session.state["command_proxy_prompt"] = format_command_proxy_prompt(session.task)

    while session.turn_index < session.max_turns:
        session.turn_index += 1
        turn = driver.create_turn(session)
        turn_record: dict[str, Any] = {
            "timestamp": iso_now(),
            "turn_index": session.turn_index,
            "model": session.state["model"],
            "assistant_message": turn.assistant_message,
            "client_command": turn.client_command,
            "done": turn.done,
            "usage": mock_usage(
                "No API call was made. Command-proxy mode is currently implemented as a local mock controller."
            ),
        }

        if turn.client_command:
            result = runner.run(turn.client_command)
            turn_record["remote_result"] = {
                "command": result.command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
            }
            session.state.setdefault("proxy_command_results", []).append(turn_record["remote_result"])

            next_path_index = len(session.state.get("proxy_read_paths", []))
            if next_path_index < len(session.task.memory_paths):
                session.state.setdefault("proxy_read_paths", []).append(session.task.memory_paths[next_path_index])

            session.trace.append(turn_record)
            continue

        if not turn.done:
            summary_lines = [
                "This note was created by the command-proxy branch of the Codex session demo.",
                "",
                f"Task goal: {session.task.goal}",
                "",
                "Proxied commands:",
            ]
            for result in session.state.get("proxy_command_results", []):
                summary_lines.append(f"- `{result['command']}` -> exit_code={result['exit_code']}")
            note_output = tools.append_daily_note(
                title=f"Command-proxy demo note for {session.task.id}",
                body="\n".join(summary_lines),
            )
            turn_record["controller_action"] = {"append_daily_note": note_output}
            session.trace.append(turn_record)
            continue

        final_text = turn.assistant_message
        session.trace.append(turn_record)
        break
    else:
        raise DemoError(f"Session exceeded max_turns={session.max_turns}")

    log_path = write_session_log(session, final_text)
    return {
        "task_id": session.task.id,
        "session_id": session.session_id,
        "adapter": adapter.name,
        "session_style": session.session_style,
        "model": session.state.get("model"),
        "usage": session.state.get("usage_summary"),
        "turns": session.turn_index,
        "final_text": final_text,
        "log_path": relative_to_workspace(session.workspace_root, log_path),
        "daily_note_path": session.state.get("daily_note_path"),
    }


def write_session_log(session: SessionContext, final_text: str) -> Path:
    ensure_directory(session.logs_dir)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    log_path = session.logs_dir / f"{date_prefix}-{session.task.id}-{session.session_id}.json"
    payload = {
        "session_id": session.session_id,
        "created_at": iso_now(),
        "adapter": session.adapter_name,
        "session_style": session.session_style,
        "task": {
            "id": session.task.id,
            "title": session.task.title,
            "goal": session.task.goal,
            "memory_paths": session.task.memory_paths,
            "extra_context": session.task.extra_context,
            "system_prompt": session.task.system_prompt,
            "system_prompt_path": session.task.system_prompt_path,
            "allow_file_edits": session.task.allow_file_edits,
        },
        "state": session.state,
        "trace": session.trace,
        "final_text": final_text,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path


def build_session_context(args: argparse.Namespace, task: TaskSpec) -> SessionContext:
    workspace_root = Path(args.workspace_root).resolve()
    notes_dir = resolve_workspace_path(workspace_root, args.notes_dir)
    logs_dir = resolve_workspace_path(workspace_root, args.logs_dir)
    ensure_directory(notes_dir)
    ensure_directory(logs_dir)
    return SessionContext(
        session_id=uuid4().hex[:10],
        workspace_root=workspace_root,
        notes_dir=notes_dir,
        logs_dir=logs_dir,
        task=task,
        adapter_name=args.mode,
        session_style=args.session_style,
        max_turns=args.max_turns,
        state={"shell_name": args.shell, "usage_view": args.usage_view},
    )


def run_single_task(args: argparse.Namespace, adapter: MockModelAdapter | OpenAIResponsesAdapter | CodexCLIAdapter) -> int:
    task_path = Path(args.task).resolve()
    task = load_task(task_path)
    session = build_session_context(args, task)
    result = run_session(session, adapter)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def process_inbox_task(
    task_path: Path,
    args: argparse.Namespace,
    adapter: MockModelAdapter | OpenAIResponsesAdapter | CodexCLIAdapter,
) -> dict[str, Any]:
    task = load_task(task_path)
    session = build_session_context(args, task)
    result = run_session(session, adapter)

    archive_dir = resolve_workspace_path(session.workspace_root, args.archive_dir)
    ensure_directory(archive_dir)
    archived_path = archive_dir / task_path.name
    shutil.move(str(task_path), archived_path)
    result["archived_task"] = relative_to_workspace(session.workspace_root, archived_path)
    return result


def watch_inbox(args: argparse.Namespace, adapter: MockModelAdapter | OpenAIResponsesAdapter | CodexCLIAdapter) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    inbox_dir = resolve_workspace_path(workspace_root, args.inbox_dir)
    archive_dir = resolve_workspace_path(workspace_root, args.archive_dir)
    ensure_directory(inbox_dir)
    ensure_directory(archive_dir)

    processed = 0
    while True:
        task_files = sorted(inbox_dir.glob("*.json"))
        if task_files:
            result = process_inbox_task(task_files[0], args, adapter)
            processed += 1
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.max_tasks and processed >= args.max_tasks:
                return 0
            continue

        if args.once:
            return 0
        time.sleep(args.poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a minimal Codex-style session demo with task polling and memory artifacts."
    )
    parser.add_argument("--mode", choices=["mock", "openai", "codex"], default="mock")
    parser.add_argument("--session-style", choices=["tool-loop", "command-proxy"], default="tool-loop")
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--notes-dir", default="memory/daily-notes")
    parser.add_argument("--logs-dir", default="memory/logs")
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--auth-file", default=str(default_codex_auth_path()))
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--usage-view", choices=["raw", "task-only"], default="raw")
    parser.add_argument("--codex-prompt-mode", choices=["trace", "minimal"], default="trace")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--shell", choices=["powershell", "cmd", "bash", "sh"], default="powershell")
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh"],
        default="medium",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a single task file.")
    run_parser.add_argument("--task", required=True)

    watch_parser = subparsers.add_parser("watch", help="Poll an inbox directory for tasks.")
    watch_parser.add_argument("--inbox-dir", default="demo/inbox")
    watch_parser.add_argument("--archive-dir", default="demo/archive")
    watch_parser.add_argument("--once", action="store_true")
    watch_parser.add_argument("--max-tasks", type=int, default=0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        adapter = build_adapter(args)
        if args.command == "run":
            return run_single_task(args, adapter)
        if args.command == "watch":
            return watch_inbox(args, adapter)
        raise DemoError(f"Unknown command: {args.command}")
    except DemoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
