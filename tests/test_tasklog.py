"""The per-task history, and the taxonomy it counts by."""

from __future__ import annotations

from pathlib import Path

import pytest

from watermill import tasklog


def _summary(**overrides) -> dict:
    base = {
        "run_id": "20260826-030000",
        "project": "demo",
        "supervised": False,
        "tasks": [
            {"id": "t-1", "title": "one", "outcome": "completed",
             "cost_cents": 40, "duration_seconds": 61.2, "commit": "abc1234"},
            {"id": "t-2", "title": "two", "outcome": "failed",
             "reason": "gate failed after the change (see t-2.log)", "cost_cents": 30},
        ],
    }
    base.update(overrides)
    return base


def test_a_run_writes_one_line_per_task(tmp_path: Path):
    written = tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    assert written == 2
    records = tasklog.read(tmp_path)
    assert [r.outcome["task_id"] for r in records] == ["t-1", "t-2"]
    assert records[0].outcome["commit"] == "abc1234"


def test_a_refused_run_records_no_tasks(tmp_path: Path):
    """A preflight refusal attempted nothing. Zero is the reading, not a gap."""
    assert tasklog.append_run(tmp_path, _summary(tasks=[]), tmp_path / "logs") == 0
    assert tasklog.read(tmp_path) == []


def test_an_absent_log_is_an_empty_history_not_an_error(tmp_path: Path):
    assert tasklog.read(tmp_path) == []


def test_a_corrupt_line_does_not_hide_the_others(tmp_path: Path):
    tasklog.append_run(tmp_path, _summary(tasks=[{"id": "a", "outcome": "completed"}]), tmp_path)
    path = tmp_path / tasklog.TASKLOG_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    tasklog.append_run(tmp_path, _summary(tasks=[{"id": "c", "outcome": "completed"}]), tmp_path)
    assert [r.outcome["task_id"] for r in tasklog.read(tmp_path)] == ["a", "c"]


# -- the taxonomy ----------------------------------------------------------


def test_an_unknown_root_cause_is_refused_rather_than_stored(tmp_path: Path):
    """Free text would make the log uncountable, which is its only purpose."""
    with pytest.raises(ValueError):
        tasklog.annotate(tmp_path, "demo", "t-1", "it-was-friday")
    assert tasklog.read(tmp_path) == []


def test_an_annotation_attaches_to_its_task(tmp_path: Path):
    tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    tasklog.annotate(tmp_path, "demo", "t-2", "vague-goal", note="two readings")
    records = {r.outcome["task_id"]: r for r in tasklog.read(tmp_path)}
    assert records["t-2"].root_cause == "vague-goal"
    assert records["t-2"].note == "two readings"
    assert records["t-1"].root_cause == ""


def test_a_second_judgement_supersedes_the_first_without_erasing_it(tmp_path: Path):
    """A correction is a new line. The log is append-only or it is editable."""
    tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    tasklog.annotate(tmp_path, "demo", "t-2", "vague-goal")
    tasklog.annotate(tmp_path, "demo", "t-2", "too-large")

    records = {r.outcome["task_id"]: r for r in tasklog.read(tmp_path)}
    assert records["t-2"].root_cause == "too-large"
    assert len(records["t-2"].annotations) == 2

    raw = (tmp_path / tasklog.TASKLOG_FILENAME).read_text()
    assert "vague-goal" in raw


def test_an_annotation_arriving_before_its_outcome_still_attaches(tmp_path: Path):
    tasklog.annotate(tmp_path, "demo", "t-1", "none")
    tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    records = {r.outcome["task_id"]: r for r in tasklog.read(tmp_path)}
    assert records["t-1"].root_cause == "none"


def test_unannotated_filters_to_what_still_needs_a_judgement(tmp_path: Path):
    tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    tasklog.annotate(tmp_path, "demo", "t-1", "none")
    remaining = tasklog.read(tmp_path, unannotated=True)
    assert [r.outcome["task_id"] for r in remaining] == ["t-2"]


def test_reading_filters_by_project(tmp_path: Path):
    tasklog.append_run(tmp_path, _summary(project="a"), tmp_path)
    tasklog.append_run(tmp_path, _summary(project="b"), tmp_path)
    assert {r.outcome["project"] for r in tasklog.read(tmp_path, project="a")} == {"a"}


# -- hints, and the line between a guess and a judgement --------------------


def test_a_hint_is_never_recorded_as_a_root_cause(tmp_path: Path):
    """The machine may suggest. Only a person may conclude."""
    tasklog.append_run(
        tmp_path,
        _summary(tasks=[{"id": "t-9", "outcome": "failed",
                         "reason": "modified fenced path(s): db.py"}]),
        tmp_path,
    )
    record = tasklog.read(tmp_path)[0]
    assert record.outcome["hint"] == "weak-scope"
    assert record.root_cause == ""
    assert tasklog.causes([record])["annotated"] == 0


def test_a_failing_gate_gets_no_hint_at_all():
    """It is consistent with four buckets. A hint wrong more often than right
    is one people learn to ignore, which costs more than having none."""
    assert tasklog.hint_for("failed", "gate failed after the change") == ""


def test_the_machine_never_suggests_a_human_only_bucket():
    """`gate-hole` above all: work that passes every check and is still wrong
    is by definition invisible to the thing running the checks."""
    for outcome in ("failed", "escalated", "completed"):
        for reason in ("gate failed", "modified fenced path(s): x", "task timeout", ""):
            assert tasklog.hint_for(outcome, reason) not in tasklog.HUMAN_ONLY


def test_every_hint_is_a_real_bucket():
    for outcome in ("failed", "escalated", "completed"):
        for reason in ("modified fenced path(s): x", "task timeout", "whatever"):
            hint = tasklog.hint_for(outcome, reason)
            assert hint == "" or hint in tasklog.ROOT_CAUSES


# -- counting --------------------------------------------------------------


def test_causes_reports_what_is_still_unlabelled(tmp_path: Path):
    """A taxonomy with its mass in one unlabelled bucket is a process nobody
    is following, which is a finding rather than a rounding error."""
    tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    tasklog.annotate(tmp_path, "demo", "t-1", "none")
    stats = tasklog.causes(tasklog.read(tmp_path))
    assert stats == {
        "tasks": 2,
        "annotated": 1,
        "unannotated": 1,
        "by_cause": {"none": 1},
        "gate_holes": 0,
    }


def test_gate_holes_are_counted_separately(tmp_path: Path):
    tasklog.append_run(tmp_path, _summary(), tmp_path / "logs")
    tasklog.annotate(tmp_path, "demo", "t-1", "gate-hole", note="passed, still wrong")
    assert tasklog.causes(tasklog.read(tmp_path))["gate_holes"] == 1


def test_causes_of_nothing_is_not_a_division_by_zero():
    assert tasklog.causes([])["tasks"] == 0
