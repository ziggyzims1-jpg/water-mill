# canon

The one master copy of every file the mill's projects share. Edit here, then
`watermill sync <project>`; never edit a synced copy (each carries a "managed by
water-mill" header, and `watermill validate` fails on drift).

| Path | Goes to |
|---|---|
| `common/<path>` | `<path>` in every target: each registered project, water-mill itself and the workshop |
| `project/<path>` | `<path>` in git projects only |
| `workshop/<path>` | `<path>` in the workshop folder only (`~/Documents/code`, override `WATERMILL_WORKSHOP`) |
| `settings.managed.json` | merged into each target's `.claude/settings.json`; only `hooks` and `permissions`, and only these entries (recorded in `.claude/watermill-managed.json` so a dropped entry is removed and the repo's own are never touched) |

`project/.github/workflows/beads-sync.yml` + `project/scripts/beads_merge.py` land
the `.beads/issues.jsonl` commits a cloud session pushes on its `claude/*` branch
onto main (union by issue id, newer `updated_at` wins, never deletes; a main with no
`issues.jsonl` yet, the first sync after `bd init` on the branch, gets the branch's file). cheme-solver's
copy is the master: Hillel's differed only in an unpinned `actions/checkout@v4`.
Water-mill gets it too: its own cloud sessions push `claude/*` branches the same way.

Why a folder of its own rather than `.claude/agents` as the canon: the canon must also hold skills, hook
scripts, the managed settings entries and the workshop's files, and water-mill's
own `.claude/agents` is then simply one more synced target.

Opting a project out of a path: `sync_exempt:` in `projects.yaml`, a map of
glob to reason (reported by validate, never failing it). Sync never merges its
PRs; CI and the landing step do.

The workshop `CLAUDE.md` master is `workshop/CLAUDE.md` (the workshop's own
rules plus the auto-mill orchestrator rule). The workshop folder is only
reachable from the laptop: the owner runs `watermill sync workshop` there.

## The git guardrail

`common/.claude/hooks/block-dangerous-git.py` plus the `PreToolUse`/`Bash` entry
in `settings.managed.json` deny `git stash` (every form), `reset --hard`,
`clean -f`, `branch -D`, `checkout .`, `restore .` and forced pushes; plain
`push`, `commit`, `worktree`, `checkout <branch>` stay allowed. So do the pinned lease
`push --force-with-lease=<ref>:<sha>` (the cloud-mill session-branch reset) and
anything inside a here-document body (commit messages and handoffs name the
banned commands). Crew instructions must not tell an agent to run a blocked
form: tailrace resets a landing worktree with `reset --keep`, not `--hard`. It is Python
(stdlib only) so it behaves the same on macOS bash 3.2 and the Linux cloud
image. Adapted from mattpocock-skills 1.2.3 (MIT). Tests: `tests/test_git_guardrail.py`.

## The skills

`common/.claude/skills/` holds 11 skills adapted for beads from mattpocock-skills
1.2.3 (MIT, Copyright (c) 2026 Matt Pocock): domain-modeling, grill-with-docs,
grilling, diagnosing-bugs, code-review, tdd, codebase-design, wayfinder, wizard,
improve-codebase-architecture, to-questionnaire. Each `SKILL.md` carries an
attribution block (upstream repo, version, license) and points at the one shared
`MATTPOCOCK-SKILLS-LICENSE`, which sync delivers beside them. Where upstream
talked to an issue tracker, the skill now says `bd` (wayfinder: the map is an epic
labelled `wayfinder:map`, tickets are child beads, blocking is `bd dep add`, the
frontier is `bd ready --parent <map> -u`). Upstream's per-skill `agents/openai.yaml`
(Codex UI metadata) is carried along untouched. wayfinder, wizard,
improve-codebase-architecture and to-questionnaire are available, not run by the
mill. A target's `.gitignore` must not drop `.claude/skills/`, or the files are
never committed. Tests: `tests/test_skills.py`.
