# Handoff — water-mill-fwm.7

## Millstone (2026-10-14)

**Where things stand.** Session branch `claude/fwm-7`, PR #58 (https://github.com/ziggyzims1-jpg/water-mill/pull/58). `docs/AI.md` written; linked from README.md, CLAUDE.md (Layout row) and canon/workshop/CLAUDE.md; STATUS.md updated; `watermill validate` warns via `sync.unmentioned_in_ai_doc` (exit code unchanged). `tests/test_sync.py` 50 passed. Full `make verify`: guard and ruff pass, 851 passed, 2 failed (`tests/test_cloud_setup.py` two tests, "tracked files changed" under `.beads/`); the same 2 fail on a clean `origin/main` worktree in this container, so environmental. Not blocked.

**What was tried and did not work.**
- The bead says `watermill register`; no such subcommand exists (`add` is it, and it runs sync last). AI.md says so.
- First red-before-green snapshot used `git diff` of everything then reverted only code files, so re-applying the whole patch failed; fixed with `git apply --include=` for the two code files.
- `sync-factory.sh` is not wired in `.claude/settings.json` (grep: only CLAUDE.md and the script itself), so AI.md says that rather than claiming it is.

**Lessons for the graph.**
- `watermill validate`'s canon-agent/skill names come from `canon/common/.claude/agents/*.md` and the directories under `canon/common/.claude/skills/`; a new agent or skill must be named in docs/AI.md or validate warns.
- `tests/test_cloud_setup.py` fails two tests in the cloud container on clean main, so `make verify` is not green there regardless of the change.

**Seams.** `watermill.sync.unmentioned_in_ai_doc` (public function, definition of "mentioned"); `watermill validate` CLI (warning printed, exit 0); the real-factory test pinning docs/AI.md completeness.

**Look here first.** `docs/AI.md` section 10 (trial) against `docs/TRIAL.md` and `watermill/trial.py` (`_refuse_trial_session`, `brief`, `due_for_scoring`); and `sync.unmentioned_in_ai_doc`.

**Open questions for the human.** Owner memory contents and where sync-factory.sh / the beads-sync workflow are wired are not in the repo; AI.md section 12 says so. Owner must run `watermill sync workshop` on the laptop (workshop CLAUDE.md changed).

**Follow-ups worth a bead.** The two `test_cloud_setup.py` failures in the cloud container; the bead text says `register` but the command is `add`.

Run record: knowledge/agent-runs/millstone-water-mill-fwm.7-a1d72bf2352a.jsonl (pr 58).

## Bolter (2026-10-14)

PR #58, head 4e16c66, bead water-mill-fwm.7. Report-only; nothing pushed.

**Sources.** CODING_STANDARDS.md, CONTEXT.md, docs/adr/0001-0018, CLAUDE.md (root, canon/workshop). Missing: CONTRIBUTING.md (not a finding). I checked every factual claim in docs/AI.md against the file it cites (crew files, ADRs, TRIAL.md, trial.py, sync.py, cli.py, settings.json, cloud-setup.sh, sync-factory.sh, the guardrail, KNOWLEDGE.md, OBSERVABILITY.md, CLI --help). Almost all of them hold: trial guards, constants, CLI flags, settings table, guardrail, sync mechanics.

**Blocking** (the bead says "describe only what exists"; AI.md line 4 makes the same promise):
1. docs/AI.md:159 cites ADR-0014 for "Knowledge has four destinations". ADR-0014 is root cause by a person. ADR-0007 is the ADR that cites that convention. Fix: cite ADR-0007.
2. docs/AI.md:263-265 says "An agent may only *propose*: a proposal is quarantined ...". docs/KNOWLEDGE.md ("What an agent may write") quarantines only the MCP `propose` tool. The crew run `watermill remember` on the CLI (bolter.md step 5, sluice.md 5a, tailrace.md 5), and those findings are not quarantined. Fix: "An agent started by `watermill run` writes through the MCP `propose` tool, which quarantines ...; crew agents call `remember` directly."
3. docs/AI.md:265-266 says "Crew roles file with their role as a tag (bolter: `--tag bolter`)". Only bolter.md says that; sluice.md and tailrace.md use `--tag <topic>`. Fix: "Bolter tags its findings `bolter`".
4. docs/AI.md:104 says "All four are told to work in their own git worktree". Tailrace makes a worktree only to resolve a conflict (step 3) and, in cloud mode, after the merge. Fix: "millstone, bolter and sluice work in their own worktree; tailrace makes one only to resolve a conflict or, in cloud mode, for its post-merge commits".
5. docs/AI.md:184-186 says the dated snapshots each say "at the top what supersedes it". Only HANDOFF.md does. HANDOFF-2026-08-28.md and HANDOFF-2026-10-13.md carry no such line. Fix: "HANDOFF.md says at the top which newer file supersedes it".

**Advisory**
- docs/AI.md:40-42 says "the crew agents additionally read the CLAUDE.md of every subfolder", citing millstone.md step 4. Only millstone does. Bolter treats those files as standards. Say "millstone".
- docs/AI.md:9-11 says the WARNING means an agent or skill "cannot ship" undescribed. The warning cannot stop it. What does is `tests/test_sync.py::test_the_real_factorys_ai_doc_names_every_agent_and_skill` in the gate. Cite the test.
- Possible Divergent Change: watermill/sync.py now holds a docs-completeness check next to distribution. The CLAUDE.md Layout row for sync.py still says only "the drift check `validate` runs". Add "and the docs/AI.md mention check" to that row.
- docs/AI.md:359-365 ("Import before export") is tailrace's laptop step 4 rule, listed under cloud constraints. Consider moving it or saying it applies on both surfaces.
- [auto-mill candidate] CLAUDE.md:51 (pre-existing, not in the diff) says "today the five crew agents". canon has four, and AI.md says four. Fix: "four".
- The code (sync.synced_names, sync.unmentioned_in_ai_doc, the cmd_validate warning, the six tests) breaks no documented standard. The local `from . import sync` matches the file's existing pattern.

