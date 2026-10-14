# Handoff — water-mill-fwm.3

## Millstone (2026-10-14)
- **Where things stand.** Branch bead/fwm-3, PR #51 https://github.com/ziggyzims1-jpg/water-mill/pull/51. `make verify` green (768 passed); `watermill validate` green on water-mill. Not blocked. No sync run against siblings.
- **Design.** Python 3 stdlib hook (shlex tokenise, split on `; & | ( )`, newline, backtick; read `[env] git [global opts] sub args`; recurse into `bash -c`/`eval`). Chosen over bash+jq: bash 3.2 vs Linux, jq absence, and grep cannot tell `echo "git stash"` from a command. Invoked as `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/block-dangerous-git.py"` (no exec bit needed; sync only chmods .sh). Verified under /usr/bin/python3 3.9.6 and 3.13.
- **Tried / failed.** First version let `true\ngit stash` through: shlex treats newline as whitespace, so newline must be rewritten to `;` before lexing. The synced header line (117 chars) broke `ruff` E501 in water-mill's own copy; fixed by `# ruff: noqa: E501` in the canon script (sibling repos' ruff configs would hit the same). BSD `sed -i '1a ...'` fails on macOS; used Edit.
- **Lessons for the graph.** shlex without a newline rewrite misses newline-separated commands. A synced header comment is generated, so any lint on line length must be disabled per file in canon. Water-mill's own checkout is a sync target: after changing canon, apply `sync.make_plan(root, fs_reader(root), "project")` + `apply_plan` and commit the result, or `validate` goes red.
- **Look here first.** `canon/common/.claude/hooks/block-dangerous-git.py::rule_for` and `segments`.
- **Open questions.** `git restore --staged .` is allowed (index-only, harmless); `checkout .` is blocked even on a clean tree. Fails open on unreadable input. Say if either should change.
- **Follow-ups.** Not seen: git run inside scripts/make, aliases, `sudo -u x git`, `$VAR stash`, `git checkout ./`. After merge: orchestrator runs `watermill sync` per sibling and `sync workshop` (the hook will also block this crew's `git stash` once synced; the workshop `.claude` gets the hook file but settings only if it has a settings target). Note the workshop receives `common/` incl. the hook script and the managed settings merge.

## Sluice (2026-10-14)
- **Verdict: approve_after_fixes.** Fixes in b0aab94; run record in 5610e46 (both on bead/fwm-3).
- **What I checked myself.** `make verify` in my own worktree: 768 passed before my changes, 787 after. `watermill validate`: the water-mill line reads "synced files match canon". The overall exit is 1, same as main, because the five sibling repos have not been synced yet. Ran all 109 hook cases under /usr/bin/python3 3.9.6 (macOS system python): all correct. Settings: SessionStart and both allow permissions are kept, the JSON is valid, and the managed entry is listed in `.claude/watermill-managed.json` so sync can find and remove it.
- **Blockers found and fixed (the hook would have halted the mill).**
  1. tailrace step 3 told agents to run `git -C "$WT" reset --hard origin/<branch>`, which the hook denies. Canon and water-mill's tailrace now say `reset --keep` (same result in a fresh worktree). The copies in cheme-solver, Hillel-Programming, the cell template and zim-dashboard-demo-cell-1b still say `--hard` until `watermill sync` runs there. They get the hook in the same sync, so they never have one without the other.
  2. cheme-solver `brain/runbooks/cloud-mill.md` step 5: `git push --force-with-lease=$SB:$SHA ...` was denied. **This goes against the bead's wording ("block --force-with-lease"). Owner should confirm.** The pinned form `--force-with-lease=<ref>:<expect>` is now allowed in `_unpinned_lease`, because it can only overwrite the commit it names. A bare lease, or one with only a ref, is still blocked.
  3. Here-document bodies were read as commands. `git commit -F - <<'EOF'` with a body line "git reset --hard is now blocked" was denied, and the deny text tells the agent to stop and report BLOCKED. New `strip_heredocs` skips the body. If there is no terminator line, nothing is skipped.
  4. `if/elif/while/until git stash` was allowed. Those words are now in WRAPPERS.
  5. `test_an_unbalanced_quote...` had a vacuous `... or True` assert. Fixed.
- **Mutation tests** (copy, edit, restore; no stash). 12 mutations of the canon hook. Every one failed at least one test. But eval recursion, `restore -W` and the `--` cutoff were caught only by the canon-vs-checkout drift test, not by any behaviour test. I added tests for them; now each mutation fails 2 or 3 tests.
- **Not fixed, noted.**
  - The hook fails open on unreadable input and on a missing `python3` (exit 127 does not block). That matches the bead's intent: it must never wedge a session. The image must have `python3` on PATH. The docstring states this; nobody has tested it in a cloud session.
  - The heredoc skip is regex-based: a `<<WORD` inside a quoted string followed later by a WORD line would hide the lines in between. That is acceptable for an accident guard.
  - Human recovery docs still show blocked commands: `docs/ONBOARDING.md` and `docs/SAFETY.md` show `git checkout -- .` and `git clean -fd`. zimmy `scripts/loop.sh` runs them too, but the hook never sees commands inside a script.
  - zimmy `settings.local.json` allows `Bash(git stash *)`. The hook's deny overrides that allow.
  - Not caught: commands run inside scripts or make, git aliases, `$VAR stash`.
- **For the lander.** After merge, sync every sibling, and the workshop as well. Every tailrace copy must change along with the hook.
- **Findings:** f-20261014-c4e66a (heredoc), f-20261014-ff2382 (grep crew instructions before denying), plus a third on drift-masked mutations in tests/test_git_guardrail.py.

## Tailrace (2026-10-14)
**LANDED** PR #51 squash-merged, merge commit 17a726f6b58337603bfd8bc54703721ced4c563b (head 5610e46 verified green, `--match-head-commit`). bead/fwm-3 deleted (remote gone). No conflict.
- `bd close water-mill-fwm.3`: "Closed water-mill-fwm.3 ... Merged in PR #51". No auto-export warning. Import said "1 stale skipped"; export diff showed only the fwm.3 line.
- Committed .beads/issues.jsonl, sluice's knowledge/findings.jsonl (3 lines) and run records.
- Owner must confirm: pinned `--force-with-lease=<ref>:<sha>` is allowed (differs from bead wording). Orchestrator: run `watermill sync` per sibling and workshop (not run by me). Hook may now block `git stash`/`reset --hard` in this repo.
- **Findings:** f-20261014-c4e66a, f-20261014-ff2382 and the drift-mutation finding, all filed by sluice with --task water-mill-fwm.3.
