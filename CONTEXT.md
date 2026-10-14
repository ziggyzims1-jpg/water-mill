# Water Mill

A multi-project orchestrator for supervised and unattended agent work: it claims
a task from a project's queue, hands it to an agent, independently verifies what
reached the repository, and writes down what happened. This glossary is the
vocabulary the code, the docs and the crew agents share; where a term has a
longer treatment, the doc is named.

## Work and its queue

**Bead**:
One task in a project's `bd` (beads) tracker, with an id such as `water-mill-fwm.6`. The unit of work the crew takes: one bead in, one pull request out.
_Avoid_: ticket, issue, task (task means a bead as the engine claims it, see below)

**Epic**:
A bead of type `epic` that groups child beads and states the owner's settled decisions for them. It is never itself worked or enrolled in a trial.
_Avoid_: milestone, project

**Task**:
A bead as the run loop sees it once claimed: one attempt, with one line in `runs/tasks.jsonl`.
_Avoid_: job, work item

**Queue**:
A project's ready beads, read through the commands in the contract's `queue.*` block.
_Avoid_: backlog, board

**Out of scope**:
The section of a bead that an implementer must obey exactly; a file marked READ ONLY there is never modified.
_Avoid_: non-goals

**Auto-mill bead**:
A bead sluice files, labelled `auto-mill`, P3, for a clearly-defined smell (file, smell, concrete fix), which the orchestrator then runs through the full crew. Limits in ADR-0002.
_Avoid_: follow-up, tech-debt ticket

## The crew

**Crew**:
The four agents that take a bead to a landed change, in order: millstone, bolter, sluice, tailrace. Their master definitions live in `canon/common/.claude/agents/`.
_Avoid_: team, pipeline

**Millstone**:
The implementer. Works one bead in its own git worktree, tests at seams, opens one pull request and writes the first handoff section.
_Avoid_: builder, coder

**Bolter**:
The standards reviewer. Report-only: checks the diff against `CODING_STANDARDS.md`, `docs/adr/`, `CONTEXT.md` and a smell baseline, and never pushes; only a broken documented standard blocks.
_Avoid_: linter, style reviewer

**Sluice**:
The spec reviewer. Verifies the PR against its bead independently, handles bolter's blocking findings, and is the only reviewer that pushes fixes to the branch.
_Avoid_: reviewer (ambiguous with bolter), QA

**Tailrace**:
The lander. Verifies one approved PR in CI, squash-merges it, closes its bead and marks the handoff `**LANDED**`. Merges run one at a time.
_Avoid_: merger, releaser

**Orchestrator**:
The top-level session that spawns the crew, carries its handoffs and bead changes to main, and decides when an agent reports BLOCKED. Not an agent definition.
_Avoid_: lead, coordinator

**Handoff**:
The note an agent writes before signing off, per bead at `HANDOFF-mill/<slug>.md` in this repo, saying where things stand and above all what failed. On the laptop never part of the PR; in cloud mode committed on the session branch and carried by the orchestrator's session docs PR.
_Avoid_: summary, status report

**BLOCKED**:
The state an agent reports when a tool call is denied or the task cannot be done within scope; it quotes the denial verbatim and never retries or routes around it.
_Avoid_: stuck, failed

**Seam**:
The public boundary where a test observes behaviour: a CLI command, a public function, a route. The millstone lists the seams it chose in the PR body and handoff.
_Avoid_: interface, unit

**Red before green**:
Evidence in the PR body that the new tests fail on the base without the change; a docs-only PR says "docs-only" instead.
_Avoid_: TDD proof

## Safety model

**Gate**:
`commands.gate` in the contract: the one command that decides whether work is kept, run twice per task and identical to what CI runs. For this repo, `make verify`.
_Avoid_: tests, CI check

**Fence**:
`fence.paths` in the contract: paths an agent may not change, named in the prompt and checked against the diff after it exits. A task that touches one has its work discarded.
_Avoid_: blocklist, protected files

**Contract**:
A project's `watermill.yaml` (or a vendored `projects/<name>.yaml`): the only coupling surface between a project and the factory. Spec in `docs/CONTRACT.md`.
_Avoid_: config, manifest

**Caps**:
The six limits on a run (task attempts, wall clock, consecutive failures, per-task timeout, unmetered tasks, spend), checked between tasks and never during one.
_Avoid_: quotas, budgets

**Refusal**:
A precondition did not hold and nothing was modified (exit 3). Distinct from a **failure**: work was attempted and did not land (exit 1).
_Avoid_: error

**Preflight**:
Everything that must hold before a run starts; a failed preflight touches nothing.
_Avoid_: setup check

**Git guardrail**:
A `PreToolUse` hook on Bash that denies `git stash` (every form), `reset --hard`, `clean -f`, `branch -D`, `checkout .`, `restore .` and forced pushes.
_Avoid_: git hook (that means a `.git/hooks` script)

**Ramp**:
The schedule of raising caps night by night (5, 8, 15 tasks), halted by any revert.
_Avoid_: rollout

