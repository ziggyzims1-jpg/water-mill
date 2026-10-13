# Handoff — water-mill-hix

## Millstone (2026-10-13)

**Where things stand.** Four PRs open, none merged, no denials: water-mill #42, watermill-cell-template #10, zim-dashboard-demo-cell-1b #32, cheme-solver #33 (same crew files, plus the runbook). water-mill `make verify`: 553 passed. Crew md5s, identical in all four: millstone a967aab2ace67c70a828dd393aa3e809, sluice f67487cd7ec888d2fa1bdb9ed7cd57cd, tailrace f2878f9a8c50375980e43fe317698a71. `watermill validate --crew-path <worktree>` says "crew files identical to water-mill's" for all three branch worktrees (plain `validate` still sees the old sibling checkouts until the PRs land; land the four together). Not Hillel (9tx). The workshop copy ~/Documents/code/.claude/agents still needs a hand sync.

**What changed.** Tailrace cloud mode: no second PR. After the bead PR merges it makes two commits on `$SB` and one push: `chore(beads): close` (issues.jsonl alone) and `docs:` (handoff, agent-run record, knowledge). beads-sync carries the first to main; the second waits for the orchestrator. Millstone/sluice/tailrace shared bullets: a later bead starts from `origin/$SB`; `$SB` is never deleted and is reset only after the session docs PR merges; issues.jsonl never rides a PR. Runbook (cheme-solver `brain/runbooks/cloud-mill.md`): new "Session close" section = session sync + ONE docs-only PR + sha-guarded merge + `--force-with-lease` reset. Laptop text untouched.

**Walkthrough (two-bead session), real git, scripted in scratchpad `wk/sim.sh` (bare origin, squash-merge and a beads-sync that rewrites issues.jsonl in reverse line order, as the real one does).** bead 1: millstone+sluice commits on `$SB`, PR squash-merged, tailrace merges main, closes a1, two commits, push, beads-sync. Orchestrator sync. bead 2 starts from `origin/$SB`, same again. Session end: sync, then PR diff vs main = `M brain/handoffs/mill/b2.md`, `A knowledge/agent-runs/tail2.jsonl`, nothing under `.beads/` (grep count 0). `git merge-tree --write-tree origin/main origin/claude/sess1` exit 0, tree b08a44cc4769, "NO CONFLICT". main's issues.jsonl ends with a1 and b2 both closed (beads-sync only).

