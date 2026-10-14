---
status: accepted
---
# The context graph is append-only JSONL rebuilt in memory, with no database

Findings, tasks and runs are three append-only JSONL files rebuilt on every call: 2,000 findings cost 43ms to build and 37ms to search, so an index buys a staleness bug and nothing else. Concurrency is handled by having no lock (one `O_APPEND` write of one line under the pipe buffer is atomic, hence `MAX_LINE_BYTES` refuses rather than truncates), which holds only on a local filesystem, never NFS or SMB. Revisit when `recall --usage` measures p95 past about 250ms. Source: `CLAUDE.md` ("There is no database, and the reason is a measurement"), `docs/KNOWLEDGE.md`.
