"""`agents record` / `whoami`: an agent's own facts, metadata only, one record per run."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from watermill import agentlog, cli, recorded, sessionlog

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"
SESSION = "11111111-aaaa-bbbb-cccc-222222222222"
CANARY = "CANARY-PRIVATE-TEXT"
PROJ = FIXTURES / "-Users-x-code-demo"
SUB = PROJ / SESSION / "subagents"


@pytest.fixture(autouse=True)
def _no_ambient_session(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


def _record(tmp_path, *argv, sessions=FIXTURES):
    out = tmp_path / "out"
    rc = cli.main(["agents", "record", "--sessions-dir", str(sessions), "--project", "demo",
                   "--out-dir", str(out), *argv])
    return rc, out


def _lines(out):
    return [json.loads(x) for p in sorted(out.glob("*.jsonl")) for x in p.read_text().splitlines()]


def test_a_record_carries_flags_and_transcript_numbers(tmp_path, capsys):
    rc, out = _record(tmp_path, "--role", "millstone", "--bead", "demo-qyz", "--pr", "7",
                      "--verdict", "landed", "--sluice-rounds", "2", "--arm", "A",
                      "--transcript", str(SUB / "agent-cmill.jsonl"))
    assert rc == 0
    (r,) = _lines(out)
    assert r["source"] == "recorded" and r["agent_kind"] == "mill-crew"
    assert r["key"] == f"session:{SESSION}:agent-cmill"  # the transcript's own key
    d = r["detail"]
    assert (d["role"], d["bead"], d["pr_number"], d["verdict"], d["sluice_rounds"], d["arm"]) \
        == ("millstone", "demo-qyz", 7, "landed", 2, "A")
    assert d["output_tokens"] == 90 and d["tokens_total"] > 0 and d["transcript_located"]
    assert d["crew_key"] == "crew:demo-qyz" and r["subject"] == "demo-qyz"
    assert r["duration_seconds"] is not None
    assert "tokens_total=" in capsys.readouterr().out


def test_the_record_path_leaks_no_transcript_content(tmp_path, capsys):
    """The 61r canary, on the path that writes into a TRACKED file."""
    for transcript in (SUB / "agent-cmill.jsonl", SUB / "agent-dsluice.jsonl",
                       PROJ / f"{SESSION}.jsonl"):
        rc, out = _record(tmp_path, "--role", "solo", "--bead", "demo-qyz",
                          "--transcript", str(transcript))
        assert rc == 0
    text = "".join(p.read_text() for p in out.glob("*.jsonl"))
    assert text and CANARY not in text
    assert CANARY not in capsys.readouterr().out + capsys.readouterr().err
    for r in _lines(out):
        for k, v in r["detail"].items():
            if isinstance(v, str) and k != "transcript":
                assert len(v) <= sessionlog.TITLE_CAP, k
        assert r["title"] is None  # not even a crew label


def test_flags_are_never_free_text(tmp_path, capsys):
    with pytest.raises(SystemExit):
        _record(tmp_path, "--verdict", CANARY)
    rc, out = _record(tmp_path, "--bead", f"x; {CANARY} \n rm -rf /")
    assert rc == 2 and not out.exists()
    assert "not a bead id" in capsys.readouterr().err


def test_a_tag_search_returns_a_path_and_keeps_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    sess = tmp_path / "sess"
    shutil.copytree(FIXTURES, sess)
    tag = sessionlog.new_tag()
    with (sess / "-Users-x-code-demo" / SESSION / "subagents" / "agent-dsluice.jsonl").open("a") as h:
        h.write(json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:00Z",
                            "message": {"content": [{"type": "tool_result", "content": tag}]}}) + "\n")
    rc, out = _record(tmp_path, "--role", "sluice", "--bead", "demo-qyz", "--run-tag", tag,
                      "--transcript", "auto", sessions=sess)
    # no CLAUDE_CODE_SESSION_ID needed when the tag is unique across the dir
    assert rc == 0, capsys.readouterr().err
    (r,) = _lines(out)
    assert r["key"].endswith("agent-dsluice") and tag not in json.dumps(r)
    assert CANARY not in json.dumps(r)


def _live_tree(tmp_path, *names):
    base = tmp_path / "proj"
    sid = "sess-1"
    (base / "-d").mkdir(parents=True)
    (base / "-d" / f"{sid}.jsonl").write_text(
        (PROJ / f"{SESSION}.jsonl").read_text())
    for n, role in names:
        f = base / "-d" / sid / "subagents" / f"agent-{n}.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text((SUB / "agent-cmill.jsonl").read_text())
        f.with_suffix(".meta.json").write_text(json.dumps({"agentType": role}))
    return base, sid


def test_self_location_solo_crew_and_ambiguity(tmp_path):
    base, sid = _live_tree(tmp_path, ("a1", "millstone"), ("b2", "sluice"))
    solo = sessionlog.locate_own(base, session_id=sid, role="solo")
    assert solo.name == "sess-1.jsonl"  # the session's CLAUDE_CODE_SESSION_ID names it
    mill = sessionlog.locate_own(base, session_id=sid, role="millstone")
    assert mill.name == "agent-a1.jsonl"  # the one live file of that role
    base2, sid = _live_tree(tmp_path / "two", ("a1", "millstone"), ("a2", "millstone"))
    with pytest.raises(sessionlog.LocateError, match="--run-tag"):
        sessionlog.locate_own(base2, session_id=sid, role="millstone")
    # a stale sibling is not a candidate
    old = time.time() - 3600
    os.utime(base2 / "-d" / sid / "subagents" / "agent-a2.jsonl", (old, old))
    got = sessionlog.locate_own(base2, session_id=sid, role="millstone")
    assert got.name == "agent-a1.jsonl"
    with pytest.raises(sessionlog.LocateError):
        sessionlog.locate_own(base2, session_id="no-such-session", role="solo")


def test_an_ambiguous_auto_refuses_and_writes_nothing(tmp_path, monkeypatch, capsys):
    base, sid = _live_tree(tmp_path, ("a1", "millstone"), ("a2", "millstone"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)
    rc, out = _record(tmp_path, "--role", "millstone", "--transcript", "auto", sessions=base)
    assert rc == 2 and not out.exists()
    assert "--run-tag" in capsys.readouterr().err


def test_an_unlocatable_transcript_still_records_the_flags(tmp_path, monkeypatch, capsys):
    """A cloud container may have no transcript: the facts are not lost with it."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "nope")
    rc, out = _record(tmp_path, "--role", "solo", "--arm", "B", "--pr", "3",
                      "--transcript", "auto", sessions=tmp_path / "missing")
    assert rc == 0
    (r,) = _lines(out)
    assert r["detail"]["transcript_located"] is False and "tokens_total" not in r["detail"]
    assert r["detail"]["arm"] == "B" and r["key"].startswith("recorded:demo:solo")
    assert "transcript not located" in capsys.readouterr().err


