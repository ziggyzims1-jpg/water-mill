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

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .registry import Registry, RegistryError

HANDOFF_DIR = Path("brain") / "handoffs" / "mill"

_LANDED = re.compile(r"^\s*\*\*LANDED\*\*", re.MULTILINE)
_TITLE = re.compile(r"^#\s+Handoff\s*[—–-]+\s*(.+?)\s*$", re.MULTILINE)
_TAILRACE = re.compile(r"^##\s+Tailrace\s*\((\d{4}-\d{2}-\d{2})", re.MULTILINE)
_NONE = re.compile(
    r"^\s*[-*]?\s*\*\*Findings:\*\*\s*none\s*(--|\u2014|\u2013|-)\s*\S",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass(frozen=True)
class Landed:
    """One bead the mill landed, and the handoff that says so."""

    bead: str  # normalised, so it compares equal to a finding's ref
    project: str
    landed_on: date
    path: Path
    waived: bool  # the handoff carries a `**Findings:** none -- why` line


def normalise(bead_id: str) -> str:
    """`Zimmy Life Tracker-092` and `zimmy-life-tracker-092` are one bead.

    bd prints the project as written in its config and older findings spelled
    it with hyphens; both are the same id and a join that treats them as two
    reports every old bead as lag.
    """
    return re.sub(r"[^a-z0-9.]+", "-", (bead_id or "").lower()).strip("-")


def parse(path: Path, project: str) -> Landed | None:
    """One handoff file, or None when it was never landed (or has no date).

    The landing date is the last `## Tailrace (date)` heading: a later section
    for a follow-up merge step is when the bead actually landed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not _LANDED.search(text):
        return None
    dates = _TAILRACE.findall(text)
    if not dates:
        return None
    try:
        landed_on = date.fromisoformat(dates[-1])
    except ValueError:
        return None
    title = _TITLE.search(text)
    bead = normalise(title.group(1)) if title else normalise(f"{project}-{path.stem}")
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
        for path in sorted(directory.glob("*.md")):
            found = parse(path, project.name)
            if found is not None:
                landed.append(found)
    return landed, missing
