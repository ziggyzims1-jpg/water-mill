# The context graph

Everything the factory has learned, in one place an agent can query while it is
working.

```bash
watermill recall "gate fails on a clean checkout"   # ask it
watermill recall --detail f-20260828-a1b2           # open one answer
watermill remember zimmy-life-tracker lesson "..."  # record a finding
watermill review                                    # the monthly sweep
```

The mechanical history was always written down -- `runs/index.jsonl` has the
runs, `runs/tasks.jsonl` the tasks and their root causes. What did not exist was
a way for the thing actually doing the work to ask **has this bitten anyone here
before**, at the moment it has the file open rather than twenty minutes earlier
when the prompt was assembled.

## The shape of it

| | |
|---|---|
| Sources of truth | `knowledge/findings.jsonl` (committed), `runs/tasks.jsonl`, `runs/index.jsonl` |
| The graph | Built in memory on every call by `watermill/recall.py`. No index, no cache, nothing to invalidate |
| Read by | `watermill recall`, and the agent's `recall` tool over MCP |
| Written by | `watermill remember` / `confirm` / `annotate-finding` (a person), the `propose` tool (an agent, quarantined) |
| Reviewed by | `watermill review`, monthly |

Findings are **committed to this repository**; run history is not. That split is
deliberate. The mechanical history is large, machine-written and local to
whichever machine ran the night -- it ships to Loki and stays in `runs/`.
Findings are small, hand-written, and the most valuable thing this factory
produces, so they live in git where they are diffable, reviewable, and present
in every checkout.

## It is queried, never loaded

This is the design constraint everything else follows from, and it is about
cost. The graph reaches an agent's context, and a context surface that returns
everything it has costs tokens on every task forever, gets *worse* as the
factory learns more, and is the reason a knowledge base ends up switched off.

So:

- the prompt carries **no findings at all** -- only six lines saying the tool
  exists (`agent.RECALL_BLOCK`);
- `recall` returns a handful of one-line hits under a hard character budget
  (`DEFAULT_LIMIT` 5, `MAX_LIMIT` 20, `BUDGET_CHARS` 1200) and says how many it
  left rather than returning them;
- `detail` opens exactly one hit, and is the only call that returns long text.

Knowledge growing must make the answers **better, never bigger**. There is a
test for each of those three, because a retrieval layer fails silently in
exactly this direction.

Two filters exist on the command line and deliberately **not** in the agent's
tool schema:

```bash
watermill recall "fence" --since 2026-06-01 --cause gate-hole
```

Free text is the right surface for somebody with a problem in front of them; a
date window and a root-cause bucket are what somebody *auditing* the graph
wants. Every parameter added to the tool is paid for in the prompt on every
task, so what goes in there is decided by measurement rather than by guess --
see **What the tool was asked** below.

## Every finding carries a date

Two of them, and they are different questions:

- `observed_at` -- when the thing happened. Set it with `--on` when you are
  writing up something from last month; a lesson learned in March and typed up
  in August is five months old, not one day old.
- `recorded_at` -- when the line was written. Never used for staleness.

Age is measured from the most recent date anybody vouched for the finding --
`observed_at`, or the last `confirm`. Past `REVIEW_AFTER_DAYS` (90) it is
**stale**: still returned, weighed down in the ranking, and labelled in every
answer. Stale is not wrong; it means nobody has looked lately, and hiding it
would throw away the only thing anybody knows on a subject.

## Superseding, when the world changes

A finding that stops being true is not edited and not deleted. It is replaced:

```bash
watermill remember zimmy-life-tracker lesson "HiGHS is the solver; the academic licence lapsed." \
    --supersedes f-20260301-9c1a --why "licence expired 2026-08"
```

The old line stays in the file, gains a `superseded_by` edge, and stops being
returned by `recall`. Looking it up by id still works and says what replaced it
-- somebody arriving with an old id has to be told the belief moved, or they
will conclude the factory never knew it.

That is the same rule as the ledger and the task log: **a correction is a new
line, never an edit.** A store that can be edited is one whose history can be
quietly improved.

