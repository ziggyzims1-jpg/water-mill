# Water Mill

A multi-project orchestrator for supervised and unattended agent work.

Water Mill claims a task from a project's queue, hands it to an agent, and then
**independently verifies what actually reached the repository** — re-running the
project's own gate, checking the diff against a declared fence, checking the
tree is clean and checking the commit names the task. Work that fails any of
those is discarded whatever the agent reported. Then it writes down what
happened, in a report and in an append-only ledger.

It knows nothing about any particular project. Everything project-specific
arrives through a contract.

**Where this actually stands: [docs/STATUS.md](docs/STATUS.md).** What it is
for and where the money comes from: [docs/PLAN.md](docs/PLAN.md).

> **NOT YET APPROVED FOR UNATTENDED USE.** Every cap has a test and the gate is
> green, but the caps have only ever been proven with **stub agents**. That
> tests the orchestrator's control flow, not how a real agent behaves inside
> it. Closing that gap is what [supervised calibration](docs/CALIBRATION.md) is
> for, and it has not run.

## The idea

The safety does not come from the loop. It comes from what surrounds it:

| Layer | What it buys | Where it lives |
|---|---|---|
| **The gate** | Work that does not build or pass is discarded | The project (`commands.gate`) |
| **The fence** | A confused task cannot reach the files that matter | The contract, checked against the diff |
| **The backup** | A mistake is recoverable | The project (`commands.backup_check`) |
| **The caps** | A runaway costs an evening, not a weekend | `watermill/caps.py` |
| **Preflight** | A run never starts on a tree it cannot attribute | `watermill/preflight.py` |
| **The report** | A morning takes ten minutes, not an hour | `watermill/report.py` |

Each one was built before the loop that depends on it, and that order was the
point.

## Quick start

```bash
make install                                  # .venv + dependencies
make verify                                   # the gate: guard, ruff, 132 tests

./bin/watermill projects                      # what this factory drives
./bin/watermill validate                      # do the contracts parse
./bin/watermill doctor                        # would a run be allowed to start
./bin/watermill doctor --gate                 # ...including the project's gate
```

Adding a project:

```bash
./bin/watermill init ../my-project            # writes a starter watermill.yaml
./bin/watermill add my-project ../my-project  # registers it here
./bin/watermill validate my-project
```

Running one:

```bash
# Supervised: stops and reports between tasks. Start here, always.
./bin/watermill run zimmy-life-tracker --max-spend 5 --max-tasks 1 --supervised

# Unattended. Refuses every skip flag.
./bin/watermill run zimmy-life-tracker --max-spend 10 --max-tasks 5 --unattended
```

There is **no default for `--max-spend`** and the run refuses to start without
one. That is deliberate: it is the only cap that assumes the run is
misbehaving, so it is the only one that fails closed.

Afterwards:

```bash
./bin/watermill report zimmy-life-tracker     # the latest morning report
./bin/watermill status                        # readiness and history per project
./bin/watermill ledger                        # every run, across every project
```

## Layout

| Path | What |
|---|---|
| `bin/watermill` | Entry point. Works without installation |
| `watermill/contract.py` | The coupling surface. Read this first |
| `watermill/registry.py` | Which repositories this factory drives |
| `watermill/preflight.py` | Everything that must hold before a run starts |
| `watermill/engine.py` | The run loop. Four decisions, one of which keeps anything |
| `watermill/caps.py` | Six caps, and the counting rules that were measured bugs |
| `watermill/meter.py` | Cost and verdict, from the agent's own output |
| `watermill/agent.py` | The prompt. Pure, so every line the agent reads is tested |
| `watermill/queue.py` | Six shell commands and a JSON shape |
| `watermill/gitwork.py` | Git, and a discard that refuses to run on the wrong path |
| `watermill/report.py` | The morning report. Pure |
| `watermill/ledger.py` | Append-only history across projects |
| `projects/` | Vendored contracts, for projects that carry none yet |
| `runs/` | Per-run logs. Gitignored, and **never pruned automatically** |
| `docs/` | The contract spec, the safety model, onboarding, calibration |

## Documentation

- **[docs/CONTRACT.md](docs/CONTRACT.md)** — every field, and why it defaults the way it does
- **[docs/SAFETY.md](docs/SAFETY.md)** — what is actually protecting you, and what is not
- **[docs/ONBOARDING.md](docs/ONBOARDING.md)** — bringing a new project into the factory
- **[docs/CALIBRATION.md](docs/CALIBRATION.md)** — the supervised session that has to happen before an unattended night

## Registered projects

| Project | Contract | State |
|---|---|---|
| `zimmy-life-tracker` | `projects/zimmy-life-tracker.yaml` | Target one. Not yet calibrated |
