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

## Public CLI Surface

The public entrypoint should stay config-driven:

- `python agents/main.py`
- `python agents/main.py --config agents/config.yaml`

The formal CLI should not expose per-agent debug switches as part of its stable surface. Manual or forced runs may still exist internally, but the public contract stays centered on loading one scheduler config and then letting the scheduler decide which agents to wake.

## What `main.py` Does

`main.py` is responsible for:

1. discovering `agents/*/agent.json`
2. loading shared scheduler config from `agents/config.yaml`
3. loading dependency order
4. polling watched inputs
5. supporting both workspace-relative paths and an absolute external `memory_root` during watched-input scanning
6. detecting whether watched inputs have changed
7. waking the right agent at the right time
8. passing runtime context to the selected launcher
9. validating required runtime artifacts for formal chain agents
10. recording scheduler state

## What `main.py` Does Not Do

`main.py` should not:

- perform note relation assignment
- maintain docs
- promote SOPs
- decide the exact note or work-order subset an agent must process
- embed Codex-specific assumptions into the orchestration contract

Its role is wakeup and coordination, not domain cognition.

## Shared Scheduler Config

Shared runtime settings belong in `agents/config.yaml`, not in hard-coded constants and not in each `agent.json`.

Current shared settings include:

- `watch`
- `sleep_seconds`
- `memory_root`
- `default_model`
- `agent_models`

This keeps one boundary clear:

- `agents/config.yaml` owns scheduler-wide runtime policy
- `agent.json` owns agent-local task, wakeup, and launcher declarations

## Wakeup Model

Each agent declares `wakeup.watch_globs` in `agent.json`.

Examples:

- `Note Relation Agent` watches `memory/daily-notes/*.md`
- `Doc Maintenance Agent` watches `agents/note-relation/runtime/work-orders/*.json`
- `SOP Promotion Agent` watches `agents/doc-maintenance/runtime/work-orders/*.json`

`main.py` polls these globs, computes an input fingerprint, and wakes the agent only when the watched input set changes.

When the shared `memory_root` points outside the repository, the same wakeup logic must still work for absolute paths rather than assuming every watched input is workspace-relative.

## Monitor Output

The scheduler should emit human-readable monitor lines that make the runtime state legible without opening JSON files.

Useful monitor output includes:

- which config file was loaded
- whether watch mode is enabled
- the current agent order
- whether an agent was skipped or launched
- the runner kind and model used for a launch
- elapsed time
- which runtime artifacts changed
- whether the scheduler is sleeping because nothing changed

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

## Runtime Artifact Enforcement

For formal chain agents such as `note-relation`, `doc-maintenance`, and `sop-promotion`, a successful wakeup should produce machine-readable runtime artifacts.

At minimum, the scheduler can require evidence that the run wrote one of:

- `runtime/work-orders/*.json`
- `runtime/state/runtime-state.json`

This enforcement belongs to orchestration rather than domain logic. It checks whether the session produced consumable runtime outputs, not whether the agent's reasoning was correct.

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