def test_whoami_prints_a_fresh_tag(capsys):
    cli.main(["agents", "whoami"])
    a = capsys.readouterr().out.strip()
    cli.main(["agents", "whoami"])
    assert a.startswith(sessionlog.TAG_PREFIX) and a != capsys.readouterr().out.strip()


def _sweep(root, *extra):
    return cli.main(["--root", str(root), "agents", "sweep", "--sessions-dir", str(FIXTURES),
                     "--settle-seconds", "0", *extra])


@pytest.mark.parametrize("record_first", [True, False])
def test_a_recorded_line_and_the_laptop_transcript_are_one_record(tmp_path, record_first):
    root = tmp_path / "factory"
    (root / "runs").mkdir(parents=True)
    runs = root / "knowledge" / "agent-runs"
    cli.main(["agents", "record", "--sessions-dir", str(FIXTURES), "--project", "demo",
              "--out-dir", str(runs), "--role", "millstone", "--bead", "demo-qyz",
              "--transcript", str(SUB / "agent-cmill.jsonl")])
    if not record_first:
        # the sweep ran first: the transcript line is already in the log
        runs_moved = tmp_path / "held"
        runs.rename(runs_moved)
        _sweep(root)
        runs_moved.rename(runs)
    _sweep(root)
    _sweep(root)  # and idempotent
    rows = [r for r in agentlog.read(root) if r["key"] == f"session:{SESSION}:agent-cmill"]
    assert len(rows) == 1
    assert rows[0]["source"] == "recorded" and rows[0]["detail"]["bead"] == "demo-qyz"
    raw = [r for r in agentlog.read_all(root) if r["key"] == rows[0]["key"]]
    assert sum(r["source"] == "recorded" for r in raw) == 1  # ingested once
    if record_first:
        assert all(r["source"] == "recorded" for r in raw)  # the sweep did not add its own
    assert CANARY not in (root / "runs" / "agents.jsonl").read_text()


def test_recorded_lines_count_in_per_run_stats_once(tmp_path):
    from watermill import agentcompare
    t = agentlog.make_record(key="k1", agent_kind="mill-crew", source="transcript",
                             project="p", outcome=None, detail={"tokens_total": 10})
    r = agentlog.make_record(key="k1", agent_kind="mill-crew", source="recorded",
                             project="p", outcome=None, detail={"tokens_total": 12})
    agentlog.append_new(tmp_path, [t])
    agentlog.append_new(tmp_path, [r])
    metric = next(m for m in agentcompare.METRICS if m.name == "tokens_total")
    pool = agentcompare._collect(agentlog.read(tmp_path), "crew", metric, None, True)
    assert pool["values"] == [12]


def test_the_recorded_directory_is_only_read_for_recorded_lines(tmp_path):
    d = tmp_path / "knowledge" / "agent-runs"
    d.mkdir(parents=True)
    forged = agentlog.make_record(key="x", agent_kind="session", source="handoff",
                                  project="p", outcome="landed")
    (d / "a.jsonl").write_text(json.dumps(forged) + "\nnot json\n")
    assert recorded.read_dir(d) == []
