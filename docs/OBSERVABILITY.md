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
dispatched from Claude Code sessions (millstone -> bolter -> sluice -> tailrace through
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
`mill-crew`, `detail` holds `handoff`, `pr_number`, `landed_at`, `bolter_rounds`, `sluice_rounds`,
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
  millstone/bolter/sluice/tailrace, else `subagent:<agentType>`). `outcome` is always
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
  - **per run** (tokens, duration, one row per millstone/bolter/sluice/tailrace
    dispatch): `source == "transcript"`.

  A transcript record carries `detail.crew_key` (and `subject`) when its label
  names exactly one known bead or PR (listed in `fields_inferred`); otherwise
  only `detail.bead_hint`. A missing link is preferred to a wrong one: a short
  id matches another project's bead only from a cwd above the checkouts (the
  workshop root), never from inside a repo.
- `cost_usd` is set only on sessions, from the transcript's own `cost-state`
  line (it covers the session's subagents too -- do not add the two).

### Recorded records (`source: "recorded"`, bead 441)

Transcripts are read from the laptop's `~/.claude/projects`, and `runs/` is
gitignored, so a **cloud** session's cost is invisible and a plain Claude session
(the crew-vs-default trial's arm B) leaves no handoff to parse. So every agent
records itself at sign-off:

```bash
TAG=$($WM/bin/watermill agents whoami)          # early in the run, its own tool call
$WM/bin/watermill agents record --transcript auto --run-tag "$TAG" \
    --role millstone --bead <id> --pr <n> [--verdict v] [--sluice-rounds n] [--arm A|B]
```

It writes ONE line (same schema, `source: "recorded"`) to
`<repo>/knowledge/agent-runs/<role>-<bead>-<agent id>.jsonl` in the repo it is
run from, **tracked** so the agent commits it with its other sign-off work. One
file per run, not one shared file, so two PRs never conflict on it.
`agents sweep` ingests that directory from the factory and every registered
checkout.

- **No double count.** The key is the transcript's own (`session:<sid>` or
  `session:<sid>:agent-<id>`), so a recorded line and the laptop sweep of the
  same run are one record: `agentlog.read` lets a `recorded` line outrank any
  other source for its key, in either order, and the sweep never appends a
  transcript line for a key that already has one. Per-run statistics accept
  `source in (transcript, recorded)`; per-bead ones still read `handoff`.
- **Privacy.** The transcript half goes through `sessionlog`'s whitelist
  (`record_for`); the flags are enums, integers or a validated bead id, never
  free text; `title` is always null. `tests/test_record.py` runs the 61r canary
  through the record path.
- **How an agent finds its own transcript** (verified from inside a subagent,
  2026-10-13): `CLAUDE_CODE_SESSION_ID` is the *top-level* session's id even in
  a subagent, so it locates the session; a subagent's file is
  `<projects>/<dir>/<session>/subagents/agent-<id>.jsonl` and nothing in the
  environment names `<id>`. A tool call reaches the transcript only after it
  returns, so a command cannot find itself, but an earlier one can: `agents
  whoami` prints a random tag, which lands in that agent's transcript as a tool
  result, and `--run-tag` selects the one transcript containing it (a path
  search; nothing read is kept). Without a tag only `--role solo` is located
  (the session's top-level file). A crew role is **never** located without a
  tag: two crew agents of one type run side by side in one session as a matter
  of course, and a record filed from the wrong transcript corrupts the numbers
  silently. A missing tag, a tag found in no transcript (`whoami` run in the
  same call as `record`) or in several is refused: exit 2, nothing written.
- **`tokens_total` is not a cost proxy.** It is `input + output` with cache
  excluded, and a crew run lives on the cache: the dogfood millstone run (340 s,
  30 tool calls) shows `tokens_total` 363 against 2.4 M `cache_read_tokens` and
  109 k `cache_creation_tokens`. A record taken at sign-off also misses the
  turns after it, and a subagent transcript under-counts streamed output (next
  item). Never rank or price runs by `tokens_total`; use the next two fields.
- **`output_tokens` is a floor for subagent runs; true for sessions** (water-mill-658,
  measured 2026-10-13 on 16 sessions and 201 subagent runs, counts only).
  A top-level session writes the final `usage` on every line of a message, so
  the largest per `message.id` is the true total (1 211 of 1 213 messages carry
  a `stop_reason`; per no-subagent session it lands within 0-6% of the
  session's own `cost-state` outputTokens for the main model, the rest being
  side calls such as the haiku title call). A
  subagent transcript is written live and never finalised: 63% of its messages
  (3 561 of 5 658) have no line with a `stop_reason`, hold the first streamed
  chunk (tens of tokens against thousands of characters of content; about 42 k
  tokens recorded for about 3.3 M characters), and nothing later fixes it --
  the file has only user/attachment/assistant lines, no result or summary line,
  the parent's `toolUseResult` for the Agent call has no usage, and the sidecar
  `.meta.json` has none; an async Agent call's `outputFile`
  (`<tmp>/<session>/tasks/<agent id>.output`) is a symlink to the same
  `subagents/` transcript (47 of 47 checked), not a second copy. So the total
  does not exist anywhere on disk for those
  messages. Records say so: `detail.output_messages_final` /
  `output_messages_partial`, and `detail.output_tokens_floor` (true when over 5%
  of messages are partial), which lists `detail.output_tokens` and
  `detail.tokens_total` in `fields_inferred`; `cost_usd_est`'s output term is a
  floor too, so `agents compare` excludes floor runs from `tokens_total` and
  `cost_usd_est` unless `--include-inferred`. **Bias for the trial
  (water-mill-166):** arm A (crew = subagents) is under-counted on output,
  the priciest class, arm B (a top-level session) is not, so token and cost
  comparisons favour the crew by measurement alone. Compare duration, tool
  calls, landed rate and `tokens_total_incl_cache`'s input side; treat any
  `--include-inferred` token/cost comparison as crew-flattering. A session's
  `cost-state` line covers its subagents (per-model outputTokens, not split
  per agent), the only independent total, but it is not per run.
  A recorded line (`agents record`) keeps the floor marking too: its flags
  replace prose guesses in `fields_inferred`, never `output_tokens_floor`.
- **The trial's token/cost figure is the session's `cost-state` total**
  (water-mill-166 design). Each trial bead runs in its OWN top-level session:
  arm A is an orchestrator session that runs the crew (millstone, bolter, sluice,
  tailrace as subagents) on that one bead, arm B a solo session on it. Then
  the session-level `cost-state` line, which folds the subagents in, is the
  true per-bead figure for both arms, and the subagent floor never enters the
  comparison. Checked 2026-10-13 on the 7 sessions with subagents and a
  `cost-state` line (counts only): `cost-state` outputTokens exceeds both the
  session's own max-per-id sum and that sum plus every subagent's floor in all
  7 (e.g. 455 k against 85 k own + 47 k subagent floors), and its input side
  (input + cache read + cache write, exact even in a first chunk) is at least
  own + subagents in all 7 (within 2-4% in three; 7-30% over in four, the
  excess not traced: side calls, compaction or transcripts no longer on disk),
  so the subagents are in it, not beside it. Its
  limits, which the trial protocol must respect: the line is written when a
  session ends (a live session has none, so read it after exit), it is
  cumulative per session (one session that ran on with more lines carried
  both snapshots; take the last), it also counts side calls (both arms pay
  those), and it is per session, so a session must hold exactly one trial
  bead -- an orchestrator session that runs several beads cannot be split.
  Duration, tool calls and landed rate still come from the records.
- **API-equivalent cost estimate and the cache-inclusive total** (water-mill-cdi).
  `detail.cost_usd_est` is an **API-equivalent estimate**: what a run's tokens
  would cost at Anthropic's first-party API list prices. On a Claude
  subscription nothing is billed per token, so it is never billed cost; use it
  to compare runs, not to reconcile a bill. It and
  `detail.tokens_total_incl_cache` (input + output + cache writes + cache reads)
  are **derived at read time**: `agentlog.read()` computes them from each
  record's model and token counters with `watermill/pricing.py` (per-model
  rates, the as-of date `AS_OF` and the source cited there), so every line, old
  or new, is priced by the current table and nothing stores a frozen figure.
  Derived records also carry `detail.cost_usd_est_as_of`; `agents compare`
  prints the as-of date and reports it as `pricing_as_of` in `--json`.
  `cost_usd_est` is named in `fields_inferred` as `detail.cost_usd_est`, and
  `cost_usd` (stated cost only) is never touched. Cache writes are priced by
  TTL from the transcript's `usage.cache_creation` split (kept as
  `detail.cache_creation_5m_tokens` / `cache_creation_1h_tokens`): 1.25x input
  for 5-minute writes, 2x for 1-hour. Writes without a split are priced at
  Claude Code's TTL for the kind of run: 1 hour for a top-level session, 5
  minutes for a subagent (what every transcript on the owner's machine showed
  on 2026-10-13). The estimate is null for a model not in the table (Haiku 5.5
  on purpose: its price is tiered by prompt size) and for a record whose
  `models` mix rate cards. `agents compare` lists it as `cost_usd_est`,
  excluded as inferred unless `--include-inferred`, and says so in its output.