## Structure: a cause and a tag, required, and fillable later

`remember` and the agent's `propose` tool refuse a finding with no root cause
(`tasklog.ROOT_CAUSES`; `none` is an explicit answer, blank is not) or no tag.
An untagged finding with no cause can be found only by its words, which is the
one way the graph is not supposed to be reached.

**`pending` means "owner to judge."** It is accepted wherever a finding's cause
is (`remember`, `propose`, `annotate-finding`) and is deliberately *not* a root
cause: it is not in `tasklog.ROOT_CAUSES`, `watermill annotate` (the task log)
refuses it, and a finding whose merged cause is `pending` is listed under
**Missing structure** until the owner annotates it. Three buckets --
`none`, `gate-hole`, `agent-error` (`tasklog.HUMAN_ONLY`) -- are judgements only
a person may make, so the agent's `propose` tool refuses them and offers
`pending` or one of the specification buckets instead. Quarantine does not make
that safe: a guess in a judgement field is still read later as a judgement.
`remember` stays permissive because the owner uses it; crew agents that write
through it use `pending` rather than any `HUMAN_ONLY` bucket.

Findings written before that rule, and any whose cause turned out wrong, are
fixed by an **annotation line** -- a new `kind_of_line: "annotation"` carrying
`id` and any of `root_cause`, `tags`, `destination`, `by`. Nothing is edited:

```bash
watermill annotate-finding f-20260828-a1b2c3 --cause missing-context --tag fence --tag beads
watermill annotate-finding f-1 f-2 f-3 --cause none --tag housekeeping   # one set of flags
watermill annotate-finding --batch fixes.jsonl --json                     # or '-' for stdin
```

A batch is JSONL, one `{"id", "cause", "tags", "destination"}` per line. Every
row is checked against the store -- and against the line cap below -- before
the first line is written, so one bad row refuses the lot instead of leaving it
half applied. The command is `annotate-finding` because `annotate` is the task
log's verb for a task's root cause.

`read()`, `get()`, `recall` and the sweep see the **merged** finding: the latest
cause and the latest destination win, tags accumulate across the finding and
every annotation. Annotations are metadata -- they feed `--cause` filtering and
the sweep and do not appear in a recall hit, so the recall budget is unchanged.
They are bounded by the same 4096-byte `O_APPEND` cap as every other line.

## What an agent may write, and what happens to it

An agent's `propose` tool appends a finding **in quarantine**. It is never
returned to any agent -- not even the one that wrote it -- until a person
promotes it in the sweep:

```bash
watermill proposals                        # what is waiting
watermill proposals --promote f-...        # agents can now recall it
watermill proposals --reject f-... --why "not true"
```

A rejected proposal stays in the file and stays invisible: rejection is a
judgement, not a deletion, so the line survives and `recall` still will not
return it -- to an agent or to `--include-proposed`. `detail` on its id says it
was rejected rather than printing it as ordinary text, because an id in a
commit message outlives the decision behind it.

This is the task log's `hint`-versus-annotation boundary one level up. A machine
records what happened; only a person records why. A guess stored in the field a
judgement belongs in is worse than a blank, because it counts.

The provenance is stamped by the orchestrator, not claimed by the caller: the
cell, the run and the task come from the command line the engine built, so an
agent cannot file a finding against a project it is not working on.

## The monthly sweep

```bash
watermill review            # what needs a decision
watermill review --record   # say the sweep happened
watermill review --check    # exit 1 if the sweep is overdue, or a landed bead has no finding
watermill review --lag      # just the beads landed without a finding
```

Knowledge rots in a way code does not. A failing test announces itself; a
finding that quietly stopped being true keeps being returned, carries the same
confident date it always had, and is read by an agent as current. Nothing in the
system can notice that on its own -- the world changed, not the file.

The sweep is seven lists, and every one of them is a decision a person has to
make:

1. **Stale** -- 90+ days unconfirmed. `confirm` it or supersede it.
2. **Proposed** -- agent findings in quarantine. Promote or reject.
3. **Twice, in two cells** -- Water Mill's own filing rule, as a query. A lesson
   that has now appeared in a second repository is ready to be promoted into the
   orchestrator's doctrine.
