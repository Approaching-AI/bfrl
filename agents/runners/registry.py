from __future__ import annotations

from .base import RunnerAdapter
from .codex.runner import CodexRunner


def get_runner(kind: str) -> RunnerAdapter:
    normalized = kind.strip().lower()
    if normalized == "codex":
        return CodexRunner()
    raise ValueError(f"Unknown runner kind: {kind}")
