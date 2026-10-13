# The crew-vs-default-Claude trial (water-mill-166, harness water-mill-d20)

Question: **does the mill crew (millstone -> sluice -> tailrace) land beads with
fewer escaped defects than one default Claude given the same bead?** Nothing
else here is the point; cost and speed are what we pay for the answer.

This file is the protocol and the **pre-registered analysis plan**. It was
written before any bead was enrolled and is fixed at the commit that adds it.
A later change to sections 4-7 is a dated amendment at the bottom, made before
the data it affects is looked at, never an edit in place.

## 1. Arms

| | Arm A (crew) | Arm B (solo) |
|---|---|---|
| Session | one top-level orchestrator session | one top-level general-purpose Claude session |
| Work | runs millstone, then sluice, then tailrace as subagents | implements, runs the gate, opens the PR |
| Ends | PR merged by tailrace after sluice approves and CI is green, bead closed | PR open and CI reported; **not merged** |
| Merge | tailrace (inside the session) | the owner, or a tailrace run outside the session |

Same for both: the bead text, the repo's gate (`make verify`), the repo's
fence, "implement, test, open a PR", the knowledge steps (recall at the start,
`watermill remember` with `--tag trial:A|B` at sign-off, a handoff), and the
merge rule (CI green, then a merge by tailrace or the owner).

**Known asymmetry, stated up front.** Arm A's session includes landing and the
bead close; arm B's does not. That makes A's measured cost and duration a
little *higher* than B's for the same work, so it works against the crew
claim, not for it. Landing is small next to implementation and review, but we
do not correct for it.

**One trial bead per top-level session.** The session's `cost-state` line is
cumulative per session, so a session that ran two beads cannot be split.
`trial start` refuses a second bead in a session.

## 2. Eligibility

A bead is eligible when all of these hold (`trial.eligibility`):

- its repo is registered in `projects.yaml`, enabled, and checked out here;
- it is not an epic and its status is `open`;
- it is not labelled `hand-only` (the owner's mark for work done by hand);
- it names no path from the repo's `fence.paths` (outside its *Out of scope*
  section), unless it carries the label `fence-directed` (the bead itself
  directs the fenced change). Mentioning `CLAUDE.md` counts: a bead that
  needs a root-doc update is excluded rather than judged;
- it is not already in the ledger.

The rules do not look at the bead's content beyond that, so they cannot
select easy beads for one arm. Ineligible beads are listed with the reason.
Water-mill's own beads are not in the trial (the factory is not a registered
project of itself).

## 3. Randomisation

`watermill trial enroll <repo> <bead>... | --ready [--dry-run] [--seed N]`

- **Stratified by repo, balanced blocks of four.** Each block of four
  consecutive enrolments in a repo holds exactly two A and two B, in an order
  shuffled by `random.Random(f"{seed}:{repo}:{block}")`. A repo's tail block
  may be partial; imbalance is at most two.
- **Seeded and logged.** One master seed per trial, drawn once, stored as the
  first ledger line, copied onto every enrol line with its block and position.
  `--seed` is accepted only while the ledger has none; a different seed later
  is refused.
- **Order cannot steer the draw.** Beads in one call are sorted by id before
  assignment, so the order they were typed in changes nothing.
- **No re-randomising.** A bead that is in the ledger is refused; there is no
  command to remove or re-draw one. The ledger is opened for append only.
- **Recorded before work starts**, in the ledger and as the bead label
  `trial:A` / `trial:B`.
- A dry run (`--dry-run`) writes nothing and, given the same `--seed`, shows
  exactly what the real run will assign.

Honest limit: the assignment is a deterministic function of the seed and the
enrolment sequence, so anyone who knows the seed *and* the sequence can predict
a bead's arm before enrolling it. The owner decides which beads to enrol; do
not enrol a bead because of the arm it would get. The dry run shows that
arm, which is why the owner reviews it with the beads fixed, not chosen.

## 4. Primary outcome (confirmatory)

**Escaped defects of severity bug or worse, per bead, within 14 days of
landing.**