4. **Still only advice** -- lessons that never became a gate check or a fence
   path. Advice is a request; a gate is not.
5. **Missing structure** -- active findings that still lack a root cause (or
   whose cause is still `pending`) or a tag after annotations are merged. Fix
   with `annotate-finding`.
6. **No root cause yet** -- discarded tasks nobody has annotated.
7. **Landed without a finding** -- beads whose handoff is marked `**LANDED**` in
   a registered checkout (`brain/handoffs/mill/*.md`, dated by the last
   `## Tailrace (date)` heading) that no active finding cites in `refs.tasks`.
   Ids are normalised, so `Zimmy Life Tracker-092` and `zimmy-life-tracker-092`
   are one bead; a bare slug (`092`) matches only on a finding filed against
   that cell, so cite the full id with `--task`. A handoff marked `**LANDED**`
   with no Tailrace date is listed as landed on an unknown date and is always
   overdue -- it is not skipped. A handoff that says `**Findings:** none -- <why>` is covered:
   deciding nothing was learned is a decision, silence is not. Only beads landed
   on or after 2026-10-05 count (`--lag-since`); earlier ones were caught up by
   hand. A checkout that is not on this machine is reported, not an error.

Nothing in it is automatic. Confirming a finding because the sweep suggested it
would be a clock resetting itself, which makes the whole staleness signal
meaningless.

**`--check` is the half that watches for absence.** It fails when the sweep is
overdue *and* when a bead landed more than 2 days ago (`--lag-days`) with no
finding, so the graph cannot fall behind the mill unnoticed. A monthly job that silently
stopped looks exactly like a month with nothing to review: both produce no
output. Same rule as the first project's backup-drill heartbeat and the Loki
`count_over_time(...[24h])` alert.

```cron
# 08:00 on the 1st -- the sweep to read
0 8 1 * *  cd /path/to/water-mill && ./bin/watermill review | mail -s "knowledge sweep" you
# 09:00 daily -- the alert that the sweep stopped happening
0 9 * * *  cd /path/to/water-mill && ./bin/watermill review --check
```

An empty factory is never overdue. An alert that fires on day one is one nobody
reads by day two.

## What the tool was asked

```bash
watermill recall --usage
watermill recall --usage --since 2026-08-01
```

The graph is the first thing here that costs tokens on every task whether or
not it earns them, and its failure modes are silent in both directions: an
agent that never calls the tool looks exactly like an agent whose questions
were all answered, and a tool that answers nothing looks exactly like a tool
nobody needed. So every call is logged to `runs/recall.jsonl` -- machine-written
telemetry, filed with the run history rather than with the findings.

Three things come out of it, and the third is the reason it exists:

1. **Was the tool called at all** -- the single unknown `--recall` exists to
   resolve, and it cannot be answered without reading a transcript.
2. **The hit rate** -- mostly-empty answers mean either a badly described tool
   or a genuinely empty graph, and those need opposite responses.
3. **The questions that came back empty** -- not a failure report. That is the
   factory telling you which findings to write next, in the agents' own words.
   It leads the sweep's tool section for that reason.

The log is never read by `recall` and never reaches an agent: a tool that could
see its own usage statistics would be a tool with an incentive.

It is also how the query surface grows. A filter earns a place in the tool
schema when the log shows agents asking for it in words -- not before, because
the schema is the one part of this feature with a cost on every task.

## Why there is no database

An obvious shape for this is SQLite: a nodes table, an edges table, FTS5 over
the finding text, and a read-only connection an agent can run arbitrary
`SELECT` against. It was considered and measured rather than assumed, and the
measurement is the argument:

> **2,000 findings: 43ms to build the whole graph in memory, 37ms to search
> it.** That is roughly a century of this factory's output, answered in under a
> tenth of a second, with no schema, no migration, no index to rebuild and
> nothing to invalidate.

Full-text search is not the thing a database would add -- `recall` already does
lexical search with IDF weighting and path-aware tokenization, which is what
gets you the entry node before the edges get you the rest. What a database
would add is a *second* representation of data whose truth lives in three JSONL
files, and a cache that can be stale is a class of bug this design does not
currently have.

