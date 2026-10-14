"""The crew-vs-default-Claude trial (water-mill-166): ledger, assignment, outcomes.

The protocol and the analysis plan are `docs/TRIAL.md`, written before data.
This module is its machinery and holds three promises:

* **Assignment cannot be steered.** Arms come from balanced blocks of four per
  repo (two A, two B, shuffled by a seeded RNG), the seed is logged in the
  ledger, beads inside one call are enrolled in sorted id order so the order the
  owner typed them in changes nothing, and a bead that is in the ledger is never
  assigned again.
* **The record is append-only.** `knowledge/trial/ledger.jsonl`, `results.jsonl`
  are only ever opened for append; a correction is a later line, and the latest
  line per bead (per `type`) wins when read.
* **Scoring is blind.** `scorepack` builds the scorer's prompt from the bead's
  own text and the rubric. It never reads an arm, a label or a finding tag into
  it (`tests/test_trial.py` pins that), and it lists beads in a hash order so the
  order leaks nothing either.

Ledger lines (`type`): `seed` (the master seed, once), `enroll` (bead, repo, arm,
seed, block, pos, enrolled_at), `start` (the session that works the bead:
session_id, surface, started_at), `pause` / `resume` (the harm stop of
docs/TRIAL.md section 6: reason, at; a resume lists the pause stamps it
clears in `resumes`, so a union merge cannot reorder a pause away; `enroll`
and `start` refuse while any pause is uncleared). Results lines: `collect` (outcomes read after
the session) and `score` (blind escape scoring).

Privacy: cost-state is read for numbers only; nothing a person or tool wrote
reaches a line (same rule as `sessionlog`).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import landed, pricing, recorded, sessionlog, stats
from .errors import WatermillError
from .registry import Registry

TRIAL_DIR = "knowledge/trial"
LEDGER = "ledger.jsonl"
RESULTS = "results.jsonl"

ARMS = ("A", "B")
BLOCK = 4
LABEL_PREFIX = "trial:"
HAND_ONLY_LABEL = "hand-only"
FENCE_DIRECTED_LABEL = "fence-directed"
ESCAPE_WINDOW_DAYS = 14
INTERIM_N = 30
FINAL_N = 60
MIN_N = 8  # fewest usable values per arm before a p-value is ever printed
SEVERITIES = ("blocker", "bug", "test-gap", "quality")
PRIMARY_SEVERITIES = ("blocker", "bug")  # "bug-or-worse"
GREEN = ("success", "neutral", "skipped")
COST_BASES = ("cost-state", "recorded-snapshot", "manual")
SETTLE_SECONDS = 300
FENCE_CLEAR_LABEL = "fence-clear"  # owner: names a fenced path but does not edit one
SENSITIVITY_LAND_DAYS = 30  # docs/TRIAL.md section 4: not landed by then = failure

# -- the owner's design decisions (2026-10-13), one switch each ----------------
#: Arm B merges its own PR (sha-guarded, after every check is green) and closes
#: the bead, so both arms end at "landed". False = arm B stops at an open PR.
ARM_B_SELF_MERGES = True
#: Cost bases that enter the cost comparison. "cost-state" is the laptop
#: session's own final total; a cloud bead has only a snapshot (or an
#: owner-supplied figure, "manual"), so cost is compared on laptop beads only.
COMPARED_COST_BASES = ("cost-state",)

#: What the blind scorer must never read: handoffs and run records name the crew
#: roles, findings carry trial:A/B tags, `.beads/` holds the trial:A/B labels.
BLIND_EXCLUDE = ("brain", "knowledge", ".beads", "HANDOFF*")
BLIND_PATHSPEC = "-- . " + " ".join(f"':(exclude){p}'" for p in BLIND_EXCLUDE)


class TrialError(WatermillError):
    """A trial command refused; nothing was written."""

    exit_code = 3


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        got = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=UTC)


# -- the files -------------------------------------------------------------


def _read(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append(path: Path, rows: list[dict]) -> None:
    """The only write this module makes to the trial files: append, nothing else."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def ledger_path(root: Path) -> Path:
    return Path(root) / TRIAL_DIR / LEDGER


def results_path(root: Path) -> Path:
    return Path(root) / TRIAL_DIR / RESULTS


def read_ledger(root: Path) -> list[dict]:
    return _read(ledger_path(root))


def read_results(root: Path) -> list[dict]:
    return _read(results_path(root))


def enrolled(ledger: list[dict]) -> dict[str, dict]:
    """bead -> its enroll line (the first; a bead is enrolled once)."""
    out: dict[str, dict] = {}
    for row in ledger:
        if row.get("type") == "enroll" and row.get("bead"):
            out.setdefault(row["bead"], row)
    return out


