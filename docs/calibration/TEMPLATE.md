# Calibration — PROJECT_NAME

**Status: not run.** Until the table below has rows, every task specification in
this project is a hypothesis and the loop is not approved for unattended use
here. Calibration is per project: what a repository teaches about writing tasks
for it does not transfer whole to the next one.

Method, and what to watch for: [../CALIBRATION.md](../CALIBRATION.md).

```bash
./bin/watermill run PROJECT_NAME --max-spend 5 --max-tasks 1 --supervised
```

## The eight

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

**Root cause** is one of the buckets in `watermill/tasklog.py`. Record each one
in the task log as well as here, so it can be counted across projects:

```bash
./bin/watermill annotate PROJECT_NAME <task-id> <root-cause> --note "..."
./bin/watermill tasks PROJECT_NAME
```

The table is the narrative and the log is the arithmetic. Neither replaces the
other: three projects each blaming their own idiosyncrasies is what the counts
are for, and a count with no story attached tells you nothing about what to fix.

## Readiness call

**Not ready.** Nothing has run.

Answered after the eight:

1. Did any task pass the gate and still turn out wrong? *(If yes: not ready,
   regardless of everything else.)*
2. Were tasks 6–8 smoother than 1–3?
3. Is the report accurate — does it describe what actually happened in the
   repository?

## What was promoted out of this

Lessons that turned into something mechanical. A note that stayed prose is a
note that will be re-learned.

| Lesson | Where it went |
|---|---|
| | |

Three destinations, in descending order of how much they are worth:

- **The gate** — a check that fails on the mistake. The only one that cannot be
  ignored.
- **`fence.paths`** — checked against the diff afterwards, so it holds whatever
  the agent believed.
- **`notes` in the contract** — advisory, in the prompt, for what neither of the
  above can express.

A lesson that is only true of this repository stops here. One that shows up in a
second project belongs in `docs/ONBOARDING.md` or in Water Mill itself — see the
filing rule there.
