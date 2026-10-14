# Handoff — water-mill-kt6

**LANDED**

## Millstone (2026-10-14)

- **Where things stand:** branch bead/kt6, PR #44 (https://github.com/ziggyzims1-jpg/water-mill/pull/44). `make verify` green (610 passed, ruff clean). Not blocked. Done: TRIAL.md s6 harm-stop rule (dated 2026-10-14) + s8 step; `trial.pause/resume/pause_state` (ledger `pause`/`resume` lines, latest wins); `trial.start` refuses while paused; `status` dict has `paused`, `render_status` prints a PAUSED line first; CLI `trial pause|resume --reason` (reason required, missing = exit 2). Tests at end of tests/test_trial.py.
- **Tried, did not work:** nothing abandoned. `make verify` first failed only for lack of `.venv` (needed `make install` in the worktree) and one E501 in the CLI help string.
- **Lessons:** water-mill's per-bead handoffs live in `HANDOFF-mill/<slug>.md`, not `brain/handoffs/mill/`. Pause/resume lines have no `bead`, so `enrolled/started/ledger_problems` ignore them without changes.
- **Look here first:** `watermill/trial.py` `pause_state` and `start`.
- **Open questions:** pause only blocks `start`; `enroll` and `brief` are NOT blocked while paused (bead said start only). Say if enroll should refuse too. Also pause/resume are not guarded against a merge=union race producing two pauses (harmless: latest wins).
- **Follow-ups:** none required; the actual trigger judgement stays a human step (no automation detects a landed blocker).

## Sluice (2026-10-14)

- **Verdict: approve_after_fixes.** Fix commit 5a9e087 is on bead/kt6. `make verify` is green in my worktree (612 passed). Scope is fine: the diff touches only docs/TRIAL.md, watermill/trial.py, watermill/cli.py, tests/test_trial.py and the millstone run record. No fenced path.
- **Mutation tests (run with a patch file, no stash).** Millstone's two tests fail when I remove start's pause check, ignore resume lines, drop the PAUSED render line, drop the double-pause guard or drop the `paused` status key. They hold. My two new tests fail on millstone's trial.py.
- **Found and fixed:**
  1. In `pause_state`, the latest line in file order won. Under merge=union, a resume written on a stale checkout could land after a newer pause and quietly unpause the trial. Now `resume` writes `resumes: [pause at-stamps]`, and `_open_pauses` clears only the pauses a resume names, so merge order no longer matters. A pause whose stamp is already in the ledger is refused.
  2. Open question: `enroll` (non-dry-run) now refuses while the trial is paused, through `_refuse_if_paused`. The bead says "the trial pauses", and enrolling writes randomisation lines and `trial:A/B` labels that invite more work. `brief` stays allowed: it is read-only and its first step is `trial start`, which refuses. Dry-run enroll, collect, score and status stay open, so beads already in their window keep being observed.
  3. TRIAL.md now cites the "section 4 rubric". Section 7 is the scoring procedure, not the rubric. TRIAL.md also now says the resume/stop decision rests on the triggering defect and how it was handled, never on status counts, rates or intervals. Without that line the stop could be read as outcome-driven.
- **Checked, no change needed:** pause and resume lines carry no `bead`, so `ledger_problems`, `enrolled` and `started` ignore them. A test asserts that `ledger_problems` is empty for all three merge orders.
- **Not fixed, follow-up worth a bead:** nothing stops a trial session (arm B) from running `watermill trial resume` itself. Changing arm B's brief is out of scope. Also, no automation detects the trigger; that judgement stays with a human.
- **Findings recorded:** f-20261014-b8e052 (union-order state), f-20261014-6e9f0e (pause must block enroll).
- **Lander:** PR #44 has two commits from the crew plus my sluice run record. No doc-table conflicts expected.

## Tailrace (2026-10-14)

**LANDED** PR #44 MERGED, squash sha 9276ea4216aab49edb6c04e43e5921f1bbc1c2d0 (sha-guarded on head 8cc7599). CI `verify` green. No conflicts.
- `bd close`: "Closed water-mill-kt6 ... Merged in PR #44", no auto-export warning.
- Follow-up bead filed: water-mill-mnn (arm B brief must forbid trial pause/resume; consider harness guard; harm-trigger detection stays a human judgement).
- **Findings:** sluice's f-20261014-b8e052 and f-20261014-6e9f0e plus two new lessons (handoff path/make install; mnn) pushed to knowledge/findings.jsonl. `review --lag`: no landed bead is waiting on a finding.
- Human must do: nothing.
