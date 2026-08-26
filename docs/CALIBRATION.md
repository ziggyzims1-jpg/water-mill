# Supervised calibration

**This has not run, in any project. Until it does, every task specification in
every registered project is a hypothesis, and the loop is not approved for
unattended use.**

This file is the method. Each project's findings live in its own record under
[`calibration/`](calibration/), because what a repository teaches about writing
tasks for it does not transfer whole to the next one.

```bash
./bin/watermill calibrate <project>   # creates docs/calibration/<project>.md
```

| Project | Record | Status |
|---|---|---|
| zimmy-life-tracker | [calibration/zimmy-life-tracker.md](calibration/zimmy-life-tracker.md) | Not run |

## What it is

Eight tasks, one at a time, watched live. Not reviewed afterwards — *watched*.

```bash
./bin/watermill run <project> --max-spend 5 --max-tasks 1 --supervised
```

`--supervised` stops after every task and prints what happened before asking
whether to continue. Run it eight times, or raise `--max-tasks` and answer the
prompt each time.

## What is being watched for

Not whether the code is right. The gate answers that, and it answers it without
you. What you are watching for is **why** a task went wrong:

- the goal was vague
- the file list was incomplete
- the out-of-scope clause did not cover something adjacent
- the task was too large for one agent invocation
- the spec assumed context the agent did not have

Each of those is a fixable property of the *specification*, and each produces a
different edit to how tasks get written. Sorting a failure into the right one of
those buckets is the entire deliverable of this exercise.

The buckets are defined in `watermill/tasklog.py` rather than listed here, so
that the words in a project's record and the words the counts are grouped by
cannot drift apart. `./bin/watermill annotate` refuses anything not in that
list.

## Record it in two places, and they do different jobs

```bash
./bin/watermill annotate <project> <task-id> <root-cause> --note "..."
./bin/watermill tasks                       # every project, counted by cause
./bin/watermill tasks --unannotated         # what still needs a judgement
```

The project's markdown record is the **narrative**: what the task was, what went
wrong, and what you changed as a result. The task log is the **arithmetic**: the
same judgement in a countable bucket, appended, never edited, across every
project the factory drives.

Both, because either alone misleads. Three projects each explaining their
failures in their own terms is exactly the situation the counts exist to cut
through — and a count with no story attached tells you nothing about what to
fix. The orchestrator writes the outcome line automatically; the bucket is
yours, and it stays honestly empty until you supply it. A `?` in
`watermill tasks` is the orchestrator's guess, offered to make annotating fast
and never stored as though a person had said it.

## The finding that halts everything

> **Work that passes the gate and is still wrong.**

If that happens, calibration stops. It means the gate has a hole, and no amount
of better task-writing compensates for a gate that can be satisfied by a wrong
answer. The gate gets a new check before anything else proceeds — including
before the remaining calibration tasks.

Write down what the hole was. That is the most valuable single output this
process can produce. `gate-hole` is one of the buckets, `watermill tasks` counts
it separately from everything else, and it is one of the three a machine may
never assign to itself — by definition it is invisible to every check the
machine runs.

## Why eight

Tasks 1–3 will reveal most of the problems. Tasks 6–8 should be noticeably
smoother. **If they are not, the template edits are not addressing the real
causes** — which is itself the finding, and it means going back to the first
three and re-reading what actually went wrong rather than what seemed to.

Eight is enough to see that trend and few enough to sit through.

## Where a lesson goes afterwards

Calibration produces knowledge, and knowledge that stays in a markdown table is
re-learned. Four destinations, in descending order of how much they are worth:

1. **The gate** — a check that fails on the mistake. The only one that cannot be
   ignored, and the only acceptable answer to a `gate-hole`.
2. **`fence.paths`** — checked against the diff afterwards, so it holds whatever
   the agent believed it was doing.
3. **`notes` in the contract** — advisory, carried in the agent's prompt, capped
   at 20 entries. For what neither of the above can express: where a project
   keeps a thing, which of two plausible idioms it uses, the trap a reasonable
   agent falls into precisely because it is reasonable.
4. **The project's calibration record** — everything else.

**A rule that can be mechanised must not be written as a note.** Stating "never
edit db.py" in the prompt instead of the fence converts an enforced guarantee
into a suggestion the agent may reasonably weigh against the task in front of
it.

### The filing rule: twice, in two repositories

A lesson from one project belongs to that project. It is promoted into
`docs/ONBOARDING.md`, `docs/SAFETY.md` or Water Mill's own code **when it has
appeared in a second repository** — because a single project's frictions are
indistinguishable from that project's idiosyncrasies, and this orchestrator's
whole claim is that it is repo-agnostic. Until then it lives in that project's
contract and its calibration record, which is where it is true.

## What calibration does *not* close

The caps were proven with **stub agents**: a stub that succeeds, one that fails,
one that escalates, one that hangs, one that reports a cost, one that reports
none. That tests the orchestrator's control flow and nothing about real agent
behaviour.

Calibration closes some of that gap — it is the first time a real agent runs
inside this loop — but eight supervised tasks is not a sample. The first
unattended night is still 5 tasks and 3 hours, and the ramp in
[SAFETY.md](SAFETY.md) is deliberately slow for that reason.

## Before the first unattended night

Three things, in order, and none of them is optional:

1. **Calibration**, above, for that project.
2. **The backup leaves the machine.** Every registered project needs a
   `backup_check` that passes, and the exports need a destination that is not
   the same disk. A mistake is recoverable; a dead SD card is not. Preflight
   enforces the first half and cannot enforce the second.
3. **A provider-side spend budget.** The spend cap here is reactive and will
   overshoot by up to one task. A budget at the provider is the only thing that
   stops an overrun outright, and it costs nothing as a second backstop.

Then one attended capped run (`--max-tasks 3`, watching), and only then a first
unattended night at 5 tasks and 3 hours.
