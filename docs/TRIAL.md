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
| Work | runs millstone, then sluice, then tailrace as subagents | implements, runs the gate, opens the PR, lands it; **no review agent** |
| Ends | PR merged after sluice approves and every check is green, bead closed | PR merged after every check is green, bead closed |
| Merge | tailrace (inside the session) | the session itself (owner's decision, 2026-10-13) |

Same for both: the bead text, the repo's gate (`make verify`), the repo's
fence, "implement, test, open a PR", the knowledge steps (recall at the start,
`watermill remember` with `--tag trial:A|B` at sign-off, a handoff), and the
**landing rule, word for word** (`trial._landing`): wait for every check-run on
the PR head to be completed and green, then squash-merge exactly that head
(`--match-head-commit` / `sha=`) as a tool call of its own, with the commit
message *subject* `<PR title> (#<n>)`, *body* `Bead <id>.`, then close the
bead the way the repo's lander does. On the laptop both arms use the branch
`bead/<slug>`; in the cloud both use the session branch. Both arms therefore
end at the same point, "landed", and the landed rate (section 5) compares like
with like. The one designed difference is the crew: arm B has no review step.

`ARM_B_SELF_MERGES` in `watermill/trial.py` is the switch for this decision
(False = arm B stops at an open PR and the owner merges); changing it after
enrolment is an amendment.

**One trial bead per top-level session.** The session's `cost-state` line is
cumulative per session, so a session that ran two beads cannot be split.
`trial start` refuses a second bead in a session.

## 2. Eligibility

A bead is eligible when all of these hold (`trial.eligibility`):

- its repo is registered in `projects.yaml`, enabled, and checked out here;
- it is not an epic and its status is `open`;
- it is not labelled `hand-only` (the owner's mark for work done by hand);
- it names no path from the repo's `fence.paths` (outside its *Out of scope*
  section) as one it may edit, unless it carries the label `fence-directed`
  (the bead itself directs the fenced change) or `fence-clear` (the owner's
  mark: it names a fenced path but edits none). Not counted as a mention: a
  citation of a handoff note (`See brain/handoffs/mill/x.md`; handoffs are
  crew output, never bead work) and a sentence that says the path is not
  changed (`db.py is fenced and not touched`, `No db.py change`) unless the
  same sentence also directs an edit. Any other mention counts, so the rule
  errs towards excluding: a bead that edits a `CLAUDE.md` row (the repo
  convention's doc update) is excluded rather than judged, and so is a bead
  that only *reads* a fenced file (`brain/samples/x.png`) until the owner
  labels it `fence-clear`;
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
  command to remove or re-draw one. The ledger is opened for append only. An
  id given twice in one call takes one position.
- **Enrol from one machine.** The ledger is `merge=union`, so two machines
  that enrol from the same base both keep their lines when git merges them: a
  bead enrolled twice (possibly once per arm), two beads on one block position
  (the block is no longer two and two), a second seed, or a bead started by two
  sessions. `trial.ledger_problems` finds each of these; `enroll`, `start` and
  `brief` refuse while any exists and `status` prints them first. It is a
  protocol failure (section 6), resolved by the owner, never by appending.
  (Byte-identical lines collapse in a union merge, which is harmless: the
  same bead with the same arm.)
- **Balance is exact in full blocks only.** `enroll` reports a repo whose last
  block is partial. A batch of eight is two exact blocks when it is eight
  beads of one repo or four in each of two repos; eight spread 2/2/2/2 over
  four repos is four half-blocks, each of which may be AA or BB.
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
  passed (scored). Both arms land their own work (section 1), so a bead that
  never landed is a failure of that arm's process, not of an external merge
  queue; such beads have no escape window and are counted in the landed rate
  (section 5) and in the sensitivity analysis below.
- **Sensitivity (reported, not confirmatory).** Treat every enrolled bead that
  did not land within 30 days of enrolment as a failure and repeat the test
  (`status`'s `sensitivity` line, same Fisher test, same looks).
- **Effect and interval.** Report the two proportions with Wilson 95% intervals
  and their difference with Newcombe's interval (`stats.newcombe_diff`).
- **Size.** About 60 landed, scored beads per arm gives ~80% power to tell a
  30% escape rate from a 10% one; the baseline escape rate for the crew is
  9.3% (Wilson 5.9-14.4%) over 183 beads, so a default Claude doing *better*
  than that is unlikely and the test is two-sided anyway.

## 5. Secondary outcomes (exploratory, no multiplicity correction)

Each is reported with its p-value and says so: there are four of them and no
correction is applied, so none is a finding on its own.

- **`cost_usd_est`, laptop beads only**: the session's final `cost-state`
  `totalCostUSD` (an API-equivalent estimate at list prices, not a bill).
  Mann-Whitney U on per-bead values, with medians; the final report adds
  `stats.bootstrap_median_diff` (seeded) for the difference. Beads run on the
  laptop or in the cloud, chosen per bead (owner's decision, 2026-10-13); only
  rows with `cost_basis` `cost-state`, which only a laptop session has, enter
  the comparison (`COMPARED_COST_BASES`). A cloud bead's cost is a snapshot
  (`recorded-snapshot`) or an owner-supplied figure (`manual`, marked
  `cost_supplied_by: owner`); both are stored and reported, never compared,
  and `status` says how many it left out. Cloud beads count in every other
  outcome.
- **Duration**: session first-to-last timestamp, wall seconds. Mann-Whitney.
- **First-push CI green**: the earliest commit of the PR that has any
  check-run, all of whose runs completed green. Fisher's exact test.
- **Landed rate**: the PR merged. Fisher's exact test. Comparable because both
  arms land their own PR under the same rule.
- **Owner corrections** (commits on the PR without a `Co-Authored-By: Claude`
  trailer, merges excluded) are recorded and reported descriptively, not tested.

## 6. Looks, stopping, and what `status` prints

- **Interim at 30 scored beads per arm; final at 60 per arm.** `trial status`
  names the stage (`pre-interim`, `interim`, `final`).
- **No early stopping on p-values.** The trial runs to 60 per arm whatever the
  interim shows. The only reasons to stop early are protocol failures (a broken
  harness, the ledger corrupted) and the harm stop below, and they are decided
  and written down without reference to the outcome data.
- **Harm stop (pre-registered 2026-10-14, before any enrolment; water-mill-kt6).**
  Not a p-value stop. *Trigger:* any trial bead, in either arm, that has landed
  on main and is found to carry a blocker-class escape by the section 7 rubric
  (would break prod, lose or corrupt data, leak a secret or personal data, or
  bypass auth). Also a trigger: an arm B run that edits a fenced path, ignores a
  READ ONLY / Out of scope mark, or merges with a failing check. The trigger is
  judged on that one defect alone, never on arm counts or rates, so it cannot
  become a look at the outcome. *Effect:* the trial pauses
  (`watermill trial pause --reason "..."`, a `pause` ledger line); `trial start`
  refuses and `trial status` prints PAUSED with the reason until the owner
  writes a resume or stop decision (`trial resume --reason "..."`). Beads
  already in their 14-day window keep being observed and scored. The offending
  change is reverted on main right away; the bead stays in the ledger as scored
  (the escape counts), not dropped.
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
  own text (title and description), the repo path, the landing commit on
  main, the landing date and the rubric. It contains no arm, no label, no
  `trial:` tag, no ledger or results path, and **no PR number** (the PR page
  shows the branch, every branch commit and the authors); beads appear in a
  hash order, not enrolment order. Two beads with the same text get the same
  block whatever their arm. `tests/test_trial.py` pins this.
- **What the scorer reads on main is the same shape for both arms.** Both
  land with the same squash message (subject `<PR title> (#<n>)`, body `Bead
  <id>.`), because GitHub's default squash body lists every branch commit:
  sluice fixups, `chore(agent-runs)` lines naming the roles, per-model
  `Co-Authored-By` trailers. The scorer is told to read `origin/main` only and
  always through `trial.BLIND_PATHSPEC`, which excludes `brain/` (handoffs:
  a `## Sluice` section names arm A), `knowledge/` (run records named by role,
  findings tagged `trial:A|B`), `.beads/` (the labels) and `HANDOFF*`; the
  test runs that pathspec through git. It is told not to open PRs, branches
  or authors on GitHub and not to `bd show` the scored beads.
- The orchestrator files the scorer's answers with `trial score`; the scorer
  never runs a `trial` command and is told not to read handoffs, run records,
  labels or comments.
- **Findings carry the arm** (`trial:A` / `trial:B`, by the owner's
  instruction, so the graph grows from both arms). The scorer must not see
  them; it is not given `watermill recall`.
- **Residual leaks, said plainly:** the scorer could ignore the instructions
  (it has the repo; blinding is by what it is given and told, not by access
  control); the landed diff's own style can differ by arm; a defect in a file
  under an excluded path would be missed (no eligible bead edits `brain/` or
  `.beads/`, fenced in every cell); and a bug bead may cite a handoff or say
  "found by sluice". The brief tells both arms to keep the words
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
   Re-running appends a new line only when something changed (a PR merged
   or a figure supplied after an earlier collect); the latest
   line per bead wins.
4. **Score**, 14 days after landing: `watermill trial scorepack` ->
   blind scorer -> `watermill trial score <bead> --none | --escape SEV:REF:SUMMARY`.
5. **Pause / resume** (section 6 harm stop): `watermill trial pause --reason "..."`,
   `watermill trial resume --reason "..."`; latest ledger line wins.
6. **Status** at any time: `watermill trial status [--json]`.

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
- `status` **compares cost on laptop beads only**: it excludes snapshots and
  owner-supplied figures from the cost comparison and says how many of each it
  excluded. Duration, CI, landing and escapes are unaffected;
- the owner can read the true session total from the Claude Code session
  usage and record it: `watermill trial collect --cost-usd <bead>=<usd>`
  (stored as `cost_basis: manual`, `cost_supplied_by: owner`, with a note; it
  persists through later collects until the owner supplies another, and is
  reported, not compared);
- if `$WM` (water-mill) is not attached to the cloud session, `trial start`,
  `recall` and `remember` cannot run; the session id then reaches the ledger
  only through the recorded line, and the findings are lost to the graph (the
  handoff's "Lessons for the graph" are filed from the laptop later). Attach
  water-mill to every trial session to avoid this; it gives that session
  write access to the factory checkout's session branch.

If every trial session runs in the cloud, the cost secondary has no data.
Duration, CI, landing and escapes do not depend on the surface.

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
