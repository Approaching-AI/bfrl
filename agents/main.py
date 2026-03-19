from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent
DEFAULT_AGENTS_DIR = "agents"
DEFAULT_POLL_SECONDS = 2.0

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runners.base import ExecutionRequest, TaskDefinition  # noqa: E402
from runners.registry import get_runner  # noqa: E402


class SchedulerError(RuntimeError):
    pass


@dataclass
class AgentSpec:
    name: str
    slug: str
    config_path: Path
    agent_dir: Path
    enabled: bool
    order: int
    task_payload: dict[str, Any]
    dependencies: list[str]
    wakeup_globs: list[str]
    launcher_kind: str
    launcher_config: dict[str, Any]
    runtime_dir: Path
    scheduler_state_file: Path
    runtime_state_dir: Path
    runtime_work_orders_dir: Path
    runtime_reports_dir: Path
    launchers_root_dir: Path


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def relative_to_workspace(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve()))
    except ValueError:
        return str(path.resolve())


def resolve_workspace_path(workspace_root: Path, requested_path: str) -> Path:
    candidate = (workspace_root / requested_path).resolve()
    root = workspace_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise SchedulerError(f"Path escapes workspace: {requested_path}")
    return candidate


def resolve_agent_path(workspace_root: Path, agent_dir: Path, requested_path: str) -> Path:
    requested = Path(requested_path)
    candidate = requested.resolve() if requested.is_absolute() else (agent_dir / requested).resolve()
    root = workspace_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise SchedulerError(f"Path escapes workspace: {requested_path}")
    return candidate


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_scheduler_state() -> dict[str, Any]:
    return {
        "run_count": 0,
        "last_run_started_at": None,
        "last_run_finished_at": None,
        "last_status": None,
        "last_input_fingerprint": None,
        "last_task_id": None,
        "last_trigger_reason": None,
        "last_launcher_kind": None,
    }


def load_scheduler_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_scheduler_state()
    return load_json_file(path)


def save_scheduler_state(path: Path, payload: dict[str, Any]) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify_name(value: str) -> str:
    cleaned: list[str] = []
    for char in value.strip().lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in {"-", "_"}:
            cleaned.append(char)
        elif char in {" ", "."}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-_")
    if not slug:
        raise SchedulerError("Agent name must contain at least one letter or number.")
    return slug


def load_agent_spec(config_path: Path, workspace_root: Path) -> AgentSpec:
    payload = load_json_file(config_path)
    agent_dir = config_path.parent.resolve()
    name = str(payload["name"])
    slug = str(payload.get("id", "")).strip() or slugify_name(name)

    paths_payload = payload.get("paths", {})
    if not isinstance(paths_payload, dict):
        raise SchedulerError("paths must be an object.")

    configured_workspace_root = resolve_agent_path(
        workspace_root, agent_dir, str(paths_payload.get("workspace_root", "../.."))
    )
    if configured_workspace_root != workspace_root.resolve():
        raise SchedulerError(
            f"{config_path} resolves paths.workspace_root to {configured_workspace_root}, "
            f"but the scheduler workspace is {workspace_root.resolve()}."
        )

    runtime_dir = resolve_agent_path(
        workspace_root, agent_dir, str(paths_payload.get("runtime_root", "runtime"))
    )
    launchers_root_dir = resolve_agent_path(
        workspace_root, agent_dir, str(paths_payload.get("launcher_root", "runtime/launchers"))
    )

    task_payload = payload.get("task")
    if not isinstance(task_payload, dict):
        raise SchedulerError("task must be an object.")
    for required_key in ["title", "goal"]:
        if required_key not in task_payload:
            raise SchedulerError(f"task is missing required field: {required_key}")

    launcher_payload = payload.get("launcher", {})
    if not isinstance(launcher_payload, dict):
        raise SchedulerError("launcher must be an object.")
    launcher_kind = str(launcher_payload.get("kind", "")).strip()
    if not launcher_kind:
        raise SchedulerError("launcher.kind is required.")
    launcher_config = launcher_payload.get("config", {})
    if not isinstance(launcher_config, dict):
        raise SchedulerError("launcher.config must be an object.")

    dependencies = [str(value) for value in payload.get("dependencies", [])]
    wakeup = payload.get("wakeup", {})
    if not isinstance(wakeup, dict):
        raise SchedulerError("wakeup must be an object.")
    wakeup_globs = [str(value) for value in wakeup.get("watch_globs", [])]

    return AgentSpec(
        name=name,
        slug=slug,
        config_path=config_path.resolve(),
        agent_dir=agent_dir,
        enabled=bool(payload.get("enabled", True)),
        order=int(payload.get("order", 100)),
        task_payload=dict(task_payload),
        dependencies=dependencies,
        wakeup_globs=wakeup_globs,
        launcher_kind=launcher_kind,
        launcher_config=dict(launcher_config),
        runtime_dir=runtime_dir,
        scheduler_state_file=runtime_dir / "scheduler-state.json",
        runtime_state_dir=runtime_dir / "state",
        runtime_work_orders_dir=runtime_dir / "work-orders",
        runtime_reports_dir=runtime_dir / "reports",
        launchers_root_dir=launchers_root_dir,
    )