def started(ledger: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in ledger:
        if row.get("type") == "start" and row.get("bead"):
            out.setdefault(row["bead"], row)
    return out


def master_seed(ledger: list[dict]) -> int | None:
    for row in ledger:
        if row.get("type") == "seed":
            return int(row["seed"])
    return None


def _open_pauses(ledger: list[dict]) -> list[dict]:
    """Pause lines no resume has cleared, in ledger order.

    A `resume` names the pauses it clears (`resumes`: their `at` stamps), so the
    answer does not depend on line order: the ledger is `merge=union`, and a
    resume written on a stale checkout must not clear a pause it never saw. A
    resume without `resumes` clears every pause above it.
    """
    pauses: list[dict] = []
    cleared: set = set()
    for row in ledger:
        if row.get("type") == "pause":
            pauses.append(row)
        elif row.get("type") == "resume":
            cleared.update(row["resumes"] if isinstance(row.get("resumes"), list)
                           else (p.get("at") for p in pauses))
    return [p for p in pauses if p.get("at") not in cleared]


def pause_state(ledger: list[dict]) -> dict | None:
    """The latest uncleared pause line if the trial is paused, else None."""
    still = _open_pauses(ledger)
    return still[-1] if still else None


def _refuse_trial_session(ledger: list[dict], kind: str, session_id: str | None) -> None:
    """Pause/resume, enroll, score and scorepack are the owner's (docs/TRIAL.md section 6):
    refuse a session that is bound to a trial bead. `trial start` is every trial session's
    first action and records CLAUDE_CODE_SESSION_ID, so the ledger itself is the marker:
    nothing for a brief to leak and nothing the owner's own terminal ever carries. A session that
    skipped `start` is not caught; that is the brief's job (it forbids these commands)."""
    if session_id and any(r.get("type") == "start" and r.get("session_id") == session_id
                          for r in ledger):
        raise TrialError(f"`trial {kind}` refused: this session ({session_id}) is bound to a trial "
                         "bead. This command is the owner's (pause, resume, enroll, score, "
                         "scorepack), run from the owner's own terminal (docs/TRIAL.md section "
                         "6); report the concern in your handoff instead.")


def refuse_trial_session(root: Path, kind: str, session_id: str | None) -> None:
    """CLI entry for the owner-only commands that take no ledger of their own."""
    _refuse_trial_session(read_ledger(root), kind, session_id)


def _set_pause(root: Path, kind: str, reason: str, now: str | None,
               session_id: str | None = None) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise TrialError(f"{kind} needs a non-empty --reason")
    ledger = read_ledger(root)
    _refuse_trial_session(ledger, kind, session_id)
    paused = pause_state(ledger)
    if kind == "pause" and paused:
        raise TrialError(f"the trial is already paused ({paused.get('reason')}); resume it first")
    if kind == "resume" and not paused:
        raise TrialError("the trial is not paused")
    line = {"type": kind, "reason": reason, "at": now or _now()}
    if kind == "pause" and any(r.get("type") == "pause" and r.get("at") == line["at"]
                               for r in ledger):
        raise TrialError(f"a pause stamped {line['at']} is already in the ledger (a resume "
                         "names pauses by stamp); try again in a second")
    if kind == "resume":
        line["resumes"] = sorted({p.get("at") for p in _open_pauses(ledger)})
    _append(ledger_path(root), [line])
    return line


def _refuse_if_paused(ledger: list[dict], what: str) -> None:
    paused = pause_state(ledger)
    if paused:
        raise TrialError(f"the trial is PAUSED since {paused.get('at')}: {paused.get('reason')}. "
                         f"No new {what} until the owner runs `watermill trial resume --reason "
                         "...` (docs/TRIAL.md section 6).")


def pause(root: Path, reason: str, *, now: str | None = None,
          session_id: str | None = None) -> dict:
    """Harm stop (docs/TRIAL.md section 6): no new `trial start` until `resume`.
    `session_id` is the caller's session; a trial-bound one is refused."""
    return _set_pause(root, "pause", reason, now, session_id)


def resume(root: Path, reason: str, *, now: str | None = None,
           session_id: str | None = None) -> dict:
    """The owner's written resume decision (same session guard as `pause`)."""
    return _set_pause(root, "resume", reason, now, session_id)


def ledger_problems(ledger: list[dict]) -> list[str]:
    """What makes the ledger unusable for assignment; empty means sound.

    The ledger is `merge=union`, so two machines that enrolled from the same base
    both keep their lines after a merge: a second master seed, a bead enrolled
    twice (possibly with two arms), two beads on one block position (the block
    is no longer two-and-two) or a bead started by two sessions. None of these
    can be repaired by appending, so every assigning command refuses on them.
    """
    problems = []
    seeds = sorted({int(r["seed"]) for r in ledger if r.get("type") == "seed"})
    if len(seeds) > 1:
        problems.append(f"{len(seeds)} master seeds in the ledger ({', '.join(map(str, seeds))})")
    beads: dict[str, list[dict]] = {}
    slots: dict[tuple, set[str]] = {}
    for row in ledger:
        if row.get("type") != "enroll" or not row.get("bead"):
            continue
        beads.setdefault(row["bead"], []).append(row)
        slot = (row.get("repo"), row.get("block"), row.get("pos"))
        slots.setdefault(slot, set()).add(row["bead"])
        if seeds and row.get("seed") is not None and int(row["seed"]) != seeds[0]:
            problems.append(f"{row['bead']} was assigned under seed {row['seed']}, not the "
                            f"master seed {seeds[0]}")
    for bead, rows in sorted(beads.items()):
        if len(rows) > 1:
            arms = "/".join(r.get("arm", "?") for r in rows)
            problems.append(f"{bead} is enrolled {len(rows)} times (arms {arms})")
    for (repo, block, pos), held in sorted(slots.items(), key=str):
        if len(held) > 1:
            problems.append(f"{repo} block {block} position {pos} holds {len(held)} beads "
                            f"({', '.join(sorted(held))}): the block is no longer balanced")
    starts: dict[str, set] = {}
    sessions: dict[str, set] = {}
    for row in ledger:
        if row.get("type") == "start" and row.get("bead"):
            starts.setdefault(row["bead"], set()).add(row.get("session_id"))
            sessions.setdefault(row.get("session_id"), set()).add(row["bead"])
    problems += [f"{b} was started by {len(s)} sessions" for b, s in sorted(starts.items())
                 if len(s) > 1]
    problems += [f"session {s} started {len(b)} trial beads" for s, b in sorted(
        sessions.items(), key=str) if len(b) > 1]
    return problems


def _refuse_if_unsound(ledger: list[dict]) -> None:
    problems = ledger_problems(ledger)
    if problems:
        raise TrialError("the trial ledger is inconsistent (concurrent enrolment merged?): "
                         + "; ".join(problems) + ". This is a protocol failure for the owner "
                         "(docs/TRIAL.md section 6); nothing written.")


def latest(results: list[dict], kind: str) -> dict[str, dict]:
    """bead -> the last results line of this `type` (later lines supersede)."""
    out: dict[str, dict] = {}
    for row in results:
        if row.get("type") == kind and row.get("bead"):
            out[row["bead"]] = row
    return out


# -- randomisation ---------------------------------------------------------


def block_arms(seed: int, repo: str, block: int) -> list[str]:
    """The arms of one block: two A and two B in an order fixed by (seed, repo, block)."""
    arms = ["A"] * (BLOCK // 2) + ["B"] * (BLOCK // 2)
    random.Random(f"{seed}:{repo}:{block}").shuffle(arms)
    return arms


def assign(seed: int, repo: str, already_in_repo: int, beads: list[str]) -> list[dict]:
    """Assign `beads` (sorted here, so call order is irrelevant) after `already_in_repo`."""
    rows = []
    for offset, bead in enumerate(sorted(beads)):
        n = already_in_repo + offset
        block, pos = divmod(n, BLOCK)
        rows.append({"bead": bead, "repo": repo, "arm": block_arms(seed, repo, block)[pos],
                     "seed": seed, "block": block, "pos": pos})
    return rows


# -- the tracker and GitHub (injectable; tests use fakes) -------------------


class Tracker:
    """`bd` run inside a repo."""

    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)

    def _bd(self, *argv: str):
        done = subprocess.run(["bd", *argv], cwd=self.cwd, capture_output=True, text=True,
                              timeout=120, check=False)
        return done

    def _json(self, *argv: str):
        done = self._bd(*argv, "--json")
        if done.returncode != 0:
            raise TrialError(
                f"bd {' '.join(argv)} failed in {self.cwd}: {done.stderr.strip()[-300:]}")
        text = done.stdout
        start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
        return json.loads(text[start:]) if start >= 0 else []

    def ready(self) -> list[dict]:
        return self._json("ready", "-n", "0")

    def show(self, bead: str) -> dict | None:
        got = self._json("show", bead)
        return got[0] if isinstance(got, list) and got else (got or None)

    def ids_with_label(self, label: str) -> set[str]:
        return {r["id"] for r in self._json("list", "--all", "-n", "0", "--label", label)}

    def add_label(self, bead: str, label: str) -> bool:
        return self._bd("label", "add", bead, label).returncode == 0


class GitHub:
    """GitHub over `gh api` REST (the only form that works in a cloud session)."""

    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)
        self._slug: str | None = None

    @property
    def slug(self) -> str:
        if self._slug is None:
            done = subprocess.run(["git", "-C", str(self.cwd), "remote", "get-url", "origin"],
                                  capture_output=True, text=True, timeout=10, check=False)
            url = done.stdout.strip().removesuffix(".git")
            m = re.search(r"[:/]([^/:]+/[^/]+)$", url)
            if not m:
                raise TrialError(f"no GitHub origin in {self.cwd}")
            self._slug = m.group(1)
        return self._slug

    def _api(self, path: str):
        done = subprocess.run(["gh", "api", f"repos/{self.slug}/{path}"], capture_output=True,
                              text=True, timeout=60, check=False)
        if done.returncode != 0:
            raise TrialError(f"gh api {path} failed: {done.stderr.strip()[-200:]}")
        return json.loads(done.stdout)

    def pr(self, number: int) -> dict:
        return self._api(f"pulls/{number}")

    def commits(self, number: int) -> list[dict]:
        return self._api(f"pulls/{number}/commits?per_page=100")

    def check_runs(self, sha: str) -> list[dict]:
        return (self._api(f"commits/{sha}/check-runs?per_page=100") or {}).get("check_runs", [])


