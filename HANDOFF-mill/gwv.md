# Handoff — water-mill-gwv

## Millstone (2026-10-05)

**Where things stand.** PARTIAL, blocked on one step. PRs (branch bead/gwv): water-mill #27, watermill-cell-template #6, zim-dashboard-demo-cell-1b #28, zimmy-life-tracker #219. `make verify` green in water-mill (383 passed); the others are docs only. `~/Documents/code/.claude/agents/{millstone,sluice,tailrace}.md` copied from the water-mill PR content (md5 50d8753f / d96f0e17 / f207002f), so the four copies match the PRs but are ahead of origin/main until the PRs merge. `scripts/sync-factory.sh` shipped and tested against a clone (ff when behind, dirty tree and missing dir untouched, rc 0, stdout empty).

**BLOCKED: the SessionStart wiring.** Writing `.claude/settings.json` (water-mill, zimmy-life-tracker, zim cell, new file in the cell template) was denied by the auto-mode classifier, reason `[Self-Modification]`; I did not retry or work around it. Nothing in the PRs touches any settings.json, so sync-factory.sh is not yet called by any hook. Intended commands:
- water-mill: `bash "$CLAUDE_PROJECT_DIR/scripts/sync-factory.sh" >/dev/null || true; bash "$CLAUDE_PROJECT_DIR/scripts/cloud-setup.sh"; bd prime --hook-json` (timeout 600)
- zimmy: prefix the existing command with `w="$CLAUDE_PROJECT_DIR/../water-mill/scripts/sync-factory.sh"; if [ -f "$w" ]; then bash "$w" >/dev/null || true; fi; `
- zim cell and template (template has no settings.json today): same prefix + `bd prime --hook-json`.
The owner or the orchestrator needs to make those four edits (or grant the permission).

**Tried and did not work.** The task text says `recall "" --task <id>` for tailrace's verification; `recall` has no `--task` flag and an empty query returns "No match", so tailrace instead greps `knowledge/findings.jsonl` for the quoted bead id (`refs.tasks`). `--cause` buckets: `gate-hole`, `agent-error` (and `none` as an annotation) are `tasklog.HUMAN_ONLY`; I told agents to use `none` and leave those to the owner. Check that this matches how `remember` validates once 4t3 lands.

**Look here first.** `.claude/agents/tailrace.md` step 5 (the verify + push-graph procedure) and `scripts/sync-factory.sh`.

**Open questions.** Should the hook also fast-forward the session's own repo? I limited it to the water-mill checkout per the bead. Should agents in a cloud session with no sibling `../water-mill` be told something other than "say so and carry on"?

**Follow-ups worth a bead.** Once brx lands, drop the "lands with water-mill-brx" caveat from tailrace.md in all four copies. Once 4t3 lands, align the `--cause/--tag/--path/--task` wording with the real validation. A check that the four agent copies stay byte-identical.

**Findings:** none recorded by me -- I did not run `watermill remember`; the lessons above (no `--task` on recall, classifier blocks .claude/settings.json) are for tailrace/orchestrator to file.

## Sluice (2026-10-05)

