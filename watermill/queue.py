"""The work queue, as six shell commands and a JSON shape.

Water Mill was built against Beads and imports none of it. A queue is whatever
answers `ready` with JSON and accepts `claim`, `release`, `close` and
`comment` -- which means a project can use Beads, a GitHub label, or a text file
and a wrapper script, and the orchestrator cannot tell.

The JSON requirement is not stylistic. Parsing a rendered table produced two
bugs in the shell version of this loop, and both were silent:

- `bd ready | grep -q` is a race under `pipefail`. `grep -q` closes the pipe on
  its first match, `bd` takes SIGPIPE, and the pipeline reports failure -- so
  the loop concluded there was no work while 27 tasks sat in the queue.
- Filtering epics out by matching rendered text matched a column the tool does
  not print, so epics were handed to the agent as work and it silently did
  nothing with them.

Both disappear when the queue speaks JSON with a type on every row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .contract import Queue as QueueContract
from .errors import WatermillError
from .proc import Result, run

#: Keys a queue payload may wrap its list in.
_LIST_KEYS = ("issues", "items", "results", "tasks", "beads", "data")
#: Candidate keys for a row's identifier and type, most specific first.
_ID_KEYS = ("id", "issue_id", "key", "name")
_TYPE_KEYS = ("issue_type", "type", "kind")
_TITLE_KEYS = ("title", "summary", "name", "description")


@dataclass(frozen=True)
class Task:
    """One unit of work, as the queue described it."""

    id: str
    title: str
    type: str
    raw: dict

    @property
    def label(self) -> str:
        return f"{self.id}: {self.title}" if self.title else self.id


class QueueError(WatermillError):
    """The queue could not be read, or refused a state change."""

    exit_code = 5


class WorkQueue:
    """Runs a contract's queue commands inside a project's working tree."""

    def __init__(self, contract: QueueContract, cwd: Path, log_dir: Path | None = None):
        self.contract = contract
        self.cwd = Path(cwd)
        self.log_dir = Path(log_dir) if log_dir else None

    @property
    def enabled(self) -> bool:
        return self.contract.enabled

    def _run(self, key: str, timeout: float = 120.0, **params: str) -> Result:
        argv = self.contract.render(key, **params)
        # tail_lines=0: the whole payload, because the caller parses it.
        return run(argv, cwd=self.cwd, timeout=timeout, tail_lines=0)

    def ready(self) -> list[Task]:
        """Tasks available to work on now, containers filtered out."""
        if not self.enabled:
            return []
        result = self._run("ready")
        if not result.ok:
            raise QueueError(
                f"queue.ready failed ({result.returncode}): {result.tail[-500:]}"
            )
        return [
            task
            for task in _parse_rows(result.tail)
            if task.type not in self.contract.exclude_types
        ]

    def ready_from(self, payload: str) -> list[Task]:
        """Parse a payload directly. Exists so tests need no subprocess."""
        return [
            task for task in _parse_rows(payload)
            if task.type not in self.contract.exclude_types
        ]

    def stale(self) -> list[Task]:
        """Tasks left claimed by an earlier run.

        A claimed task is absent from `ready`, so a run killed mid-task
        quietly shrinks the queue every time it happens. Preflight refuses on
        these rather than working around them, because the alternative is a
        queue that leaks.
        """
        if not self.enabled or not self.contract.stale:
            return []
        result = self._run("stale")
        if not result.ok:
            return []
        return _parse_rows(result.tail)

    def show(self, task_id: str) -> str:
        if not self.enabled or not self.contract.show:
            return ""
        result = self._run("show", id=task_id)
        return result.tail if result.ok else ""

    def claim(self, task_id: str) -> bool:
        if not self.enabled:
            return True
        return self._run("claim", id=task_id).ok

    def release(self, task_id: str) -> bool:
        """Hand a task back. Never allowed to raise.

        Release runs on the failure path and on the signal path, which are
        exactly the paths where raising would strand the task it was trying to
        free. The caller records the miss and moves on.
        """
        if not self.enabled:
            return True
        try:
            return self._run("release", id=task_id).ok
        except Exception:  # pragma: no cover - defensive on the cleanup path
            return False

    def close(self, task_id: str) -> bool:
        if not self.enabled:
            return True
        return self._run("close", id=task_id).ok

    def comment(self, task_id: str, text: str) -> bool:
        if not self.enabled or not self.contract.comment:
            return False
        try:
            return self._run("comment", id=task_id, text=text).ok
        except Exception:  # pragma: no cover - defensive on the cleanup path
            return False


def _parse_rows(payload: str) -> list[Task]:
    """Turn a queue payload into tasks, tolerantly.

    A row that cannot be read is skipped rather than raised on, for the same
    reason the meter returns None: this is someone else's output format, and a
    rename should cost one task rather than the whole run.
    """
    text = (payload or "").strip()
    if not text:
        return []
    data = _load_json(text)
    if data is None:
        raise QueueError(
            "queue.ready did not return JSON. Water Mill will not parse a "
            "rendered table -- see the two bugs documented in queue.py."
        )
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data] if _first(data, _ID_KEYS) else []
    if not isinstance(data, list):
        return []

    tasks: list[Task] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        identifier = _first(row, _ID_KEYS)
        if identifier is None:
            continue
        tasks.append(
            Task(
                id=str(identifier),
                title=str(_first(row, _TITLE_KEYS) or "").strip(),
                type=str(_first(row, _TYPE_KEYS) or "task").strip().lower(),
                raw=row,
            )
        )
    return tasks


def _load_json(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # A tool that prints a banner before its JSON is common enough to survive.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except (ValueError, TypeError):
                continue
    return None


def _first(obj: dict, keys):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None
