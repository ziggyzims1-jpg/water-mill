"""What the factory has learned, across every cell it drives.

`ledger.py` records one line per run and `tasklog.py` one line per task. Both
answer *what happened*. Neither can answer the question an agent has at 3am
with its hands on the code: **has this bitten anyone here before?**

This file is the store for that. One append-only JSONL, committed to the
repository rather than left in `runs/` -- the mechanical history is large,
machine-generated and local to whichever machine ran the night; findings are
small, hand-written and the most valuable thing this factory produces. They
belong in git, where they are reviewable, and where a checkout on another
machine has them.

Four rules shape it, and three of them are inherited rather than invented:

**A machine records what happened; only a person records why.** Same rule as
the task log's `hint` versus its annotation. An agent may `propose` a finding
and that proposal is **quarantined**: it is never returned to another agent
until a person promotes it. A guess stored in the field a judgement belongs in
is worse than a blank, because it counts.

**A correction is a new line, never an edit.** Same rule as the ledger. A
finding that stops being true is *superseded* by another finding, and both
lines stay. `read()` folds them at read time, which is what makes the history
of a belief recoverable rather than merely its current state.

**Every finding carries the date it was observed**, separately from the date it
was written down, because a lesson learned in March and typed up in August is
five months old, not one day old. Age is what makes a finding stale, and
staleness is a property of the world, not of the file.

**A finding that can be mechanised does not belong here.** `destination`
records where a lesson actually went -- the gate, the fence, the contract's
notes -- and empty means nowhere yet. That field exists so the monthly sweep
can find advice that should have become enforcement, which is the way knowledge
in a markdown file quietly decays.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

KNOWLEDGE_FILENAME = "knowledge/findings.jsonl"

#: What a finding *is*. Deliberately four, and deliberately not the eight
#: root-cause buckets -- those classify a task's failure and live in
#: `tasklog.ROOT_CAUSES`, which a finding may reference but does not duplicate.
KINDS: dict[str, str] = {
    "lesson": "Something to do or avoid next time in this situation.",
    "failure": "Something that went wrong, recorded so it is recognisable again.",
    "success": "Something that worked, worth repeating deliberately.",
    "measurement": "A number that was measured rather than estimated.",
}

#: Where a lesson was actually put. The order is the order of worth: a check
#: that cannot be ignored, then one checked against the diff, then advice in a
#: prompt, then a paragraph somebody has to remember to read.
DESTINATIONS: dict[str, str] = {
    "gate": "A check in the project's gate. Cannot be ignored.",
    "fence": "A path in fence.paths. Checked against the diff afterwards.",
    "note": "An advisory line in the contract's notes, carried in the prompt.",
    "record": "Written up in the project's calibration record.",
}

ACTIVE = "active"
PROPOSED = "proposed"
SUPERSEDED = "superseded"
REJECTED = "rejected"

HUMAN = "human"
AGENT = "agent"

FINDING = "finding"
CONFIRM = "confirm"
SUPERSEDE = "supersede"
PROMOTE = "promote"
REJECT = "reject"
REVIEW = "review"

#: How long a finding stands before somebody should look at it again. Ninety
#: days is a quarter: long enough that the sweep is not busywork, short enough
#: that a finding about a dependency, a price or an API cannot quietly become
#: false for a year while an agent still reads it as current.
REVIEW_AFTER_DAYS = 90

#: How long the *sweep itself* may go unrun before that is the finding. A
#: monthly job that stopped running looks exactly like a month with nothing to
#: review: both produce nothing. Thirty-five days is a month plus slack for the
#: weekend a cron was down.
SWEEP_AFTER_DAYS = 35


class KnowledgeError(ValueError):
    """A finding was refused rather than stored. Never raised at read time."""


@dataclass
class Record:
    """One finding, folded together with everything later said about it.

    The stored line is never modified. `status`, `confirmed_at` and
    `superseded_by` are all derived at read time from the lines that came
    after it, which is what makes an old belief recoverable instead of
    overwritten.
    """

    finding: dict
    confirmations: list[dict] = field(default_factory=list)
    supersessions: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.finding.get("id", ""))

    @property
    def cell(self) -> str:
        return str(self.finding.get("cell", ""))

    @property
    def kind(self) -> str:
        return str(self.finding.get("kind", ""))

    @property
    def text(self) -> str:
        return str(self.finding.get("text", ""))

    @property
    def detail(self) -> str:
        return str(self.finding.get("detail", ""))

    @property
    def author(self) -> str:
        return str(self.finding.get("author", HUMAN))

    @property
    def destination(self) -> str:
        return str(self.finding.get("destination", ""))

    @property
    def refs(self) -> dict:
        raw = self.finding.get("refs")
        return raw if isinstance(raw, dict) else {}

    @property
    def observed_at(self) -> str:
        """The date the thing happened -- not the date it was typed up."""
        return str(self.finding.get("observed_at", ""))

    @property
    def superseded_by(self) -> str:
        return str(self.supersessions[-1].get("by", "")) if self.supersessions else ""

    @property
    def confirmed_at(self) -> str:
        return str(self.confirmations[-1].get("on", "")) if self.confirmations else ""

    @property
    def status(self) -> str:
        if self.supersessions:
            return SUPERSEDED
        if self.decisions:
            last = self.decisions[-1].get("kind")
            return ACTIVE if last == PROMOTE else REJECTED
        return PROPOSED if self.author == AGENT else ACTIVE

    @property
    def last_seen(self) -> str:
        """The most recent date anybody vouched for this. Drives staleness."""
        return max(filter(None, (self.observed_at, self.confirmed_at)), default="")

    def age_days(self, as_of: date | None = None) -> int | None:
        """Days since anybody last vouched for this finding, or None if undated.

        Takes `as_of` rather than reading a clock, so every staleness decision
        in this package is testable without one.
        """
        seen = _parse_date(self.last_seen)
        if seen is None:
            return None
        return ((as_of or today()) - seen).days

    def is_stale(self, as_of: date | None = None,
                 after_days: int = REVIEW_AFTER_DAYS) -> bool:
        age = self.age_days(as_of)
        return age is not None and age > after_days

    def to_dict(self, as_of: date | None = None) -> dict:
        return {
            **self.finding,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "confirmed_at": self.confirmed_at,
            "last_seen": self.last_seen,
            "age_days": self.age_days(as_of),
            "stale": self.is_stale(as_of),
        }


# -- writing ---------------------------------------------------------------


def record(
    root: Path,
    cell: str,
    kind: str,
    text: str,
    *,
    detail: str = "",
    observed_at: str = "",
    root_cause: str = "",
    destination: str = "",
    tags: tuple[str, ...] = (),
    refs: dict | None = None,
    author: str = HUMAN,
    source_run: str = "",
    source_task: str = "",
) -> dict:
    """Store one finding. Returns the stored line.

    `observed_at` defaults to today and is accepted explicitly so a finding
    written up a week late is dated when it happened. An unknown kind or
    destination is refused rather than stored: a taxonomy whose members are
    whatever anybody typed cannot be counted, which is the only thing a
    taxonomy is for.
    """
    if kind not in KINDS:
        raise KnowledgeError(
            f"unknown kind {kind!r}. One of: {', '.join(sorted(KINDS))}"
        )
    if destination and destination not in DESTINATIONS:
        raise KnowledgeError(
            f"unknown destination {destination!r}. One of: {', '.join(sorted(DESTINATIONS))}"
        )
    if not text.strip():
        raise KnowledgeError("a finding with no text is not a finding")
    on = observed_at.strip() or today().isoformat()
    if _parse_date(on) is None:
        raise KnowledgeError(f"observed_at must be YYYY-MM-DD, got {on!r}")

    line = {
        "kind_of_line": FINDING,
        "id": _new_id(on),
        "cell": cell.strip(),
        "kind": kind,
        "text": text.strip(),
        "detail": detail.strip(),
        "observed_at": on,
        "recorded_at": _now(),
        "author": author,
        "root_cause": root_cause,
        "destination": destination,
        "tags": list(tags),
        "refs": _clean_refs(refs),
        "source_run": source_run,
        "source_task": source_task,
    }
    _append(root, line)
    return line


def propose(root: Path, cell: str, kind: str, text: str, **kwargs) -> dict:
    """An agent's suggestion, quarantined until a person promotes it.

    Deliberately the same store rather than a second file. A proposal that
    lives somewhere else is a proposal nobody reads, and the quarantine that
    matters is enforced where it can actually be tested -- in the query layer,
    which never returns a proposal to an agent.
    """
    kwargs.pop("author", None)
    return record(root, cell, kind, text, author=AGENT, **kwargs)


def confirm(root: Path, finding_id: str, *, on: str = "", by: str = "") -> dict:
    """Say a finding still holds, and reset its clock.

    This is the sweep's main verb. It is a new line rather than a touched
    field, so "still true in August" and "still true in November" are both
    recoverable rather than one overwriting the other.
    """
    when = on.strip() or today().isoformat()
    if _parse_date(when) is None:
        raise KnowledgeError(f"confirmation date must be YYYY-MM-DD, got {when!r}")
    line = {"kind_of_line": CONFIRM, "id": finding_id, "on": when,
            "by": by, "recorded_at": _now()}
    _append(root, line)
    return line


def supersede(root: Path, old_id: str, new_id: str, *, note: str = "") -> dict:
    """Record that one finding replaced another.

    The edge points forward, from the stale finding to the one that replaced
    it, and both lines survive. Looking up a superseded finding by id must not
    return nothing -- somebody arriving with the old id needs to be told what
    replaced it, not that it never existed.
    """
    if old_id == new_id:
        raise KnowledgeError("a finding cannot supersede itself")
    line = {"kind_of_line": SUPERSEDE, "id": old_id, "by": new_id,
            "note": note, "recorded_at": _now()}
    _append(root, line)
    return line


def decide(root: Path, finding_id: str, *, promote: bool, why: str = "") -> dict:
    """Promote a proposal into the shared knowledge, or reject it."""
    line = {
        "kind_of_line": PROMOTE if promote else REJECT,
        "id": finding_id,
        "why": why,
        "recorded_at": _now(),
    }
    _append(root, line)
    return line


def record_review(root: Path, *, on: str = "", by: str = "", note: str = "") -> dict:
    """Record that the monthly sweep actually happened.

    Without this line there is no way to tell a month with nothing to review
    from a month where nobody looked, and those are opposite findings.
    """
    when = on.strip() or today().isoformat()
    if _parse_date(when) is None:
        raise KnowledgeError(f"review date must be YYYY-MM-DD, got {when!r}")
    line = {"kind_of_line": REVIEW, "on": when, "by": by, "note": note,
            "recorded_at": _now()}
    _append(root, line)
    return line


# -- reading ---------------------------------------------------------------


def read(root: Path, cell: str | None = None, include_superseded: bool = False) -> list[Record]:
    """Every finding, oldest first, folded with what was later said about it.

    A line that does not parse is skipped rather than raised on, the same rule
    the ledger and the task log follow: one corrupt line from a machine that
    lost power mid-write must not make the rest unreadable.
    """
    records: list[Record] = []
    index: dict[str, Record] = {}
    pending: list[dict] = []

    for row in _lines(root):
        line_kind = row.get("kind_of_line")
        if line_kind == FINDING:
            record_ = Record(finding=row)
            records.append(record_)
            index[str(row.get("id", ""))] = record_
            continue
        if line_kind in (CONFIRM, SUPERSEDE, PROMOTE, REJECT):
            pending.append(row)

    # Applied in a second pass so an annotation may name a finding recorded
    # later in the file -- which happens as soon as two machines' knowledge is
    # merged and git orders the lines by hunk rather than by time.
    for row in pending:
        target = index.get(str(row.get("id", "")))
        if target is None:
            continue
        line_kind = row.get("kind_of_line")
        if line_kind == CONFIRM:
            target.confirmations.append(row)
        elif line_kind == SUPERSEDE:
            target.supersessions.append(row)
        else:
            target.decisions.append({**row, "kind": line_kind})

    if cell:
        records = [r for r in records if r.cell == cell]
    if not include_superseded:
        records = [r for r in records if r.status != SUPERSEDED]
    return records


def get(root: Path, finding_id: str) -> Record | None:
    """One finding by id, superseded or not."""
    for record_ in read(root, include_superseded=True):
        if record_.id == finding_id:
            return record_
    return None


def last_review(root: Path) -> dict | None:
    """The most recent recorded sweep, or None if there has never been one."""
    reviews = [row for row in _lines(root) if row.get("kind_of_line") == REVIEW]
    return reviews[-1] if reviews else None


def days_since_review(root: Path, as_of: date | None = None) -> int | None:
    row = last_review(root)
    if row is None:
        return None
    when = _parse_date(str(row.get("on", "")))
    return None if when is None else ((as_of or today()) - when).days


# -- internals -------------------------------------------------------------


def _append(root: Path, line: dict) -> None:
    path = Path(root) / KNOWLEDGE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")


def _lines(root: Path) -> list[dict]:
    path = Path(root) / KNOWLEDGE_FILENAME
    if not path.is_file():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _clean_refs(refs: dict | None) -> dict:
    """Only the four edge types, only as lists of strings.

    An unknown key is dropped rather than stored. Refs are what the graph is
    traversed by, and a typo'd edge type is an edge that exists in the file and
    not in any query -- the worst of both.
    """
    out: dict[str, list[str]] = {}
    for key in ("tasks", "runs", "paths", "cells"):
        values = (refs or {}).get(key) or []
        if isinstance(values, str):
            values = [values]
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        if cleaned:
            out[key] = cleaned
    return out


def _new_id(observed_at: str) -> str:
    """`f-20260828-a1b2`: the date it happened, then four hex.

    The date is in the identifier on purpose. A finding id turns up in commit
    messages, in a contract's notes and in another finding's supersede edge,
    and in every one of those places the first useful question is how old it
    is.
    """
    return f"f-{observed_at.replace('-', '')}-{uuid.uuid4().hex[:4]}"


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def today() -> date:
    """The clock, in exactly one place, so tests can avoid it everywhere else."""
    return datetime.now(UTC).date()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def horizon(days: int, as_of: date | None = None) -> str:
    """The date `days` ago, as YYYY-MM-DD. Used by the sweep's windows."""
    return ((as_of or today()) - timedelta(days=days)).isoformat()
