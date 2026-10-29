# Handoff — water-mill-bha

## Millstone (2026-10-29)

**Where things stand.** Branch claude/water-mill-bha, PR #113, head 889b141. `make verify` green (871 passed). Not blocked. Run tag wm-run-8c8a1c007b8e; run record staged in agent-runs/ (recorded after the PR, so tokens/duration undercount slightly).

**What was tried and did not work.** Bead suggested check-and-retry under "the lock the writer already takes": there is no lock (O_APPEND design), and check-then-append is racy; a lock contradicts CLAUDE.md. Chose more entropy (6 -> 8 hex). I edited on the SB branch in the main checkout rather than a separate worktree (REPO was already on SB); no collision with other work.

**Lessons for the graph.**
- Finding ids are `f-YYYYMMDD-` + 8 hex since 2026-10-29; older ids have 6 hex and stay valid, so any parser must accept 6 or more.
- A lock-free append design cannot be made collision-safe by checking existing ids first; only entropy closes the race.

**Seams.** `knowledge.propose` (public; id on returned record, RNG forced via monkeypatching uuid.uuid4), `knowledge.read` (legacy 6-hex ids still read).

**Duplicate scan.** knowledge/findings.jsonl: 850 finding lines, 0 duplicate ids (annotation lines reference ids and are not duplicates).

**Look here first.** watermill/knowledge.py `_new_id`; crewlog.py `_FINDING_ID` is one touched line outside the bead's file list (`{6}` -> `{6,}`), strictly needed or 8-hex citations never match; may textually touch the parallel water-mill-9uc session's file.

**Open questions.** None.

**Follow-ups.** Docs/README examples still show shorter ids; illustrative, left alone.

## Bolter (2026-10-29)

- **Reviewed:** PR #113, claude/water-mill-bha @ 889b141, detached worktree, cloud mode. Recall ran: f-20261013-ead3ca is the CI flake this bead fixes.
- **Sources:** CODING_STANDARDS.md, docs/adr/0001-0018 (0012 no-database most relevant), CONTEXT.md ("Finding"), CLAUDE.md conventions. Missing: CONTRIBUTING.md (not a finding).
- **Blocking:** none. The change keeps the lock-free O_APPEND design (ADR 0012, CLAUDE.md "There is no database"); existing ids are not rewritten (append-only / supersede-not-edit honoured); conventional commit style.
- **6-hex assumptions audit:** the only code that parses the suffix is watermill/crewlog.py:46, widened to {6,}. knowledge.py docstring's claim "nothing parses the suffix length except crewlog" checked by grep: true. Remaining stale text, docs only:
- **Advisory:**
  - watermill/agentlog.py:61 schema docstring still says "finding ids (f-YYYYMMDD-xxxxxx)"; change to "f-YYYYMMDD-<6 or 8 hex>". [auto-mill candidate] (one-line docstring, no fence/schema/CI)
  - docs/KNOWLEDGE.md:8, :90, :126 examples use 4- and 6-hex ids (f-20260828-a1b2, f-20260301-9c1a, f-20260828-a1b2c3); already inconsistent before this PR, harmless, could be refreshed to 8 hex alongside the above.
  - Not a smell, a lead for sluice: tests/test_crewlog.py:24 cites only a 6-hex id; no crewlog test shows an 8-hex id is counted (the {6,} widening is untested). Also the crewlog.py line conflicts-in-waiting with water-mill-9uc.
  - tests/test_knowledge.py:229 `import types` inside the test body; module-level import would match the file's style (judgement, trivial).
- **Findings:** none -- no blocking finding; the collision lesson is already f-20261013-ead3ca.
- **Run record:** knowledge/agent-runs/bolter-water-mill-bha-a6e4efc7ab1a.jsonl (staged at /home/user/.mill-stage/water-mill/bha/agent-runs/): {"agent_kind": "mill-crew", "cost_usd": null, "detail": {"agent_id": "a6e4efc7ab1a21237", "agent_type": "bolter", "arm": null, "bead": "water-mill-bha", "bead_hint": null, "cache_creation_1h_tokens": 0, "cache_creation_5m_tokens": 33135, "cache_creation_tokens": 33135, "cache_read_tokens": 336719, "crew_key": "crew:water-mill-bha", "cwd_repo": "water-mill", "error_count": 0, "input_tokens": 10, "interrupted": false, "message_count": 5, "model": "claude-opus-5-5", "models": ["claude-opus-5-5"], "output_messages_final": 5, "output_messages_partial": 0, "output_tokens": 1826, "output_tokens_floor": false, "pr_number": 113, "role": "bolter", "session_id": "4b23c369-561e-5ab2-bf2a-9e7261d7fa0e", "sluice_rounds": null, "stopped_by_user": false, "tokens_total": 1836, "tool_call_count": 5, "transcript": "-home-user-water-mill/4b23c369-561e-5ab2-bf2a-9e7261d7fa0e/subagents/agent-a6e4efc7ab1a21237.jsonl", "transcript_located": true, "verdict": null}, "duration_seconds": 22.174, "ended_at": "2026-10-29T11:25:35.581Z", "fields_inferred": [], "key": "session:4b23c369-561e-5ab2-bf2a-9e7261d7fa0e:agent-a6e4efc7ab1a21237", "outcome": null, "project": "water-mill", "recorded_at": "2026-10-29T11:25:37+00:00", "schema": 1, "source": "recorded", "started_at": "2026-10-29T11:25:13.407Z", "subject": "water-mill-bha", "title": null}

