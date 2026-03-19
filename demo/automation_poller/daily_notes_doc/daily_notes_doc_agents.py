from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_CONFIG_DIR = "demo/automation_poller/daily_notes_doc/configs"
FIXTURE_WORKSPACE_DIR = "demo/automation_poller/daily_notes_doc/fixtures/workspace"
SCRATCH_ROOT = "demo/automation_poller/daily_notes_doc/_scratch"

RECOGNIZED_SECTIONS = {
    "stable signals": "stable_signals",
    "active workstreams": "active_workstreams",
    "recent changes": "recent_changes",
    "decisions": "decisions",
    "open questions": "open_questions",
}
REQUIRED_DOCS = [
    "README.md",
    "current-state.md",
    "decisions.md",
    "open-questions.md",
    "source-map.md",
]
CURRENT_STATE_HEADINGS = ["## Stable Signals", "## Active Workstreams", "## Recent Changes", "## Coverage"]
DECISIONS_HEADINGS = ["## Active Decisions", "## Archived Decisions"]
OPEN_QUESTIONS_HEADINGS = ["## Open Questions", "## Recently Resolved"]
SOURCE_MAP_HEADINGS = ["## Processed Notes", "## Coverage Summary"]


class DemoError(RuntimeError):
    pass


@dataclass
class AgentConfig:
    name: str
    agent_kind: str
    config_path: Path
    workspace_dir: Path
    system_prompt_file: Path
    state_file: Path
    reports_dir: Path
    poll_interval_seconds: float
    enabled: bool
    source_agent_state_file: Path | None = None


@dataclass
class NoteRecord:
    note_id: str
    path: Path
    relative_path: str
    sections: dict[str, list[str]]


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def handle_remove_readonly(_func: Any, path: str, _exc: Any) -> None:
    os.chmod(path, 0o666)
    if os.path.isdir(path):
        os.rmdir(path)
    else:
        os.remove(path)


def resolve_workspace_path(workspace_root: Path, requested_path: str) -> Path:
    candidate = (workspace_root / requested_path).resolve()
    root = workspace_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise DemoError(f"Path escapes workspace: {requested_path}")
    return candidate


def relative_to_workspace(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root.resolve()))
    except ValueError:
        return str(path.resolve())


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def default_runtime_state() -> dict[str, Any]:
    return {
        "run_count": 0,
        "last_run_started_at": None,
        "last_run_finished_at": None,
        "next_run_at": None,
        "last_status": None,
        "processed_notes": [],
        "last_processed_note": None,
        "last_report_path": None,
    }


def load_runtime_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return default_runtime_state()
    return read_json(state_file)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def markdown_link(base_dir: Path, target_path: Path, label: str) -> str:
    relative = Path(os.path.relpath(target_path, start=base_dir))
    return f"[{label}]({relative.as_posix()})"


def normalize_heading(value: str) -> str:
    return value.strip().lower()


def note_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "memory" / "daily-notes"


def target_doc_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "memory" / "doc" / "daily-note-derived"


def source_agent_state_path(workspace_root: Path) -> Path:
    return resolve_workspace_path(
        workspace_root,
        "demo/automation_poller/daily_notes_doc/jobs/daily-notes-to-doc/state/runtime-state.json",
    )


def parse_structured_note(note_path: Path, workspace_root: Path) -> NoteRecord:
    text = note_path.read_text(encoding="utf-8")
    sections = {value: [] for value in RECOGNIZED_SECTIONS.values()}
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            current_section = RECOGNIZED_SECTIONS.get(normalize_heading(line[4:]))
            continue
        if current_section and line.startswith("- "):
            sections[current_section].append(line[2:].strip())
    return NoteRecord(
        note_id=note_path.stem,
        path=note_path.resolve(),
        relative_path=relative_to_workspace(workspace_root, note_path),
        sections=sections,
    )


def note_sort_key(path: Path) -> str:
    return path.stem