def load_all_agent_specs(agents_dir: Path, workspace_root: Path) -> list[AgentSpec]:
    specs: list[AgentSpec] = []
    for config_path in sorted(agents_dir.glob("*/agent.json")):
        specs.append(load_agent_spec(config_path, workspace_root))
    if not specs:
        raise SchedulerError(f"No agent.json files were found under {agents_dir}")
    return sorted(specs, key=lambda spec: (spec.order, spec.slug))


def build_spec_lookup(specs: list[AgentSpec]) -> dict[str, AgentSpec]:
    return {spec.slug: spec for spec in specs}


def ensure_agent_directories(spec: AgentSpec) -> None:
    for path in [
        spec.runtime_dir,
        spec.runtime_state_dir,
        spec.runtime_work_orders_dir,
        spec.runtime_reports_dir,
        spec.launchers_root_dir,
    ]:
        ensure_directory(path)


def compute_input_fingerprint(spec: AgentSpec, workspace_root: Path) -> str | None:
    if not spec.wakeup_globs:
        return None
    rows: list[str] = []
    for pattern in spec.wakeup_globs:
        normalized = pattern.replace("\\", "/")
        for path in sorted(workspace_root.glob(normalized)):
            if path.is_dir():
                continue
            stat = path.stat()
            rows.append(
                "|".join(
                    [
                        relative_to_workspace(workspace_root, path),
                        str(stat.st_mtime_ns),
                        str(stat.st_size),
                    ]
                )
            )
    if not rows:
        return None
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def should_wake_due_to_inputs(state: dict[str, Any], current_fingerprint: str | None) -> bool:
    if current_fingerprint is None:
        return False
    previous = state.get("last_input_fingerprint")
    if previous is None:
        return True
    return current_fingerprint != previous


def normalize_task_payload(spec: AgentSpec, workspace_root: Path) -> dict[str, Any]:
    payload = dict(spec.task_payload)
    payload["id"] = str(payload.get("id", "")).strip() or spec.slug

    system_prompt_path = str(payload.get("system_prompt_path", "")).strip()
    if system_prompt_path:
        payload["system_prompt_path"] = relative_to_workspace(
            workspace_root,
            resolve_agent_path(workspace_root, spec.agent_dir, system_prompt_path),
        )

    normalized_memory_paths: list[str] = []
    for raw_path in payload.get("memory_paths", []):
        normalized_memory_paths.append(
            relative_to_workspace(
                workspace_root,
                resolve_agent_path(workspace_root, spec.agent_dir, str(raw_path)),
            )
        )
    payload["memory_paths"] = normalized_memory_paths
    return payload


