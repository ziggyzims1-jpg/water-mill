# Coding standards

Only what is already enforced by a tool or written down in this repo. Where a
rule is enforced, the enforcer is named; where it is written, the document is.
Bolter reviews a diff against this file, `docs/adr/` and `CONTEXT.md`.

## Enforced by the gate (`make verify`)

`make verify` is the merge gate and CI runs exactly that command (`.github/workflows/verify.yml`): `guard`, `lint`, `test`, in that order.

- **Lint: `ruff` with `ruff.toml`.** Line length 100, target Python 3.11, rules `E`, `F`, `I` (import sorting), `B`, `UP`, `SIM`. `B904` is ignored on purpose: a bare `except Exception` on a cleanup path is deliberate and each one is commented. `tests/*` ignore `E501`, and so does `scripts/beads_merge.py`: it is a synced copy whose managed header, naming the canon path, runs past 100 columns; its canon master `canon/project/scripts/beads_merge.py` is still linted at full width. Ruff is pinned to a minor in `requirements.txt`.
- **Tests: `pytest`**, declared in `requirements.txt` so a clean checkout can run the suite. Every engine test drives a real git repository, a real gate command and a real queue built in a temp directory; nothing is mocked at the subprocess boundary (`tests/conftest.py`).
- **Guard:** the suite refuses to run without `tests/` and `.venv/bin/python`, or with `WATERMILL_ROOT` set to a real factory root, so it can never touch `runs/`.
- **No type checker.** `make typecheck` states that and exits non-zero so it can never contribute to a green result.
- **Synced files are not edited.** Files with a "managed by water-mill" header are rendered from `canon/`; `watermill validate` fails on drift. Edit `canon/`, then `watermill sync`.

## Written conventions (`CLAUDE.md`)

- **Read `docs/SAFETY.md` before changing** `engine.py`, `preflight.py`, `gitwork.py` or `caps.py`.
- **A step that cannot fail must not be part of a green result:** no `|| true`, no `-` prefixes, no `continue-on-error`; shell recipes run with `pipefail` (`Makefile`).
- **Refusals and failures have different exit codes:** a refusal (a precondition did not hold, nothing modified) exits 3; a failure (work attempted, did not land) exits 1.
- **Unknown keys in a contract or the registry are refused, never ignored.**
- **Nothing from a contract reaches a shell.** Split with `shlex`, run as argv, substitute placeholders after splitting.
- **A check that parses output asks for the whole output** (`tail_lines=0`).
- **Never normalise a path with `lstrip("./")`;** use `removeprefix`.
- **Tests assert on what reached the repository** (commit log, working tree, files on disk), not on what the orchestrator recorded about itself. Stub agents test control flow, not agent behaviour.
- **A cleanup routine is the most dangerous code here.** `gitwork.discard()` requires the caller to assert the run started; `test_a_refused_preflight_touches_nothing` pins it.
- **Caps are checked between tasks, never during one.**
- **A machine records what happened; only a person records why** (`tasklog.py`, `HUMAN_ONLY`).
- **Knowledge has four destinations:** the gate, `fence.paths`, `notes`, then the context graph. A mechanisable rule is never written as a note.
- **A context surface is queried, never loaded.** Findings carry `observed_at`; a changed belief is superseded, never edited. `knowledge/findings.jsonl` and `runs/*.jsonl` are append-only.
- **Third-party work stays off the run loop** (`ship`, `land`, `publish` are their own commands). A check that gates a decision runs before it.
- **A closed task says what closed it** (a comment on success as well as on discard).
- **A lesson is promoted into Water Mill when it has appeared twice, in two repositories.**
- **A change that moves the position updates `docs/STATUS.md` in the same commit,** and `docs/PLAN.md` if it contradicts it.
- **The trial protocol (`docs/TRIAL.md`) changes only by dated amendment,** made before the data it affects is looked at.

## Written conventions (`canon/README.md` and the crew files)

- Edit canon, never a synced copy; opt a project out only with `sync_exempt:` and a reason.
- A target's `.gitignore` must not drop `.claude/skills/`.
- Crew instructions must not tell an agent to run a form the git guardrail blocks (tailrace uses `reset --keep`).
- **Never `git stash`;** snapshot with a patch file.
- Commit style is conventional commits (`feat:`, `fix:`, `docs:`, `chore(beads):`), matching `git log`.
- Tests sit at seams, state their expected values from an independent source, and a PR shows the new tests failing on the base ("Red before green"), unless it is docs-only.
- Beads: `bd` for all task tracking, no markdown TODO lists; commit and push `.beads/issues.jsonl` after any bead write.
- Crew handoffs go in `HANDOFF-mill/<slug>.md`, never in the PR on the laptop; in cloud mode they are committed on the session branch and reach main through the orchestrator's session docs PR (water-mill-hix).
