# Catches and escapes baseline — 2026-10-13

Per-bead scores for every mill-crew bead with a handoff note on 2026-10-13: what sluice
caught before merge, and what escaped after landing. Kept as the baseline for the
crew-vs-default-Claude trial (bead `water-mill-166`), which must score its beads with the
same rubric and the same decisions below.

One file per project, one JSON object per bead:
`project, bead, pr, landed, landed_at, verdict, sluice_rounds, catches[{severity, summary}],
escapes[{severity, kind, ref, days_after, summary}], confidence, notes`.

## Rubric (severity by consequence, not by how sluice worded it)

- **blocker**: would have broken production, lost or corrupted data, leaked private data or
  credentials, opened a security hole, or made the merge gate or landing itself fail or hang.
- **bug**: wrong behaviour or output a user or downstream code would hit, short of blocker.
- **test-gap**: code was right, but tests would not have caught a regression, or a test was wrong.
- **quality**: docs, naming, comments, style, refactor, scope tidy-up, conventions.

**Catch**: a problem sluice fixed in the PR (or bounced to a follow-up bead) before merge.
**Escape**: a defect in the landed work found after landing: a bug bead traced to it, a
revert of its PR, or a fix commit naming it within 14 days.

## Decisions every scorer followed (or was normalised to)

- Headline counts use **fixed** catches only. Catches sluice filed as a follow-up bead
  instead of fixing are counted separately. In this data their summaries start with
  `deferred` (zimmy) or contain `filed hpt-` (hillel); the small-repo scorer left them out
  entirely. Filter on that when re-counting.
- Bugs that existed before the PR, which sluice merely noticed, are not catches.
- A defect seen before merge and left unfixed is never an escape, even if filed later.
- A defect found by a later PR's review counts as a catch for that PR and an escape for the
  bead whose code introduced it.
- Escapes with no stated link were attributed by code provenance (`git log -S`) and marked
  in `notes`; 12 of the 20 escapes are of this kind. Beads with such calls are `medium`
  confidence. An owner-requested revert (zimmy #204, lqg epic) is a design call, not an escape.
- Merge-conflict resolution and rebases are not catches. Orchestrator-directed fixes made
  during review are catches, noted as such.
- `landed_at` is the PR's merge date (UTC where the scorer used GitHub's `mergedAt`).

## Headline (183 reviewed and landed beads)

| | fixed before merge | escaped |
|---|---|---|
| blocker | 17 | 0 |
| bug | 199 | 15 |
| test-gap | 194 | 3 |
| quality | 82 | 2 |

Bounced to follow-up beads: 32. Beads with an escape: 17/183 (9.3%, Wilson 5.9–14.4%).
Bugs and blockers caught before merge: 216 of 231 = 93.5% (Wilson 89.6–96.0%).

## Limits

Escapes are a floor: they count only when someone filed or fixed them, and the newest beads
had days, not weeks, to fail. Scoring was done by three AI agents, unblinded, one per repo
group; borderline severity calls are written in each record's `notes`. This measures what
review adds to millstone's draft. It does not compare the crew with a default Claude.