**The threshold is a measurement, not an opinion.** Revisit it when `recall
--usage` shows a p95 above ~250ms, or when the graph outgrows memory. Both are
observable; neither is true today.

### The two SQLite hazards, and what replaces them

The advice for a SQLite version of this would be right, and both problems are
real. They are worth writing down because *this* design has to answer them too:

**Multiple writers.** Two agents can be working two tasks at once. SQLite's
answer is WAL mode and a busy timeout. This store's answer is that there is
nothing to lock: a write is one `O_APPEND` write of one line, and a write under
the pipe buffer is atomic, so concurrent appends interleave whole lines. No
lock, no busy timeout, and no `database is locked` mid-task. `MAX_LINE_BYTES`
(4096) is what keeps that true, so an over-long finding is refused rather than
written -- and the bound is enforced in `_append`, covering every writer
including the free-text `note` on a supersession.
`test_concurrent_writers_do_not_lose_or_corrupt_a_line` drives ten real
processes at it, because the guarantee is the kernel's rather than the GIL's
and a thread pool would prove nothing.

**Network mounts.** `O_APPEND` atomicity is a property of *local* filesystems,
exactly as SQLite's locking is. `knowledge/` lives in the git checkout beside
the code, which is local wherever the factory runs. **Do not put the checkout
on NFS or SMB.** That is the one deployment that would need a real database, or
a small local API in front of this one -- and it would be the reason to build
it, rather than the retrieval cost.

## Where a lesson should actually go

This graph is the **fourth** destination, and the weakest. In descending order
of worth:

1. **The gate** -- a check that fails on the mistake. Cannot be ignored.
2. **`fence.paths`** -- checked against the diff, so it holds whatever the agent
   believed it was doing.
3. **`notes` in the contract** -- advisory, in the prompt, capped at 20.
4. **A finding here** -- queryable, dated, cross-cell.

A rule that can be mechanised must not be filed as a finding. `remember
--destination gate|fence|note|record` records where a lesson actually went, and
the sweep names every lesson that never went anywhere, every month, until
somebody either mechanises it or says why it cannot be.

## Wiring it to a run

The contract decides, and the command line overrides it for one run:

```yaml
knowledge:
  recall: true      # off for a new contract until a supervised run has proven the seam
```

```bash
./bin/watermill run zimmy-life-tracker --max-spend 5 --max-tasks 1 --supervised --recall     # on, whatever the contract says
./bin/watermill run zimmy-life-tracker --max-spend 5 --max-tasks 1 --supervised --no-recall  # off, whatever the contract says
```

`run` prints `recall: on (contract)` or `recall: off (command line)` at the top
so a log says which it was. `zimmy-life-tracker` has it on since 2026-08-30.

With `--recall` the engine writes an MCP config into **the run's own log
directory** -- never into the target repository, where it would show up in `git
status` and get the task discarded for leaving the tree dirty -- and appends
`--mcp-config ... --allowedTools mcp__watermill__*` to the agent command. The
prompt is then built from what actually got wired, so it never advertises a tool
that is not there.

**This seam met a real agent on 2026-08-30** (run `20260830-090740`), and the
first attempt failed exactly the way the paragraph below predicted: the global
`--root` was placed after the `mcp` subcommand, argparse exited before the
handshake, and the agent reported `CONNECTION_CLOSED`. Fixed in the same
review; the re-run recorded one `recall` call and one proposal. The
`grep -c mcp__watermill` check on the task JSON returns 0 on a successful run
(`--output-format json` keeps only the final result) -- `recall --usage` is the
detector. The paragraph stays because the posture was right: that is the same
status `land` had before it met a real forge and found a bug on its
first attempt. Run it supervised, on one task, and read
`runs/<project>/<run>/tasks/<task>.json` for whether the tool was called at all.

It is also the one third-party-shaped thing that is deliberately **on** the run
loop, which is only acceptable because there is nothing on the other end of it:
every call is a local file read, with no network and no port.
