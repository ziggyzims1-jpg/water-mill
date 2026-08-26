# Handoff — Water Mill as the AI Software Factory

**Written:** 2026-08-26 · **Branch:** `claude/chat-session-6rmwhn` — **merged
to `main` as #1** · **Gate:** `make verify` green — ruff + 132 tests, ~17s

Read `docs/STATUS.md` first — it is the live position and this file is a
snapshot. Then `CLAUDE.md`, then `docs/SAFETY.md`.

> **Amended 2026-08-26 (second session).** Three corrections, all of them
> divergences between what a document claimed and what was true:
>
> 1. **The gate could not run from a clean checkout.** `make install` populated
>    `.venv`, and `lint`, `test`, `test-fast` and `doctor` all ran `python3` —
>    the *system* interpreter. CI hid it by pip-installing into the system
>    Python instead of running `make install`, so CI was green while
>    `make install && make verify` failed on a clean clone with
>    `No module named ruff`. Every gate target now runs `$(VENV_PY)`, `guard`
>    refuses and names the fix when the venv is absent, and CI runs
>    `make install`. The 132-test green run above was real; the wiring around it
>    was not. **The lesson is the repo's own:** a gate that is only ever run in
>    one environment is a gate that has only been tested in one environment.
> 2. **`README.md` said 123 tests.** There are 132.
> 3. **The two-loops decision (open decision #1) is half-closed.** Zimmy's
>    `LOOP.md`, `CLAUDE.md` and `scripts/loop.sh` now all say Water Mill
>    supersedes the bash loop. Deleting `loop.sh` is still yours.
>
> Also added: `docs/PLAN.md` (the business plan, now under version control and
> reconciled against reality as v2.1) and `docs/STATUS.md` (the position).

---

## Where things stand in one paragraph

Zimmy Life Tracker's PR #91 built an autonomous-agent apparatus *inside the
product* — corpus, invariants, backups, Beads, `brain/`, a 47-task backlog, and
a 590-line bash overnight loop. **That PR is now merged** (`4771298`, released
as 4.4.0). This session extracted the portable half into **Water Mill**, a
repo-agnostic multi-project orchestrator, and registered Zimmy as target #1.
Water Mill is built, tested and pushed; it has **never driven a real agent**.
The next step is supervised calibration, and it needs a human watching.

---

## What Water Mill is

An orchestrator that claims a task from a project's queue, hands it to a fresh
agent invocation, then **independently verifies what reached the repository** —
re-runs the project's gate, checks the diff against a declared fence, checks the
tree is clean, checks the commit names the task. Anything failing is discarded
regardless of what the agent reported. Then it writes a report and appends to a
cross-project ledger.

It knows nothing about any project. Everything project-specific arrives through
a **contract**.

### The two-file model

| File | Lives | Says |
|---|---|---|
| `watermill.yaml` | in the **target repo** | gate command, git target, queue commands, fenced paths, environment guards, cap overrides |
| `projects.yaml` | in **water-mill** | which checkouts exist, where, enabled or not |

A contract describes a project; the registry describes the factory's
relationship to it. Until a project carries its own contract, the registry can
point at a vendored copy under `projects/` — **the project's own file always
wins**, so migrating it in later is a move and a delete with nothing to
reconcile.

### Three deliberate changes from PR #91's design

1. **The fence is enforced, not requested.** #91 fenced by prose in the agent
   prompt. Here the paths are declared once, named in the prompt *and* checked
   against `git diff --name-only` afterwards — staged, unstaged, untracked and
   committed, all four. An instruction is a request; a diff is evidence.
2. **The runner lives outside the tree it cleans.** #91's worst bug was the loop
   `git clean -fd`-ing its own untracked script away on a refused preflight. A
   factory in a sibling checkout makes that class of bug structurally
   impossible. `gitwork.discard()` additionally requires the caller to assert
   the run actually started.
3. **Python, not bash.** Two of #91's four loop bugs (the `pipefail`/`grep -q`
   SIGPIPE race, the five-minute SIGINT) disappear structurally. The *tests* for
   the other two were ported rather than trusting the rewrite.

