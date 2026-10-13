"""Crew-file drift: every registered project's mill crew must match water-mill's.

The three crew agent files (`.claude/agents/{millstone,sluice,tailrace}.md`) are
kept byte-identical in water-mill, the cell template and every cell, because an
agent that reads a stale copy follows stale rules (water-mill-mb6). Nothing
enforced it, so `watermill validate` now compares each registered project's
copies with the factory's own. A project may be exempted with a reason in the
registry (`crew_exempt:`), which is reported but does not fail; paths outside
the registry (the workshop copy) can be checked report-only via `check_paths`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

CREW_FILES = ("millstone.md", "sluice.md", "tailrace.md")
AGENTS_DIR = Path(".claude") / "agents"


@dataclass(frozen=True)
class Drift:
    label: str
    differing: tuple[str, ...]  # file names that differ or are missing

    @property
    def clean(self) -> bool:
        return not self.differing


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def compare(reference_root: Path, other_root: Path, label: str) -> Drift:
    """Names of crew files under `other_root` that differ from `reference_root`'s."""
    bad = []
    for name in CREW_FILES:
        ref = _digest(Path(reference_root) / AGENTS_DIR / name)
        got = _digest(Path(other_root) / AGENTS_DIR / name)
        if ref is None:
            raise FileNotFoundError(
                f"reference crew file missing: {reference_root}/{AGENTS_DIR}/{name}"
            )
        if got != ref:
            bad.append(name if got is not None else f"{name} (missing)")
    return Drift(label, tuple(bad))
