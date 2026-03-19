from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class TaskDefinition:
    id: str
    title: str
    goal: str
    system_prompt_path: str = ""
    memory_paths: list[str] = field(default_factory=list)
    extra_context: str = ""
    allow_file_edits: bool = False


@dataclass
class ExecutionRequest:
    agent_id: str
    agent_name: str
    workspace_root: Path
    agent_dir: Path
    runtime_dir: Path
    runtime_state_dir: Path
    runtime_work_orders_dir: Path
    runtime_reports_dir: Path
    runner_workspace_dir: Path
    upstream_work_order_dirs: list[Path]
    wakeup_globs: list[str]
    trigger_reason: str
    launcher_kind: str
    launcher_config: dict[str, Any]
    task: TaskDefinition


@dataclass
class ExecutionResult:
    status: str
    launcher_kind: str
    started_at: str
    finished_at: str
    payload: dict[str, Any] = field(default_factory=dict)


class RunnerAdapter(Protocol):
    kind: str

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        ...
