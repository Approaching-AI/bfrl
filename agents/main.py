from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SchedulerSettings:
    watch: bool = False
    sleep_seconds: float = 2.0
    memory_root: str = "memory"
    meta_agent_root: str = "meta-agent"
    default_model: str = "gpt-5.4"
    agent_models: dict[str, str] = field(
        default_factory=lambda: {
            "note-relation": "gpt-5.4",
            "doc-maintenance": "gpt-5.4",
            "sop-promotion": "gpt-5.4",
        }
    )
    artifact_contract_agents: tuple[str, ...] = (
        "note-relation",
        "doc-maintenance",
        "sop-promotion",
    )

    @property
    def daily_notes_dir(self) -> str:
        return f"{self.memory_root}/daily-notes"

    @property
    def doc_dir(self) -> str:
        return f"{self.memory_root}/doc"

    @property
    def sop_dir(self) -> str:
        return f"{self.memory_root}/sop"

    @property
    def meta_agent_doc_dir(self) -> str:
        return f"{self.meta_agent_root}/doc"

    def path_tokens(self) -> dict[str, str]:
        return {
            "memory_root": self.memory_root,
            "daily_notes_dir": self.daily_notes_dir,
            "doc_dir": self.doc_dir,
            "sop_dir": self.sop_dir,
            "meta_agent_root": self.meta_agent_root,
            "meta_agent_doc_dir": self.meta_agent_doc_dir,
        }

    def model_for_agent(self, slug: str, configured_model: str | None) -> str:
        return self.agent_models.get(slug, configured_model or self.default_model)


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.yaml"

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


def load_structured_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SchedulerError(f"Config file not found: {path}")
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    if suffix == ".json":
        payload = json.loads(raw)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise SchedulerError("YAML config requires PyYAML. Install it or use a JSON config file.") from exc
        payload = yaml.safe_load(raw)
    else:
        raise SchedulerError(f"Unsupported config format: {path.suffix}")
    if not isinstance(payload, dict):
        raise SchedulerError("Top-level config payload must be an object.")
    return payload


def load_scheduler_settings(config_path: Path) -> SchedulerSettings:
    payload = load_structured_config(config_path)
    agent_models = payload.get("agent_models", {})
    if not isinstance(agent_models, dict):
        raise SchedulerError("agent_models must be an object.")
    return SchedulerSettings(
        watch=bool(payload.get("watch", False)),
        sleep_seconds=float(payload.get("sleep_seconds", 2.0)),
        memory_root=str(payload.get("memory_root", "memory")),
        meta_agent_root=str(payload.get("meta_agent_root", "meta-agent")),
        default_model=str(payload.get("default_model", "gpt-5.4")),
        agent_models={str(key): str(value) for key, value in agent_models.items()},
    )


def render_path_template(template: str, tokens: dict[str, str]) -> str:
    if "{" not in template:
        return template
    try:
        return template.format_map(tokens)
    except KeyError as exc:
        missing_key = str(exc).strip("'")
        raise SchedulerError(f"Unknown path template key: {missing_key}") from exc


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def emit_monitor(message: str) -> None:
    print(f"[{iso_now()}] {message}", file=sys.stderr, flush=True)


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


def resolve_task_reference_path(workspace_root: Path, agent_dir: Path, requested_path: str) -> Path:
    requested = Path(requested_path)
    if requested.is_absolute():
        return requested.resolve()

    workspace_candidate = resolve_workspace_path(workspace_root, requested_path)
    if workspace_candidate.exists():
        return workspace_candidate
    return resolve_agent_path(workspace_root, agent_dir, requested_path)


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


