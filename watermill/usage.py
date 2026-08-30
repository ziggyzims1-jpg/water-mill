"""What was asked of the context graph, and whether it answered.

The graph is the first thing in this factory that costs tokens on every task
whether or not it earns them, and the failure it can have is silent in both
directions: an agent that never calls the tool looks exactly like an agent
whose questions were all answered, and a tool that answers nothing looks
exactly like a tool nobody needed. Neither shows up in a run summary, a diff or
a gate.

So every call is written down here -- one line per query, beside the run
history rather than beside the findings, because this is machine-written
telemetry and `knowledge/` is hand-written judgement.

Three things come out of it, and the third is the one worth building for:

**Was the tool called at all.** The single unknown that `--recall` exists to
resolve, and it cannot be answered from the transcript without reading it.

**The hit rate.** A tool whose queries mostly come back empty is either badly
described in the prompt or genuinely useless yet, and those need opposite
responses.

**The questions that came back empty.** That list is not a failure report --
it is the factory telling you which findings to write next, in the agent's own
words. Nothing else in this system produces that.

It is never read by `recall` and never reaches an agent. A tool that could see
its own usage statistics would be a tool with an incentive.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

USAGE_FILENAME = "runs/recall.jsonl"


def record(
    root: Path,
    *,
    tool: str,
    cell: str = "",
    run_id: str = "",
    task_id: str = "",
    query: str = "",
    hits: int = 0,
    matched: int = 0,
    total: int = 0,
) -> None:
    """Append one call. Never raises: telemetry must not fail a task.

    A tool call that worked and a log line that did not write are not the same
    event, and only one of them is worth interrupting an agent for.
    """
    line = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": tool,
        "cell": cell,
        "run_id": run_id,
        "task_id": task_id,
        "query": query[:300],
        "hits": hits,
        "matched": matched,
        "total": total,
    }
    try:
        path = Path(root) / USAGE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, sort_keys=True) + "\n")
    except OSError:
        return


def read(root: Path, since: str = "", limit: int | None = None) -> list[dict]:
    """Every recorded call, oldest first. A corrupt line is skipped, not raised."""
    path = Path(root) / USAGE_FILENAME
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
        if not isinstance(row, dict):
            continue
        if since and str(row.get("recorded_at", ""))[:10] < since:
            continue
        rows.append(row)
    return rows[-limit:] if limit else rows


def stats(rows: list[dict]) -> dict:
    """Whether the tool is being used, and what it failed to answer."""
    searches = [r for r in rows if r.get("tool") == "recall"]
    answered = [r for r in searches if int(r.get("hits") or 0) > 0]
    empty = [r for r in searches if not int(r.get("hits") or 0)]
    tasks = {(r.get("run_id", ""), r.get("task_id", "")) for r in rows}
    tasks.discard(("", ""))

    unanswered: dict[str, int] = {}
    for row in empty:
        question = str(row.get("query", "")).strip()
        if question:
            unanswered[question] = unanswered.get(question, 0) + 1

    return {
        "calls": len(rows),
        "searches": len(searches),
        "opened": sum(1 for r in rows if r.get("tool") == "detail"),
        "proposed": sum(1 for r in rows if r.get("tool") == "propose"),
        "tasks": len(tasks),
        "answered": len(answered),
        "empty": len(empty),
        "hit_rate": (len(answered) / len(searches)) if searches else None,
        "unanswered": dict(sorted(unanswered.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
