# Handoff — water-mill-qam

## Millstone (2026-10-13)

**State:** branch bead/qam, PR #33 (https://github.com/ziggyzims1-jpg/water-mill/pull/33). `make verify` green in worktree (450 passed). Not blocked. Live ship NOT possible/attempted (Loki 10.0.0.47:3100 unreachable per brief); verified by tests + `ship --dry-run` against a fixture agents.jsonl.

**Tried / did not work:** Line-count high-water mark (the existing runs/tasks approach) rejected: agents.jsonl re-appends changed records, so a bead going unlanded -> landed would ship as two works. Replaced with a shipped-key set (`agents` in runs/.shipped.json), folded by agentlog.read(); unlanded records held back until landed; a key already shipped is never re-sent even if content later changes (use --resend). Trade-off: an abandoned unlanded bead never appears in Loki.

**Lessons for the graph:**
- Loki `| json` on an agent line yields `source_extracted`, since the record's own `source` (handoff) collides with the stream label `source`; never filter on the in-line source.
- Loki rejects samples older than reject_old_samples_max_age (default 7d), so filing agent lines at work-end time needs that raised on the owner's Loki before the first backfill.
- Agent records are filed at ended_at, not recorded_at; the line's own recorded_at is sweep time.

**Look here first:** `watermill/shipper.py` collect() (agent block), line_time(), agent_kind_bucket(); docs/grafana/agent-performance.json; tests at the bottom of tests/test_shipper.py (dashboard-label test).

**Open questions:** (1) Token panel reads `detail_tokens_total`, a name I invented because schema v1 has no token field and 61r was not visible; align with 61r's real field. (2) Added a fourth bucket `other` beyond the bead's three, to keep the set closed for unknown kinds. (3) Keep rate defined as landed beads with sluice_pushed_fixes=false over landed beads with a Sluice verdict; owner may want another definition. (4) Loki reject_old_samples setting.

**Follow-ups:** a --resend that is scoped to agents only; a Grafana import smoke test once Loki is reachable (dashboard JSON was never loaded into Grafana; LogQL unvalidated against a real Loki).

## Sluice (2026-10-13)

**Verdict: approve_after_fixes.** PR #33, fixes in 171493f and 40f3001 on bead/qam. In scope; no fenced paths touched. `make verify` was green before (450) and after (460). I also ran `ship --dry-run` against a fixture agents.jsonl. No live Loki and no Grafana import, so the LogQL has never run against a real Loki.

**What failed in the original:**
- The dashboard label test was weak. Three mutants passed: `bogus!="x"` in a selector, an `outcome=` stream label (allowed, but agent streams never carry it), and `by(bogus)`. The regex only parsed `=`/`=~` and `by (` with a space, and it checked against ALLOWED_LABELS. Now it parses all four operators, `by`/`without`, and the labels a real payload emits. A parametrized test proves it fails on each mutant.
- Wedge: with lines filed at `ended_at`, a later push can carry a line older than the newest one Loki already holds for that stream. Examples are a late-landing bead, or 61r's crew transcript backfill into the mill-crew stream. Loki 400s that push, the mark never moves, and every later ship fails, runs and tasks included. Fix: `build_payload(floors=...)` plus `newest` in runs/.shipped.json; an older line is filed at the floor and keeps its true ended_at in the JSON. Test: `test_a_line_older_than_its_stream_already_holds_is_filed_at_the_floor`. A mutation that removed the clamp failed it.
- The Sluice-rounds avg/max had no `by`. After `| json` that gives one series per bead, not a mean. Now grouped `by (agent_kind)`, with a test.
- The "keep rate" panel has been renamed "first-pass approval rate". It now really means one Sluice round with no fixes; before, a do_not_merge followed by approve counted as kept. The test refuses "keep rate" in titles and legends.
- Works vs runs (orchestrator decision): panels that count crew works filter `| json | source_extracted="handoff"`; the duration, cost and token panels filter `source_extracted="transcript"`. **Not `source="handoff"`**: after `| json` that is the stream label (always `agent`) and matches nothing. A test refuses that form.
- Tokens: kept `detail.tokens_total` as the orchestrator directed; the description says "input + output, cache excluded". **61r must actually emit `detail.tokens_total`**. Its uncommitted draft emits only input/output/cache fields, so the token panel stays empty until it does.
- A malformed `agents`/`newest` in the state file no longer crashes (TypeError before).
- OBSERVABILITY.md: the reject_old_samples_max_age warning now opens the section, explaining that until it is raised every ship fails, and to dry-run first.

**Checked and fine:** no double-ship (fold plus key set; a failed push writes no state); held back are only `outcome=="unlanded"` (61r's transcript `outcome: null` ships); an old state file without `agents` loads; the key set grows by one short string per work and runs/ is gitignored, so that is acceptable. Bucket set is closed and the refusal test was extended, not loosened.

**Not fixed / follow-ups:** a Grafana import smoke test and LogQL validation once Loki is reachable; a lines-floored count in the ship summary; abandoned unlanded beads never reach Loki (by design).
**Lander:** the OBSERVABILITY.md section is new; a concurrent doc edit there may conflict. Findings: f-20261013-498ba7, -05c472, -c25dc2, -a44fc6, -91dd08.

## Tailrace (2026-10-13)

**LANDED** PR #33 squash-merged as c6372670df14e95f804c16857e09d4e2a696475d. Verify green after the settle loop (https://github.com/ziggyzims1-jpg/water-mill/actions/runs/38425139260/job/115392433733). No conflict: GitHub reported MERGEABLE, so the expected docs/OBSERVABILITY.md conflict did not occur; 61r (PR #34) is still open and will hit it when landed (union both sections).

`bd close`: "✓ Closed water-mill-qam — Ship runs/agents.jsonl to Loki and commit a Grafana 'agent performance' dashboard: Merged in PR #33". No auto-export warning.

**Findings:** sluice's five (f-20261013-498ba7, -05c472, -c25dc2, -a44fc6, -91dd08) plus one landing lesson (conflict forecast for 61r). Nothing failed in landing.

Still by hand: LogQL/dashboard never run against real Loki; raise reject_old_samples_max_age before first ship; 61r must emit detail.tokens_total.
