# Daily Note Derived Doc Definition

This folder is the canonical target for the `daily-notes -> doc` polling agent.

## Required Files

- `current-state.md`: stable signals, active workstreams, recent changes, and coverage.
- `decisions.md`: durable decisions only, each with status and source-note citations.
- `open-questions.md`: unresolved questions only, each with status and source-note citations.
- `source-map.md`: one row per processed daily note, in sorted order, without duplicates.

## Citation Rules

- Every substantial statement in derived docs must include a `Source notes:` line.
- Citations must link to `memory/daily-notes/<note-id>.md` with a relative Markdown link.
- If evidence is insufficient, record uncertainty instead of inventing a conclusion.

## State Rules

- The source agent must maintain `processed_notes` and `last_processed_note` in its runtime state.
- Re-running the agent without new notes must not duplicate source-map entries.
- The audit agent should treat any unprocessed daily note as a stale-doc signal.
