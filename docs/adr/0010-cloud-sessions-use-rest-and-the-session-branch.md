---
status: accepted
---
# In cloud sessions: GitHub REST only, the session branch, beads as JSONL commits

Learned 2026-10-13. The cloud git proxy rejects pushes of anything but a branch, so `bd dolt push` and `refs/dolt/*` fail; `gh pr` uses GraphQL and returns 403 while `gh api` REST works; the session may push only its own `claude/...` branch. So in `CLAUDE_CODE_REMOTE=true` the session branch is the PR head, beads travel as `.beads/issues.jsonl` commits carried to main by a beads-sync workflow, handoffs are committed, and there is one orchestrator docs-only PR per session with no per-bead bookkeeping PR. The Agent tool's `isolation: "remote"` silently falls back to a local worktree on the laptop, so a real cloud run is started from claude.ai/code. Source: memory note `claude-cloud-sessions-constraints`, water-mill-mb6, water-mill-hix, `scripts/cloud-setup.sh` (water-mill-fwm.8).
