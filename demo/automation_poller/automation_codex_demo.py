from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEMO_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = DEMO_ROOT.parent

if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from codex_session_demo import (  # noqa: E402
    DemoError,
    TaskSpec,
    build_adapter,
    build_session_context,
    ensure_directory,
    iso_now,
    relative_to_workspace,
    resolve_workspace_path,
    run_session,
)


DEFAULT_CONFIG_DIR = "demo/automation_poller/configs"
DEFAULT_TASK_DIR = "demo/automation_poller/tasks"
DEFAULT_JOB_DIR = "demo/automation_poller/jobs"


@dataclass
class RunnerOptions:
    mode: str = "mock"
    session_style: str = "tool-loop"
    model: str = "gpt-5.4"
    max_turns: int = 8
    shell: str = "powershell"
    usage_view: str = "raw"
    codex_prompt_mode: str = "trace"
    background: bool = False
    reasoning_effort: str = "medium"


@dataclass
class AutomationConfig:
    name: str
    config_path: Path
    task_file: Path
    poll_interval_seconds: float
    enabled: bool
    runner: RunnerOptions
    job_dir: Path
    inbox_dir: Path
    archive_dir: Path
    logs_dir: Path
    notes_dir: Path
    state_file: Path


def slugify_name(value: str) -> str:
    cleaned = []
    for char in value.strip().lower():
        if char.isalnum():
            cleaned.append(char)
            continue
        if char in {"-", "_"}:
            cleaned.append(char)
            continue
        if char in {" ", "."}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-_")
    if not slug:
        raise DemoError("Automation name must contain at least one letter or number.")
    return slug


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_string(workspace_root: Path, path: Path) -> str:
    return relative_to_workspace(workspace_root, path.resolve())


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def load_runtime_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {
            "run_count": 0,
            "last_run_started_at": None,
            "last_run_finished_at": None,
            "last_task_id": None,
            "next_run_at": None,
        }
    return load_json_file(state_file)


def save_runtime_state(state_file: Path, state: dict[str, Any]) -> None:
    ensure_directory(state_file.parent)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_job_directories(config: AutomationConfig) -> None:
    for path in [
        config.job_dir,
        config.inbox_dir,
        config.archive_dir,
        config.logs_dir,
        config.notes_dir,
        config.state_file.parent,
    ]:
        ensure_directory(path)


def build_runtime_paths(workspace_root: Path, slug: str, payload: dict[str, Any]) -> tuple[Path, Path, Path, Path, Path, Path]:
    default_job_dir = f"{DEFAULT_JOB_DIR}/{slug}"
    job_dir = resolve_workspace_path(workspace_root, str(payload.get("job_dir", default_job_dir)))
    inbox_dir = resolve_workspace_path(
        workspace_root,
        str(payload.get("inbox_dir", relative_string(workspace_root, job_dir / "inbox"))),
    )
    archive_dir = resolve_workspace_path(
        workspace_root,
        str(payload.get("archive_dir", relative_string(workspace_root, job_dir / "archive"))),
    )
    logs_dir = resolve_workspace_path(
        workspace_root,
        str(payload.get("logs_dir", relative_string(workspace_root, job_dir / "logs"))),
    )
    notes_dir = resolve_workspace_path(
        workspace_root,
        str(payload.get("notes_dir", relative_string(workspace_root, job_dir / "notes"))),
    )
    state_file = resolve_workspace_path(
        workspace_root,
        str(payload.get("state_file", relative_string(workspace_root, job_dir / "state" / "runtime-state.json"))),
    )
    return job_dir, inbox_dir, archive_dir, logs_dir, notes_dir, state_file


def load_runner_options(payload: dict[str, Any]) -> RunnerOptions:
    runner_payload = payload.get("runner", {})
    if not isinstance(runner_payload, dict):
        raise DemoError("runner must be an object.")
    return RunnerOptions(
        mode=str(runner_payload.get("mode", "mock")),
        session_style=str(runner_payload.get("session_style", "tool-loop")),
        model=str(runner_payload.get("model", "gpt-5.4")),
        max_turns=int(runner_payload.get("max_turns", 8)),
        shell=str(runner_payload.get("shell", "powershell")),
        usage_view=str(runner_payload.get("usage_view", "raw")),
        codex_prompt_mode=str(runner_payload.get("codex_prompt_mode", "trace")),
        background=bool(runner_payload.get("background", False)),
        reasoning_effort=str(runner_payload.get("reasoning_effort", "medium")),
    )