# -- eligibility -----------------------------------------------------------

_TOKEN = re.compile(r"[A-Za-z0-9_.*/-]+")


def _scannable(text: str) -> str:
    """The bead text minus its `Out of scope` section (naming a fenced path there forbids it)."""
    lines, keep, skipping = (text or "").splitlines(), [], False
    for line in lines:
        head = line.strip().lower().lstrip("*#- ").rstrip(":")
        if head.startswith("out of scope"):
            skipping = True
            continue
        # the next section ends it, however it is marked up (`Files:`, `**Files.**`, `## Files`)
        if skipping and re.match(r"^[\s*#_-]*(goal|files|approach|verification|context|"
                                 r"acceptance|tests?|notes?)\b", line, re.I):
            skipping = False
        if not skipping:
            keep.append(line)
    return "\n".join(keep)


# A sentence that says the fenced path is NOT changed ("db.py is fenced and not
# touched", "No db.py change") names it without directing an edit.
_NOT_EDITED = re.compile(r"\bnot\s+(?:be\s+)?(?:touched|changed|edited|modified)\b|\buntouched\b|"
                         r"\bno\s+[`'\"]?[\w./-]+[`'\"]?\s+(?:change|edit)s?\b", re.I)
# ...unless the same sentence also directs an edit ("edit db.py, leave Makefile untouched"):
# then every path in it still counts (exclusion is the safe side).
_EDIT_VERB = re.compile(r"\b(?:edit|add|update|modify|write|rewrite|directs?|append|"
                        r"remove|delete|rename|migrat\w*)\b", re.I)


def _is_reference(token: str) -> bool:
    """A handoff note is crew output, never what a bead edits: citing one is a reference."""
    return "/handoffs/" in f"/{token}"


def fence_mentions(text: str, fence) -> list[str]:
    """Fence patterns the bead text names as a path it may edit (outside Out of scope).

    Not counted: handoff citations (`See brain/handoffs/mill/x.md`) and sentences
    that say the path is not changed. Anything else that names a fenced path is
    counted; the owner's `fence-clear` label overrides a false hit.
    """
    tokens = set()
    for sentence in re.split(r"(?<=[.;!?])\s+|\n", _scannable(text)):
        if _NOT_EDITED.search(sentence) and not _EDIT_VERB.search(sentence):
            continue
        tokens |= {t.strip(".,:;)(`'\"") for t in _TOKEN.findall(sentence)}
    tokens = {t for t in tokens if t and ("/" in t or "." in t or t[:1].isupper())
              and not _is_reference(t)}
    hits = []
    for pattern in fence.paths:
        one = type(fence)(paths=(pattern,))
        if any(one.violations([tok]) for tok in tokens):
            hits.append(pattern)
    return sorted(set(hits))


def eligibility(task: dict, fence, *, hand_only: set[str], fence_directed: set[str],
                enrolled_beads: set[str], fence_clear: set[str] = frozenset()) -> list[str]:
    """Why a bead cannot enter the trial; empty means eligible."""
    bead = task.get("id", "")
    why = []
    if bead in enrolled_beads:
        why.append("already enrolled (never re-randomised)")
    if str(task.get("issue_type") or task.get("type") or "task").lower() == "epic":
        why.append("epic")
    if task.get("status") not in (None, "open"):
        why.append(f"status is {task.get('status')}, not open")
    if bead in hand_only:
        why.append(f"labelled {HAND_ONLY_LABEL}")
    touched = fence_mentions(f"{task.get('title', '')}\n{task.get('description', '')}", fence)
    if touched and bead not in fence_directed and bead not in fence_clear:
        why.append(f"names fenced path(s) {', '.join(touched)} (label {FENCE_DIRECTED_LABEL} "
                   f"if the bead directs it, {FENCE_CLEAR_LABEL} if it does not edit them)")
    return why


# -- enroll ----------------------------------------------------------------


def enroll(root: Path, registry: Registry, repos: list[str], bead_ids: list[str] | None, *,
           dry_run: bool, seed: int | None = None, tracker_for=None,
           now: str | None = None) -> dict:
    """Randomise. `bead_ids=None` means every ready bead of each repo.

    Returns {seed, seed_is_new, rows, refused: [(bead, repo, reasons)], label_failures}.
    Explicit ids that are ineligible refuse the whole call (nothing written).
    """
    ledger = read_ledger(root)
    _refuse_if_unsound(ledger)
    if not dry_run:
        _refuse_if_paused(ledger, "enrolment")
    if bead_ids is not None:
        bead_ids = sorted(set(bead_ids))  # a repeated id must not take two block positions
    have = master_seed(ledger)
    if have is not None and seed is not None and seed != have:
        raise TrialError(f"the ledger already holds seed {have}; a different --seed would "
                         "re-randomise. Refusing.")
    drawn = seed if seed is not None else random.SystemRandom().randrange(1, 2**31)
    use = have if have is not None else drawn
    done = enrolled(ledger)
    stamp = now or _now()
    rows: list[dict] = []
    refused: list[tuple[str, str, list[str]]] = []
    partial: list[dict] = []
    trackers = {}
    for name in repos:
        project = registry.get(name)
        if not project.enabled or not project.exists:
            raise TrialError(f"{name}: not an active registered project on this machine")
        try:
            fence = project.load_contract().fence
        except WatermillError as exc:
            raise TrialError(f"{name}: contract unreadable ({exc}); fence unchecked") from exc
        tracker = trackers[name] = (tracker_for or Tracker)(project.path)
        hand_only = tracker.ids_with_label(HAND_ONLY_LABEL)
        directed = tracker.ids_with_label(FENCE_DIRECTED_LABEL)
        clear = tracker.ids_with_label(FENCE_CLEAR_LABEL)
        tasks = tracker.ready() if bead_ids is None else [
            t for t in (tracker.show(b) for b in bead_ids) if t]
        if bead_ids is not None:
            missing = sorted(set(bead_ids) - {t["id"] for t in tasks})
            if missing:
                raise TrialError(f"{name}: no such bead(s): {', '.join(missing)}")
        picked = []
        for task in tasks:
            if bead_ids is not None and task["id"] not in bead_ids:
                continue
            why = eligibility(task, fence, hand_only=hand_only, fence_directed=directed,
                              fence_clear=clear,
                              enrolled_beads=set(done) | {r["bead"] for r in rows})
            if why:
                refused.append((task["id"], name, why))
            else:
                picked.append(task["id"])
        in_repo = sum(1 for r in done.values() if r["repo"] == name)
        for row in assign(use, name, in_repo, picked):
            rows.append({**row, "type": "enroll", "enrolled_at": stamp})
        total = in_repo + len(picked)
        if total % BLOCK:
            arms = [r["arm"] for r in done.values() if r["repo"] == name] + [
                r["arm"] for r in rows if r["repo"] == name]
            partial.append({"repo": name, "block": total // BLOCK, "filled": total % BLOCK,
                            "A": arms.count("A"), "B": arms.count("B")})
    if bead_ids is not None and refused:
        raise TrialError("; ".join(f"{b}: {', '.join(w)}" for b, _, w in refused)
                         + ". Nothing enrolled.")
    result = {"seed": use, "seed_is_new": have is None, "rows": rows, "refused": refused,
              "label_failures": [], "partial_blocks": partial}
    if dry_run or not rows:
        return result
    out = ([{"type": "seed", "seed": use, "drawn_at": stamp,
             "rule": f"balanced blocks of {BLOCK} per repo, random.Random('seed:repo:block')"}]
           if have is None else [])
    _append(ledger_path(root), out + rows)  # ledger first: it is the record, the label a copy
    for row in rows:
        if not trackers[row["repo"]].add_label(row["bead"], f"{LABEL_PREFIX}{row['arm']}"):
            result["label_failures"].append(row)
    return result


