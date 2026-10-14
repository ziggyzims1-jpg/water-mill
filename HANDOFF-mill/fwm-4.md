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

## Sluice (2026-10-14)

- **Verdict: BLOCKED (would have been approve_after_fixes).** I pushed one fix commit, 70a8675, to `bead/fwm-4`. Then the orchestrator relayed an owner decision: set bolter's `model:` to opus. My command to make that edit (sed on `canon/common/.claude/agents/bolter.md` plus a re-render via `sync.make_plan`/`apply_plan`) was denied by the auto-mode classifier ("Unrequested Commit in a Connected App"). After that, a read-only `git status` in the worktree was denied too ("Self-Modification"). Per the owner's denial rule I stopped there. **Not done:** the bolter model change, `agents record` for this run (tag wm-run-4b1b060799c2) and its commit, and removing the worktree `scratchpad/wt-rev-52` (clean at 70a8675, nothing uncommitted).
- **Scope / fidelity.** The bolter is report-only (detached worktree, no push, no commit, no bead filed), and its blocking vs advisory split matches the epic. Sluice is the only reviewer that pushes, acts on bolter's blocking findings (fix or rebut), and bounces a PR with no red-before-green evidence unless it is docs-only. The millstone changes (tdd, seams list, diagnosing-bugs) and the trial briefs are fine. Fence: no fenced path is touched. `canon/workshop/CLAUDE.md` is the workshop file plus the crew-order line, the rule, and one extra edit to the handoff bullet (adds `## Bolter` and the HANDOFF-mill note). I judged that acceptable. The workshop file itself is untouched (mtime Sep 3). `$HANDOFFS` is defined in all four crew files, and no crew file hard-codes `brain/handoffs/mill` anywhere else. The new hook blocks nothing the crew is told to run: only `git checkout -- <file>`, `reset --keep` and `worktree remove --force`, all of which it allows.
- **Found and fixed (70a8675).** (1) tailrace.md did not state the auto-mill limits, although the workshop copy says it repeats them. I added step 4a: the limits, plus a NEEDS_MANUAL report for any labelled bead that breaks one. (2) sluice.md said it was the sole pusher of the whole crew, but millstone 7a pushes its own record. I scoped it to the reviewers, said how to write bolter's record line once bolter's worktree is gone, and stated P3 in 5d. (3) Mutation gap: hard-coding `bolter_rounds: 0` in `crewlog.parse_record` left the suite green. I added a test that goes through `parse_record`. (4) I added a test that every copy of the rule (sluice.md, tailrace.md, canon/workshop/CLAUDE.md, CLAUDE.md) carries every limit. I mutation-checked both new tests. (5) The agentlog CREW_ROLES comment wrongly said trial.py imports it; corrected.
- **Verified.** `make verify`: 795 passed on the PR head, 797 passed after my fixes. `watermill validate`: water-mill matches canon; the siblings differ, as expected. Mutations: dropping bolter from CREW_ROLES fails test_bolter, and dropping bolter from the arm B brief fails test_trial. The red-before-green evidence in the PR body is believable.
- **Remaining.** (a) The bolter model needs opus, in canon plus the re-rendered `.claude/agents/bolter.md`. (b) The bead says "sync to all crew targets including Hillel-Programming". That has not been done: validate lists zimmy, cell-1b, cheme-solver and hillel as differing. It has to happen after merge, before the bead closes or as a filed follow-up. (c) docs/AI.md (fwm.7) must carry the rule. (d) Minor: sluice steps run in the order 5, 5a, 5c, 5d, 5b.
- **Sign-off (later, on the orchestrator's instruction).** The run record was committed as c0f73eb (`knowledge/agent-runs/sluice-water-mill-fwm.4-aeba49d4de3b.jsonl`, verdict approve_after_fixes). The first tag, wm-run-4b1b060799c2, matched 2 transcripts and recorded nothing, so the record used a fresh tag, wm-run-ebc448b79000. The worktree is removed. The opus edit is still not made: the orchestrator is raising it with the owner.
- **Findings:** f-20261014-8f6c80 (test handoff-derived fields through parse_record), f-20261014-0883f3 (a rule kept in several files needs an every-copy test; destination gate).

## Tailrace (2026-10-14)

**LANDED** PR #52 squash-merged as a9edceea0502a9d30b634cbf4c95443aa1edbcc6 (sha-guarded on c0f73eb). verify green (https://github.com/ziggyzims1-jpg/water-mill/actions/runs/38580397684). No conflict. `git pull --ff-only` clean. Remote branch bead/fwm-4 still existed after merge (gh merge was run without --delete-branch because of the sha-guard command); deleted in the follow-up push step.
- `bd close`: "Closed water-mill-fwm.4 ... Merged in PR #52", no auto-export warning. `bd import` first (45 issues), then `bd export`; sorted diff showed only the fwm.4 line.
- Findings filed: 4 tailrace/millstone lessons (task water-mill-fwm.4), plus sluice's two already in the working tree. All `--cause pending`.
- Run record: knowledge/agent-runs/tailrace-water-mill-fwm.4-a5780bea8fb4.jsonl.
- Left for the orchestrator/owner: `watermill sync` to siblings (not run, per instruction); bolter model opus decision (untouched); docs/AI.md (fwm.7).
- **Findings:** f-20261014-8f6c80, f-20261014-0883f3 and four new ones above.


## Tailrace — crew sync PRs (2026-10-14)

All five diffs touched only the four agent files and .claude/watermill-managed.json; `verify` green on each head; sha-guarded squash merges; branch sync/water-mill-d5dfe0e8 deleted in each.
- zimmy-life-tracker #231: MERGED 24e10504ac652b39654eec0548f9394baf152f83 (local pull --ff-only ok)
- zim-dashboard-demo-cell-1b #34: MERGED 5be352abfe18cf9b1a8079b6b8e6eb61a829b03a (pulled)
- cheme-solver #35: MERGED fd119240a2d8a734245f2d0a275048f914947b4f (pulled)
- Hillel-Programming #65: MERGED 0758214f0a916b6a5c43a355032a327b2888b220 (local only fetched; checkout left on claude/laughing-thompson-1qbanx)
- watermill-cell-template #12: MERGED ded0fbc748bc76dbecee7455bb22bf7097223d10 (pulled)
Nothing skipped, no conflicts. No bead closes (no per-PR bead).
