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

## Task Definition

Before building the launcher request, `main.py` assembles a generic `TaskDefinition`.

Current task fields are:

- `id`
- `title`
- `goal`
- `system_prompt_path`
- `memory_paths`
- `extra_context`
- `allow_file_edits`

This keeps the execution backend aware of the real task contract rather than only receiving a raw prompt string.

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

Current `ExecutionRequest` fields are:

- `agent_id`
- `agent_name`
- `workspace_root`
- `agent_dir`
- `runtime_dir`
- `runtime_state_dir`
- `runtime_work_orders_dir`
- `runtime_reports_dir`
- `runner_workspace_dir`
- `upstream_work_order_dirs`
- `wakeup_globs`
- `trigger_reason`
- `launcher_kind`
- `launcher_config`
- `task`

This request is intentionally generic. It should not include backend-specific queue semantics.

## Instruction Layers

Adapters should treat the incoming task as a layered contract rather than a single flat prompt.

In the current Codex path, the effective instructions come from:

1. the agent `system.md`
2. the declarative task fields in `agent.json`
3. scheduler-supplied runtime context such as runtime directories and wake reason
4. a shared Codex wrapper prompt that enforces common execution expectations

This layering keeps stable agent identity, per-run context, and runner-specific guidance separate.

## Adapter Responsibilities

The selected launcher adapter is responsible for:

- translating the generic request into backend-specific execution
- managing its own private workspace under `runtime/launchers/<kind>/`
- returning a generic execution result to `main.py`

## Execution Result

The launcher returns a generic `ExecutionResult` rather than a backend-specific object.

Current result fields are:

- `status`
- `launcher_kind`
- `started_at`
- `finished_at`
- `payload`

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

Real Codex execution also established three practical constraints for this adapter:

- task-level `system_prompt_path` and explicit write permission must reach the adapter so sessions can enter a write-capable path instead of treating the run as open-ended exploration
- tighter work-order style task definitions reduce the risk that the driver times out before the model starts producing the required files
- longer wait windows may be necessary because real file-writing sessions can make correct progress even when the first visible output is delayed

The concrete launch chain is:

1. `main.py` calls the runner registry with `launcher.kind`
2. the `codex` registry entry returns `agents/runners/codex/runner.py`
3. `CodexRunner` translates the generic request into Codex-specific task arguments
4. the adapter starts `codex -m <model> app-server --listen stdio://`
5. the adapter opens a thread and turn, sends the layered task instructions, and listens for command plus final-answer events
6. the adapter returns one unified `ExecutionResult` to the scheduler

## Extension Path

To add a new runner:

1. implement the generic runner interface for a new `kind`
2. consume `request.task`, `request.launcher_config`, and `request.runner_workspace_dir`
3. return the same `ExecutionResult` shape
4. register the new runner kind in the runner registry
5. point an agent's `launcher.kind` at that runner

To add a new formal agent without breaking the runtime contract:

1. create `agents/<agent-id>/agent.json` and `system.md`
2. declare the task, dependencies, wakeup globs, and launcher kind there
3. keep long-term knowledge in `memory/`, not in runner-private folders
4. if the new agent should participate in formal artifact enforcement, update the scheduler-side enforcement list or config rather than pushing that responsibility into the runner

## Summary

The contract can be compressed into one sentence:

> `main.py` launches agents through a generic adapter interface, and each launcher keeps its own private workspace under `runtime/launchers/<kind>/` without redefining the system architecture.
