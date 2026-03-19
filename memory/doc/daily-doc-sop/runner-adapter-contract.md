# Runner Adapter Contract

## Purpose

This document defines how agents are launched without coupling the whole system to one execution backend.

## Core Principle

An agent is not the same thing as a launcher.

- the agent defines the domain mission
- the launcher defines how that mission is executed

Today one launcher may be `codex`. Later there may be others.

Therefore:

- `main.py` must be launcher-agnostic
- launcher-specific files must stay inside launcher-specific workspaces
- agent configs must declare launchers declaratively

## Config Contract

Each `agent.json` declares:

```json
{
  "launcher": {
    "kind": "codex",
    "config": {
      "model": "gpt-5.4",
      "session_style": "tool-loop",
      "max_turns": 8
    }
  }
}
```

`kind` chooses the adapter.

`config` is opaque to `main.py`. It is passed through to the selected adapter.

## Execution Request

`main.py` builds a generic execution request containing:

- agent identity
- workspace root
- agent directory
- runtime directories
- upstream work-order directories
- wakeup reason
- task definition
- launcher kind
- launcher config

This request is intentionally generic. It should not include backend-specific queue semantics.

## Adapter Responsibilities

The selected launcher adapter is responsible for:

- translating the generic request into backend-specific execution
- managing its own private workspace under `runtime/launchers/<kind>/`
- returning a generic execution result to `main.py`

## Adapter Workspace

Launcher-specific artifacts must live under:

- `agents/<agent-id>/runtime/launchers/<kind>/`

This keeps the boundary clear:

- `runtime/state/`, `runtime/work-orders/`, and `runtime/reports/` are agent runtime artifacts
- `runtime/launchers/<kind>/` is launcher-private workspace

## Why This Matters

If Codex directories are placed directly into the agent root structure, the architecture quietly becomes Codex-shaped.

That makes it harder to:

- add other launchers
- reason about what is agent state vs launcher state
- keep the scheduler clean

## Current Codex Adapter

The current `codex` adapter may keep private directories such as:

- `runs/`
- `scratch/`
- `state/`

These are launcher-private artifacts, not project memory layers.

## Summary

The contract can be compressed into one sentence:

> `main.py` launches agents through a generic adapter interface, and each launcher keeps its own private workspace under `runtime/launchers/<kind>/` without redefining the system architecture.
