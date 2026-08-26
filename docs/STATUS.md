# Status

**As of 2026-08-26.** The single place that says where the factory actually is.

`docs/PLAN.md` says what is being built and why. This file says what exists.
When they disagree, this file is right and the plan is stale — **fix the plan in
the same change that moves the line here**, or the two drift again and the plan
becomes a document nobody trusts.

---

## In one paragraph

The **substrate for verification** is built and green: a merge gate, a synthetic
corpus, invariants, a restore that has been drilled, a work graph with 47
specified tasks, and — as of this week — **Water Mill**, a repo-agnostic
orchestrator that claims a task, hands it to an agent, and independently checks
what reached the repository. The **loop has never run against a real agent, not
once, not supervised.** Everything downstream of that fact — pricing, the
maintenance line, cell one, every metric in the plan's §14 — is therefore
unmeasured rather than merely unfinished. The next unit of progress is not a
feature. It is night one.

---

## Roadmap position

Against `docs/PLAN.md` §13. **Actual position: Phase 1 complete, Phase 2 not
started.** Phases 0 and 1 were delivered ahead of schedule inside the life
tracker; two Phase-3 items (the fence engine and its declarative registry)
arrived early with Water Mill; several Phase-0 items were skipped entirely.

| Phase | Plan | Actual |
|---|---|---|
| **0. Foundations** | Multi-tenant data model; append-only entries; backup + restore drill; property tests on invariants; gate runner; budget governor; model-provider seam; per-tenant credential routing | **Partial.** Gate runner, restore drill, invariants and corpus: **done**. Budget governor: **partial** — Water Mill's `--max-spend` is reactive, checked between tasks, and overshoots by up to one task. Multi-tenant data model, model-provider seam, per-tenant credential routing: **not started** |
| **1. Memory** | Beads; `brain/`; loop runner; bead-template linter; verification-tier taxonomy; structured-logging allowlist + scrubber; Rung-0 instrument draft | **Mostly done.** Beads, `brain/`, loop runner (Water Mill), bead template and 47 Tier-1 tasks: **done**. Gate met (40+ Tier-1 beads). Bead-template *linter*, logging allowlist and scrubber: **not started**. Rung-0 instrument exists as PLAN.md Appendix C |
| **2. First loop** | Tier-1 loop overnight; merge-on-green; Falsifier; Boundary Falsifier; handoff skill; escalation format; ranked docket; test beds A/B/C | **Not started.** Zero nights run. Zero of eight supervised calibration tasks. Zero of three test beds. Falsifier and Boundary Falsifier do not exist. Handoff practice exists (`HANDOFF.md`); the escalation format and ranked docket do not |
| **3. Governance** | Fence engine + registry; audit export; content-addressed audit index; MSA draft; counsel; 10 prospect conversations | **Fence engine: done early** (`watermill/contract.py`, enforced against `git diff`, not requested in a prompt). Audit export, audit index, MSA, counsel, prospects: **not started** |
| **4. Launch + boundary proof** | Tracker live with real users; control/data split; Watchtower, Medic, Herald, Quartermaster; three free Rung-0 audits; SOC 2 window opens | **Not started.** Zero of seven standing maintenance roles exist |
| **5. Cell one** | First paid build | **Not started. No date set** — see PLAN.md §13.2, which requires one and does not contain one |
| **6. Prove the model** | Cells 2 and 3; positive contribution margin | **Not started** |

## What is green

| | Evidence |
|---|---|
| Zimmy's merge gate | `make verify` — guard, build, ruff, ESLint, both suites, ~1m31s. CI runs exactly that command |
| Water Mill's own gate | `make verify` — guard, ruff, **132 tests, ~17s**, from a clean `make install` |
| Restore, drilled | `scripts/backup_drill.py`, heartbeat checked daily by a separate job |
| Invariants and corpus | `tests/test_invariants.py` over 17 synthetic personas, deterministic from one seed |
| Work graph | 47 Tier-1 tasks in 4 epics, every one naming its files, its verification and what it must not touch |
| The fence | 24 declared paths, **all present on Zimmy's merged `main`**, checked against staged, unstaged, untracked *and* committed diffs |
| Every cap | Task attempts, wall clock, consecutive failures, per-task timeout, spend, unmetered — each triggered deliberately in a test |
| Every discard path | Uncommitted work, commit without the task id, fenced path touched, gate broken, agent did nothing, agent crashed |

## What is not

Stated as absences, because an absence is what silence looks like from the
outside.

- **Water Mill has never driven a real agent.** Every cap was proven against a
  **stub**. That is a test of the orchestrator's control flow, not of how an
  agent behaves inside it. Neither repository is approved for unattended use and
  both say so.
- **`bd` is not installed in the development container**, so preflight refuses
  at the tooling check here. `./bin/watermill doctor` currently reports exactly
  one refusal, and that is it. It must exist on whatever machine runs a night.
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
| Nights run, supervised | **0** |
| Nights run, unattended | **0** |
| Supervised calibration tasks (of 8) | **0** |
| Consecutive clean nights (Phase 2 gate needs 5) | **0** |
| Foreign test beds stood up (of 3) | **0** |
| Standing maintenance roles built (of 7) | **0** |
| Cells sold | **0** |
| Tier-1 tasks queued and ready | **47** |
| Fenced paths enforced | **24** |

## The next unit of progress

Install `bd`, clear the one refusal, and run **one** task supervised:

```bash
./bin/watermill run zimmy-life-tracker --max-spend 5 --max-tasks 1 --supervised
```

Then read `runs/zimmy-life-tracker/<run-id>/REPORT.md` **and** the prompt that
was actually sent (`prompts/<task>.txt`). The prompt is the most common root
cause of a bad task, which is why it is written to disk.

Nothing in the plan past Phase 2 can be honestly worked on before that number
stops being zero.
