# Handoff — water-mill-fwm.8

## Millstone (2026-10-14)

**Where things stand.** PR https://github.com/ziggyzims1-jpg/water-mill/pull/49, branch bead/fwm-8. `make install` + `make verify` green (634 passed); new `tests/test_cloud_setup.py` 10 passed on the new script, 4 failed / 6 passed on the old one (red output is in the PR body). Not blocked. Bead left in_progress (not closed). Run recorded with --pr 49.

**Tried and did not work.**
- First fixture used a child id `x-c3.1` with no parent `x-c3`: `bd import` fails with a FK violation on `child_counters` and the db stays empty. A jsonl with dotted ids must include the parent issue.
- First "db present" starting state ran the *current repo's* script from its real location: it scans the siblings of wherever it lives, so it ran against the scratchpad directory next to my worktree (other agents' scratch clones: cheme-solver, Hillel-Programming, sim, zimmy-life-tracker, ...), not the temp parent. Those are throwaway copies, not ~/Documents/code, but their .beads dbs/untracked bd files may have been touched. Fixed by copying the builder script into the temp `water-mill/scripts/`.
- A careless `rm -rf *` in a scratch command was blocked by the safety check ("Dangerous rm operation ... water-mill/*"); I did not retry it. Nothing ran (the preceding `cd` had failed); I used mktemp instead.

**Lessons for the graph.**
- cloud-setup.sh scans the siblings of the checkout it lives in, so any test or experiment must copy it into a temp `<parent>/water-mill/scripts/` before running.
- A bd jsonl containing a dotted child id (`x-abc.1`) needs its parent issue present or `bd import` fails with a foreign-key error.
- In zsh, `echo ======` errors ("= not found"); quote it.

**Look here first.** `scripts/cloud-setup.sh` `setup_repo` and `derive_prefix`; the test `test_a_stale_database_is_brought_up_to_the_checked_out_jsonl`.

**Open questions for the human.** (1) The suite takes ~110s (real Dolt init per repo per scenario), adding to `make verify`; acceptable, or trim to fewer repos / mark slow? (2) The `.claude/settings.json` hook is unchanged (still runs the script then `bd prime`), which is correct; the routine-cwd gap is documentation only.

**Follow-ups worth a bead.** Test the origin-carries-`refs/dolt/data` case (needs a real Dolt remote fixture; the origin-URL blanking is untested). fwm.2 should make this script canon for all repos. Iterating siblings includes iCloud duplicates like `zimmy-life-tracker 2` on a laptop (harmless in cloud).

## Sluice (2026-10-14)

**Verdict: approve_after_fixes.** Fix commit fab8410, merge of origin/main (fwm.1/fwm.2, 92b9098) 90d21f3, both pushed to bead/fwm-8. Merged with no conflicts (CLAUDE.md auto-merged; nothing on main references cloud-setup.sh; the script was not moved into canon/).

**Safety.** The script exits at once unless CLAUDE_CODE_REMOTE=true or `--force`; the SessionStart hook passes no flag. Every test copies the script into a pytest temp `<parent>/water-mill/scripts/` and runs only that copy (`_run` defaults to the copy, and the builder is a copy too). No Makefile target runs the script. I ran it only in temp parents under the scratchpad. I added a header line: never `--force` on a laptop checkout.

**Parity.** Diffed against cheme-solver/scripts/cloud-setup.sh: the same logic line for line (pin, PATH bd used as is, env file, sed for both spellings, GIT_CONFIG origin blank, LOCAL_ONLY, restore, drop the init commit, explicit import), wrapped in a `setup_repo` function plus a sibling loop.

**Found and fixed (fab8410).**
1. `( setup_repo ) || log` ran with errexit ignored, so a failed step carried on and "setup failed" could never print. It now runs `set +e; ( set -e; setup_repo ); rc=$?; set -e`, which matches cheme, where the same code runs at top level under set -e.
2. Real-data bug: zimmy-life-tracker's jsonl has 103 `zimmy-life-tracker-*` ids and 101 newer `Zimmy Life Tracker-*` ids (the laptop db's prefix). bd init rejects the spaced name as a database name (checked by hand), so two more laptop beads would have flipped the majority and left zimmy with no cloud db. derive_prefix now counts only valid database names. I checked it against all five real jsonls: cheme, hpt, water-mill, zim-dashboard-demo-cell-1b, zimmy-life-tracker.
3. Vacuous test: the fixtures used `json.dumps` with spaces, which the id pattern never matches, so every prefix fell back to the directory name. The cheme test passed only because `cheme-solver-x` starts with `cheme-`. Fixtures now write compact JSON, and the test also asserts the id does not start with `cheme-solver-`.
4. Speed: the suite went from 115s to 50s. One module-scoped no-db run (`first_run`) feeds the read-only tests. Its results are captured before the probe `bd create`, so test order does not matter. The env-file and make-install tests use `bare_world`, a parent with no beads repo. New tests cover a broken sibling (reported, the rest still built), config.yaml restored when bd init fails, and an invalid majority prefix being skipped. make verify on the merged result: 668 passed.

**Mutation checks** (mutated copies via CLOUD_SETUP_SCRIPT, no stash). Each of these turns the suite red: prefix=basename, the old errexit wrapper, no commit drop, no env-file append, no prefix filter, no guard, no import, no sync.remote sed. Removing the config restore stayed green until I added the bd-init-fails case (it is masked by the commit drop when init succeeds). The old main script fails 7 of 13 tests.

**Not fixed / follow-ups.** (a) The GIT_CONFIG origin-URL blanking is still untested: it needs a bare origin carrying refs/dolt/data. Worth a bead. (b) Cloud-created zimmy beads get `zimmy-life-tracker-*` ids while the laptop makes `Zimmy Life Tracker-*`. Both already coexist in the jsonl, but the owner may want `bd rename-prefix` on the laptop. (c) On a laptop the sibling glob includes iCloud " 2" copies (harmless in cloud). (d) fwm.2's canon could take cloud-setup.sh later, as the orchestrator said.

**Findings:** f-20261014-0226ae, f-20261014-13357d, f-20261014-67056e, plus one more (the config-restore masking lesson).

## Tailrace (2026-10-14)

**LANDED** PR #49 squash-merged as fdf2cecbda23bc38f257aea93089ca85b7343bba (sha-guarded on 064f511a; verify green, https://github.com/ziggyzims1-jpg/water-mill/actions/runs/38573019618).

- No merge conflict. Local main held 4 uncommitted fwm.8 findings in knowledge/findings.jsonl, which blocked `pull --ff-only`; I committed them as-is, then `pull --rebase` (clean).
- `bd close water-mill-fwm.8 --reason "Merged in PR #49"` and `bd close water-mill-fwm.2 --reason "Merged in PR #50 (92b9098)"` both succeeded, no auto-export warning. Sorted compare showed exactly those two lines changed.
- Millstone's first two graph lessons filed (cause pending); the zsh `echo ======` one was skipped as trivia.
- **Findings:** 6 findings reference water-mill-fwm.8 (4 pre-existing from millstone/sluice, 2 from me).
- Remote branches bead/fwm-1, bead/fwm-2, bead/fwm-8 deleted if PRs merged (see report).
