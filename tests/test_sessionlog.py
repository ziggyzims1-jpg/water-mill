"""Transcripts to agents.jsonl: metadata only, deduplicated streaming, linked crew."""

from __future__ import annotations

import json
from pathlib import Path

from watermill import agentlog, cli, sessionlog

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"
SESSION = "11111111-aaaa-bbbb-cccc-222222222222"
CANARY = "CANARY-PRIVATE-TEXT"

CREW = [
    agentlog.make_record(
        key="crew:zimmy-life-tracker-qyz", agent_kind="mill-crew", source="handoff",
        project="zimmy-life-tracker", subject="zimmy-life-tracker-qyz", outcome="landed",
        detail={"pr_number": 218},
    )
]


def _by_key(records):
    return {r["key"]: r for r in records}


def _collect(crew=CREW):
    return _by_key(sessionlog.collect(FIXTURES, crew, {"zimmy-life-tracker": Path("/Users/x/code/demo")}))


def test_a_session_counts_each_streamed_message_once():
    s = _collect()[f"session:{SESSION}"]
    d = s["detail"]
    # msg_1 was written three times with output_tokens 1 -> 5 -> 50: the largest, once.
    assert d["output_tokens"] == 50 + 7
    assert d["input_tokens"] == 2 + 2
    assert d["cache_creation_tokens"] == 100
    assert d["cache_read_tokens"] == 1000 + 2000
    assert (d["message_count"], d["tool_call_count"]) == (2, 2)
    assert d["models"] == ["claude-opus-5"]  # "<synthetic>" is not a model
    assert d["error_count"] == 1
    assert d["interrupted"] is True
    assert d["subagent_count"] == 4
    assert s["agent_kind"] == "session"
    assert s["cost_usd"] == 1.25  # stated by the transcript's own cost-state
    assert s["outcome"] is None and s["title"] is None
    assert s["project"] == s["detail"]["cwd_repo"] == "zimmy-life-tracker"


def test_a_subagent_uses_its_meta_and_never_guesses_outcome():
    r = _collect()[f"session:{SESSION}:agent-aexplore1"]
    assert r["agent_kind"] == "subagent:explore"
    assert r["outcome"] is None and r["cost_usd"] is None
    assert r["duration_seconds"] == 60.0
    assert r["detail"]["tool_call_count"] == 1
    assert r["detail"]["output_tokens"] == 30
    assert len(r["title"]) <= sessionlog.TITLE_CAP


def test_a_subagent_without_meta_is_still_recorded():
    r = _collect()[f"session:{SESSION}:agent-bnometa"]
    assert r["agent_kind"] == "subagent:unknown"
    assert r["title"] is None
    assert r["detail"]["output_tokens"] == 3


def test_a_crew_subagent_links_to_its_bead_without_a_second_outcome():
    recs = _collect()
    mill = recs[f"session:{SESSION}:agent-cmill"]
    assert mill["agent_kind"] == "mill-crew"
    assert mill["source"] == "transcript" and mill["outcome"] is None
    assert mill["detail"]["crew_key"] == "crew:zimmy-life-tracker-qyz"
    assert mill["subject"] == "zimmy-life-tracker-qyz"
    assert mill["project"] == "zimmy-life-tracker"
    assert mill["detail"]["role"] == "millstone"
    assert mill["detail"]["output_tokens"] == 90  # one message, streamed twice
    assert mill["detail"]["interrupted"] is True  # stoppedByUser in the meta
    assert "detail.crew_key" in mill["fields_inferred"]
    # a reviewer named only by its PR number links through the note's pr_number
    sluice = recs[f"session:{SESSION}:agent-dsluice"]
    assert sluice["detail"]["crew_key"] == "crew:zimmy-life-tracker-qyz"


def test_an_unknown_bead_links_nothing():
    mill = _collect(crew=[])[f"session:{SESSION}:agent-cmill"]
    assert mill["detail"]["crew_key"] is None and mill["subject"] is None
    assert mill["agent_kind"] == "mill-crew"


def test_no_transcript_content_reaches_a_record():
    records = sessionlog.collect(FIXTURES, CREW)
    assert len(records) == 5
    # message text, tool input and tool output all carry the canary in the fixtures;
    # the only place it may appear is the dispatcher's own short title label.
    assert CANARY not in json.dumps([{**r, "title": None} for r in records])
    for r in records:
        _assert_no_long_strings(r)


def _assert_no_long_strings(node, path="record"):
    safe = {"record.detail.transcript"}  # a path, not content
    if isinstance(node, dict):
        for k, v in node.items():
            _assert_no_long_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for v in node:
            _assert_no_long_strings(v, path)
    elif isinstance(node, str) and path not in safe:
        assert len(node) <= sessionlog.TITLE_CAP, f"{path} carries {len(node)} chars"


def test_only_a_clipped_description_is_free_text():
    explore = _collect()[f"session:{SESSION}:agent-aexplore1"]
    assert explore["title"].startswith("Find the CANARY-PRIVATE-TEXT handler")
    for r in sessionlog.collect(FIXTURES, CREW):
        for k, v in r["detail"].items():
            assert CANARY not in json.dumps(v), k  # description is title-only


def _sweep(root, *extra):
    return cli.main(["--root", str(root), "agents", "sweep", "--sessions-dir", str(FIXTURES),
                     "--settle-seconds", "0", *extra])


def test_sweep_is_idempotent_and_dry_run_writes_nothing(tmp_path, capsys):
    assert _sweep(tmp_path, "--dry-run") == 0
    assert not (tmp_path / "runs" / "agents.jsonl").exists()
    assert "5 record(s) new" in capsys.readouterr().out
    _sweep(tmp_path)
    first = (tmp_path / "runs" / "agents.jsonl").read_text()
    out = capsys.readouterr().out
    assert "mill-crew" in out and "session" in out
    _sweep(tmp_path)
    assert (tmp_path / "runs" / "agents.jsonl").read_text() == first
    rows = [json.loads(x) for x in first.splitlines()]
    assert CANARY not in json.dumps([{**r, "title": None} for r in rows])


def test_a_missing_sessions_dir_is_reported_not_raised(tmp_path, capsys):
    rc = cli.main(["--root", str(tmp_path), "agents", "sweep", "--sessions-dir",
                   str(tmp_path / "nope")])
    assert rc == 0 and "not found" in capsys.readouterr().out


def test_recently_modified_transcripts_are_left_for_later():
    now = FIXTURES.stat().st_mtime
    assert sessionlog.collect(FIXTURES, settle_seconds=10**9, now=now) == []


def test_repo_name_follows_worktrees_and_registered_checkouts():
    known = {"zimmy-life-tracker": Path("/a/zimmy")}
    assert sessionlog.repo_name("/a/zimmy/frontend", known) == "zimmy-life-tracker"
    assert sessionlog.repo_name("/Users/x/code/cheme-solver/.claude/worktrees/agent-1") \
        == "cheme-solver"
    assert sessionlog.repo_name(None) is None