def load_automation_config(config_path: Path, workspace_root: Path) -> AutomationConfig:
    payload = load_json_file(config_path)
    name = str(payload["name"])
    slug = slugify_name(name)
    task_file = resolve_workspace_path(workspace_root, str(payload["task_file"]))
    if not task_file.exists():
        raise DemoError(f"Task file not found: {task_file}")
    poll_interval_seconds = float(payload.get("poll_interval_seconds", 60))
    if poll_interval_seconds <= 0:
        raise DemoError("poll_interval_seconds must be positive.")

    job_dir, inbox_dir, archive_dir, logs_dir, notes_dir, state_file = build_runtime_paths(
        workspace_root=workspace_root,
        slug=slug,
        payload=payload,
    )
    return AutomationConfig(
        name=name,
        config_path=config_path.resolve(),
        task_file=task_file,
        poll_interval_seconds=poll_interval_seconds,
        enabled=bool(payload.get("enabled", True)),
        runner=load_runner_options(payload),
        job_dir=job_dir,
        inbox_dir=inbox_dir,
        archive_dir=archive_dir,
        logs_dir=logs_dir,
        notes_dir=notes_dir,
        state_file=state_file,
    )


def load_automation_configs(config_dir: Path, workspace_root: Path) -> list[AutomationConfig]:
    if not config_dir.exists():
        raise DemoError(f"Config directory not found: {config_dir}")
    configs: list[AutomationConfig] = []
    for config_path in sorted(config_dir.glob("*.json")):
        configs.append(load_automation_config(config_path, workspace_root))
    if not configs:
        raise DemoError(f"No automation config files were found in {config_dir}")
    return configs


