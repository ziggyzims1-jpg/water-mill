# Watching a night

Water Mill already writes everything worth trending. `runs/index.jsonl` is one
line per run and `runs/tasks.jsonl` is one line per task, both append-only, both
already JSON. `watermill ship` reads those two files and pushes what is new to
Loki, so Grafana can draw them.

```bash
export LOKI_URL=https://logs-prod-eu-west-0.grafana.net   # or http://pi:3100
export LOKI_USER=123456                                   # Grafana Cloud user id
export LOKI_TOKEN=glc_...                                 # omit both if self-hosted

./bin/watermill ship --dry-run    # print the payload, send nothing
./bin/watermill ship
```

Credentials are **environment, never the registry and never a contract** — the
same rule the Gurobi licence follows in the project this factory drives first. A
token checked in beside the thing it authenticates is one nobody re-reads before
the day it leaks.

## Shipping is not part of a run

It is a separate command with its own exit code, and that is the whole design.
A Loki outage, a wrong URL or an expired token must never hang the run loop,
fail a night, or leave a task claimed while a socket times out. This
orchestrator's one claim is that it is trustworthy about what reached the
repository; putting somebody else's HTTP endpoint on that path trades the thing
the program is for against a dashboard.

So run it *after* a night, or on its own timer:

```cron
30 3 * * *  cd /srv/water-mill && ./bin/watermill run zimmy --max-spend 5 --unattended
0  6 * * *  cd /srv/water-mill && ./bin/watermill ship
```

The high-water mark in `runs/.shipped.json` advances **only after a push
returned**, so a failed ship re-sends next time rather than losing the lines.
There is no retry queue and there should not be one — the history is on disk,
and `--resend` re-ships everything if a Loki instance is ever rebuilt.

## Labels are the part to get right

Three labels, and no more: `job`, `project`, `source` (`run` or `task`), plus
`outcome` on tasks. `run_id`, `task_id` and the rest are **refused as labels**
and live in the log line instead.

That is not fussiness. Every distinct combination of label values is one Loki
stream, and streams are the resource Loki actually runs out of — a label per run
creates a stream per run and degrades the install until it is unusable. The line
is JSON, so LogQL reads those fields with `| json` and loses nothing.

## Queries worth pinning

**Did last night happen at all.** The first panel to build, and the one to
alert on:

```logql
count_over_time({job="watermill", source="run"}[24h])
```

A night that silently did not run looks exactly like a quiet night — both
produce nothing. This is the same lesson the first project's backup drill
learned: a job whose success is invisible needs something *else* watching for
its absence. Alert when this hits zero, not when something looks wrong.

**Keep rate over the last week** — the number the ramp decision depends on:

```logql
sum(count_over_time({job="watermill", source="task", outcome="completed"}[7d]))
/
sum(count_over_time({job="watermill", source="task"}[7d]))
```

**Spend per project per night, in dollars:**

```logql
sum by (project) (
  sum_over_time({job="watermill", source="run"} | json | unwrap spend_cents [1d])
) / 100
```

**What actually went wrong**, once somebody has annotated it with
`watermill annotate`:

```logql
sum by (outcome) (count_over_time({job="watermill", source="task"}[7d]))
```

**Every escalation, readable:**

```logql
{job="watermill", source="task", outcome="escalated"}
  | json | line_format "{{.project}} {{.task_id}} — {{.title}}"
```

**Refused preflights**, which trend differently from failures and mean a
configuration problem rather than a project problem:

```logql
{job="watermill", source="run"} | json | refused="true"
```

## `runs/agents.jsonl`: every agent's work, one schema

`runs/tasks.jsonl` only gets a line when `watermill run` works a task. Crew work
dispatched from Claude Code sessions (millstone -> sluice -> tailrace through
the Agent tool) never reached it, so `runs/agents.jsonl` is the record that
does not care who dispatched the work. It is append-only and, like the rest of
`runs/`, gitignored. Beads `61r` (transcripts), `qam` (Loki) and `pu9` (compare)
build on this schema; the authoritative field list is the docstring of
`watermill/agentlog.py`.

