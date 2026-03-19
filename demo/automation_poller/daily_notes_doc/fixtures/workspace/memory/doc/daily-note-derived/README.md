# Daily Note Derived Doc Definition

This directory stores stable, traceable summaries distilled from processed daily notes.

## Required Files

- `README.md` defines the contract for this derived layer.
- `current-state.md` tracks stable signals, active workstreams, recent changes, and coverage.
- `decisions.md` records durable decisions with status and note citations.
- `open-questions.md` records unresolved questions with status and note citations.
- `source-map.md` is the canonical processed-note ledger.

## Citation Rules

1. Every non-trivial statement in derived docs must be backed by a `Source notes:` line.
2. Each citation must link to the exact daily note using a relative Markdown path.
3. When source evidence is ambiguous, the derived docs should preserve that ambiguity.

## State Rules

1. Notes are marked processed only after the derived docs are refreshed successfully.
2. `source-map.md` must contain one sorted row per processed note with no duplicates.
3. If no new notes exist, derived docs stay unchanged and the run is reported as a no-op.
