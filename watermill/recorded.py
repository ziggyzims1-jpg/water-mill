"""An agent's own sign-off facts, kept in the repo it worked in.

`runs/` is gitignored, and a cloud session's transcripts die with its
container, so neither `agents sweep` nor `runs/agents.jsonl` can learn what a
cloud run cost. `watermill agents record` therefore writes ONE line, in the
`agentlog` schema with `source: "recorded"`, to a TRACKED file the agent commits
with its other sign-off work:

    <repo>/knowledge/agent-runs/<run>.jsonl

One file per run, not one shared file: two concurrent PRs each adding a line to
a shared file conflict at its tail every time; two new files never do. The file
is append-only by convention (a correction is a new line in the same file;
`agentlog.read` takes the latest line per key). `agents sweep` ingests the
directory from the factory and every registered checkout, and the recorded line
outranks any parsed or transcript line for the same key (see agentlog).

Privacy: the transcript part is `sessionlog`'s whitelist (counters, timestamps,
ids). The flags are the only other input, and none is free text: the bead id is
validated, role/verdict/arm/outcome are enums, PR and rounds are integers.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

from . import agentlog, landed
from .registry import Registry, RegistryError

RECORDED_DIR = "knowledge/agent-runs"
ROLES = ("millstone", "sluice", "tailrace", "solo")
VERDICTS = ("approve", "approve_after_fixes", "do_not_merge", "reject", "landed",
            "blocked", "verify_failed", "needs_manual")
OUTCOMES = ("landed", "unlanded", "blocked")
ARMS = ("A", "B")
_BEAD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,78}$")


class RecordError(ValueError):
    """Bad input to `agents record`; nothing was written."""


def bead_subject(bead: str | None) -> str | None:
    if bead is None:
        return None
    if not _BEAD.match(bead):
        raise RecordError(f"--bead {bead!r} is not a bead id")
    return landed.normalise(bead)


def build(
    base: dict | None, *, role: str, project: str, bead: str | None = None,
    pr: int | None = None, verdict: str | None = None, sluice_rounds: int | None = None,
    arm: str | None = None, outcome: str | None = None, tag: str | None = None,
    transcript_located: bool = True,
) -> dict:
    """The recorded line: `base` (a sessionlog record, or None) plus the flags."""
    subject = bead_subject(bead)
    facts = {
        "role": role, "bead": subject, "pr_number": pr, "verdict": verdict,
        "sluice_rounds": sluice_rounds, "arm": arm,
        "transcript_located": transcript_located,
    }
    if base is None:
        key = f"recorded:{project}:{role}:{subject or 'none'}:{tag or agentlog._now()}"
        record = agentlog.make_record(
            key=key, agent_kind="mill-crew" if role != "solo" else "session",
            source=agentlog.RECORDED, project=project, subject=subject, outcome=outcome,
            detail=facts)
    else:
        record = dict(base)
        record.update(
            source=agentlog.RECORDED, recorded_at=agentlog._now(), project=project,
            subject=subject or base.get("subject"), outcome=outcome, title=None,
            agent_kind="mill-crew" if role != "solo" else base["agent_kind"],
            fields_inferred=[])
        record["detail"] = {**base["detail"], **facts}
    if subject and role != "solo":
        record["detail"]["crew_key"] = f"crew:{subject}"
    return record


def path_for(directory: Path, record: dict) -> Path:
    d = record["detail"]
    ident = d.get("agent_id") or d.get("session_id") or re.sub(r"\W+", "-", record["key"])[-12:]
    name = "-".join(x for x in (d["role"], d.get("bead"), str(ident)[:12]) if x)
    return Path(directory) / (re.sub(r"[^A-Za-z0-9._-]+", "-", name) + ".jsonl")


def write(directory: Path, record: dict) -> Path:
    """Append the record's line to its run file (created if new)."""
    path = path_for(directory, record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def read_dir(directory: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("key") and row.get("source") == agentlog.RECORDED:
                rows.append(row)
    return rows


def collect(root: Path) -> dict[str, list[dict]]:
    """Recorded lines per checkout (the factory and each registered project)."""
    checkouts = [("water-mill", Path(root))]
    with contextlib.suppress(RegistryError):
        checkouts += [(p.name, p.path) for p in Registry.load(root).active]
    found: dict[str, list[dict]] = {}
    for name, checkout in checkouts:
        directory = checkout / RECORDED_DIR
        if directory.is_dir():
            found[name] = read_dir(directory)
    return found
