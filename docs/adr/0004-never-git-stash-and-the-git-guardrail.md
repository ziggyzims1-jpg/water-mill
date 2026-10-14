---
status: accepted
---
# Never `git stash` in a mill worktree; a PreToolUse hook enforces it

Worktrees of one repo share a single `.git`, so the stash stack is global across every concurrent agent. On 2026-08-30 a stash/pop done to prove a test fails without a fix popped another agent's changes and silently reverted the fix. The rule (snapshot with a patch file instead) became a hook in canon, `block-dangerous-git.py`, that also denies `reset --hard`, `clean -f`, `branch -D`, `checkout .`, `restore .` and forced pushes; it lives in each repo's committed `.claude/settings.json` so it works in cloud sessions, and plain `push` stays allowed. Source: memory note `watermill-git-stash-hazard`, water-mill-fwm.3, `canon/README.md` ("The git guardrail"), `tests/test_git_guardrail.py`.

## Consequences

Crew instructions must never tell an agent to run a blocked form; tailrace resets a landing worktree with `reset --keep`. A gitignored hook script once blocked every Bash call (water-mill-fwm.9), so sync must not ship a settings entry whose script is ignored.
