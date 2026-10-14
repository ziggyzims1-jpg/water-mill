---
status: accepted
---
# Never `npm ci` in a checkout whose `node_modules` worktrees share

Zimmy's mill worktrees symlink `$REPO/frontend/node_modules`. On 2026-09-24 one of eight concurrent millstones ran `npm ci`, which deletes the directory first, and other agents' vite and vitest runs failed mid-run. A broken shared `node_modules` is repaired by a worktree-local install or by the orchestrator while no agent is running, never by an agent in the shared one. Same class of hazard as ADR-0004. A canon crew rule: it applies to any repo whose worktrees symlink a shared `node_modules`, today zimmy-life-tracker. Source: memory note `watermill-shared-node-modules-hazard`; codified in `canon/common/.claude/agents/millstone.md` ("Environment").
