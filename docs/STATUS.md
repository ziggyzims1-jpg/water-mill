# Status

**As of 2026-08-27.** The single place that says where the factory actually is.

`docs/PLAN.md` says what is being built and why. This file says what exists.
When they disagree, this file is right and the plan is stale — **fix the plan in
the same change that moves the line here**, or the two drift again and the plan
becomes a document nobody trusts.

---

## In one paragraph

The **substrate for verification** is built and green: a merge gate, a synthetic
corpus, invariants, a restore that has been drilled, a work graph, and **Water
Mill**, a repo-agnostic orchestrator that claims a task, hands it to an agent,
and independently checks what reached the repository. **The loop has now run
against a real agent, supervised, twice, and kept work both times** — the first
two rows of evidence this project has ever had that are not about a stub. Two
of eight calibration tasks are done and **neither has been annotated**, so the
finding the exercise exists to produce does not exist yet. Everything
downstream — pricing, the maintenance line, cell one, every metric in the
plan's §14 — remains unmeasured. The next unit of progress is not a feature. It
is the judgement on the two tasks that have already run.

---

## Roadmap position

Against `docs/PLAN.md` §13. **Actual position: Phase 1 complete, Phase 2 not
started.** Phases 0 and 1 were delivered ahead of schedule inside the life
tracker; two Phase-3 items (the fence engine and its declarative registry)
arrived early with Water Mill; several Phase-0 items were skipped entirely.

| Phase | Plan | Actual |
|---|---|---|
| **0. Foundations** | Multi-tenant data model; append-only entries; backup + restore drill; property tests on invariants; gate runner; budget governor; model-provider seam; per-tenant credential routing | **Partial.** Gate runner, restore drill, invariants and corpus: **done**. Budget governor: **partial** — Water Mill's `--max-spend` is reactive, checked between tasks, and overshoots by up to one task. Multi-tenant data model, model-provider seam, per-tenant credential routing: **not started** |
| **1. Memory** | Beads; `brain/`; loop runner; bead-template linter; verification-tier taxonomy; structured-logging allowlist + scrubber; Rung-0 instrument draft | **Mostly done.** Beads, `brain/`, loop runner (Water Mill), bead template and 47 Tier-1 tasks: **done**. Gate met (40+ Tier-1 beads). **Verification-tier taxonomy: done** — the eight root-cause buckets in `watermill/tasklog.py`, counted across projects, annotated by hand. Bead-template *linter*, logging allowlist and scrubber: **not started**. Rung-0 instrument exists as PLAN.md Appendix C |
| **2. First loop** | Tier-1 loop overnight; merge-on-green; Falsifier; Boundary Falsifier; handoff skill; escalation format; ranked docket; test beds A/B/C | **Started.** Two supervised tasks run against a real agent, both kept, neither annotated. **Merge-on-green: built** — `watermill land` opens the pull request, waits for CI and merges, and refuses to merge on a failed verify (`watermill/land.py`, `review.*` in the contract). Zero unattended nights. Zero of three test beds. Falsifier and Boundary Falsifier do not exist. Handoff practice exists (`HANDOFF.md`); the escalation format and ranked docket do not |
| **3. Governance** | Fence engine + registry; audit export; content-addressed audit index; MSA draft; counsel; 10 prospect conversations | **Fence engine: done early** (`watermill/contract.py`, enforced against `git diff`, not requested in a prompt). Audit export, audit index, MSA, counsel, prospects: **not started** |
| **4. Launch + boundary proof** | Tracker live with real users; control/data split; Watchtower, Medic, Herald, Quartermaster; three free Rung-0 audits; SOC 2 window opens | **Not started.** Zero of seven standing maintenance roles exist |
| **5. Cell one** | First paid build | **Not started. No date set** — see PLAN.md §13.2, which requires one and does not contain one |
| **6. Prove the model** | Cells 2 and 3; positive contribution margin | **Not started** |

## What is green

| | Evidence |
|---|---|
| Zimmy's merge gate | `make verify` — guard, build, ruff, ESLint, both suites, ~1m31s. CI runs exactly that command |
| Water Mill's own gate | `make verify` — guard, ruff, **196 tests, ~23s**, from a clean `make install` |
| Restore, drilled | `scripts/backup_drill.py`, heartbeat checked daily by a separate job |
| Invariants and corpus | `tests/test_invariants.py` over 17 synthetic personas, deterministic from one seed |
| Work graph | 47 Tier-1 tasks in 4 epics, every one naming its files, its verification and what it must not touch |
| The fence | 24 declared paths, **all present on Zimmy's merged `main`**, checked against staged, unstaged, untracked *and* committed diffs |
| Every cap | Task attempts, wall clock, consecutive failures, per-task timeout, spend, unmetered — each triggered deliberately in a test |
| Every discard path | Uncommitted work, commit without the task id, fenced path touched, gate broken, agent did nothing, agent crashed |
| Shipping to Loki | `watermill ship` reads the ledger and task log and pushes what is new. Off the run loop, high-water mark advances only after a push returned. **Pointed at a real Loki, which accepted the push** — the transport is no longer a guess |
| Publishing to Zimmy | `watermill publish` assembles one status snapshot per project (queue, runs, tasks, pull requests, attention) and PUTs it to `/api/watermill`. **Built, tested against a fake server, not yet pointed at a real Zimmy** -- by the rule above, a guess until it has met its real dependency once |
| The knowledge surfaces | `notes` in the contract reaches the prompt; `tasklog.py` records one line per task; `watermill tasks` counts root causes across projects. **All three are empty** — see below |

