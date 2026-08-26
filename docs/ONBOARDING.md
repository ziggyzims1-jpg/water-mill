# Bringing a project into the factory

A project is ready for unattended work when four things are true, and the order
matters — each one is what makes the next one safe.

| # | Prerequisite | Proven by |
|---|---|---|
| 1 | A gate that catches real breakage | `watermill doctor --gate` |
| 2 | A verified restore | `commands.backup_check` exits zero |
| 3 | A fence over what must not change | `watermill validate` reports a non-zero count |
| 4 | A queue deep enough that the agent never invents work | preflight's "work available" |

**A project missing any of these can still be registered and driven
supervised.** That is the point of supervised mode. What it must not do is run
overnight.

## 1. Register it

```bash
./bin/watermill init ../my-project        # writes a commented watermill.yaml
$EDITOR ../my-project/watermill.yaml
./bin/watermill add my-project ../my-project
./bin/watermill validate my-project
```

If the project cannot take a file yet, vendor the contract here instead — put it
in `projects/<name>.yaml` and point the registry at it with `contract:`. The
project's own file always wins later, so migrating it in is a move and a
deletion, with nothing to reconcile.

## 2. The gate

Set `commands.gate` to **exactly what CI runs**. Not a subset, not a faster
variant. A gate that differs from CI is two gates, and the agent will satisfy
the weaker one.

Then check it actually fails on breakage:

```bash
cd ../my-project
# break something small on purpose
<your gate command>    # this must fail
git checkout -- .
```

That sounds unnecessary and is not. A gate that cannot fail is indistinguishable
from a gate that ran, which is the whole failure mode this system exists to
prevent.

## 3. The backup

`commands.backup_check` must exit zero when a restore has been **verified**
recently. Not when a file exists — when a restore was performed and checked.

Building one is project-specific work, and the shape that has proven right is
three scripts:

- an **export** — deterministic, read-only, atomic, credentials stripped using
  the app's own redaction list rather than a second one that could drift
- a **restore** that refuses any target that is not scratch, with **no override
  flag**. The way to restore over production is to stop the app and move the
  file aside by hand, knowing that you did
- a **drill** that restores the newest export into a throwaway database, checks
  it, and deletes it. A passing drill writes a heartbeat; `backup_check` reads
  that heartbeat and fails when it goes stale

One warning from the first project that built this, because it is not obvious
and it cost a debugging session: **a check must not mutate its subject.** That
drill replayed migrations as one of its checks — and the migrations were not
purely schema, so the replay changed the data that the *next* check then read,
and it reported the corruption it had caused as a finding.

Until the export leaves the machine, a mistake is recoverable and a dead disk is
not. Preflight can enforce the first half and cannot enforce the second.

## 4. The fence

Start from these questions, not from a template:

- What has broken this project in production before? Those files.
- What can weaken the gate? The Makefile, the CI workflow, the linter config,
  the test helpers.
- What encodes a decision that took a long argument to reach? Doctrine files,
  consolidated modules, anything with a comment beginning "this is deliberately".
- What holds credentials, or decides what a backup redacts?
- The contract itself.

`watermill validate` warns when the fence is empty. An empty fence is a valid
contract and a bad idea.

## 5. The queue

Any tool that answers `ready` with JSON and accepts claim, release, close and
comment. Beads is what this was built against; a GitHub label and a wrapper
script would do.

**Depth is a safety mechanism, not a productivity one.** An agent with three
tasks and six hours does not stop after three tasks — it finds something to do,
and self-directed work drifts toward interesting code, which in most projects
means the schema, the migrations and the time handling. Those are exactly the
places it must not go.

Preflight refuses on an empty queue with the words *generate tasks, do not raise
caps*, which is the same rule from the other direction.

### What a task needs

Every task should name:

- **its files** — the agent should not have to search for where the work goes
- **a verification specific to this change** — not "the gate passes", which is
  already required, but what proves *this* task did its job
- **an out-of-scope clause** listing protected surfaces, even ones that look
  unrelated

Tasks that need a judgement call should not be in an unattended queue at all.
The agent will escalate them, which is the right outcome, but an escalation is
a task that cost money and produced nothing.

## 6. The first run

Supervised, one task, watching:

```bash
./bin/watermill run my-project --max-spend 5 --max-tasks 1 --supervised
```

Then [calibration](CALIBRATION.md): eight tasks, watched, recording *why* each
one went wrong rather than whether the code was right.

Only after that, an unattended night at 5 tasks and 3 hours — and the ramp in
[SAFETY.md](SAFETY.md#the-ramp) from there.

## Common refusals, and what they mean

| Refusal | Almost always |
|---|---|
| `clean tree` | An untracked file you meant to keep. Preflight is protecting it |
| `stale claims` | A previous run was killed. `watermill release <project> <id>` |
| `work available` | The queue is empty. Generate tasks; do not raise caps |
| `baseline gate` | The project is broken *before* the agent. Fix it first |
| `verified restore` | The drill has not run recently, or has never run |
| `not production` | An environment variable in your shell, not in the project |
| `spend ceiling` | `--max-spend` is required and has no default, on purpose |
