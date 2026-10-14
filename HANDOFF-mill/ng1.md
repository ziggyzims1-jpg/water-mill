# Handoff -- water-mill-ng1

## Millstone (2026-10-05)

- **Where things stand:** branch bead/ng1, PR #30 (https://github.com/ziggyzims1-jpg/water-mill/pull/30). make verify green (411 passed). 68 annotation lines appended to knowledge/findings.jsonl (0 deletions); Missing structure 103 -> 85; 16 if the owner applies knowledge/backfill/2026-10-human-suggested.jsonl. Not blocked.
- **What was tried and did not work:** make verify first failed on the missing .venv (worktree needs `make install`); the first verify run exceeded the 600s tool timeout and was moved to background. A network error interrupted the session mid-run; the worktree was intact. gen script's first run missed one id (527810) and BSD sed -i refused my edit; fixed in python.
- **Lessons for the graph:** most old lessons fit no non-human cause bucket, so the human-only buckets dominate the suggestions; one finding (f-20260925-fe41bc) has cause `clock`, not in ROOT_CAUSES.
- **Look here first:** knowledge/backfill/2026-10-human-suggested.jsonl and the PR body's tables.
- **Open questions for the human:** confirm/change the 69 suggested + 11 orchestrator-drafted causes; give causes for the 17 unsure findings; fix fe41bc's `clock` cause. Destinations marked `gate` for zimmy findings cite tests on zimmy origin/main I checked by grep only.
- **Follow-ups worth a bead:** annotate-finding could validate that a cause is in ROOT_CAUSES (fe41bc slipped through).

## Sluice (2026-10-05)

- **Verdict: approve_after_fixes** (pushed fb3b07d to bead/ng1; CI `verify` green on that head). Owner merges.
- **Verified:** findings.jsonl diff vs main is pure additions (main is an exact prefix), and all 68 added annotation lines match `2026-10-applied.jsonl` row for row (cause->root_cause), before and after my edit. No HUMAN_ONLY cause applied. Tags: every tag reuses main's vocabulary; sampled all 63 tag sets, none wrong enough to strip. `review` Missing structure was 85 on the PR head as claimed. Suggestions file applied on a temp copy via `annotate-finding --batch ... --json`: 80 rows, all ids exist, rc 0. `recall` still works.
- **Found and fixed:** 13 of the 14 `missing-context` causes were guesses -- the text records a codebase fact or a shipped bug and never says a brief lacked it (the PR's own stated rule). Dropped the cause (tags kept) from both the batch file and the annotation lines for ddc0f2, f421cd, fd3817, ae66d6, e4859a, e1ec72, 1ab61c, 7424fc, 60b57a, 7ed4de, c7eafc, 004068, 420ad3. Kept 73ca13 (brief lacked the table name) and the 3 `vague-goal` (077f00, 176ded, 46c355 -- mock vs prose / no owner ranking). Missing structure after merge is now 98; 29 after the suggestions.
- **Gates:** all 8 cited tests exist and pin the lesson (water-mill read locally; zimmy test_today_modes.py CreatedAt/CompletedAtLocalDateTest incl. the portable `..._on_any_platform` companions citing d12b5d, and test_analytics_trend.py, on origin/main). The PR body cited the wrong test for c66c69 (test_the_line_cap_covers_annotations is the single-row writer); corrected to tests/test_cli_recall.py::test_annotate_finding_batch_checks_the_line_cap_before_writing. Did not mutation-test the zimmy gates (read only).
- **PR body updated:** counts, the 13 moved to the unsure list with reasons, fe41bc fix command (`annotate-finding f-20260925-fe41bc --cause gate-hole`, owner to confirm), new before/after numbers.
- **Not fixed / follow-ups:** `review` does not flag an out-of-vocabulary cause (fe41bc's `clock` is invisible to Missing structure) and annotate-finding does not validate against ROOT_CAUSES on old lines -- worth a bead. The 69 suggested human causes I did not judge; that is the owner's job.
- **Lander/owner:** my finding (cause pending) is uncommitted in the main checkout's findings.jsonl; `merge=union` keeps both appends. Local `make verify` result noted in the report.
