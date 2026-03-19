from __future__ import annotations

import argparse
from pathlib import Path

from lib.codex_session_runner import (
    TaskSpec,
    build_adapter,
    build_session_context,
    ensure_directory,
    iso_now,
    relative_to_workspace,
    run_session,
)
from runners.base import ExecutionRequest, ExecutionResult, RunnerAdapter


class CodexRunner(RunnerAdapter):
    kind = "codex"

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        launcher_root = request.runner_workspace_dir
        logs_dir = launcher_root / "runs"
        scratch_dir = launcher_root / "scratch"
        state_dir = launcher_root / "state"

        for path in [launcher_root, logs_dir, scratch_dir, state_dir]:
            ensure_directory(path)

        task = TaskSpec(
            id=request.task.id,
            title=request.task.title,
            goal=request.task.goal,
            memory_paths=list(request.task.memory_paths),
            extra_context=request.task.extra_context,
            system_prompt_path=request.task.system_prompt_path,
            allow_file_edits=request.task.allow_file_edits,
        )

        args = argparse.Namespace(
            mode="codex",
            session_style=str(request.launcher_config.get("session_style", "tool-loop")),
            workspace_root=str(request.workspace_root),
            notes_dir=relative_to_workspace(request.workspace_root, scratch_dir),
            logs_dir=relative_to_workspace(request.workspace_root, logs_dir),
            max_turns=int(request.launcher_config.get("max_turns", 8)),
            poll_interval=float(request.launcher_config.get("poll_interval_seconds", 1.0)),
            api_key=request.launcher_config.get("api_key"),
            auth_file=request.launcher_config.get("auth_file", str(Path.home() / ".codex" / "auth.json")),
            model=str(request.launcher_config.get("model", "gpt-5.4")),
            usage_view=str(request.launcher_config.get("usage_view", "raw")),
            codex_prompt_mode=str(request.launcher_config.get("prompt_mode", "trace")),
            background=bool(request.launcher_config.get("background", False)),
            shell=str(request.launcher_config.get("shell", "powershell")),
            reasoning_effort=str(request.launcher_config.get("reasoning_effort", "medium")),
        )

        started_at = iso_now()
        adapter = build_adapter(args)
        session = build_session_context(args, task)
        payload = run_session(session, adapter)
        finished_at = iso_now()

        payload["runner_workspace_dir"] = relative_to_workspace(request.workspace_root, launcher_root)
        payload["scratch_dir"] = relative_to_workspace(request.workspace_root, scratch_dir)
        payload["runs_dir"] = relative_to_workspace(request.workspace_root, logs_dir)
        payload["adapter_state_dir"] = relative_to_workspace(request.workspace_root, state_dir)

        return ExecutionResult(
            status="completed",
            launcher_kind=self.kind,
            started_at=started_at,
            finished_at=finished_at,
            payload=payload,
        )