**Integration (gated)**:
An external-provider module, fenced by default and ungated only after a human wires it, proves it live and files a wiring record. Policy in `docs/policies/INTEGRATIONS.md`.
_Avoid_: connector, plugin

**Wiring record**:
`docs/integrations/<provider>.md` in a cell: the human proof that one integration works on the target.
_Avoid_: setup note

## Projects and distribution

**Project**:
A repository the factory drives, registered in `projects.yaml`.
_Avoid_: repo (when meaning a registered target), client

**Cell**:
A client project stamped from `watermill-cell-template` and named `<project>-cell-<n>`.
_Avoid_: instance, tenant

**Stamp**:
To create a new cell from the cell template GitHub repo.
_Avoid_: scaffold, fork

**Workshop**:
`~/Documents/code`, the non-git folder holding the repos and a shared `.claude/`; reachable only from the laptop.
_Avoid_: monorepo, root

**Canon**:
The `canon/` folder: the one master of every file projects share (crew agents, skills, the guardrail hook, managed settings entries, the workshop `CLAUDE.md`).
_Avoid_: templates, shared config

**Sync**:
`watermill sync <project>`: opens a CI-gated PR per repo that renders canon into it (workshop directly) and merges only its own marked entries into `.claude/settings.json`. `validate` fails on drift.
_Avoid_: deploy, push

**Managed header**:
The "managed by water-mill" line on a synced file, meaning edit canon, never the copy.
_Avoid_: generated marker

**Skill**:
A `SKILL.md` instruction set adapted from mattpocock-skills 1.2.3 for beads and delivered through canon.
_Avoid_: plugin, prompt

## Knowledge and records

**Finding**:
One line in `knowledge/findings.jsonl`: something learned, with the date it was observed, a cause and tags. A changed belief is superseded, never edited.
_Avoid_: note, memory

**Lesson**:
The most common kind of finding: a sentence that is always true about a trap or convention. Promoted into Water Mill only after appearing in two repositories.
_Avoid_: tip, learning

**Context graph**:
The findings plus the run and task logs, rebuilt in memory on every call and queried by `recall`, never loaded into a prompt.
_Avoid_: knowledge graph, knowledge base, database

**Recall**:
`watermill recall`: the one budgeted query over the graph, returning a few one-line hits; `--detail <id>` opens one.
_Avoid_: search

**Destination**:
Where a lesson belongs: the gate, `fence.paths`, `notes` in the contract, or the graph, strongest first.
_Avoid_: category

**Root cause**:
The bucket a person assigns to a task after it went wrong. A machine may offer a hint, never for `gate-hole`, `none` or `agent-error`.
_Avoid_: reason

**Agent run**:
One unit of agent work of any kind, one line in `runs/agents.jsonl`; the agent's own sign-off facts are one tracked line in `knowledge/agent-runs/` (`agents record`).
_Avoid_: session, job

**Run**:
One engine invocation over a queue, with its log under `runs/`. Gitignored and never pruned automatically.
_Avoid_: night (a night is a scheduled run)

**Ledger**:
An append-only JSONL history: `runs/index.jsonl` (runs), `runs/tasks.jsonl` (tasks), or the trial ledger `knowledge/trial/ledger.jsonl`.
_Avoid_: log (a log is the free-form per-run output)

**Knowledge sweep**:
The monthly `watermill review` of the graph; `review --check` fails when it stopped happening. Not `watermill agents sweep`, which backfills `runs/agents.jsonl` with mill crew history.
_Avoid_: audit, sweep (alone)

## Trial

**Trial**:
The pre-registered comparison of the crew against one default Claude on the same randomised beads. Protocol in `docs/TRIAL.md`.
_Avoid_: experiment, A/B test

**Arm**:
One side of the trial: A is the crew, B is a solo default Claude with no review agent. Assigned by balanced blocks of four per repo from a logged seed.
_Avoid_: group, variant

**Enrol**:
To enter a bead in the trial ledger and label it `trial:A` or `trial:B` before any work starts. Never re-randomised.
_Avoid_: assign, sign up

**Escape**:
A defect in landed work found within 14 days of landing; the primary outcome counts beads with a bug-or-worse escape.
_Avoid_: regression

**Harm stop**:
The pre-registered pause triggered by one landed blocker-class defect or an arm B breach of the fence, judged on that defect alone and never on counts.
_Avoid_: early stopping

## Other terms

**Land**:
Create, verify, merge a pull request (`watermill land`, or tailrace by hand). Never part of a run.
_Avoid_: ship (ship means sending logs to Loki)

**Ship**:
`watermill ship`: push run history to Loki. A reader, never part of a run.
_Avoid_: deploy

**Publish**:
`watermill publish`: PUT a status snapshot of every project to Zimmy. A reader; unknown is omitted, never zeroed.
_Avoid_: report

**Session branch**:
In a Claude Code cloud session, the one `claude/...` branch the session may push; it is the PR head for every bead.
_Avoid_: feature branch

**Cloud mode**:
Running the crew in a Claude Code cloud session (`CLAUDE_CODE_REMOTE=true`): REST-only GitHub, beads travelling as `issues.jsonl` commits, handoffs committed.
_Avoid_: remote mode
