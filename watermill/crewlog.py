"""Mill crew history, recovered from handoff notes and bead JSONL.

A reader: it opens each registered checkout's `brain/handoffs/mill/*.md` (and
this repository's own `HANDOFF-mill/*.md`), plus that repo's tracked
`.beads/issues.jsonl` for bead timing -- never the bd database, because the
JSONL is what is in git -- and returns `agentlog` records. It writes nothing.
`landed.py` owns the LANDED / Tailrace / findings-waiver parsing and is reused.

Nothing is estimated. Cost and duration come from a `runs/tasks.jsonl` line for
the same bead or from the note's own words, else they are null; anything read
out of free text is named in `fields_inferred`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import agentlog, landed, tasklog
from .registry import Registry, RegistryError

FACTORY_PROJECT = "water-mill"
FACTORY_HANDOFFS = Path("HANDOFF-mill")
BEADS_FILE = Path(".beads") / "issues.jsonl"

# landed.py's marker only matches a bare `**LANDED**` line; Tailrace also wrote
# `**LANDED.** PR ...` and bulleted forms. A looser marker here means more beads
# count as landed than landed.read() reports (it undercounts; not changed here).
_LANDED = re.compile(r"^[ \t]*(?:[-*][ \t]+)?\*\*LANDED\b", re.MULTILINE)
_SLUICE = re.compile(r"^##[ \t]+Sluice\b(?![ \t]+scrutiny)[^\n]*$", re.MULTILINE)
_BOLTER = re.compile(r"^##[ \t]+Bolter\b[^\n]*$", re.MULTILINE)
_HEADING = re.compile(r"^##[ \t]+\S", re.MULTILINE)
_PR = re.compile(r"\bPR[ \t]*#(\d+)")
# The verdict is one word of a fixed vocabulary somewhere after "Verdict" on the
# same line: `**Verdict: approve.**`, `### Verdict: approve_after_fixes`,
# `**Verdict still approve_after_fixes on all four**`.
_VERDICT = re.compile(
    r"\bVerdict\b[^\n]{0,40}?\b(approve[ _]after[ _]fixes|do[ _]not[ _]merge|approve|reject)\b",
    re.IGNORECASE,
)
# "pushed" not negated earlier in the same clause: "nothing pushed", "no fixes
# pushed", "pushed no fix" and "not pushed" are the common way to say the opposite.
_PUSHED = re.compile(r"\bpushed\b(?![ \t]+no\b)", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:no|not|nothing|never|without)\b[^.;:\n]*$", re.IGNORECASE)
_FINDING_ID = re.compile(r"\bf-\d{8}-[0-9a-f]{6,}\b")
_COST = re.compile(r"\bcost\b[^\n$]{0,30}\$(\d+(?:\.\d+)?)", re.IGNORECASE)


def _sluice_text(text: str) -> tuple[int, str]:
    """(rounds, the concatenated body of every Sluice section)."""
    starts = list(_SLUICE.finditer(text))
    headings = [m.start() for m in _HEADING.finditer(text)]
    bodies = []
    for m in starts:
        later = [h for h in headings if h > m.start()]
        bodies.append(text[m.start(): later[0] if later else len(text)])
    return len(starts), "\n".join(bodies)


def _bolter_rounds(text: str) -> int:
    """How many `## Bolter` sections (standards reviews) the note holds."""
    return len(_BOLTER.findall(text))


def _pushed_fixes(sluice: str, verdicts: list[str]) -> bool:
    """Whether a Sluice round pushed a fix. The verdict decides when it can.

    The sluice procedure defines `approve_after_fixes` as "you fixed issues and
    pushed" and `approve` as "mergeable as-is", so a verdict is the structured
    answer; prose is read only for `do_not_merge` or a note with no verdict,
    and a "pushed" that the same clause negates does not count.
    """
    if "approve_after_fixes" in verdicts:
        return True
    if "approve" in verdicts:
        return False
    for m in _PUSHED.finditer(sluice):
        if not _NEGATION.search(sluice[max(0, m.start() - 60): m.start()]):
            return True
    return False


def _known_bead(bead: str, beads: dict[str, dict]) -> str:
    """The bead id inside a title like `Millstone, Zimmy Life Tracker-9i7.1`.

    Normalising that title gives `millstone-zimmy-life-tracker-9i7.1`, which
    matches no bead; when the repo's JSONL holds an id the title ends with,
    that id is the subject.
    """
    if bead in beads:
        return bead
    tails = [k for k in beads if bead.endswith("-" + k)]
    return max(tails, key=len) if tails else bead


def _beads(checkout: Path) -> dict[str, dict]:
    path = checkout / BEADS_FILE
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("id"):
            out[landed.normalise(str(row["id"]))] = row
    return out


def _task_lines(root: Path) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for rec in tasklog.read(root):
        o = rec.outcome
        out[(str(o.get("project", "")), landed.normalise(str(o.get("task_id", ""))))] = o
    return out


def parse_record(
    path: Path, project: str, beads: dict[str, dict], tasks: dict[tuple[str, str], dict]
) -> dict | None:
    """One handoff note as an agentlog record, or None when unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    title = landed._TITLE.search(text)
    bead = landed.normalise(title.group(1)) if title else landed.normalise(f"{project}-{path.stem}")
    bead = _known_bead(bead, beads)
    is_landed = bool(_LANDED.search(text))
    dates = landed._TAILRACE.findall(text)
    landed_at = dates[-1] if dates and is_landed else None

    inferred: list[str] = []
    rounds, sluice = _sluice_text(text)
    verdicts = _VERDICT.findall(sluice)
    verdicts = [v.lower().replace(" ", "_") for v in verdicts]
    verdict = verdicts[-1] if verdicts else None
    if verdict:
        inferred.append("detail.sluice_verdict")
    pushed = _pushed_fixes(sluice, verdicts) if rounds else None
    if rounds:
        inferred.append("detail.sluice_pushed_fixes")
    pr = _PR.search(text)
    if pr:
        inferred.append("detail.pr_number")
    ids = set(_FINDING_ID.findall(text))
    inferred.append("detail.findings_count")

    bead_row = beads.get(bead, {})
    task = tasks.get((project, bead))
    cost = duration = None
    if task:
        if task.get("cost_cents") is not None:
            cost = task["cost_cents"] / 100
        if task.get("duration_seconds"):
            duration = float(task["duration_seconds"])
    if cost is None:
        stated = _COST.search(text)
        if stated:
            cost = float(stated.group(1))
            inferred.append("cost_usd")

    return agentlog.make_record(
        key=f"crew:{bead}",
        agent_kind="mill-crew",
        source="handoff",
        project=project,
        subject=bead,
        title=bead_row.get("title"),
        outcome="landed" if is_landed else "unlanded",
        started_at=bead_row.get("started_at"),
        ended_at=bead_row.get("closed_at") or landed_at,
        cost_usd=cost,
        duration_seconds=duration,
        fields_inferred=inferred,
        detail={
            "handoff": str(path),
            "pr_number": int(pr.group(1)) if pr else None,
            "landed_at": landed_at,
            "bolter_rounds": _bolter_rounds(text),
            "sluice_rounds": rounds,
            "sluice_verdict": verdict,
            "sluice_pushed_fixes": pushed,
            "findings_count": len(ids),
            "findings_waived": bool(landed._NONE.search(text)),
            "bead_created_at": bead_row.get("created_at"),
        },
    )


def collect(root: Path) -> tuple[dict[str, list[dict]], list[str]]:
    """Records per project, plus the projects whose handoffs are not on this machine."""
    sources: list[tuple[str, Path, Path]] = [
        (FACTORY_PROJECT, Path(root), Path(root) / FACTORY_HANDOFFS)
    ]
    try:
        for project in Registry.load(root).active:
            sources.append((project.name, project.path, project.path / landed.HANDOFF_DIR))
    except RegistryError:
        pass
    tasks = _task_lines(root)
    records: dict[str, list[dict]] = {}
    missing: list[str] = []
    for name, checkout, directory in sources:
        if not directory.is_dir():
            if name != FACTORY_PROJECT:
                missing.append(name)
            continue
        beads = _beads(checkout)
        found = [
            r for p in sorted(directory.glob("*.md"))
            if (r := parse_record(p, name, beads, tasks)) is not None
        ]
        records[name] = found
    return records, missing