def load_agent_config(config_path: Path, workspace_root: Path) -> AgentConfig:
    payload = read_json(config_path)
    agent_kind = str(payload["agent_kind"])
    if agent_kind not in {"daily-notes-to-doc", "doc-audit"}:
        raise DemoError(f"Unsupported agent_kind: {agent_kind}")
    poll_interval_seconds = float(payload.get("poll_interval_seconds", 60))
    if poll_interval_seconds <= 0:
        raise DemoError("poll_interval_seconds must be positive.")
    return AgentConfig(
        name=str(payload["name"]),
        agent_kind=agent_kind,
        config_path=config_path.resolve(),
        workspace_dir=resolve_workspace_path(workspace_root, str(payload["workspace_dir"])),
        system_prompt_file=resolve_workspace_path(workspace_root, str(payload["system_prompt_file"])),
        state_file=resolve_workspace_path(workspace_root, str(payload["state_file"])),
        reports_dir=resolve_workspace_path(workspace_root, str(payload["reports_dir"])),
        poll_interval_seconds=poll_interval_seconds,
        enabled=bool(payload.get("enabled", True)),
    )


def load_agent_configs(config_dir: Path, workspace_root: Path) -> list[AgentConfig]:
    if not config_dir.exists():
        raise DemoError(f"Config directory not found: {config_dir}")
    configs = [load_agent_config(path, workspace_root) for path in sorted(config_dir.glob("*.json"))]
    if not configs:
        raise DemoError(f"No config files found in {config_dir}")
    return configs


def next_run_due(state: dict[str, Any]) -> bool:
    next_run_at = parse_datetime(state.get("next_run_at"))
    if next_run_at is None:
        return True
    return datetime.now(next_run_at.tzinfo) >= next_run_at


def list_note_files(workspace_dir: Path) -> list[Path]:
    directory = note_dir(workspace_dir)
    ensure_directory(directory)
    return sorted(directory.glob("*.md"), key=note_sort_key)


def aggregate_statements(notes: list[NoteRecord], section_name: str) -> list[tuple[str, list[NoteRecord]]]:
    grouped: dict[str, list[NoteRecord]] = {}
    for note in notes:
        for entry in note.sections.get(section_name, []):
            grouped.setdefault(entry, []).append(note)
    return [(statement, grouped[statement]) for statement in sorted(grouped.keys())]


def citation_text(doc_dir: Path, notes: list[NoteRecord]) -> str:
    links = [markdown_link(doc_dir, note.path, note.note_id) for note in notes]
    return ", ".join(links)


