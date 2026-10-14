# Handoff — water-mill-fwm.5

## Millstone (2026-10-14)

**Where things stand.** Branch `bead/fwm-5`, PR #54 (https://github.com/ziggyzims1-jpg/water-mill/pull/54). `make verify` green in the worktree (837 passed, incl. validate on the real factory). Not blocked. fwm.9 is PR #53 (open, parallel); not yet on main, so no conflict yet. If both land: rebase and re-render `.claude/watermill-managed.json` (sync.make_plan + apply_plan on the worktree root). Never ran sync against siblings.

**What was tried and did not work.**
- First python edit script for code-review had a stray `if False else None` expression chain and silently did nothing; caught by grepping for "issue" afterwards. Rewrote cleanly.
- Cross-ref test regex first matched `` `/tmp` `` in improve-codebase-architecture as a skill; slash refs now only count when followed by skill/vocabulary/glossary.
- `git check-ignore -q` refuses multiple paths (exit 128); use it without -q and assert exit 1 and empty stdout.
- `make verify` takes ~140 s; it hit the 120 s foreground limit and had to be backgrounded.

**Lessons for the graph.**
- `bd create --parent X` inherits the parent's labels unless `--no-inherit-labels`; a wayfinder ticket without it would carry `wayfinder:map` too.
- Upstream mattpocock-skills reference only two tracker-bound skills (code-review, wayfinder); the other nine needed only an attribution block.
- Wayfinder upstream calls skills `research` and `prototype` that are not among the 11; they were rewritten inline.
- Sync's `git add -A` silently drops gitignored paths, so any target ignoring `.claude/skills/` loses the skills (fwm.9's check-ignore refusal is the guard).

**Seams.** Canon skill files (front matter, attribution, banned tracker phrases, cross-refs); `watermill.sync.canon_files` (header after front matter, shebang kept); `git check-ignore` on water-mill's tree. Tests: `tests/test_skills.py`. Red on clean main: 28 failed, 12 passed.

**Look here first.** `canon/common/.claude/skills/wayfinder/SKILL.md` ("Wayfinding operations" table) and `tests/test_skills.py::test_no_upstream_tracker_wording_remains`.

**Open questions for the human.** (1) I carried upstream `agents/openai.yaml` (Codex UI metadata, 11 files) along per the bead; they are noise for Claude Code, drop them if unwanted. (2) License ships as `.claude/skills/MATTPOCOCK-SKILLS-LICENSE`, a non-skill file inside the skills dir.  (3) Wayfinder's `--claim` / `bd ready --parent -u` commands were checked against `bd --help` only, not run on a live map.

**Follow-ups worth a bead.** docs/AI.md (fwm.7) must mention all 11 skills (validate warns later). Sync does not chmod non-.sh scripts; none exist today.

## Bolter (2026-10-14)

Reviewed PR #54 at `ba32da9` (commits `ce191ce`, `ba32da9`) in a detached worktree. Recall ran (no hit specific to skills). Laptop mode.

**Sources.** Used: `CLAUDE.md` (root conventions, "Where things are"), `canon/README.md`, ruff config, MIT text. Missing (fwm.6 not landed): `CODING_STANDARDS.md`, `docs/adr/`, `CONTEXT.md`; no `CONTRIBUTING.md`.

**Checked and clean.** All 32 synced files under `.claude/skills/` equal their `canon/common/` master apart from the one managed-header line (header after front matter in every SKILL.md/.md, after the shebang in both .sh, first line in yaml; LICENSE untouched). `.claude/watermill-managed.json` lists all 32. All 11 SKILL.md front matters parse with PyYAML, `name` = directory, only `name`/`description`/`disable-model-invocation` keys. MIT: full licence text at `canon/common/.claude/skills/MATTPOCOCK-SKILLS-LICENSE`, synced beside the skills, referenced by path from every SKILL.md attribution block with repo, version 1.2.3 and copyright.

