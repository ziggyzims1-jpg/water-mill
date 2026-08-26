# Water Mill

A multi-project orchestrator for supervised and unattended agent work. It
claims a task from a project's queue, hands it to an agent, independently
verifies what reached the repository, and writes down what happened.

**Read [docs/SAFETY.md](docs/SAFETY.md) before changing anything in
`engine.py`, `preflight.py`, `gitwork.py` or `caps.py`.** Those four files are
the safety model, and most of what looks like an odd choice in them is a bug
somebody already had.

## Working here

```bash
make install     # .venv + dependencies
make verify      # THE MERGE GATE: guard, ruff, the full suite
make test-fast   # everything except the tests that drive real subprocesses
make doctor      # preflight every registered project
```

`make verify` is the gate and CI runs exactly that command, so a check that
passes locally cannot fail in CI for a reason spelled out in a YAML file.

## Layout

| Path | Purpose |
|---|---|
| `watermill/contract.py` | The coupling surface. Read first |
| `watermill/registry.py` | Which repositories the factory drives |
| `watermill/preflight.py` | Everything that must hold before a run starts |
| `watermill/engine.py` | The run loop |
| `watermill/caps.py` | Six caps and their counting rules |
| `watermill/meter.py` | Cost and verdict from the agent's own output |
| `watermill/agent.py` | The prompt (pure) |
| `watermill/queue.py` | Queue adapter |
| `watermill/gitwork.py` | Git, and a guarded discard |
| `watermill/report.py` | The morning report (pure) |
| `watermill/ledger.py` | Append-only cross-project history, one line per run |
| `watermill/tasklog.py` | The same, one line per **task**, plus the root-cause taxonomy |
| `projects/` | Vendored contracts for projects that carry none yet |
| `docs/calibration/` | One findings record per project. The method is `docs/CALIBRATION.md` |
| `docs/` | Contract spec, safety model, onboarding, calibration. **`STATUS.md` is where things actually are; `PLAN.md` is what is being built and why** |
| `runs/` | Per-run logs. Gitignored, **never pruned automatically** |

## Conventions

- **Refusals and failures are different, and have different exit codes.** A
  refusal means a precondition did not hold and nothing was modified (exit 3). A
  failure means work was attempted and did not land (exit 1). A cron wrapper
  needs to tell them apart: a refusal every night is a configuration problem, a
  failure every night is a project problem.

- **Unknown keys in a contract or the registry are refused, never ignored.** A
  misspelled key is indistinguishable from a missing one once a run has started,
  and the missing one that matters is `fence`.

- **Nothing from a contract reaches a shell.** Commands are split with `shlex`
  and run as argv. Placeholders are substituted *after* splitting, so a task id
  or a comment body is data rather than syntax.

- **A check that parses output must ask for the whole output** (`tail_lines=0`).
  Truncated JSON does not parse as shorter JSON; it parses as a broken tool.

- **Never normalise a path with `lstrip("./")`.** It takes a character set, not
  a prefix, so `.github/workflows/x.yml` becomes `github/workflows/x.yml` and a
  fence over `.github/` silently matches nothing. Use `removeprefix`.

- **The agent's exit code is not evidence, and neither is ours.** Tests assert
  on what reached the repository — the commit log, the working tree, the files
  on disk — not on what the orchestrator recorded about itself.

- **A step that cannot fail must not be part of a green result.** No `|| true`,
  no `-` prefixes, no `continue-on-error`. `make typecheck` explains that there
  is no type checker and exits non-zero.

- **A cleanup routine is the most dangerous code here**, because it runs on the
  paths nobody tested. `gitwork.discard()` requires the caller to assert the run
  actually started; `test_a_refused_preflight_touches_nothing` pins it.

- **Caps are checked between tasks, never during one.** Halting mid-task risks a
  partial commit. The spend cap therefore overshoots by up to one task, and says
  so rather than pretending otherwise.

- **The stub agents test control flow, not agent behaviour.** Do not let a green
  suite become an argument that the loop is ready for an unattended night. See
  [docs/CALIBRATION.md](docs/CALIBRATION.md).

- **A machine records what happened; only a person records why.** `tasklog.py`
  writes one line per task automatically and leaves `root_cause` empty until
  somebody who watched supplies it. It may offer a `hint` — never for the three
  buckets in `HUMAN_ONLY`, and `gate-hole` above all, because work that passes
  every check and is still wrong is by definition invisible to the thing running
  the checks. A guess stored in the field a judgement belongs in is worse than a
  blank, because it counts.

- **Knowledge has three destinations and they are not interchangeable.** A
  lesson that can be mechanised goes into the gate (unignorable) or
  `fence.paths` (checked against the diff). Only what neither can express goes
  into `notes` in the contract, which reaches the agent's prompt as advice and
  is never checked afterwards. Writing a mechanisable rule as a note downgrades
  an enforced guarantee to a suggestion.

- **A lesson is promoted into Water Mill when it has appeared twice, in two
  repositories.** One project's frictions are indistinguishable from that
  project's idiosyncrasies, and this orchestrator's whole claim is that it is
  repo-agnostic. Until the second sighting a lesson lives in that project's
  contract and its calibration record, which is where it is true.

## Where things are

[`docs/STATUS.md`](docs/STATUS.md) is the position; [`docs/PLAN.md`](docs/PLAN.md)
is the plan. **A change that moves the position updates STATUS.md in the same
commit**, and if it contradicts the plan it updates the plan too. Left to
memory, the plan drifts into fiction and gets quietly stopped being read.

The number that governs everything else right now is **nights run: 0**.

## Adding a project

`docs/ONBOARDING.md`. Four prerequisites in order: a gate that catches real
breakage, a verified restore, a fence, and a queue deep enough that the agent
never has to invent work.
