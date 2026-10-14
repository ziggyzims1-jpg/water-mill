# Handoff — water-mill-fwm.4

## Millstone (2026-10-14)

- **Where things stand.** Branch `bead/fwm-4`, PR #52 (https://github.com/ziggyzims1-jpg/water-mill/pull/52). `make verify` green in the worktree (795 passed). Not blocked. Red-before-green evidence is in the PR body (8 new/changed tests fail on origin/main 08f833c).
- **What was tried and did not work.**
  - I first edited `canon/` in the MAIN checkout by mistake (cd'd to `$REPO`, not `$WT`): the exact trap the role file warns about. Caught before committing; moved via a patch file into the worktree and restored the main checkout with `git checkout -- <3 files>` plus `rm` of the untracked bolter.md. Main checkout is clean.
  - Put `CREW_ROLES` in `recorded.py` first; `recorded` imports `sessionlog`, so `sessionlog` importing it was circular. It lives in `agentlog.py` now (both already import it).
  - A first version of the "no hard-coded handoff dir" test was a chain of `.replace()` hacks; replaced by a line-wise check that the only line naming `brain/handoffs/mill` is the `$HANDOFFS` definition.
- **Lessons for the graph.**
  - A list of crew roles must have one definition (`agentlog.CREW_ROLES`) pinned against `canon/common/.claude/agents/*.md` by a test, or a new agent silently misses one of the five readers.
  - water-mill's own `.claude/agents` is rendered with `sync.make_plan` + `apply_plan` on the worktree root; no PR flow is needed to refresh it, and `validate` is green for water-mill only after that.
  - A bolter cannot push, so its handoff section and run record only reach the branch if sluice commits them; the crew files make sluice the sole pusher for exactly that reason.
- **Look here first.** `canon/common/.claude/agents/sluice.md` steps 4a, 5c, 5d (red-before-green bounce, bolter blocking findings, auto-mill filing) and `tests/test_bolter.py`.
- **Seams.** `agentlog.CREW_ROLES` and its readers; `trial.brief`; `crewlog.collect`; the canon agent files' contract (pinned in `tests/test_bolter.py`).
- **Open questions for the human.**
  - Bolter model is `sonnet` (report-only, checklist-bounded); change in `bolter.md` front matter if you want opus.
  - How a bolter in a laptop run gets its record file committed: I made it quote the file's line in its report and let sluice commit it (bolter has no push). Say if you would rather bolter write `knowledge/agent-runs/` directly in `$REPO`.
  - `docs/TRIAL.md` line 3 still says "millstone -> sluice -> tailrace" (pre-registered text); a dated amendment records the change instead.
- **Follow-ups worth a bead.** `watermill sync` the four crew files + new workshop CLAUDE.md to siblings (owner step, `validate` lists them as differing); `docs/AI.md` (fwm.7) must mention bolter and auto-mill (validate will warn once it exists); the cell template's own docs may name the three-agent crew. No scorecard module exists in the repo, so nothing was changed there.
- **Findings:** none filed by millstone (sluice/tailrace file from the lessons above).