**Verdict: approve_after_fixes on all four PRs** (water-mill #27, watermill-cell-template #6, zim-dashboard-demo-cell-1b #28, zimmy-life-tracker #219). `gh pr checks` green on all four after my pushes; water-mill `make verify` 383 passed in my worktree. No PR touches any settings.json (checked with `git diff --name-only`). No watermill/*.py touched.

**Copies.** millstone/sluice/tailrace .md are byte-identical across the three repo branches and `~/Documents/code/.claude/agents` (md5 50d8753f / d96f0e17 / b8199e2d). I updated the workshop tailrace.md by hand; it is ahead of origin/main until the PRs merge.

**Found and fixed (water-mill 209eb94, template 49b1db2, zim cell bca60d6, zimmy 982950e):**
- tailrace step 5 ran `git pull --rebase` before committing findings.jsonl. Git refuses a pull with unstaged changes, so it failed every time (reproduced). It now commits first, then pulls, then pushes, and reports NEEDS_MANUAL when `$WM` is not on main or has other modified files.
- "O_APPEND lines merge as a union" was false. Two branches that each append to findings.jsonl hit CONFLICT on rebase (reproduced). Added water-mill `.gitattributes` `knowledge/findings.jsonl merge=union`, and confirmed it merges cleanly.
- `review --lag` ran before the handoff was written. brx's `landed.parse` keys on the `**LANDED**` marker in the handoff, so the current bead could never show up. Now lag runs after the handoff section is written, with its output quoted afterwards. Grep (now `-ciF`) is only the fallback until brx lands.
- sync-factory.sh watchdog: `kill $worker` killed the subshell but orphaned git/ssh. They held the hook's stderr pipe, so with a 3s limit and a stalled ssh the piped run took 60s. Now the worker runs in its own process group (`set -m`, `kill -- -PID`) with stderr going to a temp file that is replayed afterwards, and pull's stderr is silenced. Retested piped hang (3s, no orphans), behind (ff + one stderr line), dirty, detached, other branch, missing dir, non-repo, no network: all rc 0 with zero stdout bytes, on /bin/bash 3.2.
- zimmy SKILL.md had a bare `git push origin main`, which from zimmy pushes zimmy, and it also pulled before committing. Every step is now `git -C ../water-mill`, commit comes first, and `--task` is required only when the lesson came from a bead.

**Causes (check 3).** `tasklog.HUMAN_ONLY = {gate-hole, none, agent-error}`. It includes `none`, and it only gates `hint_for` (machine-suggested buckets in the task log). `remember` doesn't enforce it, on main or on 4t3. 4t3's `_check_cause` requires a cause from ROOT_CAUSES ("'none' is an answer") and at least one tag, with no HUMAN_ONLY check. So the instructions ("`none` when not a task failure; gate-hole/agent-error are the owner's") are right and compatible with 4t3. Millstone's handoff claim that HUMAN_ONLY is what reserves them is imprecise. It is not enforced on findings.

**Not fixed / concerns.**
- Water-mill keeps its mill handoffs in `HANDOFF-mill/`, but the agents (and brx `landed.HANDOFF_DIR`) read `brain/handoffs/mill/`. Water-mill beads will never appear in `review --lag`. Pre-existing, so I'm noting it here. Worth a bead.
- `watermill remember watermill-cell-template ...` fails because the template is not a registered cell. Agents there should use `''` or report it. Minor.
- Once brx merges, drop the "until then grep" clause from all four tailrace copies. The SessionStart wiring is still BLOCKED (owner).

**Findings:** f-20261005-bf72b7, -411b57, -fd22b7, -670ca7 (all `--task water-mill-gwv`). They are uncommitted in water-mill knowledge/findings.jsonl, for tailrace to commit.

**For the lander:** land the four PRs in any order (no shared files). The `.gitattributes` only takes effect in a checkout once #27 is on its main.

## Sluice, second pass (2026-10-05)

**Verdict still approve_after_fixes on all four**; CI green after the new pushes, water-mill `make verify` passed. Millstone's later commits (4edca79/d46ea52/deb60d6) were already under my first pass.

- **Cause ruling applied** (orchestrator): `none` is `tasklog.HUMAN_ONLY` too, so my first-pass call that the instructions were right was wrong. Crew and the handoff skill now say: a non-human bucket (incomplete-files/missing-context/too-large/vague-goal/weak-scope) only when it clearly fits, otherwise `--cause pending`; never none/gate-hole/agent-error. Commits: water-mill d60b973, template 3c21df6, zim cell 11fe149, zimmy a5148da. Copies byte-identical incl. workshop (sluice 594bfd78, tailrace fd944b73, millstone 50d8753f).
- brx merged (db48221): tailrace's check is now `review --lag` only, run after the handoff is written; grep fallback and "until brx" caveats removed (also in sync-factory.sh's comment).
- **Findings fixed:** my four first-pass findings carried `root_cause: none`. Removed while uncommitted and re-recorded with a blank cause as f-20261005-df2aac / -c0b715 / -de41da / -916c4a (`--task water-mill-gwv`); committed and pushed to water-mill main as 2e6d5a1. The earlier ids (bf72b7 etc.) no longer exist.
- **Dependency for 4t3:** current main's `remember` stores any `--cause` string, so `pending` works today. 4t3 must accept `pending` in `_check_cause` (its branch as I read it allowed only ROOT_CAUSES), or every crew remember will be refused once 4t3 lands.

