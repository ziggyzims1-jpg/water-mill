# Handoff -- water-mill-pu9

## Millstone (2026-10-13)

**Where things stand.** Branch `bead/pu9`, PR #35 https://github.com/ziggyzims1-jpg/water-mill/pull/35. `make verify` green (509 passed, ruff clean). Not blocked. New: `watermill/stats.py`, `watermill/agentcompare.py`, `agents compare` flags in `watermill/cli.py` (`cmd_agents` dispatches to `_compare`), `tests/test_stats.py`, `tests/test_agentcompare.py`, an appended self-contained section at the end of `docs/OBSERVABILITY.md`.

**What was tried and did not work.**
- First-pass approval rate is, under the exclude-inferred rule, nearly unusable: `detail.sluice_pushed_fixes` is always in `fields_inferred` when there was a Sluice section, so 162 of 163 landed crew beads are excluded by default (n=1). I kept the rule (default exclude) and added `--include-inferred` rather than silently bypass it.
- A guessed Fisher reference number in a test failed (I had not computed it); replaced with the real scipy value. Reference numbers must be produced, not recalled.
- First draft printed per-bead rows against groups with no handoff records (always "n=0"); now collapsed to one "skipped" line.
- scipy/statsmodels are not in the repo venv; references came from a throwaway venv in the scratchpad (scipy 1.18.1, statsmodels 0.15.0), nothing added to requirements.

**Lessons for the graph.**
- `agentlog.read()` of a fresh factory root is empty unless swept; the real `runs/agents.jsonl` does not exist in the main checkout yet, so a compare run needs `agents sweep` first (I swept into a scratch root with symlinked sibling checkouts, because projects.yaml paths are relative to the root).
- Only crew work has `source=handoff` records, so every per-bead comparison against non-crew groups is structurally empty.
- Crew-vs-session per-run medians are not like-for-like in scale (a session is a whole conversation, a crew run one dispatch).
- BSD sed on macOS rejects `sed -i 's///'` without a suffix argument; use python for edits.

**Look here first.** `agentcompare.compare_metric` (the min-n gate and exclusion counting) and `stats.median_ci` (order-statistic interval; ranks pinned to the sign-test table).

**Open questions for the human.**
- Is excluding inferred values for first-pass approval right, given it leaves nothing? Alternative: treat `sluice_pushed_fixes` as acceptable-inferred for this one metric.
- Median CI is order-statistic (conservative, 96-99% actual coverage) rather than bootstrap; the bead said "bootstrap" only for the difference.
- Fisher is used for every 2x2, not only small cells (it is exact and cheap).

**Follow-ups worth a bead.** (1) cost_usd is null for all 158 crew runs and non-null only for sessions, so cost can never be compared crew-vs-X until crew cost is derived from model + tokens (pricing table). (2) `tokens_total` excludes cache; a cache-inclusive comparison may tell a different story.

## compare output on real data (temp sweep, real runs/ untouched; 347 records: 168 handoff, 158 crew transcript, 15 sessions, 6 non-crew subagents)

