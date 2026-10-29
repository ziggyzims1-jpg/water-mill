# Handoff — water-mill-9uc

## Millstone (2026-10-29)

- **Where things stand:** branch `claude/water-mill-9uc-landed-forms`, PR #112, head 940fac5. `make verify` green (879 passed); `tests/test_landed.py` 10 passed. Not blocked.
- **Change:** the LANDED rule (the looser crewlog one), `is_landed`, `known_bead`, `load_beads` now live in `watermill/landed.py`; `crewlog.py` uses them (its own `_LANDED`, `_known_bead`, `_beads`, `BEADS_FILE` removed). `landed.parse` takes an optional `beads` map; `landed.read` loads each checkout's `.beads/issues.jsonl`.
- **Real data (`review --lag`):** before 7 lagging (4 past grace), after 16 (4 past grace). Newly listed, all claudiverse: 1ff.1, 1ff.2, 1ff.3, 1ff.4, 1ff.5, 1ff.8, 2wc, 83c, 8wf. The list grew as the bead predicted.
- **What was tried and did not work:** first `make verify` failed ruff (unused `import json` left in crewlog after moving the loader); fixed. Running `review --lag` from a worktree reports every checkout "not found" because registry paths resolve as siblings of the checkout root; I symlinked the sibling clones next to the worktree in the scratchpad (read only). Also a stray `git stash list` in one of my commands was blocked by the guardrail hook; it was unneeded and I did not retry it.
- **Lessons for the graph:** `review --lag` run from a worktree needs the registered sibling checkouts next to it, or it reports them all missing. Moving a helper out of a module leaves its imports unused and `make verify` lint fails on that.
- **Seams:** `landed.parse` (the rule and title resolution), `crewlog.parse_record` (same rule applied by crewlog), `review --lag` CLI (real data). Red before green recorded in the PR body (4 failed on base).
- **Look here first:** `watermill/landed.py` `_LANDED` / `known_bead`.
- **Open questions:** none. The 4 zimmy-life-tracker entries past grace did not change (their notes already used the bare form).
- **Follow-ups worth a bead:** none.

## Bolter (2026-10-29)

PR #112, head 940fac5, reviewed in a detached worktree (cloud mode).

**Sources:** CODING_STANDARDS.md, docs/adr/0001-0018, CONTEXT.md, CLAUDE.md conventions. Missing: CONTRIBUTING.md (not a finding).

**Blocking:** none. The diff touches no fenced/safety file, adds no shell path or exit code, keeps ruff-visible style, puts tests at the landed.py seam, and uses "landed"/"tailrace" as CONTEXT.md defines them.

