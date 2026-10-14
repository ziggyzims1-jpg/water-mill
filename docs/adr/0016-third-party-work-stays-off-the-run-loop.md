---
status: accepted
---
# `ship`, `land` and `publish` are separate commands, never part of a run

Anything that talks to a third party (Loki, a forge and its CI, Zimmy) is its own command with its own exit code, so an outage cannot hang a night or leave a task claimed while a socket times out. `ship` advances its high-water mark only after a push returned and has no retry queue (`--resend` exists); `publish` omits unknown rather than zeroing it. A check that gates a decision runs before it: `land` never merges after a failed `verify`, and `review.merge` without `review.verify` is refused at contract parse time. Source: `CLAUDE.md` (Conventions), `docs/PUBLISH.md`, `docs/OBSERVABILITY.md`.