def start(root: Path, bead: str, *, session_id: str | None, remote: bool,
          now: str | None = None) -> dict:
    """Bind the calling top-level session to its trial bead (one bead per session)."""
    ledger = read_ledger(root)
    _refuse_if_unsound(ledger)
    _refuse_if_paused(ledger, "start")
    row = enrolled(ledger).get(bead)
    if row is None:
        raise TrialError(f"{bead} is not enrolled in the trial")
    if not session_id:
        raise TrialError("no CLAUDE_CODE_SESSION_ID in the environment (pass --session-id)")
    for other in ledger:
        if other.get("type") != "start":
            continue
        if other["bead"] == bead:
            raise TrialError(f"{bead} already has a session ({other['session_id']}); a bead "
                             "gets one trial session")
        if other["session_id"] == session_id:
            raise TrialError(f"session {session_id} already holds trial bead {other['bead']}; "
                             "cost-state is per session, so one trial bead per session")
    line = {"type": "start", "bead": bead, "repo": row["repo"], "arm": row["arm"],
            "session_id": session_id, "surface": "cloud" if remote else "laptop",
            "started_at": now or _now()}
    _append(ledger_path(root), [line])
    return line


# -- briefs ----------------------------------------------------------------

_REMEMBER = ('{wm}/bin/watermill remember "{cell}" <lesson|...> "<one sentence>" --cause <cause> '
             '--tag trial:{arm} --tag <topic> [--path <file>] [--task {bead}]')

_DENIED = ("If the permission system or the auto-mode classifier denies a tool call, do not "
           "retry it, re-word it or route around it: stop and report BLOCKED, quoting the denied "
           "command and the reason verbatim.")


_OWNER_ONLY = ("Owner-only commands: never run `watermill trial pause`, `trial resume`, `trial "
               "enroll`, `trial collect`, `trial score` or `trial scorepack`, and do not edit "
               "knowledge/trial/. Whether a landed blocker or defect should stop the trial is a "
               "human judgement that is the owner's alone; if you think something is wrong, say "
               "so in your handoff and keep working your bead. (`trial pause`, `resume`, "
               "`enroll`, `score` and `scorepack` also refuse a session that ran `trial "
               "start`.)")


def _slug(bead: str, repo: str) -> str:
    """The bead id with its project prefix removed, as the handoff paths spell it."""
    return landed.normalise(bead).removeprefix(landed.normalise(repo) + "-")


def merge_message(bead: str) -> str:
    """The squash commit both arms land with. It is what the blind scorer reads on main,
    so it must be identical in shape for both arms: GitHub's default squash body lists
    every branch commit (sluice fixups, `chore(agent-runs)` lines, per-model trailers),
    which would name the arm."""
    return f'subject exactly "<PR title> (#<n>)" and body exactly "Bead {bead}."'


def _merge_command(bead: str, surface: str) -> str:
    if surface == "cloud":
        return ('`gh api -X PUT repos/$O/$R/pulls/<n>/merge -f merge_method=squash -f sha="$SHA" '
                f'-f commit_title="<PR title> (#<n>)" -f commit_message="Bead {bead}."` '
                "(never delete $SB)")
    return ('`gh pr merge <n> --squash --delete-branch --match-head-commit <sha> '
            f'--subject "<PR title> (#<n>)" --body "Bead {bead}."`')


def _landing(bead: str, surface: str) -> str:
    """The merge rule, word for word the same for both arms."""
    return ("Landing (the same rule for both arms of this study): wait until EVERY check-run on "
            "the PR's head commit is completed and green (`verify` registers late; allow ~90 s "
            "before trusting an empty list), then squash-merge exactly that head, as a tool call "
            f"of its own, with the commit message {merge_message(bead)}: "
            f"{_merge_command(bead, surface)}. A red check is fixed and pushed, then wait again; "
            "never merge red, never force.")


