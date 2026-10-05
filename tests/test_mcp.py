"""The tool an agent calls mid-task, and the protocol it speaks.

Nothing here mocks the transport: `serve` is driven with real newline-delimited
JSON-RPC through file objects, because the failure this seam actually has is a
frame the client cannot parse, and a test that calls `handle()` directly cannot
see one.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from watermill import knowledge, mcp, recall


def _server(tmp_path: Path, **kwargs) -> mcp.Server:
    defaults = {"cell": "zimmy", "run_id": "20260828-030000", "task_id": "t-4"}
    defaults.update(kwargs)
    return mcp.Server(root=tmp_path, **defaults)


def _drive(server: mcp.Server, *messages: dict) -> list[dict]:
    out = io.StringIO()
    mcp.serve(server, stdin=io.StringIO("\n".join(json.dumps(m) for m in messages)), stdout=out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_the_handshake_answers_in_the_version_the_client_asked_for(tmp_path: Path):
    replies = _drive(
        _server(tmp_path),
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18"}},
    )
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert replies[0]["result"]["serverInfo"]["name"] == mcp.SERVER_NAME


def test_a_client_that_names_no_version_gets_the_default(tmp_path: Path):
    replies = _drive(_server(tmp_path), {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert replies[0]["result"]["protocolVersion"] == mcp.DEFAULT_PROTOCOL


def test_a_notification_is_not_answered(tmp_path: Path):
    """Answering `notifications/initialized` is itself a protocol error."""
    assert _drive(_server(tmp_path), {"jsonrpc": "2.0", "method": "notifications/initialized"}) == []


def test_three_tools_are_offered_and_read_only_offers_two(tmp_path: Path):
    replies = _drive(_server(tmp_path), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert [t["name"] for t in replies[0]["result"]["tools"]] == ["recall", "detail", "propose"]

    replies = _drive(
        _server(tmp_path, read_only=True), {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert [t["name"] for t in replies[0]["result"]["tools"]] == ["recall", "detail"]


def test_recall_answers_with_what_the_factory_knows(tmp_path: Path):
    knowledge.record(tmp_path, cell="zimmy", kind="lesson",
                     text="The gate must be exactly what CI runs.",
                     root_cause="none", tags=("gate",))
    text, is_error = _server(tmp_path).call("recall", {"query": "gate CI"})
    assert not is_error
    assert "exactly what CI runs" in text


def test_recall_is_scoped_to_this_cell_unless_asked_otherwise(tmp_path: Path):
    knowledge.record(tmp_path, cell="cell-1b", kind="lesson",
                     text="Integrations stay fenced until wired.",
                     root_cause="none", tags=("fence",))
    server = _server(tmp_path)
    scoped, _ = server.call("recall", {"query": "integrations fenced"})
    assert "stay fenced" not in scoped
    assert "elsewhere" in scoped, "an empty scope says where to look, not that nobody knows"
    everywhere, _ = server.call("recall", {"query": "integrations fenced", "scope": "everywhere"})
    assert "stay fenced" in everywhere


def test_a_proposal_is_stamped_with_the_provenance_the_engine_supplied(tmp_path: Path):
    """The agent is never asked which cell, run or task it is in, so it cannot
    file a finding against a project it is not working on."""
    server = _server(tmp_path)
    text, is_error = server.call(
        "propose", {"root_cause": "none", "tags": ["t"], "text": "The spec assumed a migration that does not exist.",
                    "cell": "some-other-cell", "author": "human"}
    )
    assert not is_error
    stored = knowledge.read(tmp_path)[0]
    assert stored.cell == "zimmy"
    assert stored.author == knowledge.AGENT
    assert stored.finding["source_run"] == "20260828-030000"
    assert stored.finding["source_task"] == "t-4"
    assert stored.id in text


def test_a_proposal_is_not_readable_by_the_next_recall(tmp_path: Path):
    """The point of the quarantine, asserted through the tool rather than the
    library: an agent must not be able to read its own guess back as agreed."""
    server = _server(tmp_path)
    server.call("propose", {"root_cause": "none", "tags": ["t"], "text": "Something about migrations."})
    answer, _ = server.call("recall", {"query": "migrations"})
    assert "Something about migrations" not in answer
    # And the quarantine does not leak its own existence either: the count of
    # what could be searched excludes it, so the answer is the same one an
    # empty factory gives.
    assert "Nothing has been recorded yet" in answer


def test_a_read_only_session_cannot_record_anything(tmp_path: Path):
    text, is_error = _server(tmp_path, read_only=True).call("propose", {"text": "x"})
    assert is_error
    assert knowledge.read(tmp_path) == []


def test_an_empty_proposal_is_refused_rather_than_stored(tmp_path: Path):
    text, is_error = _server(tmp_path).call("propose", {"root_cause": "none", "tags": ["t"], "text": "   "})
    assert is_error
    assert knowledge.read(tmp_path) == []


def test_an_unknown_kind_falls_back_to_lesson_rather_than_failing(tmp_path: Path):
    """A refusal here costs the agent a turn to no purpose: the text is what
    matters and the bucket is a detail a person can fix in the sweep."""
    _server(tmp_path).call("propose", {"root_cause": "none", "tags": ["t"], "text": "Something.", "kind": "musing"})
    assert knowledge.read(tmp_path)[0].kind == "lesson"


def test_detail_needs_an_id_and_says_so(tmp_path: Path):
    assert "needs an id" in _server(tmp_path).call("detail", {})[0]


def test_an_unknown_tool_is_an_error_the_agent_can_read(tmp_path: Path):
    text, is_error = _server(tmp_path).call("forget", {})
    assert is_error and "No such tool" in text


def test_an_unparsable_frame_is_answered_and_the_session_continues(tmp_path: Path):
    """One malformed frame must not take the tool away for the rest of a task."""
    out = io.StringIO()
    mcp.serve(
        _server(tmp_path),
        stdin=io.StringIO('{not json\n\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'),
        stdout=out,
    )
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["error"]["code"] == -32700
    assert "tools" in replies[1]["result"]


def test_an_unknown_method_is_a_protocol_error_not_a_crash(tmp_path: Path):
    replies = _drive(_server(tmp_path), {"jsonrpc": "2.0", "id": 9, "method": "resources/list"})
    assert replies[0]["error"]["code"] == -32601


def test_a_json_array_is_rejected_as_an_invalid_request(tmp_path: Path):
    out = io.StringIO()
    mcp.serve(_server(tmp_path), stdin=io.StringIO("[1, 2, 3]\n"), stdout=out)
    assert json.loads(out.getvalue())["error"]["code"] == -32600


def test_the_config_document_names_the_command_the_engine_built(tmp_path: Path):
    document = mcp.config_document(["/usr/bin/python3", "/factory/bin/watermill", "mcp"])
    assert document["mcpServers"][mcp.SERVER_NAME] == {
        "command": "/usr/bin/python3",
        "args": ["/factory/bin/watermill", "mcp"],
    }


def test_the_tool_descriptions_stay_short_because_every_task_pays_for_them(tmp_path: Path):
    """Not a style rule: this text is in the agent's context on every single
    task, so it is the one part of this feature with an unbounded cost."""
    assert sum(len(t["description"]) for t in mcp.TOOLS) < 1200


def test_recall_through_the_tool_is_the_same_read_the_cli_makes(tmp_path: Path):
    """One query engine. A tool that answered differently from the command a
    person debugs with would make every disagreement unattributable."""
    knowledge.record(tmp_path, cell="zimmy", kind="lesson", text="A finding about the gate.", root_cause="none", tags=("t",))
    through_tool, _ = _server(tmp_path).call("recall", {"query": "gate"})
    direct = recall.search(recall.build(tmp_path), "gate", cell="zimmy").render()
    assert through_tool == direct