- *Escape* and *severity* are the baseline's: a defect in the landed work found
  after landing and within 14 days (a bug bead traced to it, a revert of its
  PR, or a fix commit naming it). Severities: **blocker, bug, test-gap,
  quality**; "bug or worse" is blocker or bug. The rubric and every scoring
  decision are in `knowledge/baselines/2026-10-13-catches-escapes/README.md`
  and are reproduced in the scorer prompt (`trial.RUBRIC`).
- **Statistic.** The comparison is of the **proportion of beads with at least
  one bug-or-worse escape**, arm A against arm B, by two-sided **Fisher's
  exact test**, alpha 0.05. The per-bead count is reported alongside
  (descriptively; escapes cluster, so a count test would be misleading).
- **Population.** Enrolled beads that **landed** and whose 14 days have
  passed (scored). Beads that never landed have no escape window; they are
  counted in the landed rate (section 5) and in the sensitivity analysis below.
- **Sensitivity (reported, not confirmatory).** Treat every enrolled bead that
  did not land within 30 days of enrolment as a failure and repeat the test.
- **Effect and interval.** Report the two proportions with Wilson 95% intervals
  and their difference with Newcombe's interval (`stats.newcombe_diff`).
- **Size.** About 60 landed, scored beads per arm gives ~80% power to tell a
  30% escape rate from a 10% one; the baseline escape rate for the crew is
  9.3% (Wilson 5.9-14.4%) over 183 beads, so a default Claude doing *better*
  than that is unlikely and the test is two-sided anyway.

## 5. Secondary outcomes (exploratory, no multiplicity correction)

Each is reported with its p-value and says so: there are four of them and no
correction is applied, so none is a finding on its own.

- **`cost_usd_est`**: the session's final `cost-state` `totalCostUSD`
  (an API-equivalent estimate at list prices, not a bill). Mann-Whitney U on
  per-bead values, with medians; the final report adds
  `stats.bootstrap_median_diff` (seeded) for the difference. Only rows with `cost_basis` `cost-state` or `manual` enter (see
  section 8).
- **Duration**: session first-to-last timestamp, wall seconds. Mann-Whitney.
- **First-push CI green**: the earliest commit of the PR that has any
  check-run, all of whose runs completed green. Fisher's exact test.
- **Landed rate**: the PR merged. Fisher's exact test.
- **Owner corrections** (commits on the PR without a `Co-Authored-By: Claude`
  trailer, merges excluded) are recorded and reported descriptively, not tested.

## 6. Looks, stopping, and what `status` prints

- **Interim at 30 scored beads per arm; final at 60 per arm.** `trial status`
  names the stage (`pre-interim`, `interim`, `final`).
- **No early stopping on p-values.** The trial runs to 60 per arm whatever the
  interim shows. The only reasons to stop early are protocol or safety
  failures (a broken harness, an agent causing harm, the ledger corrupted), and
  they are decided and written down without reference to the outcome data.
- **No p-value is printed before the interim.** Before 30 per arm `status`
  prints counts, rates and Wilson intervals only ("p-value withheld ...");
  below 8 per arm it says "too few to say". This removes the temptation to peek.
- No alpha is spent at the interim: because it can never stop the trial,
  the final test is run at 0.05.
- **Missing data.** A bead with no collectable outcome (session lost, PR never
  found) stays in the ledger and in `status` as "in progress"; it is listed, not
  dropped, and the final report states how many there were per arm.

## 7. Blind escape scoring

- Escapes are scored **after** the 14 days, by an agent or person who is not
  told the arm. `watermill trial scorepack` builds that prompt from the bead's
  own text (title and description), the repo path, the PR number, the landing
  date and the rubric. It contains no arm, no label, no `trial:` tag, no
  ledger or results path; beads appear in a hash order, not enrolment order.
  `tests/test_trial.py` pins this.
- The orchestrator files the scorer's answers with `trial score`; the scorer
  never runs a `trial` command and is told not to read handoffs, run records,
  labels or comments.
- **Findings carry the arm** (`trial:A` / `trial:B`, by the owner's
  instruction, so the graph grows from both arms). The scorer must not see
  them; it is not given `watermill recall`.