---

## Repository map

```
water-mill/
├── bin/watermill              entry point, works without installation
├── watermill/
│   ├── contract.py            THE COUPLING SURFACE — read first
│   ├── registry.py            which repos the factory drives
│   ├── preflight.py           11 checks, cheapest first, stop at first refusal
│   ├── engine.py              the run loop: four decisions, one keeps anything
│   ├── caps.py                six caps + counting rules
│   ├── meter.py               cost/verdict from the agent's own JSON
│   ├── agent.py               the prompt (pure function)
│   ├── queue.py               six shell commands and a JSON shape
│   ├── gitwork.py             git, and a discard that refuses on the wrong path
│   ├── proc.py                process groups, no shell, streamed output
│   ├── report.py              the morning report (pure function)
│   ├── ledger.py              append-only cross-project history
│   └── scaffold/watermill.yaml  commented starter contract
├── projects/zimmy-life-tracker.yaml   vendored contract, 24 fenced paths
├── projects.yaml              the registry
├── docs/{SAFETY,CONTRACT,ONBOARDING,CALIBRATION}.md
├── tests/                     132 tests
├── Makefile                   make verify is the gate
└── runs/                      per-run logs. gitignored, never auto-pruned
```

### Commits on the branch

| SHA | What |
|---|---|
| `fa8f7e8` | Core: contract, registry, caps, meter, queue, proc, gitwork |
| `8ef683d` | Engine, preflight, report, ledger, CLI, 123 tests |
| `a3e9181` | Docs (safety/contract/onboarding/calibration), Makefile gate, CI |

---

## Zimmy's contract

`projects/zimmy-life-tracker.yaml`. Every value drawn from Zimmy's own
`CLAUDE.md`, `VERIFY.md`, `BACKUP.md` and `LOOP.md` rather than guessed.

| Field | Value | Why |
|---|---|---|
| `gate` | `make verify` | Exactly what `.github/workflows/verify.yml` runs |
| `backup_check` | `.venv/bin/python scripts/backup_drill.py --check-heartbeat` | A *verified restore*, not a backup file's existence |
| `base_branch` | `main` | |
| `target` | **`branch`** | Not `direct` yet — see open decisions |
| `queue` | beads, epics excluded | |
| `fence` | **24 paths** | All verified present on merged `main` |
| `caps` | 5 tasks, 3 hours, 30m timeout | Night one of the ramp |

The fenced paths group into six reasons, each one something Zimmy already
learned the hard way:

- **The gate and anything that weakens it** — `Makefile`, `VERIFY.md`,
  `ruff.toml`, `.github/workflows/`, the vite and eslint configs
- **The schema** — `db.py`. An index in `SCHEMA` over a column `MIGRATIONS`
  adds passes 998 tests and crash-loops the Pi on the next restart
- **The consolidations** — `services/clock.py`, `services/streak_service.py`.
  Four disagreeing definitions of "today" became one module; re-introducing a
  local one is the exact regression they ended
- **Backup and restore** — the three `scripts/backup_*.py` and `BACKUP.md`. A
  guarded restore with no override flag is only guarded while nobody adds one
- **The invariants and corpus** — `tests/test_invariants.py`, `tests/corpus.py`,
  `scripts/gen_corpus.py`, `CORPUS.md`. A task that "fixes" a failing invariant
  has almost certainly found a real bug
- **Doctrine and the work graph** — `brain/`, `.beads/`, `AGENTS.md`,
  `CLAUDE.md`. Plus `routes/backup.py` (decides what a backup redacts),
  `services/mfa_service.py` and `config.py`

---

## What is verified, and what is not

### Verified
- `make verify` green: ruff clean, 132 tests, ~17s
- Contract parses; 24 fenced paths all exist on merged `main`
- Engine tested against **real git repositories with real subprocesses** — no
  mocking at that boundary, because that boundary is where #91's bugs lived