def load_agent_spec(config_path: Path, workspace_root: Path, settings: SchedulerSettings) -> AgentSpec:
    payload = load_json_file(config_path)
    agent_dir = config_path.parent.resolve()
    name = str(payload["name"])
    slug = str(payload.get("id", "")).strip() or slugify_name(name)
    path_tokens = settings.path_tokens()

    paths_payload = payload.get("paths", {})
    if not isinstance(paths_payload, dict):
        raise SchedulerError("paths must be an object.")

    configured_workspace_root = resolve_agent_path(
        workspace_root,
        agent_dir,
        render_path_template(str(paths_payload.get("workspace_root", "../..")), path_tokens),
    )
    if configured_workspace_root != workspace_root.resolve():
        raise SchedulerError(
            f"{config_path} resolves paths.workspace_root to {configured_workspace_root}, "
            f"but the scheduler workspace is {workspace_root.resolve()}."
        )

    runtime_dir = resolve_agent_path(
        workspace_root,
        agent_dir,
        render_path_template(str(paths_payload.get("runtime_root", "runtime")), path_tokens),
    )
    launchers_root_dir = resolve_agent_path(
        workspace_root,
        agent_dir,
        render_path_template(str(paths_payload.get("launcher_root", "runtime/launchers")), path_tokens),
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
    merged_launcher_config = dict(launcher_config)
    merged_launcher_config["model"] = settings.model_for_agent(
        slug=slug,
        configured_model=str(launcher_config.get("model", "")).strip() or None,
    )

    dependencies = [str(value) for value in payload.get("dependencies", [])]
    wakeup = payload.get("wakeup", {})
    if not isinstance(wakeup, dict):
        raise SchedulerError("wakeup must be an object.")
    wakeup_globs = [
        render_path_template(str(value), path_tokens)
        for value in wakeup.get("watch_globs", [])
    ]

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
        launcher_config=merged_launcher_config,
        runtime_dir=runtime_dir,
        scheduler_state_file=runtime_dir / "scheduler-state.json",
        runtime_state_dir=runtime_dir / "state",
        runtime_work_orders_dir=runtime_dir / "work-orders",
        runtime_reports_dir=runtime_dir / "reports",
        launchers_root_dir=launchers_root_dir,
    )


def load_all_agent_specs(
    agents_dir: Path,
    workspace_root: Path,
    settings: SchedulerSettings,
) -> list[AgentSpec]:
    specs: list[AgentSpec] = []
    for config_path in sorted(agents_dir.glob("*/agent.json")):
        specs.append(load_agent_spec(config_path, workspace_root, settings))
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


