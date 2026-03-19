# Agents

This directory contains one self-contained workspace per agent.

## Layout

Each agent lives under `agents/<agent-name>/` and contains:

- `agent.json` for declarative task and launcher config
- `system.md` for the operating contract
- `runtime/` for persistent state, work orders, reports, scheduler state, and launcher workspaces

The unified scheduler entrypoint is `agents/main.py`.

`main.py` is the only poller and the only public runtime entrypoint in the formal system. Agents do not poll on their own, and `main.py` is responsible for orchestrating the whole `notes -> doc -> sop` chain.

## Data Flow

- `note-relation` reads `memory/daily-notes/` and writes machine-readable work orders into its own `runtime/work-orders/`
- `doc-maintenance` consumes upstream note-relation work orders and writes downstream work orders into its own `runtime/work-orders/`
- `sop-promotion` consumes upstream doc-maintenance work orders and writes promotion results into its own `runtime/work-orders/`

The scheduler handles polling, wakeup, and dependency-aware execution order. The agents exchange data through runtime work-order files instead of introducing a new long-term memory layer.

`main.py` only wakes agents and passes context. Each agent still inspects its own scope and decides the concrete processing set.

During orchestration, `main.py` also emits human-readable monitor lines to the terminal so you can see which agent is being checked, skipped, launched, completed, or put back into sleep.

## Launchers

Agent launch is runner-agnostic.

- `agent.json` declares `launcher.kind` and `launcher.config`
- `main.py` resolves the launcher adapter under `agents/runners/`
- launcher-private files live under `runtime/launchers/<launcher-kind>/`

Current implementation includes the `codex` launcher as one adapter, not as the system architecture itself.

Shared runtime settings now live in `agents/config.yaml`, including:

- `watch`
- `sleep_seconds`
- `memory_root`
- `default_model`
- `agent_models`

## Entrypoints

- `python agents/main.py`
  - run using the default `agents/config.yaml`
- `python agents/main.py --config agents/config.yaml`
  - run using an explicit JSON/YAML config file

## Conventions

- Keep agent behavior aligned with `AGENT.md` and the design docs under `memory/doc/daily-doc-sop/`.
- Keep the agent workspace isolated from the shared demo runtime.
- Keep the scheduler decoupled from any one launcher implementation.
- Keep the config simple enough to swap models or launchers later without changing the folder layout.
