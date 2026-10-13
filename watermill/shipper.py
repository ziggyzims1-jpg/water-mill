"""Shipping the ledger and the task log to Loki, so a night can be watched.

Water Mill already writes everything worth trending: `runs/index.jsonl` is one
line per run and `runs/tasks.jsonl` is one line per task, both append-only, both
already JSON. That is exactly the shape a log store wants, so shipping is a
*read* over files that already exist rather than a new instrumentation layer
threaded through the engine.

**Shipping is not part of a run, and that is the whole design.** It is a
separate command with its own exit code, so a Loki outage, a wrong URL or an
expired token can never hang the run loop, fail a night, or leave a task claimed
while a socket times out. The orchestrator's job is to be trustworthy about what
reached the repository; adding somebody else's HTTP endpoint to that critical
path trades the thing this program is for against a dashboard.

Four more rules, and the third is the one that ruins a Loki install:

**The high-water mark advances only after a push actually succeeded.** A failed
push that still recorded progress loses those lines permanently -- there is no
retry queue here and there should not be one, because a run's history is on disk
and can always be re-shipped by hand.

**Timestamps are strings, in nanoseconds, ascending within a stream.** Loki
answers 400 to a numeric timestamp and rejects a line older than the newest it
already holds for that stream. Both failures read as "Loki is broken" from the
outside, so both are handled here rather than left to be discovered.

**Labels are low cardinality, and the allowlist is enforced.** A label per
`run_id` or `task_id` creates a stream per run and is the documented way to make
Loki unusable. Those values belong *in the line*, which is already JSON and
which LogQL can parse with `| json`. Unknown label keys are refused rather than
ignored, for the same reason a contract refuses them.

**Credentials come from the environment.** `LOKI_URL`, `LOKI_USER`,
`LOKI_TOKEN` -- never the registry and never a contract, exactly as the Gurobi
licence is environment in the project this factory drives first. A token checked
into a repository is one nobody re-reads before the day it leaks.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from . import agentlog, ledger, tasklog

STATE_FILENAME = "runs/.shipped.json"
PUSH_PATH = "/loki/api/v1/push"
DEFAULT_TIMEOUT = 20.0

#: Label keys a stream may carry. Everything else about a run or a task lives in
#: the log line, which is JSON. This list is short on purpose: every distinct
#: combination of these values is one Loki stream, and streams are the resource
#: Loki actually runs out of.
ALLOWED_LABELS = frozenset({"job", "project", "source", "outcome", "env", "agent_kind"})

#: The only values `agent_kind` may take as a label. The full kind
#: ("subagent:builder") stays in the log line; a label per subagent type would
#: be unbounded, so anything outside the set lands in "other".
AGENT_KIND_BUCKETS = ("mill-crew", "session", "subagent", "other")

#: Never a label, whatever the caller asks for. Named separately from
#: ALLOWED_LABELS so the error can say *why* rather than only that it refused.
FORBIDDEN_LABELS = frozenset({"run_id", "task_id", "commit", "log_dir", "title",
                              "reason", "started_at", "recorded_at"})


class ShipError(Exception):
    """Shipping failed. The run history on disk is untouched."""


# -- payload (pure) --------------------------------------------------------


def to_nanos(stamp: str) -> str:
    """An ISO-8601 instant as a nanosecond epoch *string*.

    A string because Loki answers 400 to a JSON number here, which is a
    confusing failure to debug from the outside -- the request looks well formed
    and the endpoint looks broken.
    """
    text = (stamp or "").strip()
    if not text:
        moment = datetime.now(UTC)
    else:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            moment = datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return str(int(moment.timestamp() * 1_000_000_000))


def agent_kind_bucket(kind: object) -> str:
    """Collapse a free-form agent_kind to the closed label set."""
    text = str(kind or "").strip().lower()
    if text in ("mill-crew", "session"):
        return text
    if text == "subagent" or text.startswith("subagent:"):
        return "subagent"
    return "other"


def check_labels(labels: dict) -> None:
    """Refuse a label set that would shard Loki into a stream per run."""
    if "agent_kind" in labels and labels["agent_kind"] not in AGENT_KIND_BUCKETS:
        raise ShipError(
            f"agent_kind label {labels['agent_kind']!r} is outside the closed set "
            f"{', '.join(AGENT_KIND_BUCKETS)}; bucket it with agent_kind_bucket()."
        )
    for key in labels:
        if key in FORBIDDEN_LABELS:
            raise ShipError(
                f"{key!r} must not be a Loki label: it is unique per run or per "
                "task, so labelling it creates one stream per row, which is the "
                "documented way to make Loki unusable. It is already in the log "
                "line -- query it with `| json` instead."
            )
        if key not in ALLOWED_LABELS:
            raise ShipError(
                f"unknown label {key!r}. Allowed: {', '.join(sorted(ALLOWED_LABELS))}. "
                "Unknown keys are refused rather than ignored."
            )


def line_time(labels: dict, row: dict) -> str:
    """The instant a line is filed under.

    Runs and tasks use `recorded_at`. An agent record is filed at the *work's*
    end (`ended_at`, else the crew landing date, else its start), not at sweep
    time, so a backfilled bead lands on the day it happened. `recorded_at` is
    only the last resort.
    """
    if labels.get("source") == "agent":
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        for value in (row.get("ended_at"), detail.get("landed_at"), row.get("started_at")):
            if value:
                return str(value)
    return str(row.get("recorded_at", ""))


def stream_id(labels: dict) -> str:
    """A stable string for one label set, usable as a JSON object key."""
    return json.dumps(dict(sorted(labels.items())), sort_keys=True, separators=(",", ":"))


def build_payload(entries: list[tuple[dict, dict]], floors: dict | None = None) -> dict:
    """Group `(labels, row)` pairs into Loki streams.

    Values are sorted ascending within each stream, because Loki rejects a line
    older than the newest it already holds for that stream and the whole push
    fails with it -- one stale row would otherwise discard a good batch.

    `floors` (stream id -> newest nanos already shipped, kept in the state file)
    covers the same rule *across* pushes. Agent lines are filed at the work's
    end, so a later sweep can bring a record older than one already shipped to
    its stream (a bead that lands after a newer one did, transcript records
    backfilled into a stream the handoff records already filled). Such a line is
    filed at the floor instead; its JSON still carries the true `ended_at`.
    Without this the push fails, the mark never moves, and every later ship --
    runs and tasks included -- fails on the same line forever.
    """
    floors = floors if isinstance(floors, dict) else {}
    streams: dict[tuple, list] = {}
    for labels, row in entries:
        check_labels(labels)
        key = tuple(sorted(labels.items()))
        line = json.dumps(row, sort_keys=True, separators=(",", ":"))
        stamp = to_nanos(line_time(labels, row))
        try:
            floor = int(floors.get(stream_id(labels), 0))
        except (TypeError, ValueError):
            floor = 0
        if int(stamp) < floor:
            stamp = str(floor)
        streams.setdefault(key, []).append([stamp, line])
    return {
        "streams": [
            {"stream": dict(key), "values": sorted(values, key=lambda v: int(v[0]))}
            for key, values in sorted(streams.items())
        ]
    }


def collect(root: Path, state: dict, job: str = "watermill") -> tuple[list, dict]:
    """Rows not yet shipped, and the state that would follow from sending them.

    Both sources are append-only and never rewritten, which is what makes a line
    count a sound high-water mark: line N is the same line tomorrow.
    """
    entries: list[tuple[dict, dict]] = []
    nxt = dict(state)

    runs = ledger.read(root)
    for row in runs[int(state.get("runs", 0)):]:
        entries.append((
            {"job": job, "project": str(row.get("project") or "unknown"), "source": "run"},
            row,
        ))
    nxt["runs"] = len(runs)

    tasks = [r.outcome for r in tasklog.read(root)]
    for row in tasks[int(state.get("tasks", 0)):]:
        entries.append((
            {
                "job": job,
                "project": str(row.get("project") or "unknown"),
                "source": "task",
                "outcome": str(row.get("outcome") or "unknown"),
            },
            row,
        ))
    nxt["tasks"] = len(tasks)

    # Agent records are folded (latest line per key) and tracked by key, not by
    # line count: agents.jsonl re-appends a record whose content changed, so a
    # line count would ship the same piece of work twice. A key ships once,
    # when its latest line is settled. An "unlanded" crew record is held back
    # because the bead may land later and that is the same work, not a second
    # one; once shipped, a key is never re-sent (use --resend after a rebuild).
    marked = state.get("agents")
    shipped = set(marked) if isinstance(marked, list) else set()
    for row in agentlog.read(root):
        if row["key"] in shipped:
            continue
        if row.get("outcome") == "unlanded":
            continue
        entries.append((
            {
                "job": job,
                "project": str(row.get("project") or "unknown"),
                "source": "agent",
                "agent_kind": agent_kind_bucket(row.get("agent_kind")),
            },
            row,
        ))
        shipped.add(row["key"])
    nxt["agents"] = sorted(shipped)

    return entries, nxt


# -- state -----------------------------------------------------------------


def read_state(root: Path) -> dict:
    path = Path(root) / STATE_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # An unreadable mark re-ships rather than skips. A duplicate line in a
        # dashboard is a nuisance; a missing night is the thing being watched
        # for.
        return {}
    return data if isinstance(data, dict) else {}


def write_state(root: Path, state: dict) -> None:
    path = Path(root) / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**state, "shipped_at": datetime.now(UTC).isoformat(timespec="seconds")}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# -- transport -------------------------------------------------------------


def endpoint(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if not base:
        raise ShipError(
            "no Loki URL. Set LOKI_URL or pass --url. It is an environment "
            "variable rather than a registry field because a token beside it in "
            "a repository is one nobody re-reads."
        )
    return base if base.endswith(PUSH_PATH) else base + PUSH_PATH


def push(payload: dict, url: str, user: str = "", token: str = "",
         timeout: float = DEFAULT_TIMEOUT) -> None:
    """POST one batch. Raises ShipError on anything that is not a 2xx.

    stdlib urllib rather than `requests`: this project has one runtime
    dependency and one HTTP POST does not earn a second.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - http(s) URL from operator config
        endpoint(url), data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    if token:
        # Grafana Cloud takes the numeric user id as the username; a self-hosted
        # Loki usually takes neither, so both are optional and independently so.
        raw = f"{user}:{token}".encode()
        request.add_header("Authorization", "Basic " + base64.b64encode(raw).decode())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            if not 200 <= response.status < 300:
                raise ShipError(f"Loki answered {response.status}")
    except urllib.error.HTTPError as exc:
        detail = ""
        # The body is a courtesy: Loki explains *why* it refused a batch, which
        # is the difference between a bad timestamp and a bad token.
        with contextlib.suppress(Exception):
            detail = exc.read().decode("utf-8", "replace")[:300]
        raise ShipError(f"Loki answered {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ShipError(f"could not reach Loki: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ShipError(f"Loki timed out after {timeout:g}s") from exc


def ship(root: Path, url: str = "", user: str = "", token: str = "",
         job: str = "watermill", dry_run: bool = False,
         resend: bool = False, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Send everything recorded since the last successful ship.

    Returns a summary. The high-water mark moves only after the push returned,
    so a failure re-sends next time rather than losing the lines.
    """
    root = Path(root)
    url = url or os.environ.get("LOKI_URL", "")
    user = user or os.environ.get("LOKI_USER", "")
    token = token or os.environ.get("LOKI_TOKEN", "")

    state = {} if resend else read_state(root)
    entries, nxt = collect(root, state, job=job)

    if not entries:
        return {"shipped": 0, "streams": 0, "dry_run": dry_run, "state": state}

    payload = build_payload(entries, floors=state.get("newest"))
    newest = dict(state["newest"]) if isinstance(state.get("newest"), dict) else {}
    for stream in payload["streams"]:
        sid = stream_id(stream["stream"])
        top = int(stream["values"][-1][0])
        with contextlib.suppress(TypeError, ValueError):
            top = max(top, int(newest.get(sid, 0)))
        newest[sid] = str(top)
    nxt["newest"] = newest
    summary = {
        "shipped": len(entries),
        "streams": len(payload["streams"]),
        "dry_run": dry_run,
        "state": nxt,
    }
    if dry_run:
        # Nothing sent and nothing recorded, so previewing a batch does not mean
        # never shipping it -- the same rule the digest's dry run follows.
        summary["payload"] = payload
        return summary

    push(payload, url=url, user=user, token=token, timeout=timeout)
    write_state(root, nxt)
    return summary
