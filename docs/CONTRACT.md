# The project contract

One file, `watermill.yaml`, in the target repository. It is the **entire**
coupling surface between the factory and a project — Water Mill knows nothing
else about it — and it is deliberately small enough to read in one screen.

`./bin/watermill init <path>` writes a commented starter. This document explains
the decisions behind it.

## Two rules that shape everything below

**Unknown keys are refused, not ignored.** A typo in `fence` means the run
believes it has a fence and does not. Every misspelling caught at load time is
one that cannot become a silent absence at 3am, so validation is strict and
total: the whole contract parses, or none of it applies. There is no partial
load, because a half-read contract is exactly how a fence ends up empty.

**Only three fields are required, and everything else defaults conservatively.**
A project that cannot yet answer a question gets the careful answer rather than
a blank. `git.target` defaults to `branch` and not `direct`; the queue defaults
to disabled; the fence defaults to empty *and says so* in `validate` and in
every preflight.

## Where it lives

A contract belongs **in the target repository**, so it travels with the code it
describes and a change to the project's gate arrives in the same commit as the
change to its Makefile.

Until a project carries one, the registry may point at a vendored copy under
`projects/`. That is how a repository gets driven before anyone has changed a
line in it. **The project's own file always wins**, so a stale vendored copy can
never silently override a real one.

## Fields

### `name` — required

Must match the registry entry. The name attributes a run, a log directory and a
ledger entry, so a mismatch is refused rather than reconciled.

### `description` — optional

One or two sentences, printed in reports. It is for the person reading at
7am who drives four projects and needs to remember which is which — it is
**not** sent to the agent. What the agent should know goes in `notes`.

### `commands.gate` — required

The merge gate. The one command whose result decides whether a task's work is
kept, run twice per task: once on unmodified code, once after the agent.

It must be **the same command CI runs**. A gate that differs from CI is two
gates, and the weaker one is the one an agent will satisfy.

### `commands.backup_check` — optional, and the most important optional field

Must exit zero when a restore has been **verified** recently — not when a
backup file exists. A backup nobody has restored is a hypothesis.

A project without one is allowed to run, because refusing outright would stop
anyone adopting the factory. Preflight says so every time, and so does
`validate`. See [SAFETY.md](SAFETY.md#3-the-backup).

`backup_run` is **display only**: it is printed in the refusal so the operator
knows what to run. It is never executed, so it may be a shell compound like
`make backup && make drill` that would not survive `shlex` splitting.

### `git.base_branch` — required · `git.target` · `git.remote`

`branch` opens `watermill/<run-id>` and pushes it. `direct` commits onto
`base_branch`.

**Start on `branch`.** `direct` is the right answer for a mature project with a
strong gate, a verified restore and a cheap revert — but a project the factory
has never driven has demonstrated none of the three.

### `queue.*`

Six shell commands and a JSON shape. `ready` and `stale` must emit JSON: a list
of objects, or an object wrapping one under `issues`/`items`/`results`.

Parsing a rendered table is refused, and that is not stylistic. It produced two
silent bugs in the previous version of this loop:

- `bd ready | grep -q` is a race under `pipefail`. `grep -q` closes the pipe on
  its first match, `bd` takes SIGPIPE, the pipeline reports failure — and the
  loop concluded there was no work while 27 tasks sat in the queue.
- Filtering epics out by matching rendered text matched a column the tool does
  not print, so every epic was handed to the agent as work and silently did
  nothing.

Both disappear when the queue speaks JSON with a type on every row, which is
what `exclude_types` reads.

Command templates take `{id}` and `{text}`. **Substitution happens after
splitting**, so a task id or a comment body containing a space, a quote or a
semicolon becomes one argument rather than shell syntax. No shell is involved at
any point.

`kind: none` disables the queue — what a project uses while a human still hands
it one task at a time.

### `fence.paths`

Paths a task may never modify. Named in the agent's prompt **and** checked
against the diff afterwards. An instruction is a request; a diff is evidence.

Patterns are `fnmatch` globs against repository-relative paths, plus a directory
shorthand: a pattern ending in `/` matches everything beneath it. Absolute
patterns are refused.

What belongs here: the gate and anything that could weaken it, the schema and
migrations, whatever encodes the project's hardest-won decisions, the backup
scripts, and `watermill.yaml` itself.

### `notes` — optional

Advice carried into the agent's prompt. **The only field in this file that is
not a mechanism**, and the boundary is the important part.

Everything else here is checked: the gate re-runs, the fence is tested against
the diff, a cap halts the loop. A note is a request. So:

**A rule that can be mechanised does not belong here.** "Never edit `db.py`" is
a `fence.paths` entry. Writing it as a note instead converts an enforced
guarantee into a suggestion the agent may reasonably weigh against the task in
front of it — and the prompt already tells it the task wins where the two
disagree.

**A note earns its place by having cost something.** These are written after a
task went wrong, not guessed before one is attempted. What belongs here is what
no mechanism can express: where a project keeps a thing, which of two plausible
idioms it actually uses, the trap a reasonable agent falls into precisely
because it is reasonable.

```yaml
notes:
  - Integration fixtures live in tests/fixtures, not tests/data. The second
    path exists and holds something else.
  - The dev server holds port 5173; the gate reads a stale build if it is
    still running.
```

Capped at 20 entries of 500 characters, and the cap is doing a job: a prompt
the agent skims teaches it nothing while costing every task in the run. When the
list is full, the answer is not a longer list — it is to promote a note into the
gate or the fence, where it stops being advice.

A single string is accepted as one note, which is what a YAML block scalar
produces. Newlines inside a note are collapsed, because each one renders as a
bullet.

Where they come from: [CALIBRATION.md](CALIBRATION.md).

### `environment.forbid_env` · `environment.min_free_gb`

`forbid_env` refuses the run when a named variable holds a named value. The
common markers — `FLASK_ENV`, `NODE_ENV`, `APP_ENV`, `ENVIRONMENT`, `RAILS_ENV`
set to `production` — are checked already; add anything else the project uses.
`DATABASE_URL` is refused when it does not look local.

`min_free_gb` refuses on a full disk, because a gate that fails for want of
space is indistinguishable from a gate that fails for the code — and the run
would read it as the agent's fault, spend a failure against the cap, and try
again.

### `caps.*`

Per-project overrides of the platform defaults (15 tasks, 6 hours, 3 consecutive
failures, 30-minute task timeout, 3 unmetered tasks). Omitting one means **no
opinion**, not zero.

**The spend ceiling is deliberately not here.** It is an operator decision made
per run with `--max-spend`, because a ceiling checked into a repository is one
nobody re-reads before the night it matters. Putting `max_spend_usd` in a
contract is refused with that explanation.

## Precedence

Caps resolve in three layers, later winning, and `None` never overriding:

    platform defaults  ->  the contract  ->  the command line

## Checking your work

```bash
./bin/watermill validate <project>   # does it parse, and what did it actually say
./bin/watermill doctor <project>     # would a run be allowed to start
./bin/watermill doctor --gate        # ...including the project's own gate
```

`validate` prints the fence size and warns when it is zero, and warns when there
is no `backup_check`. Both warnings are worth acting on before a first run.
