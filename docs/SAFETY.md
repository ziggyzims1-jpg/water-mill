# The safety model

What is actually protecting you, what is not, and which of the two a given
sentence in the interface is describing.

## The one-line version

> The loop is trustworthy because of what surrounds it, not because of what it
> contains.

The engine is about 500 lines and most of the interesting ones are refusals. If
the gate is weak, or the fence is empty, or the backup has never been restored,
then nothing in this repository makes an unattended run safe — it makes it
*fast*, which is worse.

## The five layers, in the order they were built

Each was in place before the thing that depends on it. That is not
chronological trivia; it is the argument for why any of it is trustworthy.

### 1. The gate

`commands.gate` in the contract. Water Mill runs it **twice per task**: once on
unmodified code before any work, and once after the agent finishes.

The baseline run is the one people want to skip and the one that matters most.
**A run that begins on a red baseline cannot distinguish its own damage from
damage that was already there**, which makes every commit it produces
unreviewable. `--unattended` refuses `--skip-gate` outright for that reason.

The gate must be *the same command CI runs*. A gate that differs from CI is two
gates, and the weaker one is the one the agent will satisfy.

### 2. The fence

`fence.paths` in the contract. Named in the agent's prompt **and** checked
against `git diff --name-only` after it exits.

Stating a fence in a prompt is a request. Checking it against the diff is
evidence. Water Mill does both, and only the second one decides whether work is
kept — a task that touches a fenced path has its work discarded whatever else
it did and however well it did it.

The check reads staged changes, unstaged changes, untracked files *and* the
commit. All four, deliberately: a check that reads only the working tree misses
what the agent already committed, and one that reads only the commit misses
what it left staged. Either miss turns the fence back into a request.

What belongs behind it: the gate and anything that could weaken it, the schema
and migrations, whatever encodes the project's hardest-won decisions, the
backup scripts, and the contract itself.

### 3. The backup

`commands.backup_check` must exit zero when a restore has been **verified**
recently — not when a backup file exists. Preflight refuses otherwise.

The distinction is the whole point. A backup nobody has restored is a
hypothesis. The first project this factory drives learned that concretely: its
restore drill failed on its first real run, and the failure was the drill's own
— it replayed migrations that were not purely schema, so it was *changing the
data* the next check then read, and reported the corruption it had caused as a
finding.

> A check that mutates its subject invalidates every check after it.

A project with no `backup_check` is allowed to run, because refusing outright
would stop anyone adopting the factory at all. Preflight says so every time, in
those words, and `watermill validate` repeats it.

### 4. The caps

Six, all in `watermill/caps.py`, all tested by being triggered deliberately.

| Cap | Default | Fails |
|---|---|---|
| Task attempts | 15 | open |
| Wall clock | 6h | open |
| Consecutive failures | 3 | open |
| Per-task timeout | 30m | open |
| Unmetered tasks | 3 | open |
| **Spend** | **none** | **closed** |

Three properties are worth knowing before trusting them.

**The task cap counts attempts, not completions.** A completion cap looks
equivalent and is not: in a run where every task escalates, `completed` never
increments, so the cap never fires and the run works through the entire queue.
Measured at 48 escalations against a limit of 1.

**Caps are checked between tasks, never during one.** Halting mid-task risks a
partial commit, which is worse than overshooting. So the spend cap is
*reactive* — it will exceed its ceiling by up to one task, and the per-task
timeout is what bounds by how much. **A provider-side budget is the only thing
that can stop an overrun outright**, and setting one as a second backstop costs
nothing.

**A meter that stops counting halts the run.** A crashed agent reports no cost.
Counting that as zero would be a lie in the direction that lets a run continue,
so it counts as unmetered, and past three the run stops. A run with no meter
looks cheap right up until the invoice.

### 5. Preflight

Eleven checks, cheapest first, stopping at the first refusal. See
`watermill/preflight.py` — every one names what to do about it.

**A refusal is not a failure.** Nothing has been modified, no claim has been
taken, no agent has been invoked. That distinction has its own exit code (3),
because a refusal repeated every night is a configuration problem and a failure
repeated every night is a project problem.

Untracked files count as a dirty tree. They are precisely what a `git clean`
destroys on the first failed task, so a run that starts with them present is a
run that will delete something nobody asked it to.