**Tried and did not work.**
- Plain `git merge origin/main` into `$SB` (the mb6 recipe): CONFLICT in `.beads/issues.jsonl` the moment beads-sync has reordered it, so it fails from bead 2 onward, in tailrace step 2 and in the orchestrator sync. Fixed by `merge --no-commit --no-ff` then `checkout origin/main -- .beads/issues.jsonl` (main's copy; the next export rewrites from the bead db anyway). That the sim hit this is why the recipe is in both the tailrace file and the runbook.
- The sim's first `commit` died on "nothing to commit" when the merge was already up to date; the recipe now commits only if MERGE_HEAD exists.
- A first assertion in my edit script tripped on my own wording ("bookkeeping PR" in "No bead opens a bookkeeping PR"); harmless.

**Lessons for the graph.**
- In a cloud session, merging origin/main into the session branch conflicts on `.beads/issues.jsonl` alone after any beads-sync run; resolve by taking main's copy of that one file, never by hand-merging lines.
- A bead PR from the single session branch carries earlier beads' accumulated handoffs and run records; that is expected, not a fence violation.
- `watermill validate --crew-path` takes a repo directory, not `.claude/agents`; the latter reports every file "(missing)".

**Look here first.** "Session close" in cheme-solver `brain/runbooks/cloud-mill.md` and tailrace.md "After the merge" step 2/4.

**Open questions for the human.** (1) Because there is one session branch, bead 2's PR also carries bead 1's tailrace docs, so the "one docs-only PR" really holds only what remains after the last bead; acceptable? Alternative: second pushable branch, not available in cloud. (2) The session docs PR depends on beads-sync having run; if it is slow the orchestrator waits (documented).

**Follow-ups worth a bead.** Untested in a real cloud container (the sim covers git semantics only, not the proxy). `validate` should accept `.claude/agents` paths or say "no crew files at path". Template still not registered for plain `validate`. Hillel via 9tx.

## Sluice (2026-10-13)

**Verdicts:** water-mill #42 approve (only my run record added, 4b8a257); watermill-cell-template #10 approve; zim-dashboard-demo-cell-1b #32 approve; cheme-solver #33 **approve_after_fixes** (runbook fix 3ce039e). Bead-level: approve_after_fixes. No denials. Land all four together.

**Verified independently.** Crew md5s identical on all four `origin/bead/hix` heads (a967aab2 / f67487cd / f2878f9a); main's copies were identical across repos too. Word-diff vs main: every hunk sits inside the cloud-mode section; laptop text unchanged. `make verify`: water-mill 553 passed; cheme-solver exit 0 (429 pytest, 50 vitest, content checks) after my fix. `validate --crew-path <wt>` = "identical" for all four worktrees (plain validate still DIFFERs on siblings until they land, as expected).

**Own simulation** (scratchpad `rsim/sim.sh`, real `scripts/beads_merge.py`, container bead db exported in sorted id order, beads-sync modelled as the real workflow: reads the branch *tip* at run time, appends/replaces in main's order). 2 and 3 beads, races none / mid / last bead deferred:
- Crew recipe (tailrace step 2 checkout + step 3 `bd export`): safe for every bead except the last, because the next tailrace's export restores an earlier close from the db.
- **Runbook session sync as written (`checkout origin/main -- .beads/issues.jsonl`) dropped the LAST bead's close** (N=2 and N=3, race=last: main ended with that bead `open`). The docs PR check then passed, because `$SB`'s file equals main's, so the loss was silent. The "wait until beads-sync has run" guard was human-judged and covered closes only, not created beads.
- Fixed (3ce039e): the sync now writes main's copy and runs `beads_merge.py` with `$SB`'s copy on top (bytes identical to main when nothing is pending), then checks `git diff --quiet origin/main origin/$SB -- .beads/`. NOT DONE means wait for beads-sync, then sync again. A single union sync without the re-sync made bead 3's PR show `.beads/` (the merge base was stale); the re-sync fixes that. With the fix, all 6 cases ended with every bead closed on main, no PR carrying `.beads/`, and merge-tree clean.
- Also in 3ce039e: a claude/ guard on Session close, `SHA` defined (and checked against the `origin/$SB` you looked at) for the docs PR, and the reset lease pinned to the merged head, run only after `"merged": true`.

**Not fixed:** tailrace step 2 says issues.jsonl "always conflicts here". In my sim it never did there (only the orchestrator sync conflicts), but the step is harmless and step 3's export makes it correct. I left it alone rather than churn four md5s. The runbook recipe was checked by simulation, not by a byte-for-byte run of its bash block. Still untested in a real container (proxy, real beads-sync timing).

**Follow-ups:** the workshop copy ~/Documents/code/.claude/agents needs a hand sync; Hillel via 9tx; validate should take `.claude/agents` paths.

**Findings:** f-20261013-22633a (--cause pending, --task water-mill-hix).

## Tailrace (2026-10-13)

**LANDED** -- all four squash-merged, in order, each verify green on the verified head and crew md5s (a967aab2 / f67487cd / f2878f9a) confirmed on every PR head first:
- water-mill #42 -> 121528ff509450312e9d197dfe662ac57c40dea6
- watermill-cell-template #10 -> 973470e22596ea240901b3d4a19babfb3035dd52
- zim-dashboard-demo-cell-1b #32 -> a185a2a15d58341f5a4eaf5688e0977f1b1bea2e
- cheme-solver #33 -> ff749c9b4484d3c2a8d9552ba68e88d8dc9ee303 (its dirty .beads/interactions.jsonl untouched)

**What failed.** #42's first verify run FAILED on tests/test_knowledge.py::test_concurrent_writers_do_not_lose_or_corrupt_a_line (199 unique ids of 200: a finding-id collision, flake). I reran the failed job once (`gh run rerun --failed`), same head 4b8a257, and it went green (553 passed) before merging. No denials, no conflicts.

**Post-merge.** `git fetch` + `merge --ff-only origin/main` on the three siblings and water-mill (no pull needed, no stash). `bin/watermill validate` rc 0: zim-dashboard-demo-cell-1b and cheme-solver "crew files identical to water-mill's"; zimmy-life-tracker (workshop copy) and hillel-programming (9tx) are the pre-existing exempt DIFFERs. watermill-cell-template is not registered in plain validate (known). `bd close water-mill-hix`: closed, no auto-export warning.

**Findings:** f-20261013-22633a (sluice) plus the CI flake lesson (tests/test_knowledge.py id space), both --task water-mill-hix. Millstone's three lessons: the cloud-mode merge/.beads conflict one is covered by f-20261013-22633a's topic; the other two were filed as separate lessons.

**Hand-do.** Sync the workshop copy ~/Documents/code/.claude/agents by hand.