```
watermill agents compare
  records read: 347 (latest line per key); min n per group: 8; inferred and null values excluded per metric
  per-run metrics use source=transcript records, per-bead metrics use source=handoff records; the two are never mixed.

=== A: crew (mill-crew)   vs   B: non-crew subagents (subagent:*) ===
  -- per run (source=transcript) --
  duration_seconds
      A  n=158  median 344  95% CI 270..418   [158 records; excluded: 0 null, 0 inferred]
      B  n=6    median 138  95% CI 3.96..907   [6 records; excluded: 0 null, 0 inferred]
      too few to say: n = 158 vs 6, need at least 8 in each group
  tokens_total
      A  n=158  median 1,284  95% CI 1,104..1,918   [158 records; excluded: 0 null, 0 inferred]
      B  n=6    median 3,648  95% CI 216..41,426   [6 records; excluded: 0 null, 0 inferred]
      too few to say: n = 158 vs 6, need at least 8 in each group
  tool_call_count
      A  n=158  median 20  95% CI 17..25   [158 records; excluded: 0 null, 0 inferred]
      B  n=6    median 16  95% CI 0..54   [6 records; excluded: 0 null, 0 inferred]
      too few to say: n = 158 vs 6, need at least 8 in each group
  cost_usd
      A  n=0    no usable values   [158 records; excluded: 158 null, 0 inferred]
      B  n=0    no usable values   [6 records; excluded: 6 null, 0 inferred]
      too few to say: n = 0 vs 0, need at least 8 in each group
  -- per bead (source=handoff): skipped -- no handoff records for group B (only mill-crew work has them) --

=== A: crew (mill-crew)   vs   B: sessions ===
  -- per run (source=transcript) --
  duration_seconds
      A  n=158  median 344  95% CI 270..418   [158 records; excluded: 0 null, 0 inferred]
      B  n=0    no usable values   [15 records; excluded: 15 null, 0 inferred]
      too few to say: n = 158 vs 0, need at least 8 in each group
  tokens_total
      A  n=158  median 1,284  95% CI 1,104..1,918   [158 records; excluded: 0 null, 0 inferred]
      B  n=15   median 38,481  95% CI 2,055..85,790   [15 records; excluded: 0 null, 0 inferred]
      A-B -37,197  95% CI -84,441..-1,644  (median A - median B (seeded percentile bootstrap))
      p = 0.000317  (Mann-Whitney U, n = 158 vs 15)
  tool_call_count
      A  n=158  median 20  95% CI 17..25   [158 records; excluded: 0 null, 0 inferred]
      B  n=15   median 41  95% CI 6..79   [15 records; excluded: 0 null, 0 inferred]
      A-B -21  95% CI -55.5..14  (median A - median B (seeded percentile bootstrap))
      p = 0.468  (Mann-Whitney U, n = 158 vs 15)
  cost_usd
      A  n=0    no usable values   [158 records; excluded: 158 null, 0 inferred]
      B  n=14   median $13.99  95% CI $0.28..$45.34   [15 records; excluded: 1 null, 0 inferred]
      too few to say: n = 0 vs 14, need at least 8 in each group
  -- per bead (source=handoff): skipped -- no handoff records for group B (only mill-crew work has them) --

--- crew:sluice vs crew:millstone ---
watermill agents compare
  records read: 347 (latest line per key); min n per group: 8; inferred and null values excluded per metric
  per-run metrics use source=transcript records, per-bead metrics use source=handoff records; the two are never mixed.

=== A: crew:sluice   vs   B: crew:millstone ===
  -- per run (source=transcript) --
  duration_seconds
      A  n=56   median 417  95% CI 345..581   [56 records; excluded: 0 null, 0 inferred]
      B  n=55   median 487  95% CI 269..597   [55 records; excluded: 0 null, 0 inferred]
      A-B -69.49  95% CI -199..136  (median A - median B (seeded percentile bootstrap))
      p = 0.5533  (Mann-Whitney U, n = 56 vs 55)
  tokens_total
      A  n=56   median 1,554  95% CI 1,085..2,119   [56 records; excluded: 0 null, 0 inferred]
      B  n=55   median 1,819  95% CI 1,111..2,973   [55 records; excluded: 0 null, 0 inferred]
      A-B -265  95% CI -1,446..731  (median A - median B (seeded percentile bootstrap))
      p = 0.7546  (Mann-Whitney U, n = 56 vs 55)
  tool_call_count
      A  n=56   median 29  95% CI 22..37   [56 records; excluded: 0 null, 0 inferred]
      B  n=55   median 31  95% CI 21..47   [55 records; excluded: 0 null, 0 inferred]
      A-B -2  95% CI -20..7  (median A - median B (seeded percentile bootstrap))
      p = 0.4088  (Mann-Whitney U, n = 56 vs 55)
  cost_usd
      A  n=0    no usable values   [56 records; excluded: 56 null, 0 inferred]
      B  n=0    no usable values   [55 records; excluded: 55 null, 0 inferred]
      too few to say: n = 0 vs 0, need at least 8 in each group
  -- per bead (source=handoff): skipped -- no handoff records for group A and B (only mill-crew work has them) --
```

## Sluice (2026-10-13)

**Verdict: approve_after_fixes.** PR #35, fix commit `238d1af` pushed on top of `a213f10`. `make verify` green (514 passed); merges cleanly into current origin/main (merge-tree); no CI checks register on this repo.

