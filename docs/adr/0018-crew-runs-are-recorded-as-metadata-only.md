---
status: accepted
---
# Each agent records its own run at sign-off, metadata only

`watermill agents record --pr <n>` at sign-off writes one tracked line to `knowledge/agent-runs/`, the one record that survives a cloud container; `runs/agents.jsonl` is the local, gitignored schema for any agent kind, and transcript sweeps (`agents sweep`) take metadata only, never message text. Recording early captures seconds of a run and no PR, so the record is a sign-off step. Source: water-mill-441, water-mill-61r, water-mill-a7z, `docs/OBSERVABILITY.md`, `watermill/recorded.py`.
