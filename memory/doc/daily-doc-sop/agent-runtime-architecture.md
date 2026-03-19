# Agent Runtime Architecture

## Purpose

This document defines the runtime architecture for the single-domain `daily-notes -> doc -> sop` chain under `/agents`.

It answers a different question from the three agent design documents:

- the agent design documents define each agent's responsibility boundary
- this document defines how the three agents are packaged, configured, scheduled, and connected at runtime

## Design Goals

- Keep the runtime simple.
- Keep the agents decoupled.
- Keep long-term knowledge only in `memory/daily-notes/`, `memory/doc/`, and `memory/sop/`.
- Keep machine-readable coordination in per-agent runtime folders instead of adding a new knowledge layer.
- Make launcher choice and runner parameters configurable per agent.

## Folder Layout

The runtime lives under `agents/`.

Each agent owns one self-contained workspace:

- `agents/<agent-id>/agent.json`
- `agents/<agent-id>/system.md`
- `agents/<agent-id>/runtime/state/`
- `agents/<agent-id>/runtime/work-orders/`
- `agents/<agent-id>/runtime/reports/`
- `agents/<agent-id>/runtime/scheduler-state.json`
- `agents/<agent-id>/runtime/launchers/<launcher-kind>/`

The unified entrypoint is:

- `agents/main.py`

## Why `agents/main.py`

The scheduler is placed under `agents/` because the runtime is itself part of the agent system rather than part of the historical demo area.

This keeps three things together:

- agent configuration
- agent runtime state
- agent scheduling and wakeup logic

## `agent.json` Contract

Each agent is declared with one `agent.json`.

The file contains four kinds of information:

### 1. Identity

- `id`
- `name`
- `description`
- `enabled`
- `order`

### 2. Task Contract

Under `task`:

- `id`
- `title`
- `goal`
- `system_prompt_path`
- `memory_paths`
- `allow_file_edits`

This keeps the agent task declarative, similar to the demo task file.

### 3. Launcher Contract

Under `launcher`:

- `kind`
- `config`

This keeps backend choice and backend-specific runtime parameters local to the agent config, so future launcher swaps do not require changing the scheduler.

### 4. Runtime Wiring

- `dependencies`
- `wakeup.watch_globs`
- `paths.workspace_root`
- `paths.runtime_root`
- `paths.launcher_root`

## Data Passing

The runtime does not introduce a fourth memory tier.

Data moves through machine-readable work-order files:

1. `Note Relation Agent`
   - input: `memory/daily-notes/*.md`
   - output: `agents/note-relation/runtime/work-orders/*.json`
2. `Doc Maintenance Agent`
   - input: `agents/note-relation/runtime/work-orders/*.json`
   - output: `agents/doc-maintenance/runtime/work-orders/*.json`
3. `SOP Promotion Agent`
   - input: `agents/doc-maintenance/runtime/work-orders/*.json`
   - output: `agents/sop-promotion/runtime/work-orders/*.json`

These work-order files are runtime coordination artifacts, not long-term memory artifacts.

## State Ownership

Each agent owns three kinds of state:

- domain-specific runtime state under `runtime/state/`
- generic scheduler state under `runtime/scheduler-state.json`
- launcher-private state under `runtime/launchers/<kind>/`

The scheduler owns only generic run metadata such as:

- last run time
- last input fingerprint
- last trigger reason
- launcher used for the last run

Each agent owns the semantic processing state, such as:

- which note or upstream work order has already been consumed
- which content hash has already been read
- which downstream work order has already been emitted

## Wakeup Model

The scheduler is the only polling component.

It polls watched inputs declared in `wakeup.watch_globs` and wakes agents only when those watched inputs change.

This is intentionally simple:

- one poller prevents duplicate work
- watched inputs reduce latency after upstream changes
- agents themselves do not each maintain their own poll loop

## Dependency Model

Dependencies are declared explicitly in `agent.json`.

Current chain:

- `doc-maintenance` depends on `note-relation`
- `sop-promotion` depends on `doc-maintenance`

The scheduler uses this for:

- execution order
- wakeup chaining
- task context generation
- exposing upstream work-order directories to downstream agents

## Path Normalization

Paths inside `agent.json` are written relative to the agent directory.

The scheduler normalizes them to workspace-relative paths before invoking the runner.

This avoids two common sources of drift:

- writing config relative to the repository root in some places and the agent folder in others
- making `system.md` or design document paths silently break when the runtime is moved out of `demo/`

## Orchestration Boundary

`main.py` wakes agents, but does not rigidly assign the exact note or work-order subset they must process.

After wakeup, each agent still:

- scans its own scope
- reads its own runtime state
- decides the concrete processing set
- applies its own domain judgment

This keeps orchestration centralized without over-constraining the agents.

## Relationship To The Demo

The demo remains a reference for session execution style, but it is no longer the runtime home of the formal system.

The first formal runtime migration is:

- scheduling moved to `agents/main.py`
- launcher adapters introduced under `agents/runners/`
- the current Codex implementation wrapped as one launcher adapter
- per-agent state moved to `agents/<agent-id>/runtime/`

## Current Scope

This runtime architecture is intentionally limited to:

- one domain
- one positive chain: `daily-notes -> doc -> sop`
- no audit or demotion agent yet
- no multi-domain routing yet

## Summary

The runtime can be compressed into one sentence:

> Put each agent in its own folder, keep task and launcher config in `agent.json`, let `agents/main.py` poll and wake agents, and pass machine-readable work orders across the chain without adding a new long-term memory layer.
