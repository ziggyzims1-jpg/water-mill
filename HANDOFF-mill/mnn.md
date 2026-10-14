**LANDED**

# Handoff — water-mill-mnn

## Millstone (2026-10-14)

- **Where things stand:** branch bead/mnn, PR #45 (https://github.com/ziggyzims1-jpg/water-mill/pull/45). `make verify` green (616 passed). Not blocked. Four new tests in tests/test_trial.py fail on the old trial.py/cli.py.
- **Design:** `trial._refuse_trial_session` makes `pause`/`resume` refuse when `CLAUDE_CODE_SESSION_ID` equals a `start` line's session_id in the ledger (cli passes `trial.env_session_id()`). Chosen over an env marker or --human flag: `trial start` is already every trial session's first action, the ledger is the record, nothing leaks into briefs. `_OWNER_ONLY` text added to both arm briefs. Arm A crew line never mentioned these commands; the orchestrator brief now carries the ban.
- **Tried and did not work:** nothing abandoned.
- **Lessons:** the guard cannot catch a session that skipped `trial start` (then it has no ledger footprint); only the brief covers that. Subagents that inherit a different session id than the orchestrator would also escape the guard (unverified).
- **Look here first:** `watermill/trial.py` `_refuse_trial_session`.
- **Open questions:** do crew subagents share the orchestrator's CLAUDE_CODE_SESSION_ID? If not, guard only binds the orchestrator. Should enroll/collect/score also be guarded? Only brief-forbidden now (owner enroll in a trial session is unlikely).
- **Follow-ups:** none filed.

## Sluice (2026-10-14)

- **Verdict: approve_after_fixes.** One doc commit 6a43418 on bead/mnn. `make verify` green in my worktree (616 passed) before and after it. Scope: docs/TRIAL.md, watermill/trial.py, watermill/cli.py, tests/test_trial.py, millstone's run record. No fenced path.
- **Q1, same value at start and pause: yes.** `cmd_trial` start records `args.session_id or trial.env_session_id()`; pause/resume pass `trial.env_session_id()` (both read `CLAUDE_CODE_SESSION_ID`). Proved end to end in a temp ledger with the real `bin/watermill` and my real env: start recorded `1f77a9c6-...`; pause and resume from that env exit 3 with the refusal; the same with `CLAUDE_CODE_CHILD_SESSION=1` also refused. Only way to make it a no-op: `trial start --session-id <other>` (the brief never says to pass it).
- **Q2, subagents share the id: yes, verified, not guessed.** My env (sluice subagent) has `CLAUDE_CODE_SESSION_ID=1f77a9c6-cafb-41c6-b875-6daaa0451fba`. That is the orchestrator's own transcript file (`~/.claude/projects/.../1f77a9c6-....jsonl`, every row `sessionId` = that value), and subagent transcripts sit under `1f77a9c6-.../subagents/`. (agent-a95aa00c95fa22c04 is this sluice run's own transcript, not a second witness. The orchestrator's own echo was redacted as `<set>`, so the parent value comes from its transcript id.) So in arm A the guard binds the whole crew, not only the orchestrator. Written into TRIAL.md section 6 (6a43418).
- **Q4, owner never blocked:** with the variable unset, set to empty, or set to an id not in the ledger, pause/resume succeed (e2e plus `test_cli_pause_reads_the_session_id_from_the_environment`). An unset variable does not crash: `env_session_id` returns None, and the guard short-circuits on a falsy id.
- **Mutation tests (patch-free sed/checkout, no stash):** guard made a no-op -> 2 fail; CLI stops passing the id -> 1 fails; guard only on pause -> 1 fails; ban dropped from arm A brief -> 1 fails; from arm B brief -> 1 fails. Survived: dropping the `type == "start"` filter. That mutant is equivalent today (no other line type carries `session_id`), so it is not a gap.
- **Q3, guard enroll/collect/score/scorepack: follow-up, not in scope.** The bead asks only for pause/resume. Guarding them would not block the owner, because the owner's terminal and a separate scorer session have no `start` line. `score`/`scorepack` from a trial session is the real integrity risk: an arm could score itself. `enroll` writes the randomisation. `collect` is mechanical observation and the least risky. Worth a bead: "apply `_refuse_trial_session` to enroll (non-dry-run), score, scorepack; leave collect/status open". Today only the `_OWNER_ONLY` brief text covers them. My e2e confirmed that `trial collect` runs from a trial session.
- **Remaining limits (documented, not fixable in scope):** a session that skipped `trial start`, unsets the variable, or points `--root` at a checkout without its own start line escapes the guard. It stops mistakes, not a determined session.
- **Findings:** one lesson recorded (subagents inherit `CLAUDE_CODE_SESSION_ID`; the guard binds the arm A crew).
- **Lander:** nothing conflicting. TRIAL.md section 6 bullet only.

## Tailrace (2026-10-14)

**LANDED** PR #45 MERGED, squash sha 953ebf276754a3f9771e73a97cee6dd0a1d35aab (sha-guarded on head 1b01d0c; verify check passed). No conflict.
- `bd close water-mill-mnn`: closed, no auto-export warning.
- Filed follow-up water-mill-2ez (P2, discovered-from mnn): guard enroll (non-dry-run), score, scorepack; collect/status stay open. water-mill-166 now depends on it.
- Not mechanised: the guard only binds sessions with a start line; limits recorded as a finding.
- **Findings:** f-20261014-86e274 (sluice, subagents inherit session id) and f-20261014-af23ed (guard limits), both task water-mill-mnn.
