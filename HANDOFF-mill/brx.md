# Handoff — water-mill-brx

## Millstone (2026-10-05)

- **Where things stand:** branch `bead/brx`, PR #26 https://github.com/ziggyzims1-jpg/water-mill/pull/26. `make verify` green (390 passed, ruff clean). Not blocked.
- **Tried / did not work:** first test append was lost because a `sed` earlier in the `&&` chain failed; caught by `git status` and re-applied. A ruff E501 on the `_NONE` regex. Not mutation-tested against the pre-change code beyond the tests exercising new functions that did not exist.
- **Look here first:** `watermill/review.py` `uncovered()` and `check_line`/`_sweep_line`; `watermill/landed.py` `parse()`. Landing date = LAST `## Tailrace (date)` heading; a handoff with **LANDED** but no Tailrace heading is silently ignored (not lag).
- **Open questions:** none. Bare `**Findings:** none` (no reason) does not cover; `--check` output prints sweep line plus lag line. A finding's ref must be the full normalised id (`proj-abc`); bare slugs like `092` do not match.
- **Follow-ups:** the lander (tailrace) should write `**Findings:** none -- why` or a finding when landing; hook/cron running `review --check` is not wired. Real-sibling smoke shows no lag from 2026-09-28 onward (catch-up covered it). 4t3 touches the same Sweep dataclass/`sweep()`/render in review.py; expect a trivial textual merge.

## Sluice (2026-10-05)

- **Verdict: approve_after_fixes.** Scope clean: only `watermill/{landed,review,cli}.py`, `tests/test_review.py`, `docs/KNOWLEDGE.md`, and the module-table row in `CLAUDE.md` (the doc update the repo convention requires). No fenced path. `review` stays CLI-only — nothing in `recall.py`/`mcp.py` reaches `landed`, so the queried-never-loaded/budget doctrine is untouched. Empty factory: `review --check` on a blank root still exits 0 ("nothing recorded to sweep").
- **Fixed, commit 19c55cf (pushed to bead/brx):**
  1. A `**LANDED**` handoff with no `## Tailrace (date)` was dropped by `landed.parse()`. It now has `landed_on=None`, is listed as "landed on an unknown date", is exempt from the `--lag-since` cutoff and always counts in `Sweep.lagging` (so `--check` fails). None exist in either sibling today, so this changes nothing on real data.
  2. **Real bug:** the `_NONE` regex used `\s`, which crosses newlines. A bare `**Findings:** none` followed by a `- bullet` line read the bullet's dash as the separator and counted as covered (and so did `none --` with nothing after it). Now `[ \t]` only, and the reason can't be another dash. The millstone test passed only because the next line in its fixture was `## Tailrace`.
  3. A bare-slug ref (`--task 092`) now covers the bead when the finding's `cell` matches its project (`uncovered()` adds `normalise(f"{cell}-{task}")`). Documented in KNOWLEDGE.md: still cite the full id.
- **Verified:** `make verify` 395 passed (was 390). Mutation-tested `uncovered`, `lagging`, `normalise`, `parse`, `_NONE`, `actionable`, `check_line`. Coverage (cited/waiver), cutoff, normalisation (case/space), missing-checkout, actionable and check-lag mutants were all caught by the original tests. Three survived the original tests (grace `<`→`<=`, `dates[-1]`→`dates[0]`, the `\S` reason guard), so I added tests and each of those mutants now fails. The `if record.cell` guard mutant survives but it is equivalent (an empty cell gives the same normalised id). Real-data smoke against the siblings: `--lag` is empty from 2026-10-05; `--lag-since 2026-09-01` lists 19 (all before the catch-up).
- **Not fixed / for the orchestrator:** (a) the main water-mill checkout's `review --check` already exits 1 with "sweep overdue — last swept never". That has nothing to do with this PR, but whatever hook gets wired to `--check` will fail from day one until someone runs `review --record`. (b) water-mill's own beads (handoffs in `HANDOFF-mill/`, water-mill not in projects.yaml) are never lag-checked, and that includes this bead. Worth a follow-up bead if wanted. (c) gwv's crew text says `--task "<id>"` without saying "full bead id". The slug fallback covers it now, but gwv should still say full id. (d) `--lag` short-circuits before `--record` (combining them skips the record). Minor.
- **Lander:** the local branch `bead/brx` in the main checkout is stale at 68ab84d. The remote is 19c55cf. Expect a conflict with bead/4t3 (checked with `git merge-tree`) in three files, all "both appended here": `review.py` (`render_lag` vs 4t3's new section function, keep both), `tests/test_review.py` (both test blocks appended at the end, keep both), `docs/KNOWLEDGE.md` (4t3 inserts "5. Missing structure" and renumbers "No root cause" to 6. Make "Landed without a finding" **7** and change "six lists" to "seven lists"). `cli.py` auto-merges.

## Tailrace (2026-10-05)

**LANDED** — MERGED, squash commit db482211cb58992423a9837bdc0fdd8ca73c2c49 (PR #26, head 19c55cf).

- Verify: `gh pr checks 26 --watch --fail-fast` green on head 19c55cf (verify, https://github.com/ziggyzims1-jpg/water-mill/actions/runs/37375169843/job/111981891200). PR base was already origin/main (af20bfe); no update-branch needed, no conflict.
- Diff touched CLAUDE.md, docs/KNOWLEDGE.md, tests/test_review.py, watermill/{cli,landed,review}.py; water-mill has no `fence` in a contract and none of these is gate/schema/backup. Nothing fenced.
- `bd close water-mill-brx`: "✓ Closed water-mill-brx — watermill review: 'landed without a finding' lag list, and --check fails on lag: Merged in PR #26" (no auto-export warning).
- **Findings:** deliberately not recorded by tailrace per orchestrator instruction (to be recorded after PR #28 lands, since the `pending` cause is not on main yet). `review --lag` will list water-mill-brx only if water-mill handoffs are swept (sluice noted they are not).
- Main checkout had an unrelated uncommitted modification to `knowledge/findings.jsonl` (not mine, left untouched) and untracked `.DS_Store`.
- Orchestrator to do: record the brx findings after #28 lands; sluice's follow-ups (review --record overdue, water-mill not in lag check, gwv "full bead id" wording).
