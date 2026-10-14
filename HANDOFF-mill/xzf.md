
## Millstone (2026-10-14)
- State: branch bead/xzf, PR #47 (https://github.com/ziggyzims1-jpg/water-mill/pull/47). make verify green (623 passed). Not blocked; tailrace.md is not fenced in water-mill (no contract fence).
- Changed: watermill/trial.py arm B laptop close (import between pull and export, plus diff-only-this-bead check); .claude/agents/tailrace.md step 4 same; two tests in tests/test_trial.py. Arm A has no own export step (delegates to tailrace); millstone/sluice have no export; cloud tailrace already imports.
- Failed/abandoned: nothing. Did not run the test red-without-fix, nor recall/agents record (skipped for brevity).
- Follow-up: orchestrator must sync tailrace.md to the other repos' crew copies after landing; `watermill validate` drift flags them until then. The cloud tailrace export (step 3, tailrace.md l.46) has no diff-only-this-bead check; worth a bead.

## Sluice (2026-10-14)
- **Verdict: approve_after_fixes.** Fix commit a6b2d8e on bead/xzf. make verify green (624 passed).
- **Real failure reproduced** in a scratch bare-remote + two-clone beads repo (bd 1.2.2): old sequence (close, pull --ff-only, export) reverted the other session's closure and dropped its new bead; new sequence (import between pull and export) kept both, and the diff touched only the closed bead. `bd import` is newer-updated_at-wins, so the local close survives the import ("1 stale skipped"). Closing a bead with dependents changes only its own line.
- **Found and fixed: the PR's `git diff` check false-positives in beads-sync repos** (cheme-solver, Hillel-Programming). `scripts/beads_merge.py` appends new ids at the end of main's file; `bd export` writes its own order; so after a normal close `git diff` shows the moved lines and the check would stop every landing. Replaced with a sorted compare `diff <(git show HEAD:.beads/issues.jsonl | sort) <(sort .beads/issues.jsonl)` in `watermill/trial.py` (arm B laptop close) and tailrace.md step 4. Verified in the scratch repo: plain diff 4 lines, sorted diff only this bead's 2.
- **Added in scope: cloud tailrace export (after-merge step 3)** now carries the same sorted check (one sentence), with test `test_tailrace_cloud_export_checks_only_this_bead_changed`.
- **Mutation:** with the PR's change reverted both new tests fail. Gap found: deleting the diff check from tailrace step 4 left `test_tailrace_close_imports_between_pull_and_export` green; tightened it (and the brief test) to assert check after export and before the chore(beads) commit; all three check deletions now fail a test.
- **Process lapse (millstone):** skipped `watermill recall` and `agents record`, and did not prove the tests red without the change. Not redone.
- **Not fixed / concerns:** the check still fires (correctly) when this checkout's db holds another session's uncommitted claim (f-20261013-f47c19); the reporter must then restore the foreign lines by hand. Arm A has no own export (delegates to tailrace). Crew copies of tailrace.md in other repos drift until the orchestrator syncs them.
- **Findings:** f-20261014-2047d7 (sorted compare, not git diff), f-20261014-2132e9 (step tests must assert position).

## Tailrace (2026-10-14)
**LANDED** PR #47 squash-merged (sha-guarded on 8c974e9), merge commit f1b4b81 on main. verify green (https://github.com/ziggyzims1-jpg/water-mill/actions/runs/38561913872). No conflicts.
- Used the NEW close sequence: bd close -> pull --ff-only (already up to date) -> bd import ("Imported 34 issues, 1 stale skipped") -> bd export (35) -> sorted diff showed only water-mill-xzf's line changed. 
- bd close: "Closed water-mill-xzf ... Merged in PR #47", no auto-export warning.
- Main checkout had uncommitted sluice findings in knowledge/findings.jsonl; committed with mine.
- Findings: f-20261014-2047d7, f-20261014-2132e9 (sluice) plus one tailrace lesson. Millstone had no "Lessons for the graph" section.
- Not done (by instruction): crew-copy sync of tailrace.md to other repos (orchestrator). Open follow-up: none new.
