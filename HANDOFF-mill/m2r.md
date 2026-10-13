# Handoff — water-mill-m2r

## Millstone (2026-10-13)

- **Where things stand:** branch `bead/m2r`, PR #36 (https://github.com/ziggyzims1-jpg/water-mill/pull/36). `make verify` green (514 passed). Not blocked. Bead not closed. Files: `projects.yaml`, new `projects/cheme-solver.yaml`, `docs/STATUS.md` paragraph.
- **Counts (scratch roots with symlinked siblings; real runs/ untouched):** cheme-solver 18 handoffs read, 18 landed; records 344 -> 362 would append. Crew-linked transcript records (`detail.crew_key`) 67 -> 120 (+53); cheme-solver has 57 transcript runs. The bead's "~78" does not match what I measured (67 before); I counted `crew_key` on source=transcript.
- **review --lag for cheme-solver:** lists nothing. All 18 handoffs landed in Sept, before `review.LAG_SINCE` (2026-10-05). Overall lag list is 53 beads, none cheme-solver.
- **What was tried / did not work:** plain `--dry-run` sweep shows no transcript link count at all, so I ran a real sweep against scratch roots to count. `python -m watermill` does not work; use `bin/watermill`.
- **Fence findings:** no Gurobi/licence file exists anywhere in cheme-solver (grep). Secret-shaped inputs are only `CHEME_INVITE_CODE` etc. via `backend/cheme/config.py`; real `.env` is host-only. Deploy files target a Pi (`/home/pi`), Azure only in `docs/DEPLOY-AZURE.md`, not the bead's "Azure VM systemd unit". No `.github/workflows/`, so `gh pr checks` has nothing to watch (noted in contract `notes`).
- **Lessons for the graph:** a cell without CI makes `review.verify` (`gh pr checks --watch`) report "no checks"; cheme's landers verified locally instead.
- **Look here first:** `projects/cheme-solver.yaml` fence block.
- **Open questions:** fence includes `backend/cheme/auth.py`, `routes/auth.py`, `db.py`, `migrations/` beyond the bead's list (security/schema); owner may loosen. `.claude/`, `.codex/`, `.agents/` fenced too.
- **Follow-ups:** `--dry-run` sweep should print link counts; cheme-solver has no CI.

## Sluice (2026-10-13)

- **Verdict: approve_after_fixes.** PR #36, fix commit `a10ab32` pushed to `bead/m2r`. Water-mill `make verify` green in my worktree (514 passed) and CI green on `a10ab32`. Bead not closed, PR not merged.
- **CI-less verify (the main defect, fixed).** The copied `review.verify` (`gh pr checks {branch} --watch --fail-fast`) can never pass in cheme-solver: measured on cheme PR #25, both plain and `--watch` exit 1 within a second with "no checks reported on the 'bead/kym' branch". `land._verify_when_the_forge_is_ready` retries that for `SETTLE_SECONDS` (90 s), then reports verify FAILED and never merges. So it fails closed, not open, but only after `create` has already opened a PR. Fix: `projects/cheme-solver.yaml` now declares no `review` block (the original is kept commented, to restore with a CI workflow), so `land` refuses up front with exit 3. I confirmed `land.land()` returns `[REFUSE] ... no review.create`, and `validate` prints `review: none -- watermill land will refuse`. The contract note and the `docs/STATUS.md` paragraph say landing is supervised, on a local `make verify`.
- **The worse case is in the crew, not the code.** cheme-solver's own tailrace notes (e.g. `cheme-solver/brain/handoffs/mill/kym.md`) record 9 "no checks reported" retries and then a merge on a local `make verify`. That goes against `.claude/agents/tailrace.md` step 1. It is not fixed here. Follow-up bead: give tailrace an explicit CI-less path (for example, read the contract and, when there is no `review` block, run `make verify` in a worktree and say so) instead of improvising.
- **Fence.** All 21 original entries checked against cheme-solver. Every one exists except `.github/workflows/`, `.env` and `.beads-credential-key`, which are deliberately pre-emptive. `var/` exists, untracked. The extra entries beyond the bead's list (auth.py, routes/auth.py, config.py, db.py, migrations/, `.claude/.codex/.agents`) are justified: each changed 1-3 times in 86 commits, so fencing them does not block feature work, and a bead can direct an edit. Fixes: the comment said the real `.env` "is gitignored", which is **false**. cheme-solver `.gitignore` has no `.env` entry, while DEPLOY.md puts `.env` at the checkout root. I added `.env.*` (`.env.local` was unprotected). Left open on purpose: `backend/cheme/app.py`, which holds `_check_session_token`, the sign-in enforcement, because every router is registered there. Noted in the comment.
- **review --lag discrepancy, explained (main checkout is right).** Millstone's scratch roots (`scratchpad/root/water-mill` etc.) had no `knowledge/` directory, so `knowledge.read` returned no findings and `review.uncovered` counted every landed bead since `LAG_SINCE` (2026-10-05). I reproduced it on a fresh root with cheme-solver registered: 53 without `findings.jsonl`, 0 with it copied in. The main checkout and my PR worktree both say "no landed bead is waiting on a finding". cheme-solver contributes nothing either way because its 18 landings are dated 2026-09-29 (`--lag-since 2026-09-01` lists them). Follow-up bead: `review --lag` should refuse or warn when `knowledge/findings.jsonl` is missing instead of reporting every bead as lagging.
- **cheme gate.** I ran `make verify VENV=<cheme>/.venv` in a `git archive HEAD` copy of cheme-solver, with node_modules symlinked and nothing installed or written in cheme-solver: content, lint, pytest, typecheck, vitest and build all green.
- **Process slip.** My first push ran `make verify | tail` without `.venv`. The guard failed but the pipe hid it, so `a10ab32` was pushed before its gate. I re-ran it straight after: green, and CI green too.
- **Not fixed / follow-ups:** add `.env` to cheme-solver `.gitignore` (READ ONLY here); add CI to cheme-solver, then restore the review block; there is an untracked Fogler solutions-manual PDF in the cheme-solver root that a careless `git add -A` would commit; the vendored `projects/zim-dashboard-demo-cell-1b.yaml` is dead because that cell now has its own watermill.yaml.
- **Findings:** 3 recorded (CI-less review block; lag on a root without findings.jsonl; cheme `.env` not gitignored), all `--task water-mill-m2r`.
- **Lander:** `docs/STATUS.md` hunk sits above the hillel paragraph. A concurrent STATUS edit may conflict there.

## Tailrace (2026-10-13)

**LANDED** PR #36 MERGED, squash commit `1858964b0bc2f970fdf4eb7a1ad52df1fa0f9d6a`.

- Verify: `gh pr checks 36` green (verify pass 37s). Merge ran as its own command, not denied. No conflict (docs/STATUS.md merged cleanly).
- Failure: `gh pr merge` hit "connection reset by peer" on the GraphQL call after the squash had landed, so `--delete-branch` did not happen; I confirmed state MERGED via `gh pr view`, then deleted `bead/m2r` with `git push origin --delete`.
- `bd close water-mill-m2r --reason "Merged in PR #36"`: "Closed water-mill-m2r"; no auto-export warning. `bd export -o .beads/issues.jsonl` then showed it modified; committed as chore(beads).
- `bin/watermill validate`: "cheme-solver: ok" (gate make verify, queue beads); note: no backup_check.
- Findings: sluice's 3 findings (task water-mill-m2r) in knowledge/findings.jsonl, committed with the landing.
- By hand: this handoff note is untracked and not committed by me (brain/handoff rule); orchestrator commits it. HANDOFF-mill/ng1.md untouched.
