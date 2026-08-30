# Findings

`findings.jsonl` is what this factory has learned, one JSON line per finding,
append-only. It is **committed on purpose**, unlike `runs/`.

The run history is large, machine-written, and local to whichever machine ran
the night; it ships to Loki and stays gitignored. Findings are small,
hand-written, and the most valuable thing this factory produces -- so they
belong in git, where they are diffable, reviewable, and present in every
checkout.

Do not edit a line in this file. A finding that stopped being true is
*superseded* by a new one and both survive; a finding that still holds is
*confirmed*, which adds a line rather than touching one. A store that can be
edited is one whose history can be quietly improved, which defeats the purpose
of keeping it.

```bash
watermill remember <cell> <kind> "one sentence"   # record
watermill recall "a question"                     # ask
watermill review                                  # the monthly sweep
```

Everything else is in [`docs/KNOWLEDGE.md`](../docs/KNOWLEDGE.md).

**It is empty, and that is correct.** A finding is written after a task has gone
wrong. Seeding it from either project's CLAUDE.md would put guesses in front of
every future agent, and a guess is indistinguishable from a lesson once it is in
the list.
