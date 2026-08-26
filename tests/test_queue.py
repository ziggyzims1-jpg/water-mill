"""Parsing a queue payload, and refusing the one format that caused two bugs."""

from __future__ import annotations

import json

import pytest

from watermill.contract import Queue as QueueContract
from watermill.queue import QueueError, WorkQueue, _parse_rows


def _queue(**overrides) -> WorkQueue:
    raw = {
        "kind": "command",
        "ready": "true",
        "claim": "true",
        "release": "true",
        "close": "true",
    }
    raw.update(overrides)
    return WorkQueue(QueueContract.parse(raw), cwd=".")


def test_parses_a_bare_list():
    rows = _parse_rows(json.dumps([{"id": "a-1", "title": "one", "issue_type": "task"}]))
    assert [r.id for r in rows] == ["a-1"]
    assert rows[0].title == "one"


def test_parses_a_wrapped_list():
    payload = json.dumps({"issues": [{"id": "a-1"}, {"id": "a-2"}]})
    assert [r.id for r in _parse_rows(payload)] == ["a-1", "a-2"]


def test_epics_are_filtered_out():
    """Handing a container to an agent produces a task that silently does nothing.

    The previous version filtered by matching rendered text the tool does not
    print, so the filter matched nothing and every epic was worked as a task.
    A typed field is what makes this checkable at all.
    """
    payload = json.dumps([
        {"id": "epic-1", "issue_type": "epic"},
        {"id": "task-1", "issue_type": "task"},
    ])
    assert [r.id for r in _queue().ready_from(payload)] == ["task-1"]


def test_epic_filtering_is_case_insensitive():
    payload = json.dumps([{"id": "e-1", "issue_type": "Epic"}, {"id": "t-1"}])
    assert [r.id for r in _queue().ready_from(payload)] == ["t-1"]


def test_a_row_with_no_type_is_treated_as_work():
    assert [r.id for r in _parse_rows(json.dumps([{"id": "a-1"}]))] == ["a-1"]


def test_a_rendered_table_is_refused_rather_than_half_parsed():
    """The format that produced both queue bugs. Refusing is the fix."""
    table = "ID      STATUS   TITLE\na-1     open     do the thing\n"
    with pytest.raises(QueueError, match="did not return JSON"):
        _parse_rows(table)


def test_an_empty_payload_is_an_empty_queue_not_an_error():
    assert _parse_rows("") == []
    assert _parse_rows("[]") == []


def test_a_row_that_cannot_be_read_is_skipped_not_raised_on():
    """A rename costs one task, never the whole run."""
    payload = json.dumps([{"id": "a-1"}, {"no_identifier": True}, "a string"])
    assert [r.id for r in _parse_rows(payload)] == ["a-1"]


def test_alternative_id_keys_are_accepted():
    assert _parse_rows(json.dumps([{"issue_id": "x-9"}]))[0].id == "x-9"


def test_a_disabled_queue_reports_no_work():
    queue = WorkQueue(QueueContract.parse({"kind": "none"}), cwd=".")
    assert queue.enabled is False
    assert queue.ready() == []


def test_a_disabled_queue_reports_claims_as_succeeding():
    """With no queue there is nothing to strand, so the lifecycle is a no-op."""
    queue = WorkQueue(QueueContract.parse({"kind": "none"}), cwd=".")
    assert queue.claim("anything") is True
    assert queue.release("anything") is True


def test_release_never_raises():
    """Release runs on the failure path and the signal path.

    Those are exactly the paths where raising would strand the task it was
    trying to free.
    """
    queue = _queue(release="/nonexistent/binary {id}")
    assert queue.release("a-1") is False
