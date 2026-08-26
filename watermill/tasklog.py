"""Per-task history, and the root cause of each failure.

`ledger.py` records one line per *run* and answers the questions a ramp
decision needs: is the keep rate climbing, is spend per kept task drifting, did
last night happen at all. It cannot answer the question that actually improves
anything, which is **why** tasks fail -- because by the time a run is summarised
the individual failures have been reduced to three integers.

This file is the same append-only idea one level down: one line per task, plus a
human's later judgement about what went wrong.

Two things shape it:

**The orchestrator knows what happened and not why.** "The gate failed after the
change" is a fact it can establish; whether that happened because the spec was
vague, because the file list was incomplete or because the task was too large is
not visible from any diff. So an automatic line records the mechanical outcome
and, at most, a *hint*. The bucket that counts is supplied by a person who
watched, and until they do it is honestly absent rather than guessed.

**A correction is a new line, never an edit.** Same rule as the ledger, and it
is what makes an annotation safe to add later: the outcome line stays exactly as
it was written, and the judgement arrives beside it. `read()` folds the two
together at read time, latest annotation winning, so a second look at a task
supersedes the first without destroying it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

TASKLOG_FILENAME = "runs/tasks.jsonl"

#: The root-cause taxonomy, defined once here and referenced by
#: `docs/CALIBRATION.md` rather than repeated there. Two lists of buckets that
#: are supposed to be the same list will not stay the same list.
#:
#: Five of these are properties of the *specification*, which is the point: each
#: one implies a different edit to how tasks get written, and sorting a failure
#: into the right bucket is the entire deliverable of a calibration session.
ROOT_CAUSES: dict[str, str] = {
    "vague-goal": "The task did not say clearly enough what done looks like.",
    "incomplete-files": "The agent had to search for where the work went.",
    "weak-scope": "The out-of-scope clause did not cover something adjacent.",
    "too-large": "One agent invocation was not enough for this task.",
    "missing-context": "The spec assumed knowledge the agent did not have.",
    "gate-hole": (
        "Work passed the gate and was still wrong. This halts calibration: "
        "no amount of better task-writing compensates for a gate that a wrong "
        "answer can satisfy."
    ),
    "agent-error": (
        "The specification was sound and the agent still got it wrong. Should "
        "be rare -- when it is the most common entry it is usually a "
        "specification problem wearing a disguise."
    ),
    "none": "It worked.",
}

#: Buckets a machine may never assign to itself. `gate-hole` is the finding that
#: stops everything downstream, and it is by definition invisible to the gate --
#: something has to pass every check and still be wrong, which only a person
#: reading the diff can see. Letting the orchestrator write it would make the
#: most important signal in this system self-reported by the thing being judged.
HUMAN_ONLY = frozenset({"gate-hole", "none", "agent-error"})

OUTCOME = "outcome"
ANNOTATION = "annotation"


def hint_for(outcome: str, reason: str) -> str:
    """The bucket a mechanical failure *suggests*, or empty.

    Deliberately conservative and deliberately not stored as a judgement. Only
    two failures carry their own diagnosis: a fenced path was touched because
    nothing told the agent to stay away from it, and a timeout means the work
    did not fit in one invocation. Everything else -- above all a failing gate
    -- is consistent with four different buckets, and a hint that is wrong more
    often than right trains people to ignore the field.
    """
    text = (reason or "").lower()
    if outcome == "escalated":
        suggestion = "vague-goal"
    elif "fenced path" in text:
        suggestion = "weak-scope"
    elif "timeout" in text:
        suggestion = "too-large"
    else:
        return ""
    # Enforced rather than merely intended: a hint is machine-written, and the
    # buckets in HUMAN_ONLY are exactly the ones a machine must not reach.
    return "" if suggestion in HUMAN_ONLY else suggestion


@dataclass(frozen=True)
class Entry:
    """One task's mechanical outcome, as the run recorded it."""

    run_id: str
    project: str
    task_id: str
    title: str
    outcome: str
    reason: str = ""
    hint: str = ""
    cost_cents: int | None = None
    duration_seconds: float = 0.0
    commit: str = ""
    supervised: bool = False
    log_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": OUTCOME,
            "recorded_at": _now(),
            **{k: getattr(self, k) for k in self.__annotations__},
        }


@dataclass(frozen=True)
class Annotation:
    """A person's judgement about why one task went the way it did."""

    project: str
    task_id: str
    root_cause: str
    note: str = ""
    run_id: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": ANNOTATION,
            "recorded_at": _now(),
            **{k: getattr(self, k) for k in self.__annotations__},
        }


