# Handoff — water-mill-fwm.7

## Millstone (2026-10-14)

**Where things stand.** Session branch `claude/fwm-7`, PR #58 (https://github.com/ziggyzims1-jpg/water-mill/pull/58). `docs/AI.md` written; linked from README.md, CLAUDE.md (Layout row) and canon/workshop/CLAUDE.md; STATUS.md updated; `watermill validate` warns via `sync.unmentioned_in_ai_doc` (exit code unchanged). `tests/test_sync.py` 50 passed. Full `make verify`: guard and ruff pass, 851 passed, 2 failed (`tests/test_cloud_setup.py` two tests, "tracked files changed" under `.beads/`); the same 2 fail on a clean `origin/main` worktree in this container, so environmental. Not blocked.

**What was tried and did not work.**
- The bead says `watermill register`; no such subcommand exists (`add` is it, and it runs sync last). AI.md says so.
- First red-before-green snapshot used `git diff` of everything then reverted only code files, so re-applying the whole patch failed; fixed with `git apply --include=` for the two code files.
- `sync-factory.sh` is not wired in `.claude/settings.json` (grep: only CLAUDE.md and the script itself), so AI.md says that rather than claiming it is.

**Lessons for the graph.**
- `watermill validate`'s canon-agent/skill names come from `canon/common/.claude/agents/*.md` and the directories under `canon/common/.claude/skills/`; a new agent or skill must be named in docs/AI.md or validate warns.
- `tests/test_cloud_setup.py` fails two tests in the cloud container on clean main, so `make verify` is not green there regardless of the change.

**Seams.** `watermill.sync.unmentioned_in_ai_doc` (public function, definition of "mentioned"); `watermill validate` CLI (warning printed, exit 0); the real-factory test pinning docs/AI.md completeness.

**Look here first.** `docs/AI.md` section 10 (trial) against `docs/TRIAL.md` and `watermill/trial.py` (`_refuse_trial_session`, `brief`, `due_for_scoring`); and `sync.unmentioned_in_ai_doc`.

**Open questions for the human.** Owner memory contents and where sync-factory.sh / the beads-sync workflow are wired are not in the repo; AI.md section 12 says so. Owner must run `watermill sync workshop` on the laptop (workshop CLAUDE.md changed).

**Follow-ups worth a bead.** The two `test_cloud_setup.py` failures in the cloud container; the bead text says `register` but the command is `add`.

Run record: knowledge/agent-runs/millstone-water-mill-fwm.7-a1d72bf2352a.jsonl (pr 58).