- Every cap triggered deliberately: task attempts, wall clock, consecutive
  failures, per-task timeout, spend, unmetered
- Every discard path: uncommitted work, commit without the task id, fenced path
  touched, gate broken, agent did nothing, agent crashed
- `test_a_refused_preflight_touches_nothing` — leaves an untracked file, refuses
  preflight, asserts the file survives

### NOT verified — say this out loud before an unattended night
- **Every cap was proven against a stub agent.** That tests control flow, not
  how a real agent behaves inside the loop. This is the honest caveat and it is
  why `README.md` and `CLAUDE.md` both say *not approved for unattended use*.
- **Water Mill has never run against Zimmy.** Not once, not supervised.
- **`bd` is not installed in the dev container**, so preflight refuses at the
  tooling check here. It must exist on whatever machine actually runs this.
- **Contrast/accessibility, offsite backup, and `brain/product.md`** are all
  still open on the Zimmy side.

---

## Two bugs the suite caught (in code written this session)

Worth knowing because both are the kind that pass review:

1. **Fence normalisation used `lstrip("./")`.** That takes a character *set*,
   not a prefix — so `.github/workflows/verify.yml` normalised to
   `github/workflows/...` and a fence over `.github/` matched nothing. Zimmy
   fences `.github/`, `.beads/` and `.claude/`; all three would have been
   unguarded while the contract said they were protected. Worse than declaring
   no fence, because nobody would check. Now `removeprefix`, with a regression
   test naming the consequence.
2. **Queue commands read a 40-line tail.** Truncated JSON does not parse as
   shorter JSON — it parses as a broken queue tool. Now `tail_lines=0` for
   anything the caller parses.

---

## Next steps, in order

### 1. Install `bd` and confirm preflight passes

```bash
cd water-mill
./bin/watermill validate zimmy-life-tracker
./bin/watermill doctor zimmy-life-tracker          # cheap: no gate
./bin/watermill doctor --gate zimmy-life-tracker   # the real thing, ~1m31s
```

Expect refusals on first contact. `docs/ONBOARDING.md` has a table of every
refusal and what it almost always means. The likely ones:

- `verified restore` — Zimmy's drill has not run recently.
  Fix: `cd ../zimmy-life-tracker && make backup drill`
- `stale claims` — a bead left `in_progress`.
  Fix: `./bin/watermill release zimmy-life-tracker <id>`
- `work available` — beads DB is not populated in this checkout. `.beads/dolt/`
  is gitignored; only `.beads/issues.jsonl` is committed, so a fresh clone needs
  `bd import` or equivalent before 47 tasks appear.

### 2. First supervised task

```bash
./bin/watermill run zimmy-life-tracker --max-spend 5 --max-tasks 1 --supervised
```

Read `runs/zimmy-life-tracker/<run-id>/REPORT.md` and the prompt that was
actually sent (`prompts/<task>.txt`). The prompt is the most common root cause
of a bad task and it is written to disk for exactly that reason.

### 3. Calibration — eight tasks, watched

`docs/CALIBRATION.md` has the empty table to fill in. What is being watched for
is **not** whether the code is right — the gate answers that without you. It is
*why* a task went wrong, sorted into one of: vague goal · incomplete file list ·
weak out-of-scope clause · task too large · missing context · gate hole · agent
error.

> **The finding that halts everything: work that passes `make verify` and is
> still wrong.** That means the gate has a hole, and no amount of better
> task-writing compensates. Calibration stops and the gate gets a new check
> before anything else proceeds.

Tasks 1–3 reveal most problems; 6–8 should be noticeably smoother. If they are
not, the template edits are not addressing the real causes.

### 4. Then, and only then

- Flip Zimmy's `git.target` from `branch` to `direct` — deliberately, as a
  decision, not by default
- One attended capped run (`--max-tasks 3`, watching)
- First unattended night at 5 tasks / 3 hours, then the ramp in
  `docs/SAFETY.md`

---

## Open decisions — yours, not the next session's

