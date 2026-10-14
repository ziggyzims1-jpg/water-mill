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

Why a folder of its own rather than `.claude/agents` as the canon: the canon must also hold skills, hook
scripts, the managed settings entries and the workshop's files, and water-mill's
own `.claude/agents` is then simply one more synced target.

Opting a project out of a path: `sync_exempt:` in `projects.yaml`, a map of
glob to reason (reported by validate, never failing it). Sync never merges its
PRs; CI and the landing step do.

The workshop `CLAUDE.md` has no canon text yet; a later bead adds it under
`workshop/`.

## The git guardrail

`common/.claude/hooks/block-dangerous-git.py` plus the `PreToolUse`/`Bash` entry
in `settings.managed.json` deny `git stash` (every form), `reset --hard`,
`clean -f`, `branch -D`, `checkout .`, `restore .` and forced pushes; plain
`push`, `commit`, `worktree`, `checkout <branch>` stay allowed. It is Python
(stdlib only) so it behaves the same on macOS bash 3.2 and the Linux cloud
image. Adapted from mattpocock-skills 1.2.3 (MIT). Tests: `tests/test_git_guardrail.py`.
