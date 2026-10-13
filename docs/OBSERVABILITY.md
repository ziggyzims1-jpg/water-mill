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
  the sole free-text field is `title`, a subagent's `.meta.json` `description`
  clipped to 120 characters (sessions get none). A test plants a canary in every
  content position of a fixture and asserts it never appears.
- **Keys and kinds.** `session:<session id>` (`agent_kind: session`) and
  `session:<session id>:agent-<id>` (`mill-crew` when `agentType` starts with
  millstone/sluice/tailrace, else `subagent:<agentType>`). `outcome` is always
  `null`: a transcript does not say whether the work was good.
- **Tokens are per message, not per line.** A message is written once per
  content block with partial `usage`; the record takes the largest value per
  `message.id`, and counts each `tool_use` id once.
- **Crew records link, they do not double-count.** The handoff record
  `crew:<bead>` stays the bead's only outcome. A transcript record for a role
  run carries `detail.crew_key` (and `subject`) when its label names exactly one
  known bead or PR (listed in `fields_inferred`); otherwise `detail.bead_hint`.
  Outcome statistics read `source == "handoff"`; cost and token statistics read
  `source == "transcript"`.
- `cost_usd` is set only on sessions, from the transcript's own `cost-state`
  line (it covers the session's subagents too -- do not add the two).

## What this does not cover

It ships the ledger and the task log. It does **not** ship `run.log`, the agent
transcripts or the gate output — those are large, per-run, and already on disk
where the morning report points at them. What reaches Grafana is the shape of a
night, not its contents.

There is no metrics endpoint and no Prometheus. Every number above is a LogQL
query over lines that already existed, which is why this feature is a reader and
not an instrumentation layer.
