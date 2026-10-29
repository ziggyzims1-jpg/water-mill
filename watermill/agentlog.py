"""One line per unit of agent work, whatever kind of agent did it.

`runs/tasks.jsonl` only gets a line when `watermill run` (the headless loop)
works a task. Months of mill crew work were dispatched from Claude Code
sessions instead (millstone -> bolter -> sluice -> tailrace through the Agent tool) and
left almost nothing there. This file is the longitudinal record that does not
care who dispatched the work, so crew performance can be set beside every other
agent's. Sibling beads fill it from transcripts (61r), ship it to Loki (qam)
and compare agents (pu9); they build on the schema below, so it is stable.

Append-only, like the ledger: a correction is a new line, never an edit.

## Schema (version 1) -- one JSON object per line

Envelope, present on every record whatever the agent kind:

    schema            int     1
    key               str     stable identity of the unit of work, e.g.
                              "crew:water-mill-a7z". Re-running a sweep must
                              never duplicate a key; see "Folding" below.
    agent_kind        str     "mill-crew" | a sibling bead's kinds ("subagent",
                              "session", ...). Free-form, lowercase, hyphenated.
    source            str     how the record was produced: "handoff" (crewlog),
                              "transcript" (sessionlog: sessions and subagents,
                              kinds "session", "subagent:<type>", "mill-crew") or
                              "recorded" (the agent's own `agents record` at
                              sign-off, see `recorded.py`).
    recorded_at       str     ISO-8601 UTC, when this line was written
    project           str     registry name; "water-mill" for the factory itself
    subject           str     what the work was about -- a normalised bead id
                              ("zimmy-life-tracker-qyz") or null
    title             str|null
    outcome           str     "landed" | "unlanded" for crew work; sibling kinds
                              define their own small vocabulary
    started_at        str|null  ISO date/time the work began (bead started_at)
    ended_at          str|null  ISO date/time it ended (bead closed_at, else the
                              landing date)
    cost_usd          float|null   ONLY when stated: a tasks.jsonl line or the
                              note's own words. Never estimated; null otherwise.
    duration_seconds  float|null   same rule (an API-equivalent estimate lives
                              apart, in detail.cost_usd_est, derived by read())
    fields_inferred   [str]   names of fields parsed from free text rather than
                              read from a structured source. Stats that need
                              hard numbers exclude records listing a field.
    detail            object  agent-kind specific fields (below)

`detail` for `mill-crew`:

    handoff               str       path of the handoff note it came from
    pr_number             int|null  first "PR #n" in the note          (inferred)
    landed_at             str|null  date of the last "## Tailrace (date)"
    bolter_rounds         int       count of "## Bolter" sections (standards reviews)
    sluice_rounds         int       count of "## Sluice" sections
    sluice_verdict        str|null  last verdict word (approve, approve_after_fixes,
                                    do_not_merge, reject) after "Verdict" in a
                                    Sluice section                        (inferred)
    sluice_pushed_fixes   bool|null null when there was no Sluice section; else
                                    true for any approve_after_fixes verdict, false
                                    for approve, otherwise an un-negated "pushed"
                                    in a Sluice section                   (inferred)
    findings_count        int       distinct finding ids (f-YYYYMMDD-<6 or 8 hex>) cited (inferred)
    findings_waived       bool      the note carries "**Findings:** none -- why"
    bead_created_at       str|null  from the repo's .beads/issues.jsonl, never the bd DB

## Folding

`read()` returns the latest line per key, except that a `recorded` line beats
every non-recorded line for its key, whenever either was written: the agent's
own sign-off facts are the better evidence, and a later `agents sweep` of the
same laptop transcript (same key) must not replace them or count the run twice.
A non-recorded record for a key that already has a recorded winner is never
appended. `append_new()` writes a record only
when its content (ignoring `recorded_at`) differs from the latest line already
stored for that key, so a second sweep appends nothing, and a bead that was
unlanded at the first sweep and landed by the second gets a new line that
supersedes the old one without destroying it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from . import pricing

AGENTLOG_FILENAME = "runs/agents.jsonl"
SCHEMA_VERSION = 1
RECORDED = "recorded"
#: The mill crew in pipeline order: millstone builds, bolter reviews standards (report-only),
#: sluice reviews the spec and is the only reviewer that pushes, tailrace lands. Exactly the
#: agents in `canon/common/.claude/agents/` (pinned by tests/test_bolter.py); the one list every
#: reader of roles (sessionlog, agentcompare, recorded) imports; the trial briefs name the crew in
#: prose, pinned against canon by tests/test_trial.py.
CREW_ROLES = ("millstone", "bolter", "sluice", "tailrace")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _content(record: dict) -> str:
    return json.dumps(
        {k: v for k, v in record.items() if k != "recorded_at"}, sort_keys=True
    )


def read_all(root: Path) -> list[dict]:
    """Every line, oldest first. A line that does not parse is skipped."""
    path = Path(root) / AGENTLOG_FILENAME
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
        if isinstance(row, dict) and row.get("key"):
            rows.append(row)
    return rows


def _outranked(new: dict, held: dict) -> bool:
    """A recorded winner is not displaced by a line from any other source."""
    return held.get("source") == RECORDED and new.get("source") != RECORDED


def read(root: Path, agent_kind: str | None = None, project: str | None = None) -> list[dict]:
    """The latest line per key, in first-seen order, optionally filtered.

    Each record comes back with the derived fields (`detail.cost_usd_est`,
    `detail.tokens_total_incl_cache`) computed NOW from its counters by
    `pricing.annotate`, so every line, old or new, is priced by the current
    table. They are never stored: writers keep only raw counters.
    """
    return [pricing.annotate(r) for r in _latest(root, agent_kind, project)]


def _latest(root: Path, agent_kind: str | None = None, project: str | None = None) -> list[dict]:
    """`read` without the derived fields: the lines exactly as stored."""
    latest: dict[str, dict] = {}
    for row in read_all(root):
        held = latest.get(row["key"])
        if held is not None and _outranked(row, held):
            continue
        latest[row["key"]] = row
    return [
        r for r in latest.values()
        if (not agent_kind or r.get("agent_kind") == agent_kind)
        and (not project or r.get("project") == project)
    ]


def make_record(
    *, key: str, agent_kind: str, source: str, project: str, outcome: str,
    subject: str | None = None, title: str | None = None,
    started_at: str | None = None, ended_at: str | None = None,
    cost_usd: float | None = None, duration_seconds: float | None = None,
    fields_inferred: list[str] | None = None, detail: dict | None = None,
) -> dict:
    """A record with every envelope field present, absent values as null."""
    return {
        "schema": SCHEMA_VERSION,
        "key": key,
        "agent_kind": agent_kind,
        "source": source,
        "recorded_at": _now(),
        "project": project,
        "subject": subject,
        "title": title,
        "outcome": outcome,
        "started_at": started_at,
        "ended_at": ended_at,
        "cost_usd": cost_usd,
        "duration_seconds": duration_seconds,
        "fields_inferred": sorted(fields_inferred or []),
        "detail": detail or {},
    }


def unseen(root: Path, records: list[dict]) -> list[dict]:
    """Which of `records` would change what is stored (derived fields aside)."""
    winners = {r["key"]: r for r in _latest(root)}
    latest = {k: _content(r) for k, r in winners.items()}
    out: list[dict] = []
    for record in records:
        content = _content(record)
        held = winners.get(record["key"])
        if held is not None and _outranked(record, held):
            continue
        if latest.get(record["key"]) == content:
            continue
        latest[record["key"]] = content  # a duplicate within the batch
        winners[record["key"]] = record
        out.append(record)
    return out


def append_new(root: Path, records: list[dict]) -> list[dict]:
    """Append what is new; return it. Idempotent."""
    fresh = unseen(root, records)
    if fresh:
        path = Path(root) / AGENTLOG_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in fresh:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    return fresh
