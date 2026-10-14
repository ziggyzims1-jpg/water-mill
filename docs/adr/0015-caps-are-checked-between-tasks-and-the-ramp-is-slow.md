---
status: accepted
---
# Caps are checked between tasks; the ramp starts low and any revert halts it

Six caps (task attempts, wall clock, consecutive failures, per-task timeout, unmetered tasks, spend) are checked between tasks, never during one, because halting mid-task risks a partial commit. The spend cap therefore overshoots by up to one task and says so. The task cap counts attempts, not completions (a run where every task escalates never increments a completion count). Night 1 is 5 tasks and 3 hours, raised only on zero reverts; a cap is never raised to compensate for a thin queue. Nights run so far: 0 unattended. Source: `docs/SAFETY.md` (layer 4, "The ramp"), `CLAUDE.md`, `watermill/caps.py`.