**Statistics verified independently** (throwaway venv in the scratchpad, scipy 1.18.1 / statsmodels 0.15.0, nothing added to requirements): 400 random cases each, max abs error vs reference ~3e-16 for `stats.wilson` (proportion_confint wilson), `stats.newcombe_diff` (confint_proportions_2indep newcomb), `stats.fisher_exact` (scipy two-sided), `stats.mann_whitney` U and p (mannwhitneyu two-sided, asymptotic, use_continuity=True), tied integer and continuous data. `stats.median_ci` ranks are the narrowest with coverage >= 95% for every n in 6..159; actual coverage 95.0-99.2% (median ~98% below n=20, ~96% at 60-160, ~95.7% beyond), empirical 96.2% on lognormal n=15. The "usually 96-99%" claim was wrong at large n; corrected in `stats.py` and docs. Bootstrap percentile indexing is symmetric and agrees with scipy.stats.bootstrap(percentile) on the test data.

**Mutation tests (21, all killed after fixes):** continuity sign flip, drop continuity, drop tie correction, one-sided p, signed z, Newcombe arms swapped, Wilson term dropped, Fisher strict `<`, median CI one tail, bootstrap quantile, bootstrap y not resampled, DEFAULT_MIN_N 8->5, min-n `or`, source filter removed, each scope leak direction, any-verdict admission, admission despite other inferred fields, caveat dropped, rounds-0-as-failure. **Survived on the original branch:** an unseeded bootstrap RNG (integer data gave identical percentiles), and transcript records leaking into per-bead metrics (the old test's runs had null outcomes, so they were silently counted as excluded_null).

**Fixed in `238d1af`:** (1) orchestrator decision 1 -- `Metric.admit`/`admit_fields`, `_verdict_derived`: first-pass admits `sluice_pushed_fixes` only when `sluice_verdict` is exactly approve/approve_after_fixes and no other inferred field is hit; count printed (also under the "skipped" per-bead line); other metrics unchanged. (2) `_first_pass`: 0 Sluice rounds -> null, not a failure (that was millstone's lone n=1). (3) decision 2 -- `SESSION_CAVEAT` line above any comparison with a `session` side, plus `caveat` in JSON. (4) decision 3 -- `test_handoff_and_transcript_records_never_cross_scopes`. (5) `test_bootstrap_is_pinned_for_a_seed`. (6) "keep rate" removed from the new text (pre-existing OBSERVABILITY lines about the real keep rate untouched).

**Checked, fine:** min-n default 8 everywhere (`DEFAULT_MIN_N`, CLI default); every printed p carries "n = A vs B"; real `runs/` holds no agents.jsonl (mtime Aug 27) -- my sweep went to `scratchpad/realroot/wm`.

**Real data after fixes** (351 records): crew vs subagent: all too few (n=160 vs 6). crew vs session: tokens p=0.000103 (n=160 vs 16), tool calls p=0.3229 (n=160 vs 16), duration/cost too few. sluice vs millstone: duration p=0.547, tokens p=0.8843, tool calls p=0.4235 (n=56 vs 56). First-pass (crew handoffs): n=162 admitted via verdict, 0 prose-excluded, 1 null; 18/162 = 11% (Wilson 7.1-16.9%). Landed 163/169.

**Not fixed / follow-ups:** per-bead metrics can never be compared crew-vs-anything (only crew has handoff records) -- by design, worth noting to the owner; crew cost null (water-mill-cdi already filed). `sluice_verdict` itself is regex-parsed, so admission trusts crewlog's `_VERDICT`.

**Lander:** no conflicts expected; OBSERVABILITY section is appended at the end of the file.

## Tailrace (2026-10-13)

**LANDED** -- MERGED, PR #35, squash commit `1d38db9e04410f5e3245a87f55007bc98b07d1a1`. Retry after an earlier BLOCKED attempt (the classifier denied a chained `gh pr merge ... && pull && bd close` as "[CI Bypass]"); `gh pr checks 35` was green (verify pass, https://github.com/ziggyzims1-jpg/water-mill/actions/runs/38428562222/job/115404360657) and the merge, run as its own command, went through. No conflicts.

`bd close`: "Closed water-mill-pu9 ... : Merged in PR #35"; `bd export` wrote 16 issues, no auto-export warning. Committed .beads/issues.jsonl, sluice's 3 findings and this note's tailrace-added finding.

**Findings:** one lesson recorded (chained merge denied as CI Bypass; run merge standalone), plus sluice's 3.
