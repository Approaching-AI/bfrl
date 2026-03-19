# Main Orchestrator Design

## Purpose

This document defines the role of `agents/main.py` in the formal single-domain `daily-notes -> doc -> sop` system.

It is the runtime coordinator, not a domain agent.

## Core Principle

`main.py` is the only poller in the formal system.

The three domain agents should not each run their own polling loop. That would:

- waste tokens
- duplicate wakeup logic
- blur responsibility between orchestration and domain work

## What `main.py` Does

`main.py` is responsible for:

1. discovering `agents/*/agent.json`
2. loading dependency order
3. polling watched inputs
4. detecting whether watched inputs have changed
5. waking the right agent at the right time
6. passing runtime context to the selected launcher
7. recording scheduler state

## What `main.py` Does Not Do

`main.py` should not:

- perform note relation assignment
- maintain docs
- promote SOPs
- decide the exact note or work-order subset an agent must process
- embed Codex-specific assumptions into the orchestration contract

Its role is wakeup and coordination, not domain cognition.

## Wakeup Model

Each agent declares `wakeup.watch_globs` in `agent.json`.

Examples:

- `Note Relation Agent` watches `memory/daily-notes/*.md`
- `Doc Maintenance Agent` watches `agents/note-relation/runtime/work-orders/*.json`
- `SOP Promotion Agent` watches `agents/doc-maintenance/runtime/work-orders/*.json`

`main.py` polls these globs, computes an input fingerprint, and wakes the agent only when the watched input set changes.

## Important Boundary

Waking an agent is not the same as fully assigning its processing target.

The orchestrator can say:

- your watched inputs changed
- these upstream work-order directories exist
- these dependencies ran before you

But the agent still decides:

- what the relevant processing set is
- which files it must read
- how much evidence is enough

This preserves agent autonomy while keeping orchestration efficient.

## Scheduler State

`main.py` maintains generic scheduler state at:

- `agents/<agent-id>/runtime/scheduler-state.json`

This file tracks only orchestration concerns such as:

- run count
- last run timestamps
- last input fingerprint
- last launcher kind
- last trigger reason

It is not the same as the agent's own semantic state under `runtime/state/`.

## Execution Order

Agents are evaluated in dependency order:

1. `note-relation`
2. `doc-maintenance`
3. `sop-promotion`

This allows one orchestrator loop to trigger a full downstream chain:

- if daily notes changed, wake `note-relation`
- if its work-orders changed, wake `doc-maintenance`
- if its downstream work-orders changed, wake `sop-promotion`

## Manual Runs

`main.py` should also support manual wakeup for debugging or forced runs.

Manual wakeup is still orchestration. It does not change the fact that the agent scans its own scope after being launched.

## Summary

The orchestrator can be compressed into one sentence:

> `main.py` polls shared inputs, wakes agents in dependency order, and passes context to launchers, while leaving domain-level selection and reasoning to the agents themselves.
