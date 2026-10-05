"""What was asked of the context graph, and whether it answered.

This log exists because the graph's failure modes are silent in both
directions: a tool nobody calls and a tool that answers everything produce the
same run summary, and so do a tool that answers nothing and a tool nobody
needed.
"""

from __future__ import annotations

from pathlib import Path

from watermill import knowledge, mcp, usage


def _server(tmp_path: Path, **kwargs) -> mcp.Server:
    defaults = {"cell": "zimmy", "run_id": "20260828-030000", "task_id": "t-4"}
    defaults.update(kwargs)
    return mcp.Server(root=tmp_path, **defaults)


def test_an_absent_log_is_no_calls_not_an_error(tmp_path: Path):
    assert usage.read(tmp_path) == []
    assert usage.stats([])["calls"] == 0
    assert usage.stats([])["hit_rate"] is None


def test_every_tool_call_is_recorded_with_the_task_that_made_it(tmp_path: Path):
    knowledge.record(tmp_path, cell="zimmy", kind="lesson", text="A finding about the gate.", root_cause="none", tags=("t",))
    server = _server(tmp_path)
    server.call("recall", {"query": "gate"})

    row = usage.read(tmp_path)[0]
    assert row["tool"] == "recall"
    assert row["query"] == "gate"
    assert row["hits"] == 1
    assert (row["run_id"], row["task_id"], row["cell"]) == ("20260828-030000", "t-4", "zimmy")


def test_a_question_that_came_back_empty_is_recorded_as_such(tmp_path: Path):
    """The point of the whole file: an unanswered question is the factory
    telling you which finding to write next, in the agent's own words."""
    knowledge.record(tmp_path, cell="zimmy", kind="lesson", text="Something unrelated.", root_cause="none", tags=("t",))
    server = _server(tmp_path)
    server.call("recall", {"query": "rate limits on the upstream API"})
    server.call("recall", {"query": "rate limits on the upstream API"})

    stats = usage.stats(usage.read(tmp_path))
    assert stats["empty"] == 2
    assert stats["hit_rate"] == 0.0
    assert stats["unanswered"] == {"rate limits on the upstream API": 2}


def test_the_hit_rate_counts_searches_and_not_the_other_tools(tmp_path: Path):
    knowledge.record(tmp_path, cell="zimmy", kind="lesson", text="A finding about the gate.", root_cause="none", tags=("t",))
    server = _server(tmp_path)
    server.call("recall", {"query": "gate"})
    server.call("recall", {"query": "nothing at all like it"})
    server.call("propose", {"root_cause": "none", "tags": ["t"], "text": "Something learned."})

    stats = usage.stats(usage.read(tmp_path))
    assert (stats["searches"], stats["proposed"]) == (2, 1)
    assert stats["hit_rate"] == 0.5
    assert stats["tasks"] == 1


def test_a_window_excludes_what_came_before_it(tmp_path: Path):
    usage.record(tmp_path, tool="recall", query="old")
    rows = usage.read(tmp_path, since="2099-01-01")
    assert rows == []


def test_telemetry_never_fails_a_tool_call(tmp_path: Path):
    """A tool call that worked and a log line that did not write are different
    events, and only one of them is worth interrupting an agent for."""
    unwritable = tmp_path / "runs"
    unwritable.write_text("this is a file, so the log directory cannot be created")
    usage.record(tmp_path, tool="recall", query="x")  # must not raise
    assert usage.read(tmp_path) == []


def test_a_corrupt_line_does_not_hide_the_others(tmp_path: Path):
    usage.record(tmp_path, tool="recall", query="one")
    (tmp_path / usage.USAGE_FILENAME).open("a").write("{not json\n")
    usage.record(tmp_path, tool="recall", query="two")
    assert [r["query"] for r in usage.read(tmp_path)] == ["one", "two"]


def test_the_log_is_never_readable_through_the_graph(tmp_path: Path):
    """A tool that could see its own usage statistics would be a tool with an
    incentive. The telemetry lives beside the run history, not the findings."""
    from watermill import recall

    usage.record(tmp_path, tool="recall", query="a distinctive phrase nobody wrote down")
    graph = recall.build(tmp_path)
    assert recall.search(graph, "distinctive phrase").hits == []