def snapshot_workspace_globs(
    workspace_root: Path,
    patterns: list[str],
) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for pattern in patterns:
        for path in expand_glob_pattern(workspace_root, pattern):
            if path.is_dir():
                continue
            stat = path.stat()
            snapshot[relative_to_workspace(workspace_root, path)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def expand_glob_pattern(workspace_root: Path, pattern: str) -> list[Path]:
    requested = Path(pattern)
    search_pattern = pattern if requested.is_absolute() else str((workspace_root / pattern).resolve())
    return sorted(Path(match).resolve() for match in glob.glob(search_pattern))


def detect_snapshot_changes(
    before: dict[str, tuple[int, int]],
    after: dict[str, tuple[int, int]],
) -> list[str]:
    return sorted(path for path, marker in after.items() if before.get(path) != marker)


def build_required_artifact_patterns(
    spec: AgentSpec,
    workspace_root: Path,
    settings: SchedulerSettings,
) -> list[str]:
    if spec.slug not in settings.artifact_contract_agents:
        return []
    work_orders_pattern = relative_to_workspace(workspace_root, spec.runtime_work_orders_dir).replace("\\", "/")
    runtime_state_path = relative_to_workspace(
        workspace_root,
        spec.runtime_state_dir / "runtime-state.json",
    ).replace("\\", "/")
    return [f"{work_orders_pattern}/*.json", runtime_state_path]


def compute_input_fingerprint(spec: AgentSpec, workspace_root: Path) -> str | None:
    if not spec.wakeup_globs:
        return None
    rows: list[str] = []
    for pattern in spec.wakeup_globs:
        for path in expand_glob_pattern(workspace_root, pattern):
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


def normalize_task_payload(
    spec: AgentSpec,
    workspace_root: Path,
    settings: SchedulerSettings,
) -> dict[str, Any]:
    payload = dict(spec.task_payload)
    payload["id"] = str(payload.get("id", "")).strip() or spec.slug
    path_tokens = settings.path_tokens()

    system_prompt_path = render_path_template(str(payload.get("system_prompt_path", "")).strip(), path_tokens)
    if system_prompt_path:
        resolved_prompt_path = resolve_task_reference_path(workspace_root, spec.agent_dir, system_prompt_path)
        if not resolved_prompt_path.exists():
            raise SchedulerError(f"System prompt file not found for {spec.slug}: {system_prompt_path}")
        if not resolved_prompt_path.is_file():
            raise SchedulerError(f"System prompt path is not a file for {spec.slug}: {system_prompt_path}")
        payload["system_prompt_path"] = relative_to_workspace(workspace_root, resolved_prompt_path)

    normalized_memory_paths: list[str] = []
    for raw_path in payload.get("memory_paths", []):
        rendered_path = render_path_template(str(raw_path), path_tokens)
        resolved_memory_path = resolve_task_reference_path(workspace_root, spec.agent_dir, rendered_path)
        if not resolved_memory_path.exists():
            raise SchedulerError(f"Memory path not found for {spec.slug}: {rendered_path}")
        if not resolved_memory_path.is_file():
            raise SchedulerError(f"Memory path is not a file for {spec.slug}: {rendered_path}")
        normalized_memory_paths.append(
            relative_to_workspace(
                workspace_root,
                resolved_memory_path,
            )
        )
    payload["memory_paths"] = normalized_memory_paths
    return payload


def build_dynamic_extra_context(
    spec: AgentSpec,
    workspace_root: Path,
    spec_lookup: dict[str, AgentSpec],
    trigger_reason: str,
    settings: SchedulerSettings,
) -> str:
    runner_workspace_dir = spec.launchers_root_dir / spec.launcher_kind
    lines = [
        f"Agent home: {relative_to_workspace(workspace_root, spec.agent_dir)}",
        f"Shared memory root: {settings.memory_root}",
        f"Daily notes dir: {settings.daily_notes_dir}",
        f"Doc dir: {settings.doc_dir}",
        f"SOP dir: {settings.sop_dir}",
        f"Runtime state dir: {relative_to_workspace(workspace_root, spec.runtime_state_dir)}",
        f"Runtime work-orders dir: {relative_to_workspace(workspace_root, spec.runtime_work_orders_dir)}",
        f"Runtime reports dir: {relative_to_workspace(workspace_root, spec.runtime_reports_dir)}",
        f"Runner kind: {spec.launcher_kind}",
        f"Runner model: {spec.launcher_config.get('model', '<unset>')}",
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
    settings: SchedulerSettings,
) -> tuple[TaskDefinition, dict[str, Any]]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = normalize_task_payload(spec, workspace_root, settings)
    template_id = str(payload.get("id", spec.slug))
    task_id = f"{template_id}-{timestamp}"
    payload["id"] = task_id
    base_extra_context = str(payload.get("extra_context", "")).strip()
    dynamic_extra = build_dynamic_extra_context(spec, workspace_root, spec_lookup, trigger_reason, settings)
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
    settings: SchedulerSettings,
) -> dict[str, Any]:
    ensure_agent_directories(spec)
    state = load_scheduler_state(spec.scheduler_state_file)
    task, task_payload = build_task_instance(spec, workspace_root, spec_lookup, trigger_reason, settings)
    request = build_execution_request(spec, workspace_root, task, trigger_reason, spec_lookup)
    required_artifact_patterns = build_required_artifact_patterns(spec, workspace_root, settings)
    artifact_snapshot_before = snapshot_workspace_globs(workspace_root, required_artifact_patterns)
    must_write_artifacts = should_wake_due_to_inputs(state, input_fingerprint)
    try:
        runner = get_runner(spec.launcher_kind)
    except ValueError as exc:
        raise SchedulerError(str(exc)) from exc
    result = runner.run(request)
    artifact_snapshot_after = snapshot_workspace_globs(workspace_root, required_artifact_patterns)
    artifact_changes = detect_snapshot_changes(artifact_snapshot_before, artifact_snapshot_after)
    if must_write_artifacts and required_artifact_patterns and not artifact_changes:
        checked_patterns = ", ".join(required_artifact_patterns)
        raise SchedulerError(
            f"{spec.slug} finished without updating required runtime artifacts. Checked: {checked_patterns}"
        )

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
    payload_result["runtime_artifacts"] = {
        "enforced": must_write_artifacts and bool(required_artifact_patterns),
        "required_patterns": required_artifact_patterns,
        "changed_paths": artifact_changes,
    }
    payload_result["task"] = task_payload
    return payload_result


