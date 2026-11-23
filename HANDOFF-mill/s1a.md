
## Solo (orchestrator session, 2026-11-23)
- State: branch bead/s1a, PR #139 (https://github.com/ziggyzims1-jpg/water-mill/pull/139). Found while landing water-mill-0oj: `make verify` was red on main, on the laptop and in CI. No crew ran.
- Cause: `tests/test_recall.py::test_a_human_finding_outranks_a_mechanical_outcome_at_equal_relevance` built the graph with `recall.build(tmp_path)`, so on today's date; the helper's fixed `observed_at` (2026-08-20) passed `REVIEW_AFTER_DAYS` (90) on 2026-11-18, the finding went stale, a stale finding is weighed down, and the task outranked it.
- Changed: that test passes `TODAY` to `recall.build`, as its neighbours do. The ranking rule is untouched.
- Verified: red on the base commit, green with the change (24 in the file); ruff clean; CI `verify` green.
- Not done: other tests call `recall.build(tmp_path)` with no date; none asserts on rank or staleness today, but nothing stops the next one. A guard (a fixture that refuses a build without a date) would be a bead of its own.
- Findings: f-20261123-16151f4c.

## Lander (orchestrator session, 2026-11-23)
**LANDED** PR #139 squash-merged (sha-guarded on b0858c5), merge commit edd4369 on main. verify green on that head. Bead closed.
