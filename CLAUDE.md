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

In a Claude Code cloud session, run `scripts/cloud-setup.sh` first (it is a
no-op outside one unless given `--force`): it installs `bd` (pinned 1.2.2; a
`bd` already on PATH is used as is), forces `BD_DOLT_AUTO_PUSH=false` into
`CLAUDE_ENV_FILE`, builds the beads database of water-mill and every sibling
checkout with a `.beads/` from its tracked `issues.jsonl` alone (no Dolt remote,
no tracked file or commit changed, prefix derived from the repo's issue ids),
re-imports the jsonl every time, and runs `make install`. A fresh clone has
none of those, so `bd prime` and the crew agents fail without it. The
SessionStart hook in `.claude/settings.json` runs it ahead of `bd prime`, in one
command, because hooks for one event may run in parallel. The hook only fires
when the session's cwd is inside a repo carrying it: a routine's orchestrator
starts in `/home/user`, so it must run the script by hand first. Tests:
`tests/test_cloud_setup.py` (real `bd`, temp clones).

`scripts/sync-factory.sh` fast-forwards this checkout (`pull --ff-only`, only on
a clean `main`, bounded by a timeout) so the context graph and the crew
definitions other repos read through their sibling `../water-mill` are never
days behind. It always exits 0 and prints nothing to stdout, so a SessionStart
hook can run it ahead of `bd prime --hook-json`.

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
| `watermill/knowledge.py` | Findings: what was learned, when it was observed, and what superseded it |
| `watermill/recall.py` | The context graph over all three logs, and the one budgeted way to query it |
| `watermill/mcp.py` | The graph as a tool the agent calls mid-task. The only seam that runs *during* a task |
| `watermill/review.py` | The monthly sweep, and the check that notices the sweep stopped happening or a landed bead went unrecorded |
| `watermill/landed.py` | Beads the mill landed, read from `**LANDED**` handoffs in registered checkouts. A reader |
| `watermill/agentlog.py` | `runs/agents.jsonl`: one line per unit of agent work, any agent kind. The schema is its docstring |
| `watermill/crewlog.py` | Mill crew history recovered from handoffs and bead JSONL, for `watermill agents sweep`. A reader |
| `watermill/recorded.py` | An agent's own sign-off facts (`agents record`), one tracked line per run in `knowledge/agent-runs/`; the one record that survives a cloud container |
| `watermill/trial.py` | The crew-vs-default-Claude trial: ledger, balanced randomisation, briefs, collect, blind scoring, status. Protocol and pre-registered analysis: `docs/TRIAL.md`. A reader of sessions and PRs, never part of a run |
| `watermill/usage.py` | What agents asked the graph and what it could not answer. Never readable by an agent |
| `watermill/land.py` | The pull request: create, verify, merge. Never part of a run |
| `watermill/shipper.py` | Ships both to Loki. A reader, never part of a run |
| `watermill/publish.py` | Assembles a status snapshot of every project and PUTs it to Zimmy. A reader, never part of a run; unknown is omitted, never zeroed |
| `projects/` | Vendored contracts for projects that carry none yet |
| `docs/calibration/` | One findings record per project. The method is `docs/CALIBRATION.md` |
| `docs/TRIAL.md` | The trial protocol and its analysis plan, written before data. Amend only by dated amendment |
| `docs/OBSERVABILITY.md` | Shipping to Loki, and the LogQL worth pinning |
| `docs/KNOWLEDGE.md` | The context graph: why it is queried and never loaded, and the monthly sweep |
| `docs/` | Contract spec, safety model, onboarding, calibration. **`STATUS.md` is where things actually are; `PLAN.md` is what is being built and why** |
| `runs/` | Per-run logs. Gitignored, **never pruned automatically** |
| `knowledge/` | `findings.jsonl` -- **committed**, unlike `runs/`. See `docs/KNOWLEDGE.md` |

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

- **Knowledge has four destinations and they are not interchangeable.** A
  lesson that can be mechanised goes into the gate (unignorable) or
  `fence.paths` (checked against the diff). Only what neither can express goes
  into `notes` in the contract, which reaches the agent's prompt as advice and
  is never checked afterwards. Writing a mechanisable rule as a note downgrades
  an enforced guarantee to a suggestion. The fourth is the context graph
  (`knowledge/findings.jsonl`, `docs/KNOWLEDGE.md`) — queried rather than
  carried, so it holds what is worth knowing *sometimes* rather than what is
  worth saying every time. It is the weakest of the four, and
  `remember --destination` plus the monthly sweep exist to keep a lesson from
  settling there when one of the first three could hold it.

- **There is no database, and the reason is a measurement.** The context graph
  is three append-only JSONL files rebuilt in memory on every call: 2,000
  findings cost 43ms to build and 37ms to search, so an index would buy a
  staleness bug and nothing else. Two consequences are load-bearing rather than
  incidental. Concurrency is handled by *not having a lock* — one `O_APPEND`
  write of one line under the pipe buffer is atomic, which is why
  `MAX_LINE_BYTES` refuses an over-long line instead of truncating it, and why
  the concurrency test drives ten real processes rather than threads. And that
  atomicity, exactly like SQLite's locking, holds only on a **local**
  filesystem: never put this checkout on NFS or SMB. Revisit the whole decision
  when `recall --usage` measures a p95 past ~250ms — not before, and not on
  anybody's estimate including this one.

- **A context surface is queried, never loaded.** The findings never enter a
  prompt; six lines saying a `recall` tool exists do. Anything an agent reads on
  every task is paid for on every task, so a surface that returns everything it
  knows costs more as the factory learns more — which is backwards, and is how a
  knowledge base ends up switched off. `recall` returns a few one-line hits
  under a character budget and says how many it left; `detail` opens exactly
  one. Knowledge growing must make the answers better, never bigger. The
  corollary is that the *tool schema* grows by measurement too: `recall
  --usage` records every query and, above all, every one that came back empty —
  which is both the list of findings worth writing and the evidence for which
  filter has earned a place in the schema every task pays for.

- **A finding carries the date it was observed, and a belief that changes is
  superseded rather than edited.** `observed_at` is when the thing happened and
  is not the day it was typed up; staleness is measured from it, or from the
  last time somebody confirmed it. A stale finding is still returned and
  labelled, because it may be the only thing anybody knows. A finding that
  stopped being true gets a `superseded_by` edge to the one that replaced it and
  both lines stay, so looking up an old id says what the belief moved to instead
  of returning nothing.

- **Silence is a failure mode, so something has to watch for absence.** A night
  that never ran looks exactly like a quiet night: both produce nothing. That is
  why `docs/OBSERVABILITY.md` makes `count_over_time(...[24h])` the first panel
  and the thing to alert on. This is the second sighting of the rule — the first
  project's backup drill needed a separate job to notice the drill had stopped —
  so by the rule below it now lives here. Third sighting:
  `watermill review --check`, which fails when the monthly knowledge sweep has
  stopped running, because a sweep nobody ran and a month with nothing to review
  produce identical output.

- **Anything that talks to a third party stays off the run loop.** `ship` is its
  own command with its own exit code, so a Loki outage cannot hang a night or
  leave a task claimed while a socket times out. Its high-water mark advances
  only after a push returned; there is no retry queue, because the history is
  still on disk and `--resend` exists. `land` is the second sighting: opening a
  pull request and waiting on CI is somebody else's build queue, and a night
  that blocked on it would hold a claimed task open across the outage.

- **A check that gates a decision runs before it, or it is decoration.** The
  gate runs before the work is kept; `review.verify` runs before the merge, and
  `land` never calls `merge` after a failed `verify` whatever the forge says
  about mergeability. `review.merge` without `review.verify` is refused at
  parse time rather than at 3am, so the dangerous combination is
  unrepresentable rather than merely discouraged.

- **A closed task says what closed it.** Every discard left a comment
  explaining itself and every success left nothing, so the queue held a
  complete record of the work this factory threw away and none of the work it
  kept -- the commit lived only in the ledger, in a repository the project
  cannot see. `WorkQueue.can_comment` exists because `comment()` returns False
  both for a project that declared no comment command and for a declared one
  that failed, and treating those the same means choosing between a false
  alarm everywhere and silence where it matters.

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


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
