# Daily Note Derived Doc Definition

This directory stores the stable, compressed documentation layer derived from daily notes.

## Required Files

- `current-state.md`
- `decisions.md`
- `open-questions.md`
- `source-map.md`

## Citation Rules

- Every non-trivial statement in derived docs must include a `Source notes:` line.
- Every citation must point to the exact daily-note file with a relative Markdown link.
- If evidence is ambiguous, the docs should preserve the ambiguity instead of adding certainty.

## State Rules

- Rebuild derived docs from the full processed note set after ingesting pending notes.
- Never mark a note as processed unless the derived docs were updated successfully.
- Keep `source-map.md` sorted and deduplicated as the canonical ingestion ledger.
