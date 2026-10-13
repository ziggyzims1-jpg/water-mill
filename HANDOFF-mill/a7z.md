# Handoff -- water-mill-a7z

## Millstone (2026-10-13)

- **Where things stand:** branch `bead/a7z`, PR #32 (https://github.com/ziggyzims1-jpg/water-mill/pull/32), rebased on origin/main. `make verify` green (425 passed). Not blocked. Bead not closed. Real `--dry-run` sweep (165 new records): hillel-programming 62 read (59 landed), water-mill 4 (3), zim-dashboard-demo-cell-1b 20 (20), zimmy-life-tracker 79 (78). Nothing written to the real `runs/`.
- **What was tried and did not work:** (1) first dry run from the worktree showed every sibling "not found" because registry paths are relative to the factory root and the worktree sits in the scratchpad; use `--root <main checkout>`. (2) `landed.py`'s `_LANDED` marker only matches a bare `**LANDED**` line, so 51 of 79 zimmy notes read as unlanded; Tailrace also wrote `**LANDED.** ...`. crewlog.py uses its own looser `^\s*(- )?\*\*LANDED\b`.
- **Deviation from the bead:** "append only unseen keys" became "append when content differs from the latest line for the key" (`agentlog.unseen`), otherwise a bead recorded as unlanded could never be updated when it lands. Second sweep still appends 0.
- **Schema decision:** common envelope + kind-specific `detail` object (documented in `watermill/agentlog.py` docstring and docs/OBSERVABILITY.md) so 61r's non-mill records share the top-level fields. `read()` folds to latest line per key.
- **Lessons for the graph:** `watermill/landed.py` undercounts landed beads because its marker misses `**LANDED.**`; `review`'s lag list is probably affected. Registry project paths resolve against the factory root, so run readers with `--root` from a worktree.
- **Look here first:** `watermill/crewlog.py::parse_record`; `agentlog.unseen`.
- **Open questions for the human:** should `landed.py` adopt the looser marker (changes `review` output)? `sluice_pushed_fixes` is a keyword heuristic (`pushed` / approve_after_fixes in Sluice sections), flagged inferred; it can over-report when a note says "nothing pushed".
- **Follow-ups worth a bead:** loosen landed.py marker; cost/duration are null for all 165 records (no note states them), so the pu9 comparison will need 61r's transcripts for those; a write-at-landing hook in the crew agent files (out of scope here).

## Sluice (2026-10-13)

- **Verdict: approve_after_fixes.** PR #32, fix commit `e9d89bd` pushed to `bead/a7z` on top of `e10e356`. `make verify` green in my worktree (437 passed).
- **Scope:** files match the bead (agentlog.py, crewlog.py, cli.py flags only, tests, OBSERVABILITY.md) plus two CLAUDE.md module-table rows (repo convention; fine). No sibling repo touched; landed.py untouched. Real dry run writes nothing (`runs/agents.jsonl` still absent).
- **Millstone's flagged points:** (1) idempotence deviation is justified: "only unseen keys" would freeze an unlanded bead forever; `agentlog.read()` folds to the latest line per key, so stats never double-count; `read_all()` is the only unfolded view and is named as such. `detail.handoff` is a resolved absolute path, so re-sweeps under a different `--root` spelling don't churn. (2) crewlog `_LANDED` is anchored at line start; checked every one of 157 real loose matches by eye — all genuine `**LANDED.**` lines; added tests that "Not **LANDED** yet", "will be **LANDED**" and a backticked mention stay unlanded. (3) `detail.sluice_pushed_fixes` and `detail.sluice_verdict` are in `fields_inferred`. (4) schema in both docstring and OBSERVABILITY.md; cost/duration null on all 166 real records. (5) `factory_root()` defaults to the package's own checkout, so from the main checkout no `--root` is needed; from a worktree it is.
- **Found and fixed (`e9d89bd`, crewlog.py):** `sluice_pushed_fixes` keyword match read "nothing pushed"/"no fixes pushed" as a push — 18/18 real `approve` verdicts came out pushed=true. Now verdict-first (`_pushed_fixes`: approve_after_fixes→true, approve→false, negation-guarded prose otherwise). `_VERDICT` captured "still" from `**Verdict still approve_after_fixes` and missed `### Verdict: x`; now matches the fixed vocabulary. Titles like `# Handoff — Millstone, Zimmy Life Tracker-9i7.1` keyed as `millstone-zimmy-life-tracker-9i7.1` (2 zimmy notes); `_known_bead` resolves to the JSONL id. Mutation-tested each fix (each mutation fails a test; one survivor closed by adding an implementer-pushed case).
- **Not fixed:** landed.py has the same role-prefixed-title flaw and the strict marker (bead 9uc covers the marker; add the title to it). `ended_at` mixes a full timestamp (closed_at) with a bare date (landed_at fallback) — documented as "date/time", acceptable for v1. zimmy-8lm has no row in the JSONL, so its title is null (correct).
- **BLOCKED:** `watermill remember` (three lessons: verdict-first parsing, role-prefixed titles, test parsers against real notes) was denied by the auto-mode classifier ("Modify Shared Resources"); not retried. Orchestrator should record them.
- **Lander:** CLAUDE.md module table rows may conflict with concurrent landings; dry-run counts now hillel 62 (59 landed), water-mill 5 (3), zim-dashboard 20 (20), zimmy 79 (78).

## Tailrace (2026-10-13)

**LANDED** — PR #32 squash-merged, merge commit 5bc7fd88ce4ce9a5063d119ccaa62875e4bfa620. verify green (37s), no conflict, rebase not needed.

- `bd close water-mill-a7z`: "Closed water-mill-a7z ... Merged in PR #32"; no auto-export warning. Ran `bd export -o .beads/issues.jsonl` (1 line changed), committed with this note.
- **Findings:** recorded the three lessons Sluice could not (verdict-first sluice_pushed_fixes; role-prefixed titles resolved via .beads/issues.jsonl, incl. landed.py/9uc; test parsers on real notes), each --cause pending --task water-mill-a7z, in knowledge/findings.jsonl. `remember` was not denied this time. It printed "Not mechanised" nudges only.
- Failed/none. Hand-off for humans: judge the three `pending` causes; fix landed.py title flaw under 9uc.