**Advisory:**
- Possible Duplicated Code: watermill/crewlog.py:93-95 (parse_record) repeats the title -> normalise -> known_bead derivation that watermill/landed.py:118-120 (parse) now does. Fix: extract landed.bead_of(text, path, project, beads) and call it from both, which also removes crewlog's reach into landed._TITLE. [auto-mill candidate]
- Possible Feature Envy (pre-existing, made more visible): crewlog.py reads the private landed._TITLE and landed._TAILRACE. Fix: a public landed.tailrace_dates(text) beside is_landed, alongside the helper above.
- Stale docstring: the watermill/landed.py module docstring (lines 8-9) says the module opens only brain/handoffs/mill/*.md, but read() now also reads .beads/issues.jsonl through load_beads. Fix: add one clause.
- tests/test_landed.py:52: `landed.parse(...).bead` on a possible None fails with an AttributeError, not an assertion message. Fix: assert not None first, as the other tests do.

**Findings:** none -- no blocking finding, so nothing repeatable to record.

**Recall:** f-20261013-f1d4b5 (role-prefixed titles resolve via .beads/issues.jsonl) is the lesson this PR acts on.

**Run record:** agent-runs/bolter-water-mill-9uc-a0115b63ba8d.jsonl
`{"agent_kind": "mill-crew", "cost_usd": null, "detail": {"agent_id": "a0115b63ba8d2453a", "agent_type": "bolter", "arm": null, "bead": "water-mill-9uc", "bead_hint": null, "cache_creation_1h_tokens": 0, "cache_creation_5m_tokens": 32065, "cache_creation_tokens": 32065, "cache_read_tokens": 405748, "crew_key": "crew:water-mill-9uc", "cwd_repo": "water-mill", "error_count": 0, "input_tokens": 12, "interrupted": false, "message_count": 6, "model": "claude-opus-5-5", "models": ["claude-opus-5-5"], "output_messages_final": 6, "output_messages_partial": 0, "output_tokens": 2085, "output_tokens_floor": false, "pr_number": 112, "role": "bolter", "session_id": "3443f9c6-dd0a-5d38-96db-69a1677f23f3", "sluice_rounds": null, "stopped_by_user": false, "tokens_total": 2097, "tool_call_count": 6, "transcript": "-home-user-water-mill/3443f9c6-dd0a-5d38-96db-69a1677f23f3/subagents/agent-a0115b63ba8d2453a.jsonl", "transcript_located": true, "verdict": null}, "duration_seconds": 23.492, "ended_at": "2026-10-29T11:25:13.913Z", "fields_inferred": [], "key": "session:3443f9c6-dd0a-5d38-96db-69a1677f23f3:agent-a0115b63ba8d2453a", "outcome": null, "project": "water-mill", "recorded_at": "2026-10-29T11:25:15+00:00", "schema": 1, "source": "recorded", "started_at": "2026-10-29T11:24:50.421Z", "subject": "water-mill-9uc", "title": null}`

## Sluice (2026-10-29)

**Verdict: approve_after_fixes.** Head now `c3ea8ac` (one fix commit on top of 940fac5). `make verify` green in a detached worktree: 880 passed.

**Red before green:** reproduced. The PR's `tests/test_landed.py` on `origin/main` code: 4 failed, 6 passed, exactly as the PR body says.

**Scope:** only `watermill/landed.py`, `watermill/crewlog.py`, `tests/test_landed.py`. No handoff note, no tailrace.md, nothing in knowledge.py / test_knowledge.py / projects/cheme-solver.yaml.

**Real data (zimmy-life-tracker, `landed.parse` over all 132 notes in `brain/handoffs/mill/`):** main counts 79 landed; this branch counts 129 (all 129 ids resolve to a bead in the checkout's `.beads/issues.jsonl`). The 3 still unlanded (8lm, hga, fwm-6) carry no marker at all (fwm-6 is a water-mill bead's note). The bead's premise is satisfied. `review --lag` does not move for zimmy because every one of the 50 newly counted notes landed before `LAG_SINCE` (2026-10-05): 51 zimmy notes fall on or after it both before and after. Other checkouts: claudiverse 16 -> 35, cheme-solver 21 -> 22, hillel-programming 98 -> 99.

**A form still missed (not tailrace's):** 8 Hillel-Programming notes put the marker in the title, `# Handoff — hpt-266.1 **LANDED** (#122, d1c4dbc, 2026-10-26)` (266-1, 564, bfo, lo1-1..4, zyt-15), owner-written in 547ebf0, no `## Tailrace` section. `is_landed` misses them and `_TITLE` would swallow the tail into the bead id. Out of this bead's "forms tailrace wrote"; filed **water-mill-tgj** (P2 bug, unlabelled: the owner decides whether owner-written forms count). claudiverse cpx ("Landed: PR #98", orchestrator) and 1gn-2 (owner merged) are also unmarked, likewise not tailrace's.

**Bolter findings (all advisory, none blocking):**
1. Duplicated bead-id derivation: **fixed** in c3ea8ac (`landed.bead_of(text, path, project, beads)`, called by `landed.parse` and `crewlog.parse_record`). It is the bead's own goal ("share one helper"), so it belonged here, not in a follow-up.
2. crewlog reads private `landed._TAILRACE` / `_NONE`: not fixed (pre-existing); filed **water-mill-210** (P3, `auto-mill`).
3. Stale module docstring: **fixed** in c3ea8ac.
4. `tests/test_landed.py` `.bead` on a possible None: **fixed** in c3ea8ac.

**Mutation tests:** reverting `_LANDED` to the old bare rule fails the bullet case; dropping `known_bead` from parse fails the role-prefix test. **Gap:** making `landed.read` call `parse` without the checkout's beads (the actual `review --lag` path) left all 80 landed/review/crewlog tests green. Fixed in c3ea8ac with `test_read_resolves_titles_through_each_checkouts_beads` (projects.yaml + sibling checkout); the mutation now fails it.

**auto-mill beads filed:** water-mill-210. Ordinary: water-mill-tgj. Both created with `BD_DOLT_AUTO_PUSH=false`; they reach `.beads/issues.jsonl` by tailrace's export.

**Findings (remembered to knowledge/findings.jsonl, tailrace commits):**
- A test of landed.parse with a beads map does not prove review --lag resolves titles; only a read()-level test catches landed.read dropping load_beads.
- Some handoff notes carry the LANDED marker in the title line (Hillel, owner-written); is_landed misses them and the id is garbage (water-mill-tgj).

**For the lander:** run records staged in `agent-runs/` (millstone, bolter, sluice-water-mill-9uc-a87e43856211.jsonl). No doc-table rows touched.

## Tailrace (pre-merge, 2026-10-29)
Head c3ea8ace35795cd20a9db6d7c75f9c928935a368; mergeable=true, mergeable_state=blocked; check-runs: verify completed/success (only one). Not merged per orchestrator instruction.

## Tailrace (2026-10-29)

**LANDED** PR #112 squash-merged by the master orchestrator as 5dd77913066b3441b31cac5e4485d51c482d3b3f (the merge permission was the master's, not tailrace's).

- Pre-merge: head c3ea8ac verified (`verify` success). Main then moved (water-mill-bha, 6732639, crewlog `_FINDING_ID` `{6,}`); merged cleanly (no conflict) as d65cfb2, `make verify` 883 passed, pushed. The master merged before d65cfb2's checks were awaited, so that head was not CI-verified by tailrace.
- Post-merge on `claude/water-mill-9uc-landed-forms`: `bd close` -> "Closed water-mill-9uc ... Merged in PR #112 (squash 5dd7791...)"; no auto-export warning. Commit d77c89d (jsonl alone), then merged origin/main (f8808da).
- Failure worth naming: merging main refused over dirty `knowledge/findings.jsonl`; saved sluice's 2 lines aside, restored the file, merged, re-appended (no stash). `.beads/issues.jsonl` conflicted (expected); took main's, then `bd import` before `bd export` because the container db was stale (a bare export would have dropped/reverted main's beads 8kp, rxu, sds, xpd, zpz, reopened 5s8/bha). Final diff vs origin/main: 9uc closed + new tgj, 210 only.
- auto-mill follow-ups: see `## Sluice`; `bd list -l auto-mill` to confirm (tgj P2 and 210 P3 were filed).
- **Findings:** 3 remembered by tailrace (2 millstone lessons, 1 own) plus sluice's 2, all in `knowledge/findings.jsonl`, committed on the session branch (cloud, `$WM` is this repo).
- Lessons for the graph: review --lag from a worktree needs sibling checkouts; moving a helper leaves unused imports that fail lint; in a stale cloud bd db, import main's jsonl before export.