def build_dynamic_extra_context(
    spec: AgentSpec,
    workspace_root: Path,
    spec_lookup: dict[str, AgentSpec],
    trigger_reason: str,
) -> str:
    runner_workspace_dir = spec.launchers_root_dir / spec.launcher_kind
    lines = [
        f"Agent home: {relative_to_workspace(workspace_root, spec.agent_dir)}",
        f"Runtime state dir: {relative_to_workspace(workspace_root, spec.runtime_state_dir)}",
        f"Runtime work-orders dir: {relative_to_workspace(workspace_root, spec.runtime_work_orders_dir)}",
        f"Runtime reports dir: {relative_to_workspace(workspace_root, spec.runtime_reports_dir)}",
        f"Runner kind: {spec.launcher_kind}",
        f"Runner workspace dir: {relative_to_workspace(workspace_root, runner_workspace_dir)}",
        f"Wake reason: {trigger_reason}",
        "main.py only handles wakeup and coordination. You must inspect your relevant scope yourself and decide the concrete processing set.",
    ]
    if spec.dependencies:
        lines.append("Dependencies: " + ", ".join(spec.dependencies))
        lines.append("Upstream work-order dirs:")
        for dependency in spec.dependencies:
            dependency_spec = spec_lookup.get(dependency)
            if dependency_spec is None:
                lines.append(f"- {dependency}: <missing agent config>")
                continue
            lines.append(
                "- "
                + dependency
                + ": "
                + relative_to_workspace(workspace_root, dependency_spec.runtime_work_orders_dir)
            )
    if spec.wakeup_globs:
        lines.append("Wakeup watch globs:")
        lines.extend(f"- {pattern}" for pattern in spec.wakeup_globs)
    return "\n".join(lines)


def build_task_instance(
    spec: AgentSpec,
    workspace_root: Path,
    spec_lookup: dict[str, AgentSpec],
    trigger_reason: str,
) -> tuple[TaskDefinition, dict[str, Any]]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = normalize_task_payload(spec, workspace_root)
    template_id = str(payload.get("id", spec.slug))
    task_id = f"{template_id}-{timestamp}"
    payload["id"] = task_id
    base_extra_context = str(payload.get("extra_context", "")).strip()
    dynamic_extra = build_dynamic_extra_context(spec, workspace_root, spec_lookup, trigger_reason)
    if base_extra_context:
        payload["extra_context"] = base_extra_context + "\n\n" + dynamic_extra
    else:
        payload["extra_context"] = dynamic_extra
    payload["created_at"] = iso_now()

    return TaskDefinition(
        id=payload["id"],
        title=str(payload["title"]),
        goal=str(payload["goal"]),
        system_prompt_path=str(payload.get("system_prompt_path", "")),
        memory_paths=[str(path) for path in payload.get("memory_paths", [])],
        extra_context=str(payload.get("extra_context", "")),
        allow_file_edits=bool(payload.get("allow_file_edits", False)),
    ), payload


def build_execution_request(
    spec: AgentSpec,
    workspace_root: Path,
    task: TaskDefinition,
    trigger_reason: str,
    spec_lookup: dict[str, AgentSpec],
) -> ExecutionRequest:
    upstream_dirs: list[Path] = []
    for dependency in spec.dependencies:
        dependency_spec = spec_lookup.get(dependency)
        if dependency_spec is not None:
            upstream_dirs.append(dependency_spec.runtime_work_orders_dir)

    return ExecutionRequest(
        agent_id=spec.slug,
        agent_name=spec.name,
        workspace_root=workspace_root,
        agent_dir=spec.agent_dir,
        runtime_dir=spec.runtime_dir,
        runtime_state_dir=spec.runtime_state_dir,
        runtime_work_orders_dir=spec.runtime_work_orders_dir,
        runtime_reports_dir=spec.runtime_reports_dir,
        runner_workspace_dir=spec.launchers_root_dir / spec.launcher_kind,
        upstream_work_order_dirs=upstream_dirs,
        wakeup_globs=list(spec.wakeup_globs),
        trigger_reason=trigger_reason,
        launcher_kind=spec.launcher_kind,
        launcher_config=dict(spec.launcher_config),
        task=task,
    )