def brief(root: Path, bead: str, *, surface: str = "laptop",
          registry: Registry | None = None) -> str:
    """The exact prompt for the session working `bead` (arm from the ledger)."""
    if surface not in ("laptop", "cloud"):
        raise TrialError("surface is laptop or cloud")
    ledger = read_ledger(root)
    _refuse_if_unsound(ledger)
    row = enrolled(ledger).get(bead)
    if row is None:
        raise TrialError(f"{bead} is not enrolled in the trial")
    arm, repo = row["arm"], row["repo"]
    cell = repo
    wm = str(Path(root).resolve()) if surface == "laptop" else "$WM"
    if surface == "laptop":
        project = (registry or Registry.load(root)).get(repo)
        where = f"The repo is {project.path} ($REPO). The factory checkout is {wm} ($WM)."
    else:
        where = ("You are in a Claude Code cloud session ($REPO = the current checkout, "
                 "GitHub slug from `git remote get-url origin`). $WM is ../water-mill ONLY if it "
                 "was attached to this session; if it is absent, skip every `watermill` step and "
                 "say so in your handoff.")
    slug = _slug(bead, repo)
    sess = (f"Run, as your FIRST action, `{wm}/bin/watermill trial start {bead}` (it records this "
            "session's id in the trial ledger; it refuses a second bead in one session). If it "
            "refuses, stop and report why.")
    know = (f"Knowledge steps (both arms read and write the same graph): at the start run "
            f"`{wm}/bin/watermill recall \"<bead title and nouns of its Goal>\" --cell \"{cell}\"` "
            f"(then `--everywhere` if the cell has nothing). At sign-off, for every lesson a later "
            f"agent would repeat, run `" + _REMEMBER.format(wm=wm, cell=cell, arm=arm, bead=bead)
            + f"`. EVERY finding you write carries `--tag trial:{arm}` (plus its other tags).")
    secret = ("Do not write the words \"trial\" or \"arm\", or the label, into PR titles, PR "
              "bodies, commit messages or the bead text: the escape scorer is blind to the arm "
              "and must stay so. The tag belongs in findings only.")
    branch = (f"The PR branch is `bead/{slug}` (worktree: `git -C $REPO worktree add \"$WT\" -b "
              f"bead/{slug} origin/main`)." if surface == "laptop" else
              "The PR branch is the session branch $SB (see the cloud flow below).")
    landing = _landing(bead, surface)
    if arm == "A":
        crew = ("TRIAL: this bead is trial:A. Every `watermill remember` you run must carry "
                "--tag trial:A in addition to its other tags. Do not write the words 'trial' or "
                "'arm' into the PR title, body, commits or bead text. When the PR is "
                f"squash-merged, the commit message is {merge_message(bead)} "
                f"({_merge_command(bead, surface)}).")
        body = [
            f"You are the ORCHESTRATOR for exactly ONE bead: {bead} (repo {repo}). This is a "
            "controlled trial of the mill crew; do not take any other bead in this session.",
            where, sess,
            "Run the crew as subagents, one after another, never in parallel and never "
            "skipping a step: millstone (implements, opens the PR), then sluice (reviews it), "
            "then tailrace (verifies CI and lands it) only after sluice approves. Do not "
            "implement or review the change yourself.",
            "Put this line VERBATIM into the prompt of EACH crew agent (millstone, sluice and "
            "tailrace), after the bead id: \"" + crew + "\" Do not edit the crew definition files.",
            "Everything else follows the crew agents' own definitions, including their handoffs "
            "and (in a cloud session) their cloud mode. " + branch,
            landing + " (tailrace does this, with the message above.)",
            know, secret, _DENIED, _OWNER_ONLY,
            "Your own sign-off, as the last things you do: write a short orchestrator handoff "
            "(where things stand, what failed, lessons, open questions); then, as its own tool "
            f"call earlier in the run, you will have run `{wm}/bin/watermill agents whoami` and "
            f"kept the tag; now run `{wm}/bin/watermill agents record --transcript auto --run-tag "
            f"<tag> --role orchestrator --arm A --bead {bead} --pr <n> --outcome "
            "<landed|unlanded|blocked>` and commit that one file.",
        ]
    else:
        if ARM_B_SELF_MERGES:
            end = (landing + " Then close the bead the way the repo's lander does: "
                   + (f"`bd close {bead} --reason \"Merged in PR #<n>\"`, `git -C $REPO pull "
                      "--ff-only`, `bd import .beads/issues.jsonl` (the pull does not import; "
                      "exporting from a stale DB reverts closures and drops beads), `bd export -o "
                      ".beads/issues.jsonl`, check `diff <(git show HEAD:.beads/issues.jsonl | "
                      "sort) <(sort .beads/issues.jsonl)` shows only this bead's old and new line "
                      "(sorted: export and beads-sync order lines differently; if not, stop and "
                      f"report), commit it (`chore(beads): "
                      f"close {bead}`) and push." if surface == "laptop" else
                      f"`BD_DOLT_AUTO_PUSH=false bd close {bead} --reason \"Merged in PR #<n>\"`; "
                      "the close travels as `.beads/issues.jsonl` on $SB via beads-sync (Session "
                      "close below)."))
        else:
            end = ("Stop there: do NOT merge and do NOT close the bead. The merge is handled "
                   "afterwards by the owner (or a tailrace run outside this session).")
        body = [
            f"You are a single general-purpose Claude working ONE bead: {bead} (repo {repo}). "
            "This is a controlled trial against the mill crew; do not take any other bead.",
            where, sess,
            f"Read the bead (`bd show {bead}`, in full including Out of scope and any READ ONLY "
            "marks) and the repo's CLAUDE.md files, and obey the repo's fence. Do the work in "
            "your own git worktree, never the main checkout. " + branch + " Do NOT use the "
            "millstone, sluice or tailrace agents, and do not delegate review to another agent; "
            "you may run tests and reread your own diff.",
            "Implement, add the tests the bead asks for, run the repo's gate (`make verify` in "
            "the worktree) until green, then open a pull request whose body names the bead and "
            "says how you verified it.",
            end,
            "Your handoff: write `brain/handoffs/solo/" + slug + ".md` in the repo (where things "
            "stand, what you tried that failed, lessons, look-here-first, open questions).",
            know, secret, _DENIED, _OWNER_ONLY,
            f"Sign-off: earlier, as its own tool call, run `{wm}/bin/watermill agents whoami` and "
            f"keep the tag; at the very end, with the outcome known, run `{wm}/bin/watermill "
            f"agents record --transcript auto --run-tag <tag> --role solo --arm B --bead {bead} "
            "--pr <n> --outcome <landed|unlanded|blocked>` and commit that one file"
            + (" with your handoff, from $REPO's main checkout, and push." if surface == "laptop"
               else " with your handoff on $SB."),
        ]
    if surface == "cloud":
        body.append(_cloud_steps(arm, bead, slug))
        body.append(_cloud_cost_note(arm))
    else:
        body.append("Laptop: use `gh pr create` for the PR and the crew's normal laptop flow. "
                    "The session's final cost is read from its cost-state line after you exit.")
    return "\n\n".join(body) + "\n"


def _cloud_steps(arm: str, bead: str, slug: str) -> str:
    common = (
        "Cloud flow (cheme-solver brain/runbooks/cloud-mill.md): GitHub is REST only, never "
        "`gh pr ...` or GraphQL: use `gh api repos/$O/$R/...` (O/R from `git remote get-url "
        "origin`). The session branch is the PR branch: `SB=$(git branch --show-current)` must "
        "start with `claude/`, else stop and report BLOCKED. Worktrees are `git worktree add "
        "--detach \"$WT\" origin/main`; publish with `git push origin HEAD:refs/heads/$SB`; never "
        "push `main`, never delete `$SB`. Prefix EVERY bd command with `BD_DOLT_AUTO_PUSH=false` "
        "and run `BD_DOLT_AUTO_PUSH=false bd import -i .beads/issues.jsonl` first; bead changes "
        "reach main only through beads-sync, never in a PR. PR: `gh api -X "
        "POST repos/$O/$R/pulls -f title=... -f head=\"$SB\" -f base=main -f body=...`; CI: poll "
        "`gh api repos/$O/$R/commits/$SHA/check-runs` until the `verify` run is "
        "completed/success (it registers late; settle ~90 s). Handoffs and agent-run records are "
        "COMMITTED on $SB (the container is thrown away).")
    close = (" After the merge, the runbook's Session close (session sync, the one docs-only PR "
             "with the handoffs and records, reset of $SB only after that PR merged).")
    if arm == "A":
        return common + " Merge is tailrace's REST merge (above);" + close
    if ARM_B_SELF_MERGES:
        return common + close + " You are the session, so the Session close is yours."
    return (common + " Do NOT merge. Commit the handoff and the `agents record` file on $SB, push, "
            "and stop with the PR open and its check-runs reported.")


def _cloud_cost_note(arm: str) -> str:
    return (
        "Cost, said plainly: a session cannot read its own FINAL cost-state (Claude Code writes "
        "it at exit), and a cloud transcript does not come back to the laptop. The `agents "
        "record` line you commit is therefore a SNAPSHOT of this session's own transcript "
        "(tokens, cache, tool calls, timestamps) taken at sign-off"
        + ("; it does NOT include the crew subagents' tokens, so for arm A it is a floor"
           if arm == "A" else "")
        + ". `trial collect` stores it with cost_basis=recorded-snapshot; cost is compared on "
        "laptop beads only, so `trial status` keeps it out of the cost comparison (duration, CI, "
        "landing and escapes still count). The owner may record the true figure from the "
        "session's final usage with `watermill trial collect --cost-usd <bead>=<usd>`; it is "
        "stored as owner-supplied (cost_basis=manual) and reported, not compared.")


# -- collect ---------------------------------------------------------------


def _cost_state(path: Path) -> dict | None:
    """The LAST cost-state line of a session file, numbers only; None if it has none."""
    last = None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                if '"cost-state"' not in raw:
                    continue
                with contextlib.suppress(ValueError):
                    row = json.loads(raw)
                    if isinstance(row, dict) and row.get("type") == "cost-state":
                        last = row
    except OSError:
        return None
    if last is None:
        return None
    sums = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for usage in (last.get("modelUsage") or {}).values():
        for key, src in (("input", "inputTokens"), ("output", "outputTokens"),
                         ("cache_read", "cacheReadInputTokens"),
                         ("cache_write", "cacheCreationInputTokens")):
            n = (usage or {}).get(src)
            if isinstance(n, int) and not isinstance(n, bool):
                sums[key] += n
    cost = last.get("totalCostUSD")
    ok = isinstance(cost, (int, float)) and not isinstance(cost, bool)
    return {"cost": float(cost) if ok else None, **sums}


