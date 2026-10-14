# Handoff — water-mill-fwm.1

## Millstone (2026-10-14)
- **Where things stand.** Branch bead/fwm-1, PR #48 https://github.com/ziggyzims1-jpg/water-mill/pull/48, head 85e21f1. tests/test_trial.py 73 passed; `make verify` passed (626 passed). Not blocked.
- **What was tried and did not work.** Nothing abandoned. The fresh-start test passes before and after (it pins existing behaviour; only the archived-not-live test is red-before); the PR body says so.
- **Lessons for the graph.** `trial.read_ledger` reads only `knowledge/trial/ledger.jsonl`, so moving a cancelled ledger under `knowledge/trial/archive/` is enough to start a fresh trial with a new seed.
- **Look here first.** `tests/test_trial.py::test_a_trial_with_an_archived_ledger_starts_fresh`.
- **Open questions for the human.** None. The closing note is a `cancelled` line appended inside the archive file, so the archive is no longer byte-identical to the old ledger.
- **Follow-ups worth a bead.** None new. The lander still closes water-mill-166 as cancelled after merge.