def record_scheduler_state(
    spec: AgentSpec,
    state: dict[str, Any],
    task_id: str,
    started_at: str,
    finished_at: str,
    input_fingerprint: str | None,
    trigger_reason: str,
) -> dict[str, Any]:
    updated = dict(state)
    updated["run_count"] = int(updated.get("run_count", 0)) + 1
    updated["last_task_id"] = task_id
    updated["last_run_started_at"] = started_at
    updated["last_run_finished_at"] = finished_at
    updated["last_status"] = "completed"
    updated["last_input_fingerprint"] = input_fingerprint
    updated["last_trigger_reason"] = trigger_reason
    updated["last_launcher_kind"] = spec.launcher_kind
    save_scheduler_state(spec.scheduler_state_file, updated)
    return updated


def run_agent_once(
    workspace_root: Path,
    spec: AgentSpec,
    spec_lookup: dict[str, AgentSpec],
    trigger_reason: str,
    input_fingerprint: str | None,
) -> dict[str, Any]:
    ensure_agent_directories(spec)
    state = load_scheduler_state(spec.scheduler_state_file)
    task, task_payload = build_task_instance(spec, workspace_root, spec_lookup, trigger_reason)
    request = build_execution_request(spec, workspace_root, task, trigger_reason, spec_lookup)
    try:
        runner = get_runner(spec.launcher_kind)
    except ValueError as exc:
        raise SchedulerError(str(exc)) from exc
    result = runner.run(request)

    state = record_scheduler_state(
        spec=spec,
        state=state,
        task_id=task.id,
        started_at=result.started_at,
        finished_at=result.finished_at,
        input_fingerprint=input_fingerprint,
        trigger_reason=trigger_reason,
    )

    payload_result = dict(result.payload)
    payload_result["agent"] = {
        "id": spec.slug,
        "name": spec.name,
        "config_path": relative_to_workspace(workspace_root, spec.config_path),
        "agent_dir": relative_to_workspace(workspace_root, spec.agent_dir),
        "runtime_dir": relative_to_workspace(workspace_root, spec.runtime_dir),
        "scheduler_state_file": relative_to_workspace(workspace_root, spec.scheduler_state_file),
        "launcher_kind": spec.launcher_kind,
        "order": spec.order,
        "dependencies": spec.dependencies,
        "run_count": state["run_count"],
        "trigger_reason": trigger_reason,
    }
    payload_result["task"] = task_payload
    return payload_result


def resolve_agent_by_name(specs: list[AgentSpec], name: str) -> AgentSpec:
    matches = [spec for spec in specs if spec.slug == name or spec.name == name]
    if not matches:
        raise SchedulerError(f"No agent found for name: {name}")
    if len(matches) > 1:
        raise SchedulerError(f"Multiple agents matched name: {name}")
    return matches[0]