def run_orchestration_cycle(
    workspace_root: Path,
    specs: list[AgentSpec],
    spec_lookup: dict[str, AgentSpec],
    settings: SchedulerSettings,
    trigger_reason: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    emit_monitor(f"Starting orchestration cycle across {len(specs)} agent(s).")
    for spec in specs:
        state = load_scheduler_state(spec.scheduler_state_file)
        input_fingerprint = compute_input_fingerprint(spec, workspace_root)
        if not should_wake_due_to_inputs(state, input_fingerprint):
            emit_monitor(
                f"[{spec.slug}] no watched-input change detected; skipping."
            )
            continue
        emit_monitor(
            f"[{spec.slug}] input change detected; launching {spec.launcher_kind} "
            f"with model {spec.launcher_config.get('model', '<unset>')}."
        )
        started_at = time.monotonic()
        result = run_agent_once(
            workspace_root=workspace_root,
            spec=spec,
            spec_lookup=spec_lookup,
            trigger_reason=trigger_reason,
            input_fingerprint=input_fingerprint,
            settings=settings,
        )
        elapsed_seconds = max(0.0, time.monotonic() - started_at)
        changed_artifacts = result.get("runtime_artifacts", {}).get("changed_paths", [])
        if isinstance(changed_artifacts, list) and changed_artifacts:
            artifact_summary = ", ".join(str(path) for path in changed_artifacts)
        else:
            artifact_summary = "no tracked runtime artifact changes"
        emit_monitor(
            f"[{spec.slug}] completed in {elapsed_seconds:.1f}s; artifacts: {artifact_summary}."
        )
        results.append(result)
    emit_monitor(f"Orchestration cycle finished; {len(results)} agent(s) executed.")
    return results


def run_orchestrator_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    settings = load_scheduler_settings(config_path)
    workspace_root = WORKSPACE_ROOT
    agents_dir = SCRIPT_DIR
    specs = load_all_agent_specs(agents_dir, workspace_root, settings)
    spec_lookup = build_spec_lookup(specs)
    specs = [spec for spec in specs if spec.enabled]
    if not specs:
        raise SchedulerError("No enabled agents are available for orchestration.")
    emit_monitor(f"Loaded config: {config_path}")
    emit_monitor(
        f"Watch mode: {'on' if settings.watch else 'off'}; "
        f"poll interval: {settings.sleep_seconds}s; memory root: {settings.memory_root}."
    )
    emit_monitor(
        "Enabled agents in order: "
        + " -> ".join(spec.slug for spec in specs)
    )

    while True:
        cycle_results = run_orchestration_cycle(
            workspace_root=workspace_root,
            specs=specs,
            spec_lookup=spec_lookup,
            settings=settings,
            trigger_reason="main.py orchestrated the notes->doc->sop chain",
        )
        if cycle_results:
            print(json.dumps(cycle_results, ensure_ascii=False, indent=2))
        elif not settings.watch:
            emit_monitor("No agents needed work in this pass; exiting.")
            print("[]")
            return 0
        if not settings.watch:
            return 0
        if not cycle_results:
            emit_monitor(f"No changes detected; sleeping for {settings.sleep_seconds}s.")
            time.sleep(settings.sleep_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orchestrate the full notes->doc->sop agent chain from a config file."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the scheduler config file (.json, .yaml, or .yml).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_orchestrator_command(args)
    except SchedulerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