## Sluice, third pass (2026-10-05)

Orchestrator's blocking list: cause rule and brx/grep removal were already in d60b973 (second pass). New this pass: tailrace forbids `git pull --autostash` / `rebase.autoStash` explicitly; the zimmy skill says HUMAN_ONLY causes only when the owner stated that cause in the session, and bans `pull --autostash` (zimmy 08ba8da, PR #219 still open). water-mill `make verify` passed.

**Problem:** water-mill #27, template #6 and zim cell #28 were squash-merged at 21:43 (heads d60b973/3c21df6/11fe149, i.e. with the second-pass fixes) while I was working; their branches were deleted. My autostash push recreated `bead/gwv` on all three remotes (5b9855a, 7939620, 99bc26e), each one commit on the old head, not on main. The autostash line is therefore NOT on main in those three repos, while the workshop copy (tailrace md5 edb319e6) already has it, so the four copies differ until a follow-up lands. I did not delete the recreated branches or open PRs; orchestrator to decide (cherry-pick the one-line commit onto main in a follow-up PR, then delete the branches).

My findings: already re-recorded with a blank cause and pushed (2e6d5a1). Once 4t3 is on main, annotate them `--cause pending` with `annotate-finding` (f-20261005-df2aac, -c0b715, -de41da, -916c4a).

## Tailrace (2026-10-05)

**LANDED** -- all four PRs squash-merged, each after a fresh green `verify`; fences checked (no settings.json, zimmy diff only `.claude/skills/handoff/SKILL.md`, owner-directed; cells/water-mill diffs only `.claude/agents/*`, `.gitattributes`, `CLAUDE.md`, `scripts/sync-factory.sh`).

- water-mill #27 -> 02aa9bd (head d60b973, verify green 36s)
- watermill-cell-template #6 -> 3dd7964 (head 3c21df6, green 23s)
- zim-dashboard-demo-cell-1b #28 -> ac13c88 (head 11fe149, green 1m34s)
- zimmy-life-tracker #219 -> 134984e (head moved a5148da -> 08ba8da during review; CI run 37377709490 ran on 08ba8da, green 4m16s, which is sluice's third-pass head)

No conflicts. `bd close water-mill-gwv`: closed, no auto-export warning.

**Findings:** none new from landing -- findings for gwv already on main (f-20261005-df2aac, -c0b715, -de41da, -916c4a).

**Still open (orchestrator):** sluice's third pass recreated `bead/gwv` on the three agent-repo remotes (water-mill 5b9855a, template 7939620, zim cell 99bc26e) with the one-line "no `pull --autostash`" tailrace edit that is NOT on main there (zimmy has its skill version, merged). The four tailrace copies now differ until that is cherry-picked in a follow-up PR; then delete those branches. I did not touch them.

## Sluice, follow-up (2026-10-05)

Autostash line landed as follow-up PRs from fresh `gwv-autostash` branches off origin/main (cherry-picks of 5b9855a/7939620/99bc26e): water-mill #29, watermill-cell-template #7, zim-dashboard-demo-cell-1b #29. Each is a one-line tailrace.md change; after them all four tailrace copies match the workshop copy (md5 edb319e6). water-mill `make verify` passed. The recreated `bead/gwv` remote branches in those three repos are deleted (each checked: head was my duplicate commit, no open PR). Not merged; zimmy #219 and water-mill #28 untouched.

## Tailrace follow-up (2026-10-05)

**LANDED** all three autostash follow-ups, one at a time, each verify green on current head, squash-merged with branch deleted. Diffs were only `.claude/agents/tailrace.md`.

- water-mill #29: a22d664ff1f2ba44c33c0153e79d509b27f860de
- watermill-cell-template #7: fa74e4441e4b714f6fb8c784875f04de4bf21406
- zim-dashboard-demo-cell-1b #29: 31c7e8aecfb5077dec26af81548ab54607aaa427

No conflicts. No bd changes. Local checkouts fast-forwarded; tailrace.md md5 verified equal across all three (see report). The Sluice follow-up section above was uncommitted in this file and was committed together with this section.

**Findings:** none -- one-line follow-up, lesson already recorded as f-20261005-d1a6d9