def load_task_template(task_file: Path) -> dict[str, Any]:
    payload = load_json_file(task_file)
    required = ["id", "title", "goal"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise DemoError(f"Task template is missing required fields: {', '.join(missing)}")
    return payload


def build_task_instance(config: AutomationConfig) -> tuple[TaskSpec, dict[str, Any]]:
    template = load_task_template(config.task_file)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    template_id = str(template.get("id", slugify_name(config.name)))
    task_id = f"{template_id}-{timestamp}"
    payload = dict(template)
    payload["id"] = task_id
    payload["automation_name"] = config.name
    payload["created_at"] = iso_now()
    return TaskSpec.from_json(payload), payload


def enqueue_task(config: AutomationConfig, payload: dict[str, Any], workspace_root: Path) -> Path:
    ensure_job_directories(config)
    task_path = config.inbox_dir / f"{payload['id']}.json"
    task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "event": "task_enqueued",
                "automation": config.name,
                "task_path": relative_string(workspace_root, task_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return task_path


def make_runner_namespace(
    cli_args: argparse.Namespace,
    config: AutomationConfig,
) -> argparse.Namespace:
    workspace_root = Path(cli_args.workspace_root).resolve()
    return argparse.Namespace(
        mode=config.runner.mode,
        session_style=config.runner.session_style,
        workspace_root=str(workspace_root),
        notes_dir=relative_string(workspace_root, config.notes_dir),
        logs_dir=relative_string(workspace_root, config.logs_dir),
        max_turns=config.runner.max_turns,
        poll_interval=config.poll_interval_seconds,
        api_key=cli_args.api_key,
        auth_file=cli_args.auth_file,
        model=config.runner.model,
        usage_view=config.runner.usage_view,
        codex_prompt_mode=config.runner.codex_prompt_mode,
        background=config.runner.background,
        shell=config.runner.shell,
        reasoning_effort=config.runner.reasoning_effort,
    )


def archive_task_file(task_path: Path, config: AutomationConfig, workspace_root: Path) -> Path:
    ensure_directory(config.archive_dir)
    archived_path = config.archive_dir / task_path.name
    shutil.move(str(task_path), archived_path)
    print(
        json.dumps(
            {
                "event": "task_archived",
                "automation": config.name,
                "archived_task": relative_string(workspace_root, archived_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return archived_path


def record_run_state(
    config: AutomationConfig,
    state: dict[str, Any],
    task_id: str,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    started = parse_datetime(started_at)
    if started is None:
        raise DemoError("started_at could not be parsed.")
    next_run_at = (started + timedelta(seconds=config.poll_interval_seconds)).isoformat(timespec="seconds")
    updated = dict(state)
    updated["run_count"] = int(updated.get("run_count", 0)) + 1
    updated["last_task_id"] = task_id
    updated["last_run_started_at"] = started_at
    updated["last_run_finished_at"] = finished_at
    updated["next_run_at"] = next_run_at
    save_runtime_state(config.state_file, updated)
    return updated


def next_run_due(state: dict[str, Any]) -> bool:
    next_run_at = parse_datetime(str(state.get("next_run_at")) if state.get("next_run_at") else None)
    if next_run_at is None:
        return True
    return datetime.now(next_run_at.tzinfo) >= next_run_at


def run_automation_once(
    cli_args: argparse.Namespace,
    config: AutomationConfig,
) -> dict[str, Any]:
    workspace_root = Path(cli_args.workspace_root).resolve()
    ensure_job_directories(config)
    state = load_runtime_state(config.state_file)
    task, payload = build_task_instance(config)
    task_path = enqueue_task(config, payload, workspace_root)
    started_at = iso_now()

    runner_args = make_runner_namespace(cli_args, config)
    adapter = build_adapter(runner_args)
    session = build_session_context(runner_args, task)
    result = run_session(session, adapter)

    archived_path = archive_task_file(task_path, config, workspace_root)
    finished_at = iso_now()
    state = record_run_state(
        config=config,
        state=state,
        task_id=task.id,
        started_at=started_at,
        finished_at=finished_at,
    )

    result["automation"] = {
        "name": config.name,
        "config_path": relative_string(workspace_root, config.config_path),
        "poll_interval_seconds": config.poll_interval_seconds,
        "task_template": relative_string(workspace_root, config.task_file),
        "job_dir": relative_string(workspace_root, config.job_dir),
        "state_file": relative_string(workspace_root, config.state_file),
        "next_run_at": state["next_run_at"],
        "run_count": state["run_count"],
    }
    result["archived_task"] = relative_string(workspace_root, archived_path)
    return result


def run_list_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config_dir = resolve_workspace_path(workspace_root, args.config_dir)
    configs = load_automation_configs(config_dir, workspace_root)
    rows = []
    for config in configs:
        state = load_runtime_state(config.state_file)
        rows.append(
            {
                "name": config.name,
                "enabled": config.enabled,
                "poll_interval_seconds": config.poll_interval_seconds,
                "task_template": relative_string(workspace_root, config.task_file),
                "config_path": relative_string(workspace_root, config.config_path),
                "job_dir": relative_string(workspace_root, config.job_dir),
                "next_run_at": state.get("next_run_at"),
                "run_count": state.get("run_count", 0),
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def run_single_config_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config_path = resolve_workspace_path(workspace_root, args.config)
    config = load_automation_config(config_path, workspace_root)
    if not config.enabled and not args.include_disabled:
        raise DemoError(f"Automation is disabled: {config.name}")
    result = run_automation_once(args, config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def watch_single_config_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config_path = resolve_workspace_path(workspace_root, args.config)
    config = load_automation_config(config_path, workspace_root)
    if not config.enabled and not args.include_disabled:
        raise DemoError(f"Automation is disabled: {config.name}")

    runs = 0
    while True:
        state = load_runtime_state(config.state_file)
        if next_run_due(state):
            result = run_automation_once(args, config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            runs += 1
            if args.max_runs and runs >= args.max_runs:
                return 0
            continue

        if args.once:
            return 0
        time.sleep(args.sleep_seconds)


def watch_all_configs_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config_dir = resolve_workspace_path(workspace_root, args.config_dir)
    configs = load_automation_configs(config_dir, workspace_root)
    if not args.include_disabled:
        configs = [config for config in configs if config.enabled]
    if not configs:
        raise DemoError("No enabled automations are available to watch.")

    runs = 0
    while True:
        ran_any = False
        for config in configs:
            state = load_runtime_state(config.state_file)
            if not next_run_due(state):
                continue
            result = run_automation_once(args, config)
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
        description="Run configured Codex automations on a polling interval."
    )
    parser.add_argument("--workspace-root", default=str(WORKSPACE_ROOT))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--auth-file", default=str(Path.home() / ".codex" / "auth.json"))
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--include-disabled", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List all automation configs and runtime state.")
    list_parser.add_argument("--config-dir", default=DEFAULT_CONFIG_DIR)

    run_parser = subparsers.add_parser("run", help="Run one automation config immediately.")
    run_parser.add_argument("--config", required=True)

    watch_parser = subparsers.add_parser("watch", help="Watch one automation config and run it on schedule.")
    watch_parser.add_argument("--config", required=True)
    watch_parser.add_argument("--once", action="store_true")
    watch_parser.add_argument("--max-runs", type=int, default=0)

    watch_all_parser = subparsers.add_parser("watch-all", help="Watch all enabled automation configs.")
    watch_all_parser.add_argument("--config-dir", default=DEFAULT_CONFIG_DIR)
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
            return run_single_config_command(args)
        if args.command == "watch":
            return watch_single_config_command(args)
        if args.command == "watch-all":
            return watch_all_configs_command(args)
        raise DemoError(f"Unknown command: {args.command}")
    except DemoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
