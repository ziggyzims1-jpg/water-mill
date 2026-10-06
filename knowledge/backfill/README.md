# Structure backfill, 2026-10 (bead water-mill-ng1)

- `2026-10-applied.jsonl` -- the batch applied with `watermill annotate-finding --batch`
  (tags everywhere; a non-human cause or a `gate` destination only where the text shows it).
  Its annotation lines are already in `findings.jsonl`.
- `2026-10-human-suggested.jsonl` -- causes only a person may assign
  (`tasklog.HUMAN_ONLY`), drafted but NOT applied. Read it, edit or delete rows, then:

      ./bin/watermill annotate-finding --batch knowledge/backfill/2026-10-human-suggested.jsonl --json

Findings in neither file (the "unsure" list in the PR) still need the owner's cause.
