# Supervised calibration

**This has not run. Until it does, every task specification in every registered
project is a hypothesis, and the loop is not approved for unattended use.**

## What it is

Eight tasks, one at a time, watched live. Not reviewed afterwards — *watched*.

```bash
./bin/watermill run zimmy-life-tracker --max-spend 5 --max-tasks 1 --supervised
```

`--supervised` stops after every task and prints what happened before asking
whether to continue. Run it eight times, or raise `--max-tasks` and answer the
prompt each time.

## What is being watched for

Not whether the code is right. The gate answers that, and it answers it without
you. What you are watching for is **why a task went wrong**:

- the goal was vague
- the file list was incomplete
- the out-of-scope clause did not cover something adjacent
- the task was too large for one agent invocation
- the spec assumed context the agent did not have

Each of those is a fixable property of the *specification*, and each produces a
different edit to how tasks get written. Sorting a failure into the right one of
those five buckets is the entire deliverable of this exercise.

## The finding that halts everything

> **Work that passes the gate and is still wrong.**

If that happens, calibration stops. It means the gate has a hole, and no amount
of better task-writing compensates for a gate that can be satisfied by a wrong
answer. The gate gets a new check before anything else proceeds — including
before the remaining calibration tasks.

Write down what the hole was. That is the most valuable single output this
process can produce.

## Why eight

Tasks 1–3 will reveal most of the problems. Tasks 6–8 should be noticeably
smoother. **If they are not, the template edits are not addressing the real
causes** — which is itself the finding, and it means going back to the first
three and re-reading what actually went wrong rather than what seemed to.

Eight is enough to see that trend and few enough to sit through.

## Record it here

| # | Task | Outcome | Root cause | What changed as a result |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |

**Root cause** is one of: vague goal · incomplete file list · weak out-of-scope
clause · task too large · missing context · gate hole · agent error · none (it
worked).

"Agent error" should be rare. If it is the most common entry, that is usually a
specification problem wearing a disguise.

## Readiness call

**Not ready.** Nothing has run.

Filled in after the eight, answering three questions:

1. Did any task pass the gate and still turn out wrong? *(If yes: not ready,
   regardless of everything else.)*
2. Were tasks 6–8 smoother than 1–3?
3. Is the report accurate — does it describe what actually happened in the
   repository?

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

1. **Calibration**, above.
2. **The backup leaves the machine.** Every registered project needs a
   `backup_check` that passes, and the exports need a destination that is not
   the same disk. A mistake is recoverable; a dead SD card is not. Preflight
   enforces the first half and cannot enforce the second.
3. **A provider-side spend budget.** The spend cap here is reactive and will
   overshoot by up to one task. A budget at the provider is the only thing that
   stops an overrun outright, and it costs nothing as a second backstop.

Then one attended capped run (`--max-tasks 3`, watching), and only then a first
unattended night at 5 tasks and 3 hours.