**Blocking.**
1. `docs/STATUS.md` not updated. `CLAUDE.md` "Where things are": "A change that moves the position updates STATUS.md in the same commit". Shipping 11 skills to every synced target moves it; fwm.2 (#50) and fwm.4 (#52) each added a STATUS bullet (STATUS.md:144, :151). Conforming change: one bullet "Skills in canon (2026-10-14, water-mill-fwm.5)" saying what ships, that wayfinder/wizard/improve-codebase-architecture/to-questionnaire are available-not-run, and the .gitignore caveat.

**Advisory.**
- Possible Primitive Obsession / hand-rolled parser: `tests/test_skills.py::front_matter` splits lines on ":" and strips quotes, so a description with an unquoted `: ` (invalid YAML, skill fails to load) passes. Fix: `yaml.safe_load` (PyYAML is already a dependency) and assert the keys. [auto-mill candidate]
- Possible leaky header: `wizard/SKILL.md` line 38 says "Copy `template.sh` to the target path"; the synced copy carries `# managed by water-mill (...template.sh)`, so every generated wizard falsely claims to be managed. Fix: one sentence in canon `wizard/SKILL.md` to delete that line after copying (same for `diagnosing-bugs/scripts/hitl-loop.template.sh` if copied). [auto-mill candidate]
- Weak assertion: `test_every_skill_carries_the_attribution_block` checks "MIT" and "Matt Pocock" anywhere in the file; match the full attribution sentence instead.
- Duplicated list: the 11 names live in `EXPECTED`, `canon/README.md` and the bead; fine for now, worth one source if docs/AI.md (fwm.7) adds a fourth.
- `CLAUDE.md` Layout row for `canon/` still says "today the four crew agents" (stale since fwm.4); descriptive only.
- `test_water_mills_own_copies_are_committed_not_ignored` checks SKILL.md + LICENSE only, not aux files (template.sh, agents/*.yaml).

**Findings:** f-20261014-8e0597 (canon change needs a STATUS.md entry; cause incomplete-files).

**Run record** (uncommitted; sluice commits it): `knowledge/agent-runs/bolter-water-mill-fwm.5-a949e54673b0.jsonl`, copy at `<scratchpad>/bolter-water-mill-fwm.5-a949e54673b0.jsonl` (`/private/tmp/claude-501/-Users-andrewzimmerman-Documents-code/1f77a9c6-cafb-41c6-b875-6daaa0451fba/scratchpad/`). Line: key `session:1f77a9c6-cafb-41c6-b875-6daaa0451fba:agent-a949e54673b010834`, role=bolter bead=water-mill-fwm.5 pr=54 tool_calls=11 duration_s=66.168 transcript_located=true (full JSON in the scratchpad copy). Note `agent_type` recorded as general-purpose (spawned as an ad-hoc agent with bolter.md as role).

**What failed.** Nothing failed. `knowledge/findings.jsonl` was written in the main checkout by `remember`; tailrace commits it.

## Sluice (2026-10-14)

**Verdict: approve_after_fixes.** Head now `1f67f11` (fixes `967d63c`, records `1f67f11`). Laptop mode. Recall ran; nothing specific to skills beyond the make_plan/apply_plan render lesson (used).

**Spec check.** All 11 skills present; every supporting file is byte-identical to upstream 1.2.3 (`diff -rq` against the plugin cache). SKILL.md diffs: nine are the attribution block only; code-review and wayfinder carry the bd rewrite, read hunk by hunk, no tracker wording left (grep for issue tracker / docs/agents / setup-matt / triage / to-issues / /research / /prototype is clean). code-review also dropped upstream's `.scratch/` spec location (that belongs to the local-markdown tracker), which is fine. `agents/openai.yaml` kept, left for the owner as asked. No fence or out-of-scope file touched.

**Wayfinder commands run live** on a scratch `bd init` repo (bd 1.2.2): create epic with `wayfinder:map`, child tickets with `--parent --no-inherit-labels -l wayfinder:<type>`, `bd dep add`, `bd ready --parent <map> -u`, `bd list --parent --status open,in_progress` and `--status closed`, `bd update --claim` (claimed ticket leaves the frontier), `bd comments add` + `bd close --reason` (blocked ticket joins the frontier), `bd update <map> -d`. All work as the table says. Confirmed `--no-inherit-labels` is needed: a child created without it carried `wayfinder:map`.

**Red before green.** Reproduced: new `tests/test_skills.py` on clean `origin/main` gives 28 failed, 12 passed, as the PR body says.

**Bolter blocking (STATUS.md): fixed** in `967d63c`, a "Skills in canon (2026-10-14, water-mill-fwm.5)" bullet with what ships, the four available-not-run skills and the gitignore caveat.

**Bolter advisories.** Fixed in `967d63c`: front matter parsed with `yaml.safe_load` and keys checked (a): mutation with an unquoted `: ` in grilling's description was green before, red after; wizard and diagnosing-bugs now tell the agent to delete the managed header from a copied template (b), re-rendered into `.claude/skills/` via make_plan/apply_plan; attribution test matches the full sentence (mutation red); the stale CLAUDE.md Layout row for `canon/`. Not fixed: the duplicated skill-name list (no harm until a fourth copy appears).

**Found myself.** `test_water_mills_own_copies_are_committed_not_ignored` could never fail: `git check-ignore` skips tracked files unless given `--no-index`. Mutation (template.sh added to .gitignore) stayed green; with `--no-index` and every synced skill file in the list it fails. fwm.9's sync guard (PR #53) checks untracked files at first sync, where no `--no-index` is right; not a bug there.

**Gate.** `make verify` 837 passed before and after the fixes.

**Auto-mill beads:** none, I fixed both candidates instead.
**Findings:** f-20261014-78ab40 (check-ignore needs --no-index for tracked files), f-20261014-3cd250 (test front matter with yaml.safe_load).
**Run records** committed in `1f67f11`: `knowledge/agent-runs/bolter-water-mill-fwm.5-a949e54673b0.jsonl` (copied as is) and `sluice-water-mill-fwm.5-a3501fea9c06.jsonl` (transcript located).

**What failed / for the lander.** Nothing broke. PR #53 does not touch CLAUDE.md, STATUS.md or skills; the only overlap is `.claude/watermill-managed.json`. Whichever lands second: rebase, re-render with make_plan + apply_plan, run `make verify`. My fixes did not change the manifest. Not run: sync against siblings; Claude Code actually loading the skills.

**Update after PR #53 landed.** Merged `origin/main` into `bead/fwm-5` (no force-push), head `87db190`. No conflicts. Re-render with make_plan + apply_plan was a no-op, so the manifest already matched canon. `watermill validate`: "water-mill: synced files match canon"; the siblings still differ, waiting on the owner's `watermill sync`. `make verify` 843 passed. Pushed.

## Tailrace (2026-10-14)

**LANDED** MERGED PR #54, squash commit 9d2d7e333136b04f6483fa4cf1279239730d76d0 (sha-guarded on head 87db190; CI `verify` green; remote branch bead/fwm-5 deleted). No conflict.

**bd close:** `✓ Closed water-mill-fwm.5 ... Merged in PR #54`, no auto-export warning. Pulled ff-only, `bd import` (44 imported, 2 stale skipped), `bd export`; sorted diff showed exactly water-mill-fwm.5 (closed) and water-mill-faw (in_progress claim, expected), nothing else.

**auto-mill:** none (sluice fixed both candidates itself).

**Findings:** filed the two millstone lessons not already recorded (bd --parent label inheritance; upstream wayfinder referencing skills outside the set); the other two millstone lessons and sluice/bolter's were already in the graph (f-20261014-01f238, -78ab40, -3cd250, -8e0597).

**For the human:** siblings still differ from canon until the owner runs `watermill sync`. Not run: Claude Code actually loading the skills.