def _find_session(sessions_dir: Path, session_id: str) -> Path | None:
    hits = sorted(Path(sessions_dir).expanduser().glob(f"*/{session_id}.jsonl"))
    return hits[0] if len(hits) == 1 else None


def _recorded_rows(project_path: Path, bead: str) -> list[dict]:
    want = landed.normalise(bead)
    directory = Path(project_path) / recorded.RECORDED_DIR
    if not directory.is_dir():
        return []
    return [r for r in recorded.read_dir(directory) if r.get("subject") == want]


def _session_outcome(sessions_dir: Path, row: dict, recs: list[dict], settle: float,
                     now: float) -> tuple[dict | None, str]:
    """(session facts, why-not). Prefers the real cost-state; falls back to a recorded snapshot."""
    sid = row.get("session_id")
    if sid:
        path = _find_session(sessions_dir, sid)
        if path is not None:
            if now - path.stat().st_mtime < settle:
                return None, "session transcript still being written"
            cs = _cost_state(path)
            rec = sessionlog.record_for(path, Path(sessions_dir).expanduser())
            if cs is not None and cs["cost"] is not None and rec is not None:
                total = cs["input"] + cs["output"] + cs["cache_read"] + cs["cache_write"]
                return {"cost_basis": "cost-state", "cost_usd_est": round(cs["cost"], 6),
                        "tokens_total_incl_cache": total, "tokens_output": cs["output"],
                        "tokens_input": cs["input"], "cache_read_tokens": cs["cache_read"],
                        "cache_write_tokens": cs["cache_write"],
                        "subagent_count": rec["detail"].get("subagent_count"),
                        "started_at": rec["started_at"], "ended_at": rec["ended_at"],
                        "duration_seconds": _span(rec["started_at"], rec["ended_at"])}, ""
    snaps = [r for r in recs if r["detail"].get("role") in recorded.SESSION_ROLES
             and r["detail"].get("transcript_located")]
    if snaps:
        snap = pricing.annotate(json.loads(json.dumps(snaps[-1])))
        d = snap["detail"]
        return {"cost_basis": "recorded-snapshot", "cost_usd_est": d.get("cost_usd_est"),
                "tokens_total_incl_cache": d.get("tokens_total_incl_cache"),
                "tokens_output": d.get("output_tokens"), "tokens_input": d.get("input_tokens"),
                "cache_read_tokens": d.get("cache_read_tokens"),
                "cache_write_tokens": d.get("cache_creation_tokens"),
                "subagent_count": d.get("subagent_count"),
                "started_at": snap.get("started_at"), "ended_at": snap.get("ended_at"),
                "duration_seconds": _span(snap.get("started_at"), snap.get("ended_at")),
                "session_id": d.get("session_id")}, ""
    if sid:
        return None, "session has no cost-state line yet (still running?) and no recorded snapshot"
    return None, "no session known (run `trial start` at the top of the session)"


def _span(a: str | None, b: str | None) -> float | None:
    x, y = _parse(a), _parse(b)
    return max(0.0, (y - x).total_seconds()) if x and y else None


def _pr_outcome(gh, number: int) -> dict:
    pr = gh.pr(number)
    merged_at = pr.get("merged_at")
    commits = gh.commits(number)
    first_green = None
    for commit in commits:
        runs = gh.check_runs(commit["sha"])
        if runs:
            done = [r for r in runs if r.get("status") == "completed"]
            first_green = len(done) == len(runs) and all(r.get("conclusion") in GREEN for r in done)
            break
    def by_agent(c: dict) -> bool:
        message = ((c.get("commit") or {}).get("message") or "").lower()
        return "co-authored-by: claude" in message

    owner = sum(1 for c in commits if len(c.get("parents") or [0]) <= 1 and not by_agent(c))
    return {"pr_number": number, "landed": bool(merged_at), "landed_at": merged_at,
            "landed_sha": pr.get("merge_commit_sha") if merged_at else None,
            "first_push_ci_green": first_green, "owner_corrections": owner}


def collect(root: Path, registry: Registry, *, sessions_dir: Path, gh_for=GitHub,
            prs: dict[str, int] | None = None, manual_cost: dict[str, float] | None = None,
            dry_run: bool = False, settle: float = SETTLE_SECONDS, now: float | None = None,
            stamp: str | None = None) -> dict:
    """Read the outcome of every enrolled bead whose session has ended; append changes."""
    ledger = read_ledger(root)
    starts = started(ledger)
    existing = latest(read_results(root), "collect")
    unknown = sorted(set(manual_cost or {}) - set(enrolled(ledger)))
    if unknown:
        raise TrialError(f"--cost-usd for bead(s) not in the trial: {', '.join(unknown)}")
    clock = now if now is not None else time.time()
    session_use: dict[str, list[str]] = {}
    for s in starts.values():
        session_use.setdefault(s["session_id"], []).append(s["bead"])
    new, waiting = [], []
    for bead, enr in enrolled(ledger).items():
        repo = enr["repo"]
        try:
            project = registry.get(repo)
        except WatermillError:
            waiting.append((bead, f"{repo} is no longer registered"))
            continue
        recs = _recorded_rows(project.path, bead)
        facts, why = _session_outcome(sessions_dir, starts.get(bead, {}), recs, settle, clock)
        if facts is None:
            if manual_cost and bead in manual_cost:
                why += " (the --cost-usd figure was NOT stored: re-run collect when it is ready)"
            waiting.append((bead, why))
            continue
        notes = []
        if len(session_use.get(starts.get(bead, {}).get("session_id"), [])) > 1:
            notes.append("session holds several trial beads: cost not attributable")
            facts["cost_usd_est"], facts["cost_basis"] = None, "none"
        before = existing.get(bead)
        if manual_cost and bead in manual_cost:
            facts["cost_usd_est"], facts["cost_basis"] = float(manual_cost[bead]), "manual"
        elif before and before.get("cost_basis") == "manual":
            # an owner-supplied figure stays until the owner supplies another: a later
            # collect must not silently put the snapshot back
            facts["cost_usd_est"], facts["cost_basis"] = before["cost_usd_est"], "manual"
        if facts.get("cost_basis") == "manual":
            facts["cost_supplied_by"] = "owner"
            notes.append("cost_usd_est supplied by the owner (--cost-usd), not read from a "
                         "cost-state line")
        number = (prs or {}).get(bead) or next(
            (r["detail"]["pr_number"] for r in reversed(recs)
             if r["detail"].get("pr_number")), None)
        pr = {"pr_number": None, "landed": False, "landed_at": None, "landed_sha": None,
              "first_push_ci_green": None, "owner_corrections": None}
        if number:
            try:
                pr = _pr_outcome(gh_for(project.path), number)
            except WatermillError as exc:
                notes.append(f"github lookup failed: {exc}")
                pr["pr_number"] = number
        else:
            notes.append("no PR number found (records carry none; pass --pr BEAD=N)")
        sid = starts.get(bead, {}).get("session_id") or facts.pop("session_id", None)
        facts.pop("session_id", None)
        row = {"type": "collect", "bead": bead, "repo": repo, "arm": enr["arm"],
               "session_id": sid, "surface": starts.get(bead, {}).get("surface"),
               **facts, **pr, "notes": notes}
        if before and {k: v for k, v in before.items() if k != "collected_at"} == row:
            continue  # nothing changed since the last collect
        new.append({**row, "collected_at": stamp or _now()})
    if not dry_run:
        _append(results_path(root), new)
    return {"collected": new, "waiting": waiting}


