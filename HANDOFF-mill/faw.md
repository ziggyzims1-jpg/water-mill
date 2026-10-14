# Handoff — water-mill-faw

## Millstone (2026-10-14)
- **Where things stand**: branch bead/faw, PR #56 (https://github.com/ziggyzims1-jpg/water-mill/pull/56). `make verify` passed (805 tests); tests/test_sync.py 42 passed. Not blocked. Recall ran (nothing on _git input=). Run record committed on the branch.
- **What was tried and did not work**: nothing abandoned. Note the first `make verify && git push && gh pr create` chain exceeded the 120s tool timeout and went to background; the PR was then created separately.
- **Lessons for the graph**: `_git(check=False)` cannot tell exit 1 from 128; accept exit codes explicitly with `ok=`. A `make verify` run takes ~2 min, longer than the default tool timeout.
- **Seams**: `watermill.sync._git` (private; the interface the bead specifies; 1-vs-128 only reachable here), plus existing fwm.9 refusal tests for `gitignored()` behaviour.
- **Look here first**: `watermill/sync.py` `_git` and `gitignored`. Red evidence: the two new `test_git_*` tests failed with TypeError on the base.
- **Open questions**: none.
- **Follow-ups**: the error message for a check-ignore failure now reads "git check-ignore -v --stdin failed in ..." (was "git check-ignore failed in ..."); no test depended on it.

## Bolter (2026-10-14)
- **Reviewed**: PR #56, bead/faw @ 108d095 (968afbb refactor + run-record commit), detached worktree wt-bolter-faw. Laptop mode. Recall ran (hits: check-ignore lessons f-20261014-78ab40, -a2e85f; nothing on `_git` input=).
- **Sources**: water-mill `CLAUDE.md` Conventions, `ruff.toml` (E,F,I,B,UP,SIM; ruff clean on both files), `docs/SAFETY.md` (sync.py not one of the four safety files). **Missing**: `CODING_STANDARDS.md`, `docs/adr/`, `CONTEXT.md`, `CONTRIBUTING.md` (fwm.6 backfill not here yet); no folder-level CLAUDE.md under `watermill/` or `tests/`.
- **Blocking**: none. argv-only, no shell; full stdout read; `stdin=None` alongside `input=` is legal for `subprocess.run`.
- **Advisory**:
  1. `tests/test_sync.py::test_git_feeds_input_on_stdin`: possible test that cannot fail. With nothing ignored, a `_git` that dropped `input` (stdin=DEVNULL) also exits 1 with empty stdout, so the test passes either way. Fix: write `.gitignore` with `a`, feed `"a\nb\n"`, assert `"a\n"` comes back. `[auto-mill candidate]` (tests only; but depth 1, so file normally, never auto-run).
  2. `watermill/sync.py::_git` parameter `input`: possible Mysterious Name / builtin shadow (ruff `A` not selected, so tooling won't catch it). Fix: rename `stdin_text` (or keep, matching `subprocess.run`'s own name; judgement, low value).
  3. `_git` now has two overlapping failure knobs (`check`, `ok`): not a smell yet with real callers for both; noted only.
- **Findings:** none -- no blocking finding, so nothing repeatable to record.
- **Run record**: `knowledge/agent-runs/bolter-water-mill-faw-affaacd81d41.jsonl` (written in the worktree, uncommitted; copy at scratchpad `bolter-faw-record/bolter-water-mill-faw-affaacd81d41.jsonl`) for sluice to commit. Line: role=bolter bead=water-mill-faw pr=56 key=session:1f77a9c6-cafb-41c6-b875-6daaa0451fba:agent-affaacd81d4102a80 tool_calls=7 transcript_located=True.

## Sluice (2026-10-14)
- **Verdict**: approve_after_fixes. Diff matches the bead exactly: `_git` gains `input=`/`ok=`, `gitignored()` reuses it with `ok=(0, 1)`, exit 128 still raises SyncError. Only `watermill/sync.py` and `tests/test_sync.py` (+ run records) touched; no fence/safety file (sync.py is not in docs/SAFETY.md's four). Laptop mode. Recall ran (check-ignore lessons f-20261014-78ab40/-a2e85f; nothing on `_git` stdin).
- **Red before green**: believable and reproduced. The two new `test_git_*` tests on base `watermill/sync.py` fail with TypeError (unknown kwarg `input`).
- **Bolter blocking**: none to resolve. Advisory 1 fixed in e883c9f: `test_git_feeds_input_on_stdin` now writes `.gitignore` with `a`, feeds `"a\nb\n"`, asserts `"a\n"` (and keeps the exit-1/empty case). Advisory 2 (`input` shadows a builtin): kept, deliberately. It matches `subprocess.run`'s own name, and ruff `A` is not selected. Advisory 3 (`check` vs `ok`): left alone, both have real callers.
- **Mutations** (patch-copy, no stash): drop stdin → 3 fail (incl. the strengthened test); `!= 0` instead of `not in ok` → fails; accept 128 in `_git` → fails; `gitignored` with `ok=(0,)` → fails; **`gitignored` with `ok=(0, 1, 128)` stayed green**. That was a gap, closed in e883c9f by `test_gitignored_raises_when_git_itself_fails` (now fails under that mutation).
- **Independent verify**: `make install && make verify` in wt-sluice-faw: 806 passed, verify: passed. ruff clean.
- **Findings**: f-20261014-0dc9bf (a stdin test must make stdin change the output), f-20261014-f820b6 (pin the excluded exit code when widening `ok`). Both `--cause pending`.
- **Auto-mill beads filed**: none. faw is itself auto-mill (depth 1), and no advisory was left that is worth a bead.
- **Run records**: committed in 39a3356, `knowledge/agent-runs/sluice-water-mill-faw-a8de8de77181.jsonl` plus the bolter's `bolter-water-mill-faw-affaacd81d41.jsonl` (copied verbatim from scratchpad).
- **For the lander**: branch head is now 39a3356 (was 108d095). Not merged, bead not closed. Commit trailers say `Claude Opus 5.5` (the session attribution) rather than the role file's `Claude Fable 5`.

## Tailrace (2026-10-14)
**LANDED** -- MERGED, PR #56 squash-merged as 0ca227a2c1b77d244849ef4d33cee54585d94525 (head 39a33565 sha-guarded via --match-head-commit; verify check green, 41s). Remote branch bead/faw deleted by the merge.
- No conflict.
- `bd close`: "Closed water-mill-faw -- Give sync._git an input= kwarg and use it in gitignored(): Merged in PR #56"; no auto-export warning. Pulled ff-only, bd import (44 issues, 2 stale skipped), export. Sorted diff: faw line plus one other: water-mill-fwm.6 open -> in_progress (started_at set), a claim by the parallel fwm.6 crew; committed as it is a claim, not a revert.
- auto-mill: none (sluice filed none; faw itself is depth 1).
- Findings: sluice f-20261014-0dc9bf and f-20261014-f820b6 reference faw; tailrace added the make-verify-timeout lesson. The knowledge/findings.jsonl commit also carries parallel sluice runs' appended lines.
- `review --lag` output: see report.