def render_current_state(doc_dir: Path, notes: list[NoteRecord], processed_note_ids: list[str]) -> str:
    stable_signals = aggregate_statements(notes, "stable_signals")
    active_workstreams = aggregate_statements(notes, "active_workstreams")
    recent_changes = aggregate_statements(notes, "recent_changes")
    last_processed = processed_note_ids[-1] if processed_note_ids else "none"
    lines = [
        "# Daily Note Derived Current State",
        "",
        "This document captures stable project state distilled from processed daily notes.",
        "",
        "## Stable Signals",
    ]
    if stable_signals:
        for statement, refs in stable_signals:
            lines.append(f"- {statement}")
            lines.append(f"  Source notes: {citation_text(doc_dir, refs)}")
    else:
        lines.append("- No stable signals have been extracted yet.")
    lines.extend(["", "## Active Workstreams"])
    if active_workstreams:
        for statement, refs in active_workstreams:
            lines.append(f"- {statement}")
            lines.append(f"  Source notes: {citation_text(doc_dir, refs)}")
    else:
        lines.append("- No active workstreams have been extracted yet.")
    lines.extend(["", "## Recent Changes"])
    if recent_changes:
        for statement, refs in recent_changes:
            lines.append(f"- {statement}")
            lines.append(f"  Source notes: {citation_text(doc_dir, refs)}")
    else:
        lines.append("- No recent changes have been extracted yet.")
    lines.extend(
        [
            "",
            "## Coverage",
            f"- Processed note count: {len(processed_note_ids)}",
            f"- Last processed note: {last_processed}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_decisions(doc_dir: Path, notes: list[NoteRecord]) -> str:
    active_decisions = aggregate_statements(notes, "decisions")
    lines = [
        "# Derived Decisions",
        "",
        "This document records durable decisions distilled from daily notes.",
        "",
        "## Active Decisions",
    ]
    if active_decisions:
        for statement, refs in active_decisions:
            lines.append(f"- Decision: {statement}")
            lines.append("  Status: active")
            lines.append(f"  Source notes: {citation_text(doc_dir, refs)}")
    else:
        lines.append("- No active decisions have been extracted yet.")
    lines.extend(["", "## Archived Decisions", "- No archived decisions yet."])
    return "\n".join(lines) + "\n"


def render_open_questions(doc_dir: Path, notes: list[NoteRecord]) -> str:
    open_questions = aggregate_statements(notes, "open_questions")
    lines = [
        "# Derived Open Questions",
        "",
        "This document tracks unresolved questions that still need evidence or a decision.",
        "",
        "## Open Questions",
    ]
    if open_questions:
        for statement, refs in open_questions:
            lines.append(f"- Question: {statement}")
            lines.append("  Status: open")
            lines.append(f"  Source notes: {citation_text(doc_dir, refs)}")
    else:
        lines.append("- No open questions are pending.")
    lines.extend(["", "## Recently Resolved", "- No resolved questions have been recorded yet."])
    return "\n".join(lines) + "\n"


def render_source_map(doc_dir: Path, notes: list[NoteRecord]) -> str:
    lines = [
        "# Daily Note Source Map",
        "",
        "This ledger tracks which daily notes have already been ingested into derived docs.",
        "",
        "## Processed Notes",
        "",
        "| Note | Sections Contributed | Summary |",
        "| --- | --- | --- |",
    ]
    for note in notes:
        sections = []
        for key, values in note.sections.items():
            if values:
                sections.append(key.replace("_", " "))
        summary = []
        for key in ["stable_signals", "decisions", "open_questions"]:
            summary.extend(note.sections.get(key, [])[:1])
        lines.append(
            f"| {markdown_link(doc_dir, note.path, note.note_id)} | {', '.join(sections) if sections else 'none'} | "
            f"{'; '.join(summary[:2]) if summary else 'No structured entries extracted.'} |"
        )
    lines.extend(
        [
            "",
            "## Coverage Summary",
            f"- Processed note count: {len(notes)}",
            f"- Latest processed note: {notes[-1].note_id if notes else 'none'}",
        ]
    )
    return "\n".join(lines) + "\n"


def ensure_doc_schema_readme(doc_dir: Path) -> Path:
    ensure_directory(doc_dir)
    readme_path = doc_dir / "README.md"
    if readme_path.exists():
        return readme_path
    content = "\n".join(
        [
            "# Daily Note Derived Doc Definition",
            "",
            "This folder is the canonical target for the `daily-notes -> doc` polling agent.",
            "",
            "## Required Files",
            "",
            "- `current-state.md`: stable signals, active workstreams, recent changes, and coverage.",
            "- `decisions.md`: durable decisions only, each with status and source-note citations.",
            "- `open-questions.md`: unresolved questions only, each with status and source-note citations.",
            "- `source-map.md`: one row per processed daily note, in sorted order, without duplicates.",
            "",
            "## Citation Rules",
            "",
            "- Every substantial statement in derived docs must include a `Source notes:` line.",
            "- Citations must link to `memory/daily-notes/<note-id>.md` with a relative Markdown link.",
            "- If evidence is insufficient, record uncertainty instead of inventing a conclusion.",
            "",
            "## State Rules",
            "",
            "- The source agent must maintain `processed_notes` and `last_processed_note` in its runtime state.",
            "- Re-running the agent without new notes must not duplicate source-map entries.",
            "- The audit agent should treat any unprocessed daily note as a stale-doc signal.",
        ]
    )
    readme_path.write_text(content + "\n", encoding="utf-8")
    return readme_path


def update_runtime_state(
    state_file: Path,
    state: dict[str, Any],
    *,
    status: str,
    poll_interval_seconds: float,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    started = parse_datetime(started_at)
    if started is None:
        raise DemoError("started_at could not be parsed.")
    updated = dict(state)
    updated["run_count"] = int(updated.get("run_count", 0)) + 1
    updated["last_run_started_at"] = started_at
    updated["last_run_finished_at"] = finished_at
    updated["last_status"] = status
    updated["next_run_at"] = (started + timedelta(seconds=poll_interval_seconds)).isoformat(timespec="seconds")
    write_json(state_file, updated)
    return updated


def run_daily_notes_to_doc_agent(config: AgentConfig, workspace_root: Path) -> dict[str, Any]:
    started_at = iso_now()
    state = load_runtime_state(config.state_file)
    notes = [parse_structured_note(path, workspace_root) for path in list_note_files(config.workspace_dir)]
    processed_notes = list(state.get("processed_notes", []))
    pending_notes = [note for note in notes if note.note_id not in processed_notes]
    doc_dir = target_doc_dir(config.workspace_dir)
    ensure_doc_schema_readme(doc_dir)
    ensure_directory(config.reports_dir)

    if not pending_notes:
        report_path = config.reports_dir / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-no-new-notes.md"
        report_path.write_text(
            "\n".join(
                [
                    "# Daily Notes To Doc Run",
                    "",
                    "No new daily notes were detected.",
                    "",
                    f"- checked_at: {iso_now()}",
                    f"- last_processed_note: {state.get('last_processed_note') or 'none'}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        state["last_report_path"] = relative_to_workspace(workspace_root, report_path)
        finished_at = iso_now()
        state = update_runtime_state(
            config.state_file,
            state,
            status="skipped",
            poll_interval_seconds=config.poll_interval_seconds,
            started_at=started_at,
            finished_at=finished_at,
        )
        return {
            "agent": config.name,
            "agent_kind": config.agent_kind,
            "status": "skipped",
            "pending_notes": [],
            "processed_notes": processed_notes,
            "report_path": relative_to_workspace(workspace_root, report_path),
            "state_file": relative_to_workspace(workspace_root, config.state_file),
            "next_run_at": state["next_run_at"],
        }

    processed_notes.extend(note.note_id for note in pending_notes)
    full_processed = [note for note in notes if note.note_id in processed_notes]
    current_state_path = doc_dir / "current-state.md"
    decisions_path = doc_dir / "decisions.md"
    open_questions_path = doc_dir / "open-questions.md"
    source_map_path = doc_dir / "source-map.md"
    current_state_path.write_text(render_current_state(doc_dir, full_processed, processed_notes), encoding="utf-8")
    decisions_path.write_text(render_decisions(doc_dir, full_processed), encoding="utf-8")
    open_questions_path.write_text(render_open_questions(doc_dir, full_processed), encoding="utf-8")
    source_map_path.write_text(render_source_map(doc_dir, full_processed), encoding="utf-8")

    report_path = config.reports_dir / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-daily-notes-to-doc.md"
    report_path.write_text(
        "\n".join(
            [
                "# Daily Notes To Doc Run",
                "",
                f"- run_at: {iso_now()}",
                f"- pending_note_count: {len(pending_notes)}",
                f"- pending_notes: {', '.join(note.note_id for note in pending_notes)}",
                f"- target_doc_dir: {relative_to_workspace(workspace_root, doc_dir)}",
                f"- system_prompt_file: {relative_to_workspace(workspace_root, config.system_prompt_file)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state["processed_notes"] = processed_notes
    state["last_processed_note"] = processed_notes[-1]
    state["last_report_path"] = relative_to_workspace(workspace_root, report_path)
    state["doc_hashes"] = {
        "current-state.md": hash_text(current_state_path.read_text(encoding="utf-8")),
        "decisions.md": hash_text(decisions_path.read_text(encoding="utf-8")),
        "open-questions.md": hash_text(open_questions_path.read_text(encoding="utf-8")),
        "source-map.md": hash_text(source_map_path.read_text(encoding="utf-8")),
    }
    finished_at = iso_now()
    state = update_runtime_state(
        config.state_file,
        state,
        status="updated",
        poll_interval_seconds=config.poll_interval_seconds,
        started_at=started_at,
        finished_at=finished_at,
    )
    return {
        "agent": config.name,
        "agent_kind": config.agent_kind,
        "status": "updated",
        "pending_notes": [note.note_id for note in pending_notes],
        "processed_notes": processed_notes,
        "target_doc_dir": relative_to_workspace(workspace_root, doc_dir),
        "generated_docs": [
            relative_to_workspace(workspace_root, current_state_path),
            relative_to_workspace(workspace_root, decisions_path),
            relative_to_workspace(workspace_root, open_questions_path),
            relative_to_workspace(workspace_root, source_map_path),
        ],
        "report_path": relative_to_workspace(workspace_root, report_path),
        "state_file": relative_to_workspace(workspace_root, config.state_file),
        "next_run_at": state["next_run_at"],
    }


def collect_note_references(text: str) -> list[str]:
    references: list[str] = []
    marker = "]("
    for line in text.splitlines():
        start = 0
        while True:
            index = line.find(marker, start)
            if index == -1:
                break
            close_index = line.find(")", index + len(marker))
            if close_index == -1:
                break
            references.append(line[index + len(marker):close_index])
            start = close_index + 1
    return references


def validate_doc_headings(path: Path, required_headings: list[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    findings = []
    for heading in required_headings:
        if heading not in text:
            findings.append(f"Missing heading `{heading}` in {path.name}.")
    return findings


def finalize_audit_run(
    config: AgentConfig,
    workspace_root: Path,
    state: dict[str, Any],
    findings: list[str],
    started_at: str,
) -> dict[str, Any]:
    status = "pass" if not findings else "fail"
    report_path = config.reports_dir / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-doc-audit.md"
    lines = [
        "# Doc Audit Report",
        "",
        f"- run_at: {iso_now()}",
        f"- status: {status}",
        f"- system_prompt_file: {relative_to_workspace(workspace_root, config.system_prompt_file)}",
        "",
        "## Findings",
    ]
    if findings:
        for finding in findings:
            lines.append(f"- {finding}")
    else:
        lines.append("- No findings. Derived docs are aligned with the doc definition and current note coverage.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state["last_report_path"] = relative_to_workspace(workspace_root, report_path)
    state["last_findings"] = findings
    finished_at = iso_now()
    state = update_runtime_state(
        config.state_file,
        state,
        status=status,
        poll_interval_seconds=config.poll_interval_seconds,
        started_at=started_at,
        finished_at=finished_at,
    )
    return {
        "agent": config.name,
        "agent_kind": config.agent_kind,
        "status": status,
        "findings": findings,
        "report_path": relative_to_workspace(workspace_root, report_path),
        "state_file": relative_to_workspace(workspace_root, config.state_file),
        "next_run_at": state["next_run_at"],
    }


def audit_docs(config: AgentConfig, workspace_root: Path) -> dict[str, Any]:
    started_at = iso_now()
    state = load_runtime_state(config.state_file)
    doc_dir = target_doc_dir(config.workspace_dir)
    ensure_directory(config.reports_dir)
    findings: list[str] = []

    for required_name in REQUIRED_DOCS:
        if not (doc_dir / required_name).exists():
            findings.append(f"Missing required doc file `{required_name}`.")
    if findings:
        return finalize_audit_run(config, workspace_root, state, findings, started_at)

    findings.extend(validate_doc_headings(doc_dir / "current-state.md", CURRENT_STATE_HEADINGS))
    findings.extend(validate_doc_headings(doc_dir / "decisions.md", DECISIONS_HEADINGS))
    findings.extend(validate_doc_headings(doc_dir / "open-questions.md", OPEN_QUESTIONS_HEADINGS))
    findings.extend(validate_doc_headings(doc_dir / "source-map.md", SOURCE_MAP_HEADINGS))

    source_text = (doc_dir / "source-map.md").read_text(encoding="utf-8")
    processed_rows = [line for line in source_text.splitlines() if line.startswith("| [")]
    note_ids = [line.split("](", 1)[0].replace("| [", "") for line in processed_rows]
    if len(note_ids) != len(set(note_ids)):
        findings.append("source-map.md contains duplicate processed note entries.")

    for doc_name in ["current-state.md", "decisions.md", "open-questions.md"]:
        doc_text = (doc_dir / doc_name).read_text(encoding="utf-8")
        if "Source notes:" not in doc_text:
            findings.append(f"{doc_name} does not contain any `Source notes:` citations.")
        for reference in collect_note_references(doc_text):
            target_path = (doc_dir / reference).resolve()
            if not target_path.exists():
                findings.append(f"{doc_name} references missing note `{reference}`.")

    source_state_file = config.source_agent_state_file or source_agent_state_path(workspace_root)
    source_state = load_runtime_state(source_state_file)
    processed_notes = list(source_state.get("processed_notes", []))
    discovered_notes = [path.stem for path in list_note_files(config.workspace_dir)]
    pending_notes = [note_id for note_id in discovered_notes if note_id not in processed_notes]
    if pending_notes:
        findings.append("Derived docs are stale because unprocessed daily notes exist: " + ", ".join(pending_notes))
    if note_ids != processed_notes:
        findings.append("source-map.md note order does not match the source agent processed_notes state.")

    return finalize_audit_run(config, workspace_root, state, findings, started_at)


def run_agent(config: AgentConfig, workspace_root: Path) -> dict[str, Any]:
    ensure_directory(config.reports_dir)
    ensure_directory(config.state_file.parent)
    if config.agent_kind == "daily-notes-to-doc":
        return run_daily_notes_to_doc_agent(config, workspace_root)
    if config.agent_kind == "doc-audit":
        return audit_docs(config, workspace_root)
    raise DemoError(f"Unsupported agent_kind: {config.agent_kind}")


def list_agents(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config_dir = resolve_workspace_path(workspace_root, args.config_dir)
    rows = []
    for config in load_agent_configs(config_dir, workspace_root):
        state = load_runtime_state(config.state_file)
        rows.append(
            {
                "name": config.name,
                "agent_kind": config.agent_kind,
                "enabled": config.enabled,
                "poll_interval_seconds": config.poll_interval_seconds,
                "workspace_dir": relative_to_workspace(workspace_root, config.workspace_dir),
                "system_prompt_file": relative_to_workspace(workspace_root, config.system_prompt_file),
                "state_file": relative_to_workspace(workspace_root, config.state_file),
                "last_status": state.get("last_status"),
                "next_run_at": state.get("next_run_at"),
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def run_single_agent_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config = load_agent_config(resolve_workspace_path(workspace_root, args.config), workspace_root)
    if not config.enabled and not args.include_disabled:
        raise DemoError(f"Agent is disabled: {config.name}")
    print(json.dumps(run_agent(config, workspace_root), ensure_ascii=False, indent=2))
    return 0


def watch_single_agent_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    config = load_agent_config(resolve_workspace_path(workspace_root, args.config), workspace_root)
    if not config.enabled and not args.include_disabled:
        raise DemoError(f"Agent is disabled: {config.name}")
    runs = 0
    while True:
        if next_run_due(load_runtime_state(config.state_file)):
            print(json.dumps(run_agent(config, workspace_root), ensure_ascii=False, indent=2))
            runs += 1
            if args.max_runs and runs >= args.max_runs:
                return 0
            continue
        if args.once:
            return 0
        time.sleep(args.sleep_seconds)


def watch_all_agents_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    configs = load_agent_configs(resolve_workspace_path(workspace_root, args.config_dir), workspace_root)
    if not args.include_disabled:
        configs = [config for config in configs if config.enabled]
    if not configs:
        raise DemoError("No enabled agents are available to watch.")
    runs = 0
    while True:
        ran_any = False
        for config in configs:
            if not next_run_due(load_runtime_state(config.state_file)):
                continue
            print(json.dumps(run_agent(config, workspace_root), ensure_ascii=False, indent=2))
            runs += 1
            ran_any = True
            if args.max_runs and runs >= args.max_runs:
                return 0
        if args.once:
            return 0
        if not ran_any:
            time.sleep(args.sleep_seconds)


def reset_validation_workspace(workspace_root: Path) -> Path:
    scratch_root = resolve_workspace_path(workspace_root, SCRATCH_ROOT)
    ensure_directory(scratch_root)
    validation_jobs_dir = scratch_root / "validation-jobs"
    if validation_jobs_dir.exists():
        shutil.rmtree(validation_jobs_dir, onexc=handle_remove_readonly)
    validation_dir = scratch_root / "validation-workspace"
    if validation_dir.exists():
        shutil.rmtree(validation_dir, onexc=handle_remove_readonly)
    shutil.copytree(resolve_workspace_path(workspace_root, FIXTURE_WORKSPACE_DIR), validation_dir)
    return validation_dir


def validation_state_path(workspace_root: Path, agent_name: str) -> Path:
    return resolve_workspace_path(
        workspace_root,
        f"{SCRATCH_ROOT}/validation-jobs/{agent_name}/state/runtime-state.json",
    )


def validation_reports_dir(workspace_root: Path, agent_name: str) -> Path:
    return resolve_workspace_path(
        workspace_root,
        f"{SCRATCH_ROOT}/validation-jobs/{agent_name}/reports",
    )


def write_validation_note(validation_dir: Path, note_name: str, body: str) -> None:
    note_path = validation_dir / "memory" / "daily-notes" / note_name
    note_path.write_text(body, encoding="utf-8")


def build_validation_note_body() -> str:
    return "\n".join(
        [
            "# 2026-03-19-01",
            "",
            "## Session 1",
            "",
            "### Stable Signals",
            "- The automation demo now includes dedicated daily-notes and doc-audit polling agents.",
            "",
            "### Active Workstreams",
            "- Validate stale-doc detection whenever a new daily note lands before doc refresh.",
            "",
            "### Recent Changes",
            "- Added a validation-only note to prove stale detection and recovery.",
            "",
            "### Decisions",
            "- Keep source-map ordering aligned with the source agent processed_notes state.",
            "",
            "### Open Questions",
            "- Should the future real-model version merge semantically similar bullets beyond exact-text matching?",
            "",
        ]
    )


def validation_assert(condition: bool, message: str) -> None:
    if not condition:
        raise DemoError(f"Validation failed: {message}")


def run_validate_command(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    validation_dir = reset_validation_workspace(workspace_root)
    configs = {
        config.name: config
        for config in load_agent_configs(resolve_workspace_path(workspace_root, args.config_dir), workspace_root)
    }
    source_config = AgentConfig(
        **{
            **configs["daily-notes-to-doc"].__dict__,
            "workspace_dir": validation_dir,
            "state_file": validation_state_path(workspace_root, "daily-notes-to-doc"),
            "reports_dir": validation_reports_dir(workspace_root, "daily-notes-to-doc"),
        }
    )
    audit_config = AgentConfig(
        **{
            **configs["doc-audit"].__dict__,
            "workspace_dir": validation_dir,
            "state_file": validation_state_path(workspace_root, "doc-audit"),
            "reports_dir": validation_reports_dir(workspace_root, "doc-audit"),
            "source_agent_state_file": validation_state_path(workspace_root, "daily-notes-to-doc"),
        }
    )

    first_source = run_agent(source_config, workspace_root)
    validation_assert(first_source["status"] == "updated", "source agent should process fixture notes on first run")
    validation_assert(len(first_source["pending_notes"]) == 2, "fixture workspace should start with two pending notes")

    second_source = run_agent(source_config, workspace_root)
    validation_assert(second_source["status"] == "skipped", "source agent should skip when no new notes exist")

    first_audit = run_agent(audit_config, workspace_root)
    validation_assert(first_audit["status"] == "pass", "audit should pass immediately after a fresh doc rebuild")

    write_validation_note(validation_dir, "2026-03-19-01.md", build_validation_note_body())
    stale_audit = run_agent(audit_config, workspace_root)
    validation_assert(stale_audit["status"] == "fail", "audit should fail when a new daily note has not been ingested")
    validation_assert(
        any("stale" in finding.lower() for finding in stale_audit["findings"]),
        "audit findings should mention stale derived docs",
    )

    refreshed_source = run_agent(source_config, workspace_root)
    validation_assert(
        refreshed_source["status"] == "updated" and refreshed_source["pending_notes"] == ["2026-03-19-01"],
        "source agent should ingest the new validation note exactly once",
    )

    final_audit = run_agent(audit_config, workspace_root)
    validation_assert(final_audit["status"] == "pass", "audit should pass again after refresh")

    source_map_text = (target_doc_dir(validation_dir) / "source-map.md").read_text(encoding="utf-8")
    source_rows = [line for line in source_map_text.splitlines() if line.startswith("| [2026-03-19-01]")]
    validation_assert(len(source_rows) == 1, "source-map should not duplicate newly processed notes")
    current_state_text = (target_doc_dir(validation_dir) / "current-state.md").read_text(encoding="utf-8")
    validation_assert("Source notes:" in current_state_text, "current-state doc should retain source-note citations")

    print(
        json.dumps(
            {
                "validation_workspace": relative_to_workspace(workspace_root, validation_dir),
                "steps": [
                    "source agent initial ingest",
                    "source agent idempotent rerun",
                    "audit pass on fresh docs",
                    "audit stale detection after new note",
                    "source agent refresh after new note",
                    "audit recovery pass",
                ],
                "final_source_result": refreshed_source,
                "final_audit_result": final_audit,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the daily-notes -> doc and doc-audit polling agent demo.")
    parser.add_argument("--workspace-root", default=str(WORKSPACE_ROOT))
    parser.add_argument("--config-dir", default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--include-disabled", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List the configured agents and runtime state.")
    run_parser = subparsers.add_parser("run", help="Run one agent immediately.")
    run_parser.add_argument("--config", required=True)
    watch_parser = subparsers.add_parser("watch", help="Watch one agent and run it on schedule.")
    watch_parser.add_argument("--config", required=True)
    watch_parser.add_argument("--once", action="store_true")
    watch_parser.add_argument("--max-runs", type=int, default=0)
    watch_all_parser = subparsers.add_parser("watch-all", help="Watch all enabled agents.")
    watch_all_parser.add_argument("--once", action="store_true")
    watch_all_parser.add_argument("--max-runs", type=int, default=0)
    subparsers.add_parser("validate", help="Run end-to-end validation for both polling agents.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            return list_agents(args)
        if args.command == "run":
            return run_single_agent_command(args)
        if args.command == "watch":
            return watch_single_agent_command(args)
        if args.command == "watch-all":
            return watch_all_agents_command(args)
        if args.command == "validate":
            return run_validate_command(args)
        raise DemoError(f"Unknown command: {args.command}")
    except DemoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