def run_list_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    agents_dir = resolve_workspace_path(workspace_root, args.agents_dir)
    specs = load_all_agent_specs(agents_dir, workspace_root)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        state = load_scheduler_state(spec.scheduler_state_file)
        rows.append(
            {
                "id": spec.slug,
                "name": spec.name,
                "enabled": spec.enabled,
                "order": spec.order,
                "launcher_kind": spec.launcher_kind,
                "config_path": relative_to_workspace(workspace_root, spec.config_path),
                "agent_dir": relative_to_workspace(workspace_root, spec.agent_dir),
                "runtime_dir": relative_to_workspace(workspace_root, spec.runtime_dir),
                "scheduler_state_file": relative_to_workspace(workspace_root, spec.scheduler_state_file),
                "launchers_root_dir": relative_to_workspace(workspace_root, spec.launchers_root_dir),
                "dependencies": spec.dependencies,
                "wakeup_globs": spec.wakeup_globs,
                "run_count": state.get("run_count", 0),
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def run_single_agent_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    agents_dir = resolve_workspace_path(workspace_root, args.agents_dir)
    specs = load_all_agent_specs(agents_dir, workspace_root)
    spec_lookup = build_spec_lookup(specs)
    spec = resolve_agent_by_name(specs, args.agent)
    if not spec.enabled and not args.include_disabled:
        raise SchedulerError(f"Agent is disabled: {spec.name}")
    result = run_agent_once(
        workspace_root=workspace_root,
        spec=spec,
        spec_lookup=spec_lookup,
        trigger_reason="manual run requested from main.py",
        input_fingerprint=compute_input_fingerprint(spec, workspace_root),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def watch_single_agent_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    agents_dir = resolve_workspace_path(workspace_root, args.agents_dir)
    specs = load_all_agent_specs(agents_dir, workspace_root)
    spec_lookup = build_spec_lookup(specs)
    spec = resolve_agent_by_name(specs, args.agent)
    if not spec.enabled and not args.include_disabled:
        raise SchedulerError(f"Agent is disabled: {spec.name}")

    runs = 0
    while True:
        state = load_scheduler_state(spec.scheduler_state_file)
        input_fingerprint = compute_input_fingerprint(spec, workspace_root)
        if should_wake_due_to_inputs(state, input_fingerprint):
            result = run_agent_once(
                workspace_root=workspace_root,
                spec=spec,
                spec_lookup=spec_lookup,
                trigger_reason="watched inputs changed; inspect your scope yourself",
                input_fingerprint=input_fingerprint,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            runs += 1
            if args.max_runs and runs >= args.max_runs:
                return 0
            continue

        if args.once:
            return 0
        time.sleep(args.sleep_seconds)


def watch_all_agents_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    agents_dir = resolve_workspace_path(workspace_root, args.agents_dir)
    specs = load_all_agent_specs(agents_dir, workspace_root)
    spec_lookup = build_spec_lookup(specs)
    if not args.include_disabled:
        specs = [spec for spec in specs if spec.enabled]
    if not specs:
        raise SchedulerError("No enabled agents are available to watch.")

    runs = 0
    while True:
        ran_any = False
        for spec in specs:
            state = load_scheduler_state(spec.scheduler_state_file)
            input_fingerprint = compute_input_fingerprint(spec, workspace_root)
            if not should_wake_due_to_inputs(state, input_fingerprint):
                continue
            result = run_agent_once(
                workspace_root=workspace_root,
                spec=spec,
                spec_lookup=spec_lookup,
                trigger_reason="main.py detected changed watched inputs; inspect your scope yourself",
                input_fingerprint=input_fingerprint,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            runs += 1
            ran_any = True
            if args.max_runs and runs >= args.max_runs:
                return 0
        if args.once:
            return 0
        if not ran_any:
            time.sleep(args.sleep_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the agent system under /agents with runner-agnostic orchestration."
    )
    parser.add_argument("--workspace-root", default=str(WORKSPACE_ROOT))
    parser.add_argument("--agents-dir", default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--include-disabled", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List all agent configs and runtime state.")
    list_parser.add_argument("--agents-dir", default=DEFAULT_AGENTS_DIR)

    run_parser = subparsers.add_parser("run", help="Run one agent immediately.")
    run_parser.add_argument("--agents-dir", default=DEFAULT_AGENTS_DIR)
    run_parser.add_argument("--agent", required=True)

    watch_parser = subparsers.add_parser("watch", help="Poll watched inputs for one agent.")
    watch_parser.add_argument("--agents-dir", default=DEFAULT_AGENTS_DIR)
    watch_parser.add_argument("--agent", required=True)
    watch_parser.add_argument("--once", action="store_true")
    watch_parser.add_argument("--max-runs", type=int, default=0)

    watch_all_parser = subparsers.add_parser("watch-all", help="Poll watched inputs and orchestrate all enabled agents.")
    watch_all_parser.add_argument("--agents-dir", default=DEFAULT_AGENTS_DIR)
    watch_all_parser.add_argument("--once", action="store_true")
    watch_all_parser.add_argument("--max-runs", type=int, default=0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            return run_list_command(args)
        if args.command == "run":
            return run_single_agent_command(args)
        if args.command == "watch":
            return watch_single_agent_command(args)
        if args.command == "watch-all":
            return watch_all_agents_command(args)
        raise SchedulerError(f"Unknown command: {args.command}")
    except SchedulerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