## Sluice (2026-10-29)

- **Verdict: approve_after_fixes.** Pushed 330a930 (test only) onto 889b141. Round 1.
- **Scope:** diff touches watermill/knowledge.py (`_new_id` 6 -> 8 hex + docstring), tests/test_knowledge.py, and the one crewlog.py `_FINDING_ID` line (`{6}` -> `{6,}`), which is strictly needed: with `{6}` the trailing `\b` makes an 8-hex id match nothing. No lock added; O_APPEND design untouched. No fenced path touched. Entropy rather than check-and-retry is one of the two options the bead offered; 32 bits is "much rarer", not impossible, which the docstring states honestly.
- **Red before green:** reproduced. origin/main's watermill/ + the PR's tests: `test_ids_do_not_collide_when_the_first_24_bits_of_the_random_part_do` fails at `first != second` (forced uuid4 draws sharing six hex), deterministically; green on the PR.
- **Duplicate scan (independent):** knowledge/findings.jsonl has 923 lines: 850 `kind_of_line=finding`, 68 annotation, 5 supersede. 850 finding ids, 850 distinct, 0 duplicates; all 6 hex. Confirms millstone.
- **Bolter blocking:** none. Advisory 3 (crewlog widening untested) confirmed by mutation: reverting to `{6}` left all crewlog+knowledge tests green. Fixed in 330a930: `test_a_freshly_minted_id_is_one_a_handoff_citation_counts` (in tests/test_knowledge.py, to stay inside the bead's files and off the parallel water-mill-9uc session's test_crewlog.py) asserts `crewlog._FINDING_ID` finds a minted id and a legacy 6-hex id. Mutation re-run: `{6}` now fails it; `hex[:6]` fails the collision test. Advisory 4 (`import types` in test body) fixed in the same commit. Advisories 1-2 filed as auto-mill.
- **Auto-mill filed:** water-mill-8kp (agentlog.py:61 docstring + docs/KNOWLEDGE.md:8/:90/:126 example ids to 8 hex). Created in the local bd db; it travels via .beads/issues.jsonl by the usual route.
- **Verified:** `make verify` green in a detached worktree at 330a930 (872 passed).
- **Not fixed:** the concurrent-writers test is still probabilistic (now ~1 in 200k per run at 200 same-day writes rather than ~1 in 800); the deterministic test is the guarantee. Not worth more.
- **For the lander:** crewlog.py line 46 may textually conflict with water-mill-9uc; keep `{6,}`. Finding remembered into $REPO/knowledge/findings.jsonl (working tree, uncommitted; cell ''): crewlog regex vs id shape coupling.
- **Run records:** sluice-water-mill-bha-a66085a95415.jsonl staged in agent-runs/ (bolter's and millstone's already there).

**Findings:** one lesson recorded (`--cause pending`, tags finding-ids/test-gap).

## Tailrace (2026-10-29, run by the orchestrator)

- **Landed:** PR #113 was squash-merged by the master session as 6732639 (child sessions are refused the merge, "Merge Without Review"; the auto-mode classifier also refused launching tailrace). CI `verify` was green at head 330a930. Bead water-mill-bha closed in the local bd db.
- **Bead file did not reach main.** The close and the new auto-mill bead water-mill-8kp were committed on claude/water-mill-bha (de1798a) and pushed, but the beads-sync run failed all 5 attempts with `GH013: Changes must be made through a pull request` on main: the repo has no BEADS_SYNC_TOKEN bypass, so the built-in token cannot push. This docs PR restores `.beads/issues.jsonl` to main's copy so it stays out of the PR; the bead change has to reach main another way (owner's call).
- **Finding f-20261029-675255dd** was recorded with `cell: ""` because `watermill remember water-mill` is refused ("unknown project"; related open bead water-mill-yal). The cell it should have been filed under is **water-mill**.
- **Duplicate scan after adding it:** 851 finding ids, 851 distinct.
- **Not run:** water-mill-8kp (auto-mill); the master schedules it.