1. **Two loops now exist.** PR #91 merged `scripts/loop.sh` into Zimmy, and
   Water Mill's engine replaces it. Leaving both invites someone running the
   wrong one, and `LOOP.md` still documents the bash one as *the* loop. Options:
   delete `scripts/loop.sh` and repoint `LOOP.md` at Water Mill; or keep it as a
   fallback and say so loudly at the top of both files. **Recommendation:**
   delete it — a second path to production that nobody tests is how the fence
   gets bypassed. Not done this session because it is a change to Zimmy that you
   did not ask for.
2. **Offsite backup.** Still the open item from #91. Preflight enforces "a
   restore was verified"; it cannot enforce "the export left the machine". A
   mistake is recoverable; a dead SD card is not. My token cannot create the
   backup repo and it is outside this session's repo scope.
3. **`brain/product.md`** — eight unanswered questions. Question 4 settles the
   live contradiction between the Habits tab drawing streak numbers and the
   miss-check being built never to show them.
4. **A provider-side spend budget.** Water Mill's spend cap is *reactive*: it is
   checked between tasks, so it overshoots by up to one task (measured at $1.20
   against a $1.00 ceiling in #91). A budget at the provider is the only thing
   that stops an overrun outright, and costs nothing as a second backstop.
5. **Should Zimmy carry its own `watermill.yaml`?** Currently vendored in
   `projects/`. Move it into Zimmy once calibration proves the fence and gate
   are right — then a change to Zimmy's gate arrives in the same commit as the
   change to its Makefile.

---

## Things that would be easy to get wrong

Doctrine that took a bug to learn. Also in `CLAUDE.md`.

- **Refusal ≠ failure, and they have different exit codes.** Refusal is exit 3,
  nothing modified. Failure is exit 1, work attempted and not landed. A refusal
  every night is a configuration problem; a failure every night is a project
  problem.
- **Unknown keys in a contract are refused, never ignored.** A misspelled key is
  indistinguishable from a missing one once a run has started, and the missing
  one that matters is `fence`.
- **Nothing from a contract reaches a shell.** `shlex` split, run as argv,
  placeholders substituted *after* splitting so a task id is data not syntax.
- **`tail_lines=0` for anything you parse.** See bug #2 above.
- **Never `lstrip("./")` a path.** See bug #1 above.
- **The task cap counts attempts, not completions.** A completion cap never
  fires in a run where every task escalates — measured at 48 escalations
  against a limit of 1.
- **Caps are checked between tasks, never during one.** Halting mid-task risks a
  partial commit.
- **A step that cannot fail must not be part of a green result.** No `|| true`,
  no `-` prefixes, no `continue-on-error`. `make typecheck` exits non-zero on
  purpose.
- **Tests assert on what reached the repository** — the commit log, the working
  tree, the files on disk — never on what the orchestrator recorded about
  itself. The agent's exit code is not evidence and neither is ours.
- **A cleanup routine is the most dangerous code here**, because it runs on the
  paths nobody tested.

---

## Command reference

```bash
make install                       # .venv + deps
make verify                        # THE GATE: guard, ruff, 132 tests
make doctor                        # preflight every registered project

./bin/watermill projects           # what this factory drives
./bin/watermill validate [project] # does the contract parse, and what did it say
./bin/watermill doctor [project] [--gate]
./bin/watermill run <project> --max-spend N [--max-tasks N] [--supervised|--unattended]
./bin/watermill report <project> [run-id]
./bin/watermill status             # readiness + last run per project
./bin/watermill ledger [project]   # history across projects
./bin/watermill release <project> <task-id>
./bin/watermill init <path>        # write a starter contract into a project
./bin/watermill add <name> <path>  # register it here
```

`--max-spend` has **no default** and the run refuses without it. It is the only
cap that assumes the run is misbehaving, so it is the only one that fails closed.

`--unattended` refuses `--skip-gate` and `--skip-backup` outright. A skipped
baseline makes every later result in the run unattributable, which is acceptable
only while somebody is reading the diff.