# -- scoring (blind) -------------------------------------------------------


def due_for_scoring(root: Path, *, today: datetime | None = None) -> list[dict]:
    """Collected, landed beads whose escape window has closed and that have no score."""
    results = read_results(root)
    scored = latest(results, "score")
    when = today or datetime.now(UTC)
    due = []
    for bead, row in latest(results, "collect").items():
        landed_at = _parse(row.get("landed_at"))
        window = timedelta(days=ESCAPE_WINDOW_DAYS)
        final = bead in scored and not scored[bead].get("early")  # a provisional score re-opens it
        if landed_at and not final and when - landed_at >= window:
            due.append(row)
    return sorted(due, key=lambda r: hashlib.sha256(r["bead"].encode()).hexdigest())


RUBRIC = """Severity is by consequence, not by how anyone worded it:
- blocker: would have broken production, lost or corrupted data, leaked private data or
  credentials, opened a security hole, or made the merge gate or landing itself fail or hang.
- bug: wrong behaviour or output a user or downstream code would hit, short of blocker.
- test-gap: the code was right but tests would not have caught a regression, or a test was wrong.
- quality: docs, naming, comments, style, refactor, scope tidy-up, conventions.
An ESCAPE is a defect in the landed work found AFTER it landed and within 14 days of landing:
a bug bead traced to it, a revert of its PR, or a fix commit naming it. Rules: a defect seen
before merge and left unfixed is never an escape; a bug that existed before the change is not
an escape; with no stated link, attribute by code provenance (`git log -S`) and say so; an
owner-requested revert is a design call, not an escape; merge-conflict resolution is not a
defect. Findings you cannot trace to this change within the window do not count."""


def scorepack(root: Path, tracker_for=None, registry: Registry | None = None,
              today: datetime | None = None) -> str:
    """The blind scorer's prompt: beads and the rubric, no arm, no label, no ledger.

    Each bead's block is built from fields both arms share in form (id, repo,
    landing commit and date, title, description), so two beads with the same text
    give the same block whatever their arm. The PR number is left out on purpose:
    the PR page shows the branch, the per-commit history (sluice fixups, crew run
    records) and the authors. The scorer works on `origin/main` with
    `BLIND_PATHSPEC`, which hides handoffs, run records, findings and `.beads/`.
    """
    reg = registry or Registry.load(root)
    blocks = []
    for row in due_for_scoring(root, today=today):
        project = reg.get(row["repo"])
        task = (tracker_for or Tracker)(project.path).show(row["bead"]) or {}
        blocks.append(
            f"### {row['bead']}\nRepo: {project.path}\n"
            f"Landed commit on main: {row.get('landed_sha') or 'unknown (find it by date)'}\n"
            f"Landed: {(row.get('landed_at') or '')[:10]}\nTitle: {task.get('title', '')}\n\n"
            f"{task.get('description', '')}\n")
    if not blocks:
        return ""
    return (
        "You are scoring landed changes for defects that escaped into the code after "
        "they merged. For each bead below, work only in its repo and look for escapes in "
        "the 14 days after the landing date.\n\n" + RUBRIC + "\n\n"
        "How to look, and what not to look at:\n"
        "- Read history on `origin/main` only, and ALWAYS limit git to this pathspec: "
        f"`git log origin/main {BLIND_PATHSPEC}` (and the same for `git show`, `git diff`, "
        "`git log -S`). Those excluded paths hold notes and records about how the work was "
        "done; they are not the work and must not influence a score.\n"
        "- Do not open the pull requests, branches or commit authors on GitHub, and do not "
        "run `bd show` on the beads listed below (their text is given here). Find bug beads "
        "with `bd search <bead id>` / `bd list`, and read those.\n"
        "- Use only evidence about the DEFECT: the bead text, the landed diff, later commits, "
        "reverts and bug beads. Do not try to work out who or what produced the change.\n\n"
        "Reply with one JSON object per line, per bead, nothing else:\n"
        '{"bead": "<id>", "escapes": [{"severity": "blocker|bug|test-gap|quality", "kind": '
        '"bug-bead|revert|fix-commit|other", "ref": "<bead id, PR or sha>", "days_after": <int>, '
        '"summary": "<one sentence>"}], "confidence": "high|medium|low", '
        '"notes": "<one sentence>"}\n'
        'Use "escapes": [] when you find none. Beads:\n\n' + "\n".join(blocks))


def score(root: Path, bead: str, escapes: list[dict], *, scorer: str = "", early: bool = False,
          today: datetime | None = None, stamp: str | None = None) -> dict:
    """Append one blind score for a bead (latest line wins)."""
    results = read_results(root)
    got = latest(results, "collect").get(bead)
    if got is None or not got.get("landed"):
        raise TrialError(f"{bead} has no landed collect line; nothing to score")
    due = _parse(got["landed_at"]) + timedelta(days=ESCAPE_WINDOW_DAYS)
    if (today or datetime.now(UTC)) < due and not early:
        raise TrialError(f"{bead}: the 14-day window closes {due.date()}; --early marks the score "
                         "provisional (status ignores it)")
    for e in escapes:
        if e.get("severity") not in SEVERITIES:
            raise TrialError(
                f"severity {e.get('severity')!r} is not one of {', '.join(SEVERITIES)}")
    row = {"type": "score", "bead": bead, "escapes": escapes, "scorer": scorer[:60],
           "early": bool(early), "scored_at": stamp or _now()}
    _append(results_path(root), [row])
    return row


# -- status ----------------------------------------------------------------


def _group(rows: list[dict]) -> dict[str, list[dict]]:
    return {a: [r for r in rows if r["arm"] == a] for a in ARMS}


def _prop(label: str, k: dict, n: dict, show_p: bool) -> dict:
    out = {"metric": label, "n": dict(n), "k": dict(k), "p_value": None, "note": ""}
    if min(n.values()) == 0:
        out["note"] = "too few to say (an arm has no data)"
        return out
    out["rate"] = {a: round(k[a] / n[a], 4) for a in ARMS}
    out["wilson95"] = {a: [round(x, 4) for x in stats.wilson(k[a], n[a])] for a in ARMS}
    if min(n.values()) < MIN_N:
        out["note"] = f"too few to say (fewer than {MIN_N} per arm)"
    elif not show_p:
        out["note"] = "p-value withheld until the pre-registered interim (30 per arm)"
    else:
        p = stats.fisher_exact(k["A"], n["A"] - k["A"], k["B"], n["B"] - k["B"])
        out["p_value"] = round(p, 6)
    return out


def _cont(label: str, values: dict[str, list[float]], show_p: bool) -> dict:
    n = {a: len(values[a]) for a in ARMS}
    out = {"metric": label, "n": n, "p_value": None, "note": ""}
    if min(n.values()) == 0:
        out["note"] = "too few to say (an arm has no data)"
        return out
    out["median"] = {a: round(stats.median(values[a]), 4) for a in ARMS}
    if min(n.values()) < MIN_N:
        out["note"] = f"too few to say (fewer than {MIN_N} per arm)"
    elif not show_p:
        out["note"] = "p-value withheld until the pre-registered interim (30 per arm)"
    else:
        out["p_value"] = round(stats.mann_whitney(values["A"], values["B"])[1], 6)
    return out


