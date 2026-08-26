"""Run history across every project the factory drives.

One append-only JSONL file at the factory root. It exists because the questions
that matter about an autonomous system are longitudinal and no single run can
answer them: is the revert rate going up, is one project escalating far more
than the others, has spend per kept task drifted, did last night's run happen
at all.

Append-only, and never rewritten. A ledger that can be edited is one whose
history can be quietly improved, which defeats the purpose of keeping it.
A correction is a new line, not an edit to an old one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILENAME = "runs/index.jsonl"


@dataclass(frozen=True)
class Entry:
    """One run, flattened to the fields worth trending."""

    run_id: str
    project: str
    started_at: str
    ended_at: str
    refused: bool
    supervised: bool
    halt_reason: str
    attempted: int
    completed: int
    failed: int
    escalated: int
    spend_cents: int
    under_counted: bool
    log_dir: str

    @classmethod
    def from_summary(cls, summary: dict, log_dir: Path) -> Entry:
        counts = summary.get("counts", {})
        return cls(
            run_id=summary.get("run_id", ""),
            project=summary.get("project", ""),
            started_at=summary.get("started_at", ""),
            ended_at=summary.get("ended_at", ""),
            refused=bool(summary.get("refused")),
            supervised=bool(summary.get("supervised")),
            halt_reason=summary.get("halt_reason", ""),
            attempted=int(counts.get("attempted", 0)),
            completed=int(counts.get("completed", 0)),
            failed=int(counts.get("failed", 0)),
            escalated=int(counts.get("escalated", 0)),
            spend_cents=int(summary.get("spend_cents", 0)),
            under_counted=bool(summary.get("under_counted")),
            log_dir=str(log_dir),
        )

    def to_dict(self) -> dict:
        return {
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **{k: getattr(self, k) for k in self.__annotations__},
        }


def append(root: Path, entry: Entry) -> None:
    path = Path(root) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")


def read(root: Path, project: str | None = None, limit: int | None = None) -> list[dict]:
    """Every recorded run, newest last.

    A line that does not parse is skipped rather than raised on. A ledger is
    read to answer a question about a hundred runs; one corrupt line from a
    machine that lost power mid-write must not make the other ninety-nine
    unreadable.
    """
    path = Path(root) / LEDGER_FILENAME
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        if project and row.get("project") != project:
            continue
        rows.append(row)
    return rows[-limit:] if limit else rows


def stats(rows: list[dict]) -> dict:
    """Aggregate the trends the ramp decision actually depends on."""
    real = [r for r in rows if not r.get("refused")]
    attempted = sum(int(r.get("attempted", 0)) for r in real)
    completed = sum(int(r.get("completed", 0)) for r in real)
    failed = sum(int(r.get("failed", 0)) for r in real)
    escalated = sum(int(r.get("escalated", 0)) for r in real)
    spend = sum(int(r.get("spend_cents", 0)) for r in real)
    return {
        "runs": len(rows),
        "runs_refused": len(rows) - len(real),
        "attempted": attempted,
        "completed": completed,
        "failed": failed,
        "escalated": escalated,
        "spend_cents": spend,
        "keep_rate": (completed / attempted) if attempted else None,
        "escalation_rate": (escalated / attempted) if attempted else None,
        "cents_per_kept_task": (spend / completed) if completed else None,
        "under_counted_runs": sum(1 for r in real if r.get("under_counted")),
    }