@dataclass
class Record:
    """An outcome folded together with whatever was later said about it."""

    outcome: dict
    annotations: list[dict] = field(default_factory=list)

    @property
    def root_cause(self) -> str:
        """The latest human judgement, or empty. A hint is never promoted here."""
        return self.annotations[-1]["root_cause"] if self.annotations else ""

    @property
    def note(self) -> str:
        return self.annotations[-1].get("note", "") if self.annotations else ""


def append_run(root: Path, summary: dict, log_dir: Path) -> int:
    """Record every task a run attempted. Returns how many lines were written.

    A refused run writes nothing, because it attempted no tasks -- and a zero
    here is the correct reading of a preflight refusal rather than a gap.
    """
    tasks = summary.get("tasks") or []
    written = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        outcome = str(task.get("outcome", ""))
        reason = str(task.get("reason", ""))
        append(
            root,
            Entry(
                run_id=str(summary.get("run_id", "")),
                project=str(summary.get("project", "")),
                task_id=str(task.get("id", "")),
                title=str(task.get("title", "")),
                outcome=outcome,
                reason=reason,
                hint=hint_for(outcome, reason),
                cost_cents=task.get("cost_cents"),
                duration_seconds=float(task.get("duration_seconds") or 0.0),
                commit=str(task.get("commit", "")),
                supervised=bool(summary.get("supervised")),
                log_dir=str(log_dir),
            ),
        )
        written += 1
    return written


def append(root: Path, entry: Entry | Annotation) -> None:
    path = Path(root) / TASKLOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")


def annotate(
    root: Path,
    project: str,
    task_id: str,
    root_cause: str,
    note: str = "",
    run_id: str = "",
) -> None:
    """Record why a task went the way it did.

    An unknown bucket is refused rather than stored. The taxonomy is the whole
    value of this log -- eight buckets that can be counted across projects say
    something, and free text does not.

    A judgement attaches to the **task**, not to one attempt at it, so a task
    discarded on Monday and retried on Tuesday carries the same root cause on
    both lines. That is deliberate: every bucket except `agent-error` describes
    a property of the *specification*, and the specification did not change
    between the two attempts.
    """
    if root_cause not in ROOT_CAUSES:
        raise ValueError(
            f"unknown root cause {root_cause!r}. One of: "
            f"{', '.join(sorted(ROOT_CAUSES))}"
        )
    append(
        root,
        Annotation(
            project=project, task_id=task_id, root_cause=root_cause,
            note=note, run_id=run_id,
        ),
    )


def read(
    root: Path,
    project: str | None = None,
    limit: int | None = None,
    unannotated: bool = False,
) -> list[Record]:
    """Every task recorded, oldest first, with its annotations folded in.

    A line that does not parse is skipped rather than raised on, for the same
    reason the ledger does it: one corrupt line from a machine that lost power
    mid-write must not make the other ninety-nine unreadable.
    """
    path = Path(root) / TASKLOG_FILENAME
    if not path.is_file():
        return []

    records: list[Record] = []
    index: dict[tuple[str, str], list[Record]] = {}
    pending: dict[tuple[str, str], list[dict]] = {}

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
        key = (str(row.get("project", "")), str(row.get("task_id", "")))
        if row.get("kind") == ANNOTATION:
            # An annotation may name a task this log has not seen -- a run from
            # before this file existed, or a pruned line. Held rather than
            # dropped, so it attaches if the outcome turns up further down.
            for record in index.get(key, []):
                record.annotations.append(row)
            if key not in index:
                pending.setdefault(key, []).append(row)
            continue
        record = Record(outcome=row, annotations=list(pending.pop(key, [])))
        records.append(record)
        index.setdefault(key, []).append(record)

    if project:
        records = [r for r in records if r.outcome.get("project") == project]
    if unannotated:
        records = [r for r in records if not r.root_cause]
    return records[-limit:] if limit else records


def causes(records: list[Record]) -> dict:
    """What the failures were actually caused by, as far as anyone has said.

    `unannotated` is reported rather than hidden, because a taxonomy with most
    of its mass in one unlabelled bucket is a taxonomy nobody is filling in --
    and that is a finding about the process, not a rounding error.
    """
    counts: dict[str, int] = {}
    unannotated = 0
    for record in records:
        cause = record.root_cause
        if cause:
            counts[cause] = counts.get(cause, 0) + 1
        else:
            unannotated += 1
    return {
        "tasks": len(records),
        "annotated": len(records) - unannotated,
        "unannotated": unannotated,
        "by_cause": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "gate_holes": counts.get("gate-hole", 0),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
