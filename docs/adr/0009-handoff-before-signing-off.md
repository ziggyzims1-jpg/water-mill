---
status: accepted
---
# Every agent writes a handoff before signing off

Owner's rule, 2026-08-28: no agent ends its turn without a handoff, written by the agent that still holds the context, because a compaction summary is a mechanical squeeze of a transcript. It says what failed, names files and functions, carries no diffs, fits one page, and is written even when blocked. Per bead it is one file with a dated section per agent; in this repo it is `HANDOFF-mill/<slug>.md`, in others `brain/handoffs/mill/`. It is never part of the PR (a handoff in the diff is a fence violation) except in cloud mode, where the container is thrown away. Source: memory note `agent-handoff-rule`, workshop `CLAUDE.md`, water-mill PR #12.