```bash
./bin/watermill agents sweep --dry-run   # per-project counts, writes nothing
./bin/watermill agents sweep             # safe to cron
```

One JSON object per line. Envelope (every agent kind): `schema` (1), `key`
(stable identity, `crew:<bead id>`), `agent_kind` (`mill-crew` here), `source`,
`recorded_at`, `project`, `subject` (normalised bead id), `title`, `outcome`
(`landed` / `unlanded`), `started_at`, `ended_at`, `cost_usd`,
`duration_seconds`, `fields_inferred`, and a kind-specific `detail` object. For
`mill-crew`, `detail` holds `handoff`, `pr_number`, `landed_at`, `sluice_rounds`,
`sluice_verdict`, `sluice_pushed_fixes`, `findings_count`, `findings_waived` and
`bead_created_at`.

Rules that make it trustworthy:

- **Null, never a guess.** `cost_usd` and `duration_seconds` are filled only from
  a `tasks.jsonl` line for the same bead or the note's own words. Anything parsed
  out of free text is named in `fields_inferred` (as `detail.pr_number`, ...), so
  a statistic needing hard numbers can exclude those records.
- **Idempotent, and a later line supersedes.** `read()` returns the latest line
  per `key`. A sweep appends a record only if its content differs from the
  latest stored line, so a second sweep appends 0, and a bead that was
  `unlanded` and later lands gets a new line rather than an edit.
- **Sources.** Each registered project's `brain/handoffs/mill/*.md` and
  water-mill's own `HANDOFF-mill/*.md`, with bead timing from that checkout's
  tracked `.beads/issues.jsonl` (never the bd database). A checkout that is not
  on this machine is reported and skipped.
- **Landed means a line starting `**LANDED`** (bare or `**LANDED.**`), which is
  looser than `landed.py`, whose strict marker misses the second form.

### Transcript records (`source: "transcript"`, bead 61r)

`agents sweep` also reads Claude Code's own transcripts
(`--sessions-dir`, default `~/.claude/projects`; `--no-sessions` skips them;
`--settle-seconds`, default 300, leaves live sessions for the next sweep) and
appends one record per top-level session and per subagent run. Implementation
and field list: the docstring of `watermill/sessionlog.py`.

- **Metadata only, by construction.** Counters, timestamps, model names and ids.
  No message text, tool input or tool output ever enters a record or a log line;
  the sole free-text field is `title`, and only mill-crew runs carry one: the
  `.meta.json` `description` label ("Sluice: review PR #32 (a7z)") clipped to
  60 characters. Sessions and other subagents get `title: null` -- their
  descriptions summarise private work. A test plants a canary in every content
  position of a fixture and asserts it appears nowhere in any record.
- **Keys and kinds.** `session:<session id>` (`agent_kind: session`) and
  `session:<session id>:agent-<id>` (`mill-crew` when `agentType` starts with
  millstone/sluice/tailrace, else `subagent:<agentType>`). `outcome` is always
  `null`: a transcript does not say whether the work was good.
- **Tokens are per message, not per line.** A message is written once per
  content block with partial `usage`; the record takes the largest value per
  `message.id`, and counts each `tool_use` id once. `detail.tokens_total` is
  `input_tokens + output_tokens` -- cache reads and writes are excluded (they
  are `detail.cache_read_tokens` / `detail.cache_creation_tokens`).
