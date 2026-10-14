---
status: accepted
---
# Beads are committed and pushed as `.beads/issues.jsonl`

Any session or agent that creates, updates, closes or defers a bead commits and pushes `.beads/issues.jsonl` (a `chore(beads): ...` commit) before signing off. On 2026-09-03 the owner found three days of bead activity uncommitted and asked that beads always be reachable from any machine; bd's hooks re-export on commit, but a write with no commit never leaves the machine. Source: memory note `beads-push-to-git`, workshop `CLAUDE.md` ("Beads live in git"). The bd Dolt remote is not used for transport (see ADR-0010).