## What is deliberately *not* protecting you

Being clear about this matters more than the list above, because these are the
things it is easy to assume.

- **The agent's permission mode.** The default agent command accepts edits
  without prompting, because an unattended run has nobody to answer a prompt.
  The permission model is not what makes this safe; the fence, the gate and the
  discard are.
- **The agent's exit code.** Never treated as evidence. Neither is its summary.
- **Review.** With `git.target: direct` there is no merge step. The safety comes
  from the gate and the backup — and the corollary is that **the morning revert
  has to stay genuinely routine**. If reverting ever feels expensive enough to
  talk yourself out of, that is the signal to switch back to `branch`, not the
  signal to skim harder.

  `watermill land` and the `review.*` block do not change this. What they
  automate is the *mechanics* of a pull request — open it, wait for CI, merge
  it — and CI runs the same gate the run already ran twice. That is worth
  having: it proves the forge agrees with the local result, and it removes the
  step most likely to be skipped at the end of a long night. It is **not** a
  human reading the diff, and a green `land` is not evidence that anybody has.
  While the ramp is young, `--no-merge` is the honest setting: it opens the
  pull request, proves it green, and leaves the button to a person.
- **Stub-agent tests.** 126 of them, and they prove the orchestrator's control
  flow. They say nothing about how a real agent behaves inside it.
- **The context graph.** `--recall` gives the agent a tool that reads what this
  factory has learned (`docs/KNOWLEDGE.md`). It is *advice with a search box*,
  and advice is a request: nothing recalled is checked afterwards, nothing
  recalled can widen a task's scope, and the fence, the gate and the discard
  decide the outcome exactly as they did before. Two consequences worth stating.
  A finding is written by a person or proposed by an agent, so the text an agent
  reads may be text an agent wrote — which is why a proposal is quarantined
  until somebody promotes it, and why nothing in the store is ever treated as an
  instruction. And it is the only thing here that runs *during* a task, which is
  acceptable only because every call is a local file read: no network, no port,
  nothing on the other end that can be slow.
- **This document.** Doctrine that exists but does not load is decoration.

## The cleanup rule

> A cleanup routine is the most dangerous code in a program, because it runs on
> the paths nobody tested.

The previous version of this orchestrator ran `git clean -fd` on *every* exit
path — including a refused preflight, the one path where the tree was never the
run's to touch. On the first attempt ever made it deleted its own untracked
script and the run's logs.

So `gitwork.discard()` takes an explicit `run_started` argument and returns
without doing anything when it is False. It is not a convenience flag: it is the
caller asserting that this orchestrator put the changes there and therefore has
standing to remove them. `test_a_refused_preflight_touches_nothing` is the test,
and it asserts on an untracked file still being present afterwards.

## Recovering from a killed run

`kill -INT` (or Ctrl-C) is handled: the agent and its whole process group are
killed, the claim is released, uncommitted work is discarded and a partial
report is written.

Answering **`n` at a supervised run's prompt is not that** and must not be
routed through it. Ctrl-C means something is wrong, so it throws the in-flight
work away; `n` means that is enough for tonight, and every task already
committed stays committed. It ends the run through the ordinary path, so the
report, the ledger line and the task log are all written -- which they were
not while the prompt raised `KeyboardInterrupt`: the ordinary way to finish a
supervised run left the work in the repository and the run absent from
`watermill status` and from everything `watermill ship` sends onward.
`test_stopping_at_the_supervised_prompt_still_records_the_run` is the test.

`kill -KILL` cannot be trapped, so none of that runs. What it leaves is a dirty
tree, possibly a `watermill/<run-id>` branch checked out, and one task still
claimed. **All three block the next run at preflight** rather than being
inherited silently. Recover with:

```bash
cd <project>
git checkout -- . && git clean -fd
git checkout <base-branch>
watermill release <project> <task-id>
```

## The ramp

Conservative caps raised slowly beat aggressive caps tuned down after an
incident.

| Night | Tasks | Hours | Gate to continue |
|---|---|---|---|
| 1 | 5 | 3 | Zero reverts, report accurate |
| 2–3 | 8 | 4 | Zero reverts |
| 4–7 | 15 | 6 | Under 15% revert rate |

**Never raise a cap to compensate for a low task count.** If work is running
out, generate more tasks. **Any revert halts the ramp.**