- **Crew records link, they do not double-count -- filter on `source`.** A
  crew transcript record keeps `agent_kind: mill-crew`, the same kind as the
  handoff record, so `agent_kind == "mill-crew"` alone counts every bead two to
  four times. The rule for every reader (stats, dashboards):
  - **per bead** (outcome, one row per piece of work): `source == "handoff"`,
    key `crew:<bead>`;
  - **per run** (tokens, duration, one row per millstone/sluice/tailrace
    dispatch): `source == "transcript"`.

  A transcript record carries `detail.crew_key` (and `subject`) when its label
  names exactly one known bead or PR (listed in `fields_inferred`); otherwise
  only `detail.bead_hint`. A missing link is preferred to a wrong one: a short
  id matches another project's bead only from a cwd above the checkouts (the
  workshop root), never from inside a repo.
- `cost_usd` is set only on sessions, from the transcript's own `cost-state`
  line (it covers the session's subagents too -- do not add the two).

## Shipping agent work to Loki (`source="agent"`)

**Before the first ship after this lands, raise `reject_old_samples_max_age` on
the Loki side** (`limits_config`, default 1 week; it must exceed the age of the
oldest record in `runs/agents.jsonl`, months for the crew backfill). Agent lines
are filed at the work's end, so with the default Loki answers 400 to the
backfill, the mark does not move, and **every** later `watermill ship` fails on
the same lines -- runs and tasks included, since they go in the same push. Run
`watermill ship --dry-run` first to see the oldest timestamp you are about to
send.

`watermill ship` also sends `runs/agents.jsonl`, and `docs/grafana/agent-performance.json`
is an importable dashboard over it (Grafana: Dashboards, Import, upload the
file; the Loki datasource is the dashboard's `datasource` variable, picked from
the drop-down at the top of the dashboard).

- **Labels.** `job`, `project`, `source="agent"` and `agent_kind`, bucketed to a
  closed set: `mill-crew`, `session`, `subagent`, `other` (anything unknown). The
  full kind (`subagent:builder`) stays in the line. `key` and every per-record
  value are refused as labels, as before. The record's own `source`
  (`handoff`, `transcript`) collides with the stream label, so after `| json`
  it is `source_extracted`.
- **Timestamp is the work's end**: `ended_at`, else `detail.landed_at`, else
  `started_at`; `recorded_at` (sweep time) only as a last resort. History lands
  on the day it happened -- except a line older than the newest its stream
  already holds in Loki (a bead that lands after a newer one, transcript
  records backfilled into the `mill-crew` stream). That line is filed at the
  stream's newest instant instead, because Loki refuses it otherwise; its JSON
  keeps the true `ended_at`. The per-stream newest instant is `newest` in
  `runs/.shipped.json`.
- **The mark is per key, not a line count.** `agents.jsonl` re-appends a record
  whose content changed, so line N is not stable work. The shipper folds with
  `agentlog.read()` and records shipped keys in `runs/.shipped.json` under
  `agents`; a key ships once. A `mill-crew` record with `outcome="unlanded"` is
  held back until it lands, so one bead is never two works (an abandoned bead
  therefore never reaches Loki). A shipped record that later changes is not
  re-sent (`--resend` after a rebuild). State files without `agents` ship
  everything once; the `runs`/`tasks` marks are untouched. The key list grows by
  one short string per piece of work, forever; `runs/` is not committed.
- **Works versus runs.** Crew transcript records (one per millstone, sluice or
  tailrace run) share `agent_kind="mill-crew"` with the per-bead handoff
  records. Panels that count crew *works* (records per kind, landed per week,
  Sluice rounds, first-pass rate) filter `| json | source_extracted="handoff"`;
  panels about *runs* (duration, cost, tokens) filter
  `source_extracted="transcript"`. Never `| json | source="handoff"`: that is
  the stream label and is always `agent`. Tokens read `detail.tokens_total`
  (input + output, cache excluded), which the transcript sweep emits. An empty
  line is no data, not zero. Each panel's description says what it excludes.
- **"First-pass approval rate" is not the keep rate.** The keep rate above is
  completed tasks over all tasks. The crew panel is: landed crew beads with
  exactly one Sluice round and no Sluice-pushed fixes, over landed crew beads
  that had a Sluice review. It rests on fields parsed from handoff prose.

## What this does not cover

It ships the ledger and the task log. It does **not** ship `run.log`, the agent
transcripts or the gate output — those are large, per-run, and already on disk
where the morning report points at them. What reaches Grafana is the shape of a
night, not its contents.

There is no metrics endpoint and no Prometheus. Every number above is a LogQL
query over lines that already existed, which is why this feature is a reader and
not an instrumentation layer.

## `watermill agents compare`: reading the statistics (bead pu9)

Grafana draws the trend; this command answers "is crew different from other
agents, or is that noise?" with small-sample statistics written in stdlib
(`watermill/stats.py`, grouping logic in `watermill/agentcompare.py`).

```bash
./bin/watermill agents compare                       # crew vs non-crew subagents, crew vs sessions
./bin/watermill agents compare --kind crew:sluice --vs crew:millstone --since 2026-09-01
./bin/watermill agents compare --kind crew --vs session --json
```

Groups: `crew` (`mill-crew`), `crew:<role>` (`millstone` / `sluice` / `tailrace`),
`subagent` (every `subagent:*`), `session`, or any exact `agent_kind`. `--since`
keeps work whose end date (else start, else landing date) is on or after it;
undated records are dropped and counted. `--min-n` (default 8) and `--seed`
(bootstrap, default 0) exist; **do not lower `--min-n` to get a p-value.**

**Works vs runs -- the output is split in two and never mixes them.**
`agent_kind == "mill-crew"` alone counts each bead several times, so:

- *per run* (`source == "transcript"`): `duration_seconds`, `tokens_total`,
  `tool_call_count`, `cost_usd`. Compare crew runs with non-crew subagent runs
  or with sessions. A session is a whole conversation, a crew run is one
  dispatch, so crew-vs-session medians differ in scale by construction.
- *per bead* (`source == "handoff"`): `landed_rate`, `sluice_rounds` (landed
  beads), `first_pass_approval_rate`. Only crew work has handoff records, so
  against any other group this section prints "skipped" rather than a
  comparison.

**First-pass approval rate** = landed with exactly one Sluice round and no
pushed fixes. ("Keep rate" means something else here; it is not used.) It rests
on `detail.sluice_pushed_fixes`, which is always parsed from prose and so is
listed in `fields_inferred`: by default every such record is excluded and the
row shows `excluded: N inferred`. `--include-inferred` puts them back.

**Per metric, each group shows** `n` (usable values), the median (or rate) with a
95% interval, and `[records; excluded: nulls, inferred]` so you can see how much
was thrown away. Then, only if both groups have at least `--min-n` usable values:

| Data | Interval per group | Difference A - B | p-value |
|---|---|---|---|
| durations, tokens, tool calls, sluice rounds (skewed) | median, distribution-free from order statistics (coverage at least 95%, usually 96-99%) | seeded percentile bootstrap of the difference in medians | Mann-Whitney U, normal approximation with tie and continuity correction |
| proportions (landed, first-pass) | Wilson score | Newcombe hybrid score | Fisher exact, two-sided |

Otherwise it prints `too few to say: n = 158 vs 6, need at least 8 in each
group` and no difference or p-value. That is the correct output for most pairs
today (about 155 crew runs against ~6 non-crew subagent runs and ~16 sessions).
A p-value is always printed with both n. The medians' interval is `n/a` below
n = 6. The bootstrap interval for a difference of medians is approximate at small
n; the p-value, not the interval, is what the minimum-n rule protects.

Reading a result: a small p with an interval that excludes 0 says the groups
differ on that metric in this sample; it does not say why (crew runs are
role-specific, sessions are different work). A large p with wide intervals is
"cannot tell", not "the same". When more than 5 metrics are tested in one
comparison a warning is printed: no multiple-comparison correction is applied.
`tests/test_stats.py` pins every formula to SciPy / statsmodels values and
textbook examples (Fisher's tea tasting, 17/35).