**Findings:** f-20261014-fae317 (lesson: only the MCP `propose` tool quarantines; `watermill remember` from a crew agent does not). It was written to /home/user/water-mill/knowledge/findings.jsonl, uncommitted, for tailrace.

**Run record:** knowledge/agent-runs/bolter-water-mill-fwm.7-a518abadd930.jsonl (copy at <scratchpad>/bolter-58/knowledge/agent-runs/). Sluice commits it.

## Sluice (2026-10-14)

**Verdict: approve_after_fixes.** Fixes in 3f39df6 (on top of 4e16c66).

**Scope.** Every topic the bead lists is in `docs/AI.md` (harnesses/settings/hooks/SessionStart, crew and order, rules and where they live incl. memory/fence/handoffs/beads-in-git, 11 skills with source, graph, agent-run tracking, Loki/Grafana, cloud, sync, trial in depth incl. how to start a new trial, adding a project). Linked from README.md, CLAUDE.md, canon/workshop/CLAUDE.md. STATUS.md updated. No fenced path, no `.beads/` in the PR. `register` in the bead is `add` in the CLI; AI.md says so.

**Red before green.** Reproduced: origin/main + the PR's `tests/test_sync.py` and `docs/AI.md` only: 6 failed, 44 passed (AttributeError `unmentioned_in_ai_doc`). Believable and matches the PR body.

**Bolter blocking findings: all five fixed in 3f39df6.** (1) ADR-0014 -> ADR-0007 (verified: 0007 cites "four destinations", 0014 is root cause by a person). (2) Quarantine now attributed only to the MCP `propose` tool; crew `remember` is direct (KNOWLEDGE.md:26,145). (3) Only bolter tags by role. (4) Tailrace worktree only for a conflict or cloud post-merge. (5) Only HANDOFF.md points at a newer snapshot (checked the heads of all three). Advisories also fixed: subfolder CLAUDE.md (millstone; bolter treats them as standards), gate test named as what stops shipping undescribed, import-before-export marked laptop rule too, CLAUDE.md "five" -> "four" crew agents, sync.py Layout row names the AI.md check. Also fixed myself: "Millstone, bolter and sluice ... gets/runs" grammar and claim (tailrace records too but does not start with recall); guard call sites (`_set_pause` for pause/resume, `cmd_trial` for enroll/score/scorepack).

**Verified independently.** Trial section spot-checked against `watermill/trial.py` (MIN_N 8, INTERIM_N 30, FINAL_N 60, SEVERITIES, BLIND_EXCLUDE, ARM_B_SELF_MERGES, COMPARED_COST_BASES, block seed string, hand-only/fence-directed/fence-clear, guard list) and `knowledge/trial/` (only archive/): holds. `make verify` in the worktree: 851 passed, 2 failed in `tests/test_cloud_setup.py`; the same 2 fail on clean origin/main here (container bd 1.3.1 vs pin 1.2.2). Environmental; CI is the judge. `./bin/watermill validate` prints no WARNING (its exit 1 here is unregistered sibling checkouts missing in the container, same on main).

**Mutation tests.** Dropping the lookahead, dropping `re.I`, disabling the cli print, making the warning fail the exit code, and globbing no agents each failed a test. **Dropping the lookbehind survived** (the test only had suffix cases): fixed in 3f39df6 by adding `pre-beta` / `my-alpha-skill`; the mutation now fails.

**Findings:** f-20261014-e239c5 (whole-word regex needs a prefix case), f-20261014-20deed (crew doc claims must be checked per agent file). Uncommitted in the main checkout's `knowledge/findings.jsonl`, for tailrace, along with bolter's f-20261014-fae317.

**Auto-mill beads:** none. Bolter's one candidate (CLAUDE.md "five") was fixed in place.

**Not fixed / for the lander.** None blocking. `watermill sync workshop` on the laptop is the owner's (workshop CLAUDE.md changed). CLAUDE.md Layout table rows may conflict with another PR touching that table: union. Run records: bolter-water-mill-fwm.7-a518abadd930.jsonl (copied verbatim from its report) and this sluice record, committed with this section.

## Tailrace (2026-10-14)

**LANDED** -- PR #58 squash-merged as dd781ecf67c7a1e2890f76a1c08fdb4201ca0ab9 (verified head 612dbb7, `verify` and `sync` check-runs success).

- Merged origin/main into claude/fwm-7 (merge 612dbb7): no conflicts, CLAUDE.md Layout table merged cleanly. #60 added no new canon agent or skill (it ships beads-sync workflow + scripts/beads_merge.py), so docs/AI.md mention check and tests/test_sync.py pass unchanged.
- Local `make verify`: 858 passed, 2 failed (tests/test_cloud_setup.py, the known bd 1.3.1 vs pin 1.2.2 env failures). CI green.
- `bd close water-mill-fwm.7`: "Closed water-mill-fwm.7 ... Merged in PR #58", no export warning. Committed only the fwm.7 line of .beads/issues.jsonl; `bd export` also reordered dependency entries of 4 other beads (166, 9tx, fwm.4, pu9, same sets, order only), which I did not commit.
- auto-mill: none.
- Findings: bolter/sluice f-20261014-fae317, f-20261014-e239c5, f-20261014-20deed moved onto main; two millstone lessons recorded for water-mill-fwm.7.
- Owner must run `watermill sync workshop` on the laptop (workshop CLAUDE.md changed).
