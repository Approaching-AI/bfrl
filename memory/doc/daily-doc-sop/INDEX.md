# Daily Doc SOP Design Index

## Scope

This folder contains the design documents for the single-domain `daily-notes -> doc -> sop` positive promotion chain.

Current scope:

- single domain only
- positive chain only
- no audit / demotion agent yet

## Documents

- [daily-doc-sop-system-design.md](daily-doc-sop-system-design.md)
  - Overall system design and agent boundaries.
- [daily-doc-sop-methodology-review.md](daily-doc-sop-methodology-review.md)
  - Review of the current three-agent methodology and a more stable cluster-aware design direction.
- [agent-runtime-architecture.md](agent-runtime-architecture.md)
  - Runtime packaging, scheduler contract, per-agent folder layout, and work-order flow under `/agents`.
- [main-orchestrator-design.md](main-orchestrator-design.md)
  - `main.py` as the only poller and orchestrator for the three-agent chain.
- [runner-adapter-contract.md](runner-adapter-contract.md)
  - Runner-agnostic launcher interface and adapter-private workspace rules.
- [note-relation-agent-design.md](note-relation-agent-design.md)
  - Agent 1 design for note triage, relation assignment, and work-order emission.
- [doc-maintenance-agent-design.md](doc-maintenance-agent-design.md)
  - Agent 2 design for doc updates, doc creation, and doc index maintenance.
- [sop-promotion-agent-design.md](sop-promotion-agent-design.md)
  - Agent 3 design for SOP promotion and SOP index maintenance.