- **Residual leaks, said plainly:** the landed work itself can reveal the arm
  (a crew PR has sluice fixup commits; an arm B PR does not), and a defect's
  bug bead may cite a handoff. The brief tells both arms to keep the words
  "trial" and "arm" out of PRs, commits and bead text, but the scoring is
  blind to the label, not to the style of the work. Report this limit with
  the result.
- A score filed before the 14 days is `early`, provisional, and ignored by
  `status`; a later score replaces it. Scores are append-only (latest wins).

## 8. Running it

Everything goes through `watermill trial` (all state is in
`knowledge/trial/`, tracked: `ledger.jsonl` and `results.jsonl`, append-only,
`merge=union`).

1. **Enrol** (owner, after reviewing the dry run):
   `watermill trial enroll <repo> <bead>...` (or `--ready`). Commit
   `knowledge/trial/` and each repo's `.beads/issues.jsonl` (the labels).
2. **Brief**: `watermill trial brief <bead> [--surface laptop|cloud]` prints the
   exact prompt for the session. Start a new top-level session with it. The
   brief's first action is `watermill trial start <bead>`, which records
   `CLAUDE_CODE_SESSION_ID` and the surface in the ledger.
3. **Collect** after the session has exited: `watermill trial collect`.
   For each started bead it reads:
   - *laptop*: the session transcript `~/.claude/projects/*/<session>.jsonl`
     (found by the ledger's session id), its **last** `cost-state` line
     (numbers only), the first and last timestamps; the session must have a
     `cost-state` line and have stopped being written for five minutes;
   - the PR (number from the agents' own `knowledge/agent-runs/` record, or
     `--pr BEAD=N`) through the REST API: merged, first-green CI, owner commits.
   Re-running appends a new line only when something changed (for arm B the
   PR is merged after the session, so a later collect records it); the latest
   line per bead wins.
4. **Score**, 14 days after landing: `watermill trial scorepack` ->
   blind scorer -> `watermill trial score <bead> --none | --escape SEV:REF:SUMMARY`.
5. **Status** at any time: `watermill trial status [--json]`.

### Cloud sessions: what is missing, plainly

A cloud session's transcript does not come back to the laptop, and a session
**cannot read its own final `cost-state`** (Claude Code writes that line when
the session ends). So for a cloud run:

- the brief has the session run `agents record --role orchestrator|solo --arm
  A|B --bead <id> --pr <n>` at sign-off and commit the file: a **snapshot** of
  its own transcript's counters (tokens, cache, timestamps) as of sign-off,
  which also carries its session id;
- `collect` stores it with `cost_basis: recorded-snapshot`. For arm A the
  snapshot is the orchestrator only; the crew subagents' tokens are **not**
  in it, so it is a floor that flatters the crew, and for arm B it misses only
  the last few turns;
- `status` **excludes snapshots from the cost comparison** and says how many
  it excluded. Duration, CI, landing and escapes are unaffected;
- the owner can read the true session total from the Claude Code session
  usage and supply it: `watermill trial collect --cost-usd <bead>=<usd>`
  (stored as `cost_basis: manual`, and then included);
- if `$WM` (water-mill) is not attached to the cloud session, `trial start`,
  `recall` and `remember` cannot run; the session id then reaches the ledger
  only through the recorded line, and the findings are lost to the graph (the
  handoff's "Lessons for the graph" are filed from the laptop later). Attach
  water-mill to every trial session to avoid this; it gives that session
  write access to the factory checkout's session branch.

If every trial session runs in the cloud, the cost secondary cannot be
analysed without the manual step. Duration, CI, landing and escapes can.

## 9. Not measured, not claimed

- Quality of the work beyond escapes and CI (readability, design).
- Anything about beads outside the eligibility rules (fence-touching, epics,
  hand-only): the result does not generalise to them.
- The two arms differ in more than "crew vs not": the crew has a review step
  and a different prompt. The trial answers whether the whole crew *process*
  beats a default Claude on escapes; it cannot say which part does the work.
- Subagent token counts are floors (water-mill-658); the trial never uses them,
  only session totals.
- The baseline's 9.3% was scored unblinded by three AI agents; the trial's
  escape rate for arm A is scored blind and may differ for that reason alone.

## Amendments

(none)
