---
status: accepted
---
# The crew-vs-default-Claude trial is pre-registered, with a harm stop that is not a p-value stop

The trial (harness water-mill-d20) compares the crew (arm A) with one default Claude (arm B, no review agent, which merges its own PR by the owner's decision of 2026-10-13) on escaped bug-or-worse defects within 14 days, by Fisher's exact test, with randomisation balanced in blocks of four per repo from a logged seed, no re-randomising, one bead per top-level session, no p-value before the interim at 30 per arm, and no early stopping on p-values. The harm stop (pre-registered 2026-10-14 before any enrolment, water-mill-kt6) pauses the trial on one landed blocker-class defect or an arm B fence breach, judged on that defect alone; only the owner runs `trial pause` / `resume`, and the harness refuses them (and `enroll`, `score`, `scorepack`) from a session that ran `trial start` (water-mill-mnn, water-mill-2ez). Sections 4-7 change only by dated amendment. Source: `docs/TRIAL.md`.

## Consequences

On 2026-10-14 the owner cancelled the first batch: the ledger is archived under `knowledge/trial/archive/`, labels removed, water-mill-166 closed as cancelled (water-mill-fwm.1). The harness stays live and the next trial starts a fresh ledger and seed.