def _sensitivity(enr: dict, collected: dict, scores: dict, when: datetime) -> tuple[dict, dict]:
    """Section 4's sensitivity population: every scored bead, plus every bead enrolled at
    least SENSITIVITY_LAND_DAYS ago that did not land within that many days of enrolment,
    which counts as a failure (as does a scored bead with a bug-or-worse escape)."""
    k, n = dict.fromkeys(ARMS, 0), dict.fromkeys(ARMS, 0)
    limit = timedelta(days=SENSITIVITY_LAND_DAYS)
    for bead, row in enr.items():
        arm = row["arm"]
        got = collected.get(bead) or {}
        enrolled_at, landed_at = _parse(row.get("enrolled_at")), _parse(got.get("landed_at"))
        late = (enrolled_at is not None and when - enrolled_at >= limit
                and (landed_at is None or landed_at - enrolled_at > limit))
        final = scores.get(bead) if got.get("landed") and bead in scores and not scores[
            bead].get("early") else None
        if late:
            n[arm] += 1
            k[arm] += 1
        elif final is not None:
            n[arm] += 1
            k[arm] += any(e["severity"] in PRIMARY_SEVERITIES for e in final["escapes"])
    return k, n


def status(root: Path, *, today: datetime | None = None) -> dict:
    ledger = read_ledger(root)
    enr, starts = enrolled(ledger), started(ledger)
    results = read_results(root)
    collected, scores = latest(results, "collect"), latest(results, "score")
    per_arm = {}
    for a in ARMS:
        beads = [b for b, r in enr.items() if r["arm"] == a]
        got = [collected[b] for b in beads if b in collected]
        landed_rows = [r for r in got if r.get("landed")]
        scored = [b for b in (r["bead"] for r in landed_rows)
                  if b in scores and not scores[b].get("early")]
        per_arm[a] = {"enrolled": len(beads),
                      "in_progress": sum(1 for b in beads if b not in collected),
                      "started": sum(1 for b in beads if b in starts),
                      "collected": len(got), "landed": len(landed_rows), "scored": len(scored)}
    n_scored = {a: per_arm[a]["scored"] for a in ARMS}
    smallest = min(n_scored.values())
    stage = ("final" if smallest >= FINAL_N else "interim" if smallest >= INTERIM_N
             else "pre-interim")
    show_p = stage != "pre-interim"
    primary_k, primary_n = {}, {}
    for a in ARMS:
        rows = [r for r in collected.values() if r["arm"] == a and r.get("landed")
                and r["bead"] in scores and not scores[r["bead"]].get("early")]
        primary_n[a] = len(rows)
        primary_k[a] = sum(1 for r in rows if any(
            e["severity"] in PRIMARY_SEVERITIES for e in scores[r["bead"]]["escapes"]))
    rows_arm = {a: [r for r in collected.values() if r["arm"] == a] for a in ARMS}
    landed_k = {a: sum(1 for r in rows_arm[a] if r.get("landed")) for a in ARMS}
    landed_n = {a: len(rows_arm[a]) for a in ARMS}
    ci_rows = {a: [r for r in rows_arm[a] if r.get("first_push_ci_green") is not None]
               for a in ARMS}
    ci_k = {a: sum(1 for r in ci_rows[a] if r["first_push_ci_green"]) for a in ARMS}
    ci_n = {a: len(ci_rows[a]) for a in ARMS}

    def vals(field, basis=None):
        return {a: [float(r[field]) for r in rows_arm[a] if r.get(field) is not None
                    and (basis is None or r.get("cost_basis") in basis)] for a in ARMS}

    sens_k, sens_n = _sensitivity(enr, collected, scores, today or datetime.now(UTC))
    metrics = {
        "primary": _prop("beads with an escaped bug-or-worse defect (landed, scored)",
                         primary_k, primary_n, show_p),
        "sensitivity": _prop(f"escape OR not landed within {SENSITIVITY_LAND_DAYS} days of "
                             "enrolment (sensitivity, not confirmatory)", sens_k, sens_n, show_p),
        "secondary": [
            _cont(f"cost_usd_est (laptop beads only: cost_basis {'/'.join(COMPARED_COST_BASES)})",
                  vals("cost_usd_est", COMPARED_COST_BASES), show_p),
            _cont("duration_seconds", vals("duration_seconds"), show_p),
            _prop("first-push CI green", ci_k, ci_n, show_p),
            _prop("landed", landed_k, landed_n, show_p),
        ]}
    excluded: dict[str, int] = {}
    for r in collected.values():
        if r.get("cost_basis") not in COMPARED_COST_BASES:
            basis = r.get("cost_basis") or "none"
            excluded[basis] = excluded.get(basis, 0) + 1
    return {"per_arm": per_arm, "stage": stage, "metrics": metrics,
            "ledger_problems": ledger_problems(ledger),
            "cost_compared_bases": list(COMPARED_COST_BASES),
            "cost_excluded_by_basis": excluded,
            "cost_snapshots_excluded": excluded.get("recorded-snapshot", 0),
            "paused": pause_state(ledger),
            "seed": master_seed(ledger), "escape_window_days": ESCAPE_WINDOW_DAYS}


def render_status(s: dict) -> str:
    lines = [f"Trial status: stage {s['stage']} (interim at {INTERIM_N} scored per arm, final at "
             f"{FINAL_N}; no stopping on p-values)", ""]
    if s.get("paused"):
        lines.insert(0, f"PAUSED since {s['paused'].get('at')}: {s['paused'].get('reason')}  "
                        "(no new start until `trial resume --reason`; beads in their window are "
                        "still observed and scored)")
    for problem in s.get("ledger_problems") or []:
        lines.append(f"LEDGER INCONSISTENT: {problem}")
    if s.get("ledger_problems"):
        lines += ["  (protocol failure: enroll/start/brief refuse until the owner resolves it; "
                  "docs/TRIAL.md section 6)", ""]
    lines.append(f"{'':<6}{'enrolled':>9}{'started':>9}{'in prog.':>9}{'collected':>10}"
                 f"{'landed':>8}{'scored':>8}")
    for a, r in s["per_arm"].items():
        lines.append(f"arm {a:<2}{r['enrolled']:>9}{r['started']:>9}{r['in_progress']:>9}"
                     f"{r['collected']:>10}{r['landed']:>8}{r['scored']:>8}")
    lines.append("")
    for m in [s["metrics"]["primary"], s["metrics"]["sensitivity"], *s["metrics"]["secondary"]]:
        tag = ("PRIMARY " if m is s["metrics"]["primary"] else
               "sensitiv." if m is s["metrics"]["sensitivity"] else "secondary")
        n = f"n A={m['n']['A']} B={m['n']['B']}"
        if "rate" in m:
            body = f"A {m['rate']['A']:.0%} vs B {m['rate']['B']:.0%}"
        elif "median" in m:
            body = f"median A {m['median']['A']} vs B {m['median']['B']}"
        else:
            body = ""
        p = f"  p={m['p_value']}" if m["p_value"] is not None else ""
        note = f"  [{m['note']}]" if m["note"] else ""
        lines.append(f"{tag}  {m['metric']}: {n}  {body}{p}{note}")
    lines.append("\nCost is compared on laptop beads only (the session's own final cost-state); "
                 "cloud beads keep duration, CI, landing and escapes.")
    if s["cost_excluded_by_basis"]:
        parts = ", ".join(f"{n} {b}" for b, n in sorted(s["cost_excluded_by_basis"].items()))
        lines.append(f"Excluded from the cost comparison: {parts} (manual = owner-supplied, "
                     "reported descriptively; see docs/TRIAL.md section 8).")
    return "\n".join(lines) + "\n"


def env_session_id() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID")

