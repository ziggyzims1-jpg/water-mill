"""Which beads the mill has landed, read from the handoffs the lander marked.

The knowledge graph is only as current as the last time somebody wrote down
what a landed bead taught. Whether that happened is a question about two
files in two repositories -- the handoff that says **LANDED** and the finding
that cites the bead -- and nothing joins them unless this module does.

It is a **reader**: it opens each registered checkout's
`brain/handoffs/mill/*.md` and writes nothing. A checkout that is not on this
machine is reported, never raised on, because a lag list that crashes on one
missing sibling would be switched off by the first laptop without it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .registry import Registry, RegistryError

HANDOFF_DIR = Path("brain") / "handoffs" / "mill"
BEADS_FILE = Path(".beads") / "issues.jsonl"

# The one LANDED rule, shared with crewlog.py. A marker opens a line (optionally
# as a bullet) and is bold: `**LANDED**`, `**LANDED.** PR #1 merged`. Prose that
# merely mentions the word ("not LANDED", "will be **LANDED** once") is not one.
# `[ \t]` and not `\s`, which would let the marker start on a later line.
_LANDED = re.compile(r"^[ \t]*(?:[-*][ \t]+)?\*\*LANDED\b", re.MULTILINE)
_TITLE = re.compile(r"^#\s+Handoff\s*[—–-]+\s*(.+?)\s*$", re.MULTILINE)
_TAILRACE = re.compile(r"^##\s+Tailrace\s*\((\d{4}-\d{2}-\d{2})", re.MULTILINE)
_NONE = re.compile(
    # One line only: `\s` would cross the newline and read the next bullet's
    # dash as the separator, so a bare `none` above a list counted as covered.
    r"^[ \t]*[-*]?[ \t]*\*\*Findings:\*\*[ \t]*none[ \t]*(--|\u2014|\u2013|-)"
    r"[ \t]*[^\s\u2014\u2013-]",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass(frozen=True)
class Landed:
    """One bead the mill landed, and the handoff that says so."""

    bead: str  # normalised, so it compares equal to a finding's ref
    project: str
    landed_on: date | None  # None: marked LANDED with no `## Tailrace (date)`
    path: Path
    waived: bool  # the handoff carries a `**Findings:** none -- why` line


def normalise(bead_id: str) -> str:
    """`Zimmy Life Tracker-092` and `zimmy-life-tracker-092` are one bead.

    bd prints the project as written in its config and older findings spelled
    it with hyphens; both are the same id and a join that treats them as two
    reports every old bead as lag.
    """
    return re.sub(r"[^a-z0-9.]+", "-", (bead_id or "").lower()).strip("-")


def is_landed(text: str) -> bool:
    """Whether a handoff note carries the lander's LANDED marker."""
    return bool(_LANDED.search(text))


def known_bead(bead: str, beads: dict[str, dict]) -> str:
    """The bead id inside a title like `Millstone, Zimmy Life Tracker-9i7.1`.

    Normalising that title gives `millstone-zimmy-life-tracker-9i7.1`, which
    matches no bead; when the repo's JSONL holds an id the title ends with,
    that id is the subject.
    """
    if bead in beads:
        return bead
    tails = [k for k in beads if bead.endswith("-" + k)]
    return max(tails, key=len) if tails else bead


def load_beads(checkout: Path) -> dict[str, dict]:
    """The checkout's `.beads/issues.jsonl` rows keyed by normalised id."""
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
            out[normalise(str(row["id"]))] = row
    return out


def parse(path: Path, project: str, beads: dict[str, dict] | None = None) -> Landed | None:
    """One handoff file, or None when it was never landed.

    The landing date is the last `## Tailrace (date)` heading: a later section
    for a follow-up merge step is when the bead actually landed. A handoff
    marked **LANDED** with no such heading keeps `landed_on=None` rather than
    being dropped: this module exists to notice absences, and skipping the
    files it cannot date would be one.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not is_landed(text):
        return None
    dates = _TAILRACE.findall(text)
    try:
        landed_on = date.fromisoformat(dates[-1]) if dates else None
    except ValueError:
        landed_on = None
    title = _TITLE.search(text)
    bead = normalise(title.group(1)) if title else normalise(f"{project}-{path.stem}")
    bead = known_bead(bead, beads or {})
    return Landed(
        bead=bead,
        project=project,
        landed_on=landed_on,
        path=path,
        waived=bool(_NONE.search(text)),
    )


def read(root: Path) -> tuple[list[Landed], list[str]]:
    """Every landed bead in every registered checkout, plus what was unreachable."""
    try:
        registry = Registry.load(root)
    except RegistryError:
        return [], []
    landed: list[Landed] = []
    missing: list[str] = []
    for project in registry.active:
        directory = project.path / HANDOFF_DIR
        if not directory.is_dir():
            missing.append(project.name)
            continue
        beads = load_beads(project.path)
        for path in sorted(directory.glob("*.md")):
            found = parse(path, project.name, beads)
            if found is not None:
                landed.append(found)
    return landed, missing
