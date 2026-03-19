# Agents

This directory contains one self-contained workspace per agent.

## Layout

Each agent lives under `agents/<agent-name>/` and contains:

- `agent.json` for declarative task and launcher config
- `system.md` for the operating contract
- `runtime/` for persistent state, work orders, reports, scheduler state, and launcher workspaces

The unified scheduler entrypoint is `agents/main.py`.

`main.py` is the only poller in the formal system. Agents do not poll on their own.

## Data Flow

- `note-relation` reads `memory/daily-notes/` and writes machine-readable work orders into its own `runtime/work-orders/`
- `doc-maintenance` consumes upstream note-relation work orders and writes downstream work orders into its own `runtime/work-orders/`
- `sop-promotion` consumes upstream doc-maintenance work orders and writes promotion results into its own `runtime/work-orders/`

The scheduler handles polling, wakeup, and dependency-aware execution order. The agents exchange data through runtime work-order files instead of introducing a new long-term memory layer.

`main.py` only wakes agents and passes context. Each agent still inspects its own scope and decides the concrete processing set.

## Launchers

Agent launch is runner-agnostic.

- `agent.json` declares `launcher.kind` and `launcher.config`
- `main.py` resolves the launcher adapter under `agents/runners/`
- launcher-private files live under `runtime/launchers/<launcher-kind>/`

Current implementation includes the `codex` launcher as one adapter, not as the system architecture itself.

## Entrypoints

- `python agents/main.py list`
- `python agents/main.py run --agent note-relation`
- `python agents/main.py watch --agent doc-maintenance`
- `python agents/main.py watch-all`

## Conventions

- Keep agent behavior aligned with `AGENT.md` and the design docs under `memory/doc/daily-doc-sop/`.
- Keep the agent workspace isolated from the shared demo runtime.
- Keep the scheduler decoupled from any one launcher implementation.
- Keep the config simple enough to swap models or launchers later without changing the folder layout.