## What is not

Stated as absences, because an absence is what silence looks like from the
outside.

- **Water Mill has never driven a real agent.** Every cap was proven against a
  **stub**. That is a test of the orchestrator's control flow, not of how an
  agent behaves inside it. Neither repository is approved for unattended use and
  both say so.
- **`watermill land` has now run against a real forge, once, and found a bug on
  its first attempt.** It opened zimmy-life-tracker#98 correctly and then failed
  its own verify: `gh pr checks` was asked in the same second as `gh pr create`,
  answered "no checks reported", and exited non-zero — on a check that went
  green two minutes later. A tool that was not ready read as a red build. The
  landing was completed by hand and the window is fixed, but the wider lesson
  stands: **every one of these commands is a stub-tested guess until it has met
  a real forge once.** Nothing else in the review block has.
- **Both kept tasks have now landed.** `watermill/20260827-060430` merged as
  zimmy-life-tracker#98, and `watermill/20260826-231244`
  (`zimmy-life-tracker-jam.1`) reached `main` in zimmy-life-tracker#97. Neither
  is annotated, which is the part that still counts as missing.
- **Loki is connected; the alert on absence is the half still missing.** The
  transport was tested against a recorder, which proved the payload Loki would
  receive and nothing about whether Loki accepts it. It has now met a real one
  and the push was accepted, so `ship` is off the guess list — the second
  command here to meet its real dependency, after `land` met a real forge. What
  that does *not* yet buy is the reason the shipping exists: a night that
  silently did not run looks exactly like a quiet night, and only an alert
  firing on `count_over_time(...[24h]) == 0` can tell them apart
  (`docs/OBSERVABILITY.md`). A dashboard somebody has to remember to open is
  not that. Until that alert exists, absence is still unwatched.
- **The knowledge surfaces exist and hold nothing.** A contract can carry
  `notes` into the prompt, the task log can count root causes, and
  `docs/calibration/` has a record per project — but every one of them is empty,
  because a note is written after a task goes wrong and no task has run. They
  were built now so the first supervised session has somewhere to put what it
  finds; filling them in from either project's CLAUDE.md would put guesses in
  every prompt, and a guess is indistinguishable from a lesson once it is in the
  list.
- **`bd` is installed and preflight is green.** `./bin/watermill doctor` reports
  zero refusals for `zimmy-life-tracker`. This was the one thing blocking a
  first run and it is no longer blocking anything.
- **Zero of the plan's seven metrics (§14) are instrumented.** Water Mill's
  ledger records cost and verdict per run, which is the seed of the cost oracle
  and nothing more. Human-minutes per cell, escalations per day and contribution
  margin have no counter anywhere.
- **The three pricing numbers do not exist.** PLAN.md §8.3 requires 90 days of
  measured maintenance before a price is set. The clock starts at the first
  successful night, not today.
- **Zero of the four Sovereign seams exist** (PLAN.md §6.8): per-tenant
  credential routing, telemetry allowlist, content-addressed audit index,
  secrets abstraction. The plan calls these near-zero cost *if done now*, which
  means the cost is rising every week they are skipped.
- **The target sector is unchosen** (PLAN.md §17.1), and it blocks the Phase 4
  Rung-0 audits.
- **The backup does not leave the machine.** Preflight can enforce "a restore
  was verified"; it cannot enforce "the export left the building". A mistake is
  recoverable; a dead SD card is not.
- **Two overnight loops now exist.** Zimmy's `scripts/loop.sh` and Water Mill's
  engine do the same job. Both files now say which is which; deleting the bash
  one is an open decision.

## Counters

Every number that should be climbing and is currently zero.

| | Now |
|---|---|
| Nights run, supervised | **2** |
| Nights run, unattended | **0** |
| Supervised calibration tasks (of 8) | **2** |
| Consecutive clean nights (Phase 2 gate needs 5) | **0** |
| Foreign test beds stood up (of 3) | **0** |
| Standing maintenance roles built (of 7) | **0** |
| Cells sold | **0** |
| Tasks with a recorded root cause | **0** -- the gap that matters |
| Contract notes carried into a prompt | **0** |
| Tier-1 tasks queued and ready | **48** |
| Fenced paths enforced | **24** |

## The next unit of progress

Two tasks have run and been kept. Neither has a judgement on it, and the
judgement is the deliverable — the code was always going to be checked by the
gate without anybody's help.

```bash
./bin/watermill tasks --unannotated
```

Then read `runs/zimmy-life-tracker/<run-id>/REPORT.md` **and** the prompt that
was actually sent (`prompts/<task>.txt`). The prompt is the most common root
cause of a bad task, which is why it is written to disk.

Then record what you concluded, while it is still fresh:

```bash
./bin/watermill annotate zimmy-life-tracker <task-id> <root-cause> --note "..."
```

That is the first row of `docs/calibration/zimmy-life-tracker.md` and the first
line in the task log with a judgement on it. Both are empty right now, and the
counters above stay at zero until one task has been watched and named.

Nothing in the plan past Phase 2 can be honestly worked on before that number
stops being zero.
