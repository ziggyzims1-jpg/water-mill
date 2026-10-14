# Handoff — water-mill-fwm.1

## Millstone (2026-10-14)
- **Where things stand.** Branch bead/fwm-1, PR #48 https://github.com/ziggyzims1-jpg/water-mill/pull/48, head 85e21f1. tests/test_trial.py 73 passed; `make verify` passed (626 passed). Not blocked.
- **What was tried and did not work.** Nothing abandoned. The fresh-start test passes before and after (it pins existing behaviour; only the archived-not-live test is red-before); the PR body says so.
- **Lessons for the graph.** `trial.read_ledger` reads only `knowledge/trial/ledger.jsonl`, so moving a cancelled ledger under `knowledge/trial/archive/` is enough to start a fresh trial with a new seed.
- **Look here first.** `tests/test_trial.py::test_a_trial_with_an_archived_ledger_starts_fresh`.
- **Open questions for the human.** None. The closing note is a `cancelled` line appended inside the archive file, so the archive is no longer byte-identical to the old ledger.
- **Follow-ups worth a bead.** None new. The lander still closes water-mill-166 as cancelled after merge.

## Sluice (2026-10-14)
- **Verdict: approve_after_fixes.** PR #48 head now 5800e0e (was 85e21f1). Scope matches the bead's in-repo half (archive + closing note, TRIAL.md, tests); ZIM labels (ZIM e9ead49) and closing water-mill-166 are correctly left out. No fenced path touched.
- **Verified.** `make verify` green before and after the fix (626 passed). Nothing but `watermill/trial.py` reads `knowledge/trial/ledger.jsonl` (`ledger_path` / `read_ledger`, plus `cli.py` printing the path); `_read` returns [] for a missing file, so `trial status`/`enroll` work with no live ledger. Mutation: making `read_ledger` also read `archive/*.jsonl` fails `test_a_trial_with_an_archived_ledger_starts_fresh`.
- **Append-only question.** No conflict: the `cancelled` line is an append, no existing line was edited, and TRIAL.md's no-edit-in-place rule binds sections 4-7 only; the §8 one-line edit and the dated amendment are within the rules.
- **Fixed (5800e0e).** (1) The `cancelled` line was stamped `2026-10-14T00:00:00`, before the 11:41 enrolments it closes; now the commit time `13:00:16`. (2) `test_the_cancelled_first_batch_is_archived_not_live` asserted the live ledger does not exist, which would turn the gate red the day the next batch is enrolled; it now asserts the live ledger never carries seed 20261013 or a `cancelled` line, and that the closing line postdates the enrolments. Mutations: restoring T00:00 fails it; copying the archive back to `ledger.jsonl` fails it; a fresh-seed live ledger passes it.
- **Not fixed / for the lander.** A branch cut before this merge that appends to `knowledge/trial/ledger.jsonl` would, via git rename detection, land its lines in the archive file instead; nobody should enrol on an old base. `.gitattributes` still names `knowledge/trial/ledger.jsonl merge=union`, which is right for the next batch. Close water-mill-166 as cancelled after merge. Two findings recorded in the main checkout's `knowledge/findings.jsonl` (uncommitted; tailrace commits it).

## Tailrace (2026-10-14)
**LANDED** water-mill-fwm.1 -- PR #48 squash-merged as f0e7339154c8e1172ffce00a74c48c598504f084 (verified head 5800e0e206243597adfd8e03d555d272f6acf881; `verify` check-run success on that sha, https://github.com/ziggyzims1-jpg/water-mill/actions/runs/38568711276/job/115867938501). No conflict.
- **bd close.** `Closed water-mill-fwm.1 ... Merged in PR #48 (squash f0e7339...)` and `Closed water-mill-166 ... Cancelled per epic water-mill-fwm (first batch archived in PR #48)`; no auto-export warning. Ran `bd import` first (43 issues). `.beads/issues.jsonl` NOT exported or committed: the orchestrator exports and pushes beads to main.
- **Failed.** Deleting branch `bead/fwm-1` was refused by the proxy (HTTP 403 "Write access to this GitHub API path is not permitted"); not retried. The remote branch still exists; delete by hand or ignore.
- **Findings.** Sluice's 2 lessons plus 1 from tailrace (f-20261014-30a10a: stale branches appending to the renamed ledger land in the archive via rename detection), all committed on claude/fwm-orchestrator for the orchestrator to carry to main.
- **By hand.** Orchestrator: export/push beads, carry findings to main.