- **No transcript, still a record.** If `auto` finds nothing (a container
  without `~/.claude/projects`), the flags are recorded alone
  (`detail.transcript_located: false`, no token fields) and a warning is printed.
  **Not tested in a real cloud container**: the path layout and the env var are
  assumed to match the laptop's there.
  A flags-only line is keyed `recorded:<project>:<role>:<bead>:<tag>`, not by
  the transcript, so it cannot fold with a laptop transcript of the same run;
  that is why a laptop run whose transcript exists but cannot be pinned is
  refused rather than recorded flags-only.
- **Not on the dashboard yet.** The per-run Grafana panels filter
  `source_extracted="transcript"`, so recorded lines (the cloud runs) do not
  appear there until those panels learn `recorded` too.

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
- **Works versus runs.** Crew transcript records (one per millstone, bolter, sluice or
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

Groups: `crew` (`mill-crew`), `crew:<role>` (`millstone` / `bolter` / `sluice` / `tailrace`),
`subagent` (every `subagent:*`), `session`, or any exact `agent_kind`. `--since`
keeps work whose end date (else start, else landing date) is on or after it;
undated records are dropped and counted. `--min-n` (default 8) and `--seed`
(bootstrap, default 0) exist; **do not lower `--min-n` to get a p-value.**

**Works vs runs -- the output is split in two and never mixes them.**
`agent_kind == "mill-crew"` alone counts each bead several times, so:

- *per run* (`source` in `transcript`, `recorded`; a recorded line wins its
  key, so a run counts once): `duration_seconds`, `tokens_total`,
  `tool_call_count`, `cost_usd`. Compare crew runs with non-crew subagent runs
  or with sessions. A session is a whole conversation, a crew run is one
  agent's task, so crew-vs-session medians differ in scale by construction;
  any comparison with a `session` side prints a one-line `caveat:` above it
  (and a `caveat` field in `--json`). The numbers are still printed.
- *per bead* (`source == "handoff"`): `landed_rate`, `sluice_rounds` (landed
  beads), `first_pass_approval_rate`. Only crew work has handoff records, so
  against any other group this section prints "skipped" rather than a
  comparison.

**First-pass approval rate** = landed with exactly one Sluice round and no
pushed fixes; a landed bead with no Sluice round has no value. It rests on
`detail.sluice_pushed_fixes`, which crewlog always lists in `fields_inferred`.
When `detail.sluice_verdict` is exactly `approve` or `approve_after_fixes` the
flag follows that verdict word, not prose (`crewlog._pushed_fixes`), so those
records are admitted and the row says `admitted N with pushed-fixes from the
verdict`. Records whose flag came from the prose fallback (`do_not_merge`, or
no verdict) stay excluded (`excluded: N inferred`) unless `--include-inferred`.
This admission applies to this metric only; every other metric excludes any
inferred value.

**Per metric, each group shows** `n` (usable values), the median (or rate) with a
95% interval, and `[records; excluded: nulls, inferred]` so you can see how much
was thrown away. Then, only if both groups have at least `--min-n` usable values:

| Data | Interval per group | Difference A - B | p-value |
|---|---|---|---|
| durations, tokens, tool calls, sluice rounds (skewed) | median, distribution-free from order statistics (coverage at least 95%: about 98% below n = 20, approaching 95% as n grows) | seeded percentile bootstrap of the difference in medians | Mann-Whitney U, normal approximation with tie and continuity correction |
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
