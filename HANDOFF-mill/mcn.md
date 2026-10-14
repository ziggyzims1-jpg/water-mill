# Handoff — water-mill-mcn

## Millstone (2026-10-14)
- **Where things stand**: branch bead/mcn, PR #60 (https://github.com/ziggyzims1-jpg/water-mill/pull/60). `make verify` green, 852 passed. Not blocked. Siblings NOT synced (orchestrator does; owner merges).
- **What was tried and did not work**: first `make verify` failed lint: the managed header for `canon/project/scripts/beads_merge.py` is 101 cols, over water-mill's ruff 100 (E501). Fixed with a per-file ignore in `ruff.toml`. Second run failed `test_the_real_factory_matches_its_own_canon` and the guardrail sync test: `.claude/watermill-managed.json` lists synced files and had to be regenerated (done via `sync.make_plan` + `apply_plan` on the repo root).
- **Lessons for the graph**: Adding a canon file also requires water-mill's own rendered copy plus a regenerated `.claude/watermill-managed.json`, or the real-factory drift test fails. A synced .py header names the canon path, so a long path breaks a 100-col ruff on the target. canon/project/ reaches git projects and water-mill itself but not the workshop; canon/common reaches the workshop too.
- **Reconciliation**: cheme vs Hillel differ only in `actions/checkout` (cheme SHA-pinned, Hillel `@v4`); `beads_merge.py` identical. Used cheme's. Both get a sync PR anyway because of the header.
- **Seams**: `sync.canon_files`, `beads_merge.py` subprocess CLI, `sync.make_plan` exempt, `sync.gitignored`.
- **Look here first**: `tests/test_beads_sync_canon.py`.
- **Open questions**: none. Decision made: water-mill gets the workflow (its cloud sessions push claude/* too). Hillel's ruff selects only E4/E7/E9, so E501 won't hit; but if a target's ruff selects E501 over scripts/, it needs the same ignore.
- **Follow-ups worth a bead**: a validate-time lint-width warning for synced .py headers, if more long-path canon scripts appear.

## Bolter (2026-10-14)
- **Sources**: CODING_STANDARDS.md, docs/adr/ (esp. 0003 beads-in-git, 0006 canon/sync), CONTEXT.md, CLAUDE.md, canon/README.md, ruff.toml. Missing: CONTRIBUTING.md (not a finding). Recall run; nothing contradicting.
- **Blocking**: none.
- **ruff.toml question**: the per-file `"scripts/beads_merge.py" = ["E501"]` is consistent with the standards. It follows the existing `tests/*` per-file-ignore pattern with a reason comment. The only line over 100 is the generated header (line 2, 104 cols). The canon master `canon/project/scripts/beads_merge.py` has no header and is still linted at full width by `ruff check .` (passes), and validate's drift check keeps the rendered copy equal to canon plus header, so the ignore hides nothing real. Shortening `sync.HEADER_TEXT` (watermill/sync.py:64) would re-render every synced file in every repo and cause churn PRs everywhere. That is out of scope for this bead, and the header shape is part of ADR-0006.
- **Advisory**:
  1. CODING_STANDARDS.md, "Enforced by the gate" lint bullet, still says only "`tests/*` ignore `E501`". That bullet now under-describes ruff.toml. Fix: add "and `scripts/beads_merge.py` (a synced copy whose managed header runs past 100; its canon master is linted at full width)". This is a one-line doc fix sluice can push in-branch.
  2. ruff.toml comment on the new ignore: could add "the canon master is still width-checked" so a later reader does not widen the ignore to all of `scripts/`. Optional.
  3. Possible Data Clumps in canon/project/scripts/beads_merge.py `merge()`: `lines` and `recs` are two dicts keyed by the same id and always assigned together. One `id -> (line, rec)` dict would fix that. Low value: the file is byte-identical to cheme's proven master, and changing it means all targets diverge. Not an auto-mill candidate.
- **Findings:** none -- no blocking finding, so no repeatable trap to record.
- **Run record**: knowledge/agent-runs/bolter-water-mill-mcn-aa8666dd6ef5.jsonl in the wt (copy at scratchpad/bolter-water-mill-mcn-aa8666dd6ef5.jsonl); key session:1f77a9c6-cafb-41c6-b875-6daaa0451fba:agent-aa8666dd6ef59bf21, role=bolter bead=water-mill-mcn pr=60. Sluice commits it.

## Sluice (2026-10-14)
- **Verdict**: approve_after_fixes. Spec met: canon/project carries cheme's byte-identical pair (Hillel differs only in unpinned `actions/checkout@v4`), water-mill gets rendered copies + regenerated `.claude/watermill-managed.json`, tests red first. No out-of-scope edits; `.github/workflows/` touched only as the bead directs.
- **Red before green**: reproduced: new `tests/test_beads_sync_canon.py` on origin/main (9399f0e) gives 5 failed, 1 passed (the gitignore test passes on base by design).
- **Bolter**: no blocking. Advisory 1 + 2 applied in a8756b3 (CODING_STANDARDS.md lint bullet names the `scripts/beads_merge.py` E501 ignore and why; ruff.toml comment says the canon master is still width-checked). Advisory 3 (Data Clumps in `merge()`) left: keeps byte-identity with cheme/Hillel. Bolter run record committed as `knowledge/agent-runs/bolter-water-mill-mcn-aa8666dd6ef5.jsonl`.
- **Workflow safety (water-mill)**: triggers only on `push` to `claude/**` with `.beads/issues.jsonl` in paths, so its own push to main cannot retrigger it (and a GITHUB_TOKEN push triggers no workflows at all, so verify.yml on main will not run on the chore(beads) commit either). Token is the default GITHUB_TOKEN with `contents: write` only. Checks out `main`, runs main's own `scripts/beads_merge.py` (branch code is never executed, the branch file is read via `git show` as data), `git add .beads/issues.jsonl` only. Deleted-branch pushes skipped. water-mill main has no branch protection (private free repo, protection API 403), so the push will be accepted.
- **Fixture**: water-mill's real `.beads/issues.jsonl` (48 beads) vs a shuffled branch variant missing 5 beads, 3 newer-edited, 2 stale, 2 new: 50 out, nothing dropped, no dups, 3 edits won, stale lost, 45 untouched lines byte-identical, second run idempotent. All `updated_at` in water-mill/cheme/Hillel/zimmy are `YYYY-MM-DDTHH:MM:SSZ`, so string comparison is sound.
- **YAML**: rendered workflow parses (header line 1 is a comment); test asserts it. Rendered script keeps the shebang on line 1, header on line 2.
- **Mutations** (separate worktree, file copies, no stash): drop base-only ids, incoming-always-wins, base-always-wins, no malformed refusal, skip new ids: each killed by exactly one test.
- **Verify**: `make verify` 852 passed, before and after a8756b3.
- **Not fixed / concerns**: same-second `updated_at` tie keeps main's record, so a branch edit in the same second as main's is lost (inherited from the proven master; low risk). Deletions never propagate by design. A workflow mutation such as `git add -A` would not be caught by tests (YAML-level only).
- **Auto-mill beads**: none (advisory 3 is not a candidate; no other concrete smell).
- **Findings**: one lesson recorded (lint ignore for a synced copy must be documented in the gate bullet, canon master still checked).
- **Lander**: sync PRs to sibling repos are fenced CI changes: owner merges, not tailrace. A concurrent cloud session (fwm.7) works water-mill; the `.claude/watermill-managed.json` list may conflict if it adds canon too.

## Tailrace (2026-10-14)
**LANDED** — PR #60 squash-merged, merge commit 12f8f5c6d91ad7813ee091fd7ab7a5ffdcda1a79 (sha-guarded on head 19e11e8; verify green). Remote branch bead/mcn deleted. No conflicts.
- `bd close`: "Closed water-mill-mcn ... Merged in PR #60", no auto-export warning. Pulled ff, `bd import` (47 imported, 1 stale skipped), exported; sorted diff showed only the mcn line.
- auto-mill: none.
- Findings: sluice's lesson (f-20261014-5c5af9) already recorded; filed millstone's two lessons (managed.json drift; canon/project vs canon/common reach). Bolter advisory 3 not filed (not a lesson).
- By hand: orchestrator opens the sibling sync PRs (fenced CI; owner merges). I did not run watermill sync.
