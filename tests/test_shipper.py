"""Shipping to Loki.

Nothing here reaches the network. The transport is replaced at
`shipper.urllib.request.urlopen`, which is the seam -- the function under test
is not stubbed out, so what is exercised is the payload that would actually have
been sent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from watermill import ledger, shipper, tasklog


def _run(root: Path, project="demo", run_id="r-1", **over):
    summary = {
        "run_id": run_id, "project": project,
        "started_at": "2026-08-26T03:00:00+00:00",
        "ended_at": "2026-08-26T04:00:00+00:00",
        "refused": False, "supervised": False, "halt_reason": "queue exhausted",
        "counts": {"attempted": 2, "completed": 1, "failed": 1, "escalated": 0},
        "spend_cents": 120, "under_counted": False,
        "tasks": [
            {"id": "t-1", "title": "one", "outcome": "completed"},
            {"id": "t-2", "title": "two", "outcome": "failed", "reason": "gate failed"},
        ],
    }
    summary.update(over)
    ledger.append(root, ledger.Entry.from_summary(summary, root / "logs"))
    tasklog.append_run(root, summary, root / "logs")


class Recorder:
    """Stands in for urlopen. Captures the request; never opens a socket."""

    def __init__(self, status=204, raises=None):
        self.status, self.raises, self.calls = status, raises, []

    def __call__(self, request, timeout=None):
        self.calls.append(request)
        if self.raises:
            raise self.raises
        rec = self

        class R:
            status = rec.status
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R()

    @property
    def payload(self):
        return json.loads(self.calls[-1].data.decode())


@pytest.fixture
def send(monkeypatch):
    def _install(**kw):
        rec = Recorder(**kw)
        monkeypatch.setattr(shipper.urllib.request, "urlopen", rec)
        return rec
    return _install


# -- the payload Loki actually accepts -------------------------------------


def test_timestamps_are_strings_not_numbers():
    """Loki answers 400 to a numeric timestamp, which reads from the outside
    like the endpoint being broken rather than like a malformed request."""
    payload = shipper.build_payload([({"job": "watermill"},
                                      {"recorded_at": "2026-08-26T03:00:00+00:00"})])
    stamp = payload["streams"][0]["values"][0][0]
    assert isinstance(stamp, str)
    assert stamp.isdigit()


def test_timestamps_are_nanoseconds():
    ns = shipper.to_nanos("2026-08-26T03:00:00+00:00")
    assert len(ns) == 19


def test_values_are_ascending_within_a_stream():
    """Loki rejects a line older than the newest it holds for that stream, and
    fails the whole push with it -- one stale row would discard a good batch."""
    rows = [{"recorded_at": f"2026-08-26T0{h}:00:00+00:00", "n": h} for h in (5, 1, 3)]
    payload = shipper.build_payload([({"job": "watermill"}, r) for r in rows])
    stamps = [int(v[0]) for v in payload["streams"][0]["values"]]
    assert stamps == sorted(stamps)


def test_an_unparseable_timestamp_does_not_raise():
    assert shipper.to_nanos("not a date").isdigit()
    assert shipper.to_nanos("").isdigit()


def test_rows_with_different_labels_become_different_streams():
    payload = shipper.build_payload([
        ({"job": "w", "project": "a"}, {"recorded_at": "2026-08-26T03:00:00+00:00"}),
        ({"job": "w", "project": "b"}, {"recorded_at": "2026-08-26T03:00:00+00:00"}),
    ])
    assert len(payload["streams"]) == 2


def test_the_line_is_the_whole_row_as_json():
    """The row is queried with `| json` in LogQL, so it has to survive intact."""
    row = {"recorded_at": "2026-08-26T03:00:00+00:00", "run_id": "r-1", "spend_cents": 120}
    payload = shipper.build_payload([({"job": "w"}, row)])
    assert json.loads(payload["streams"][0]["values"][0][1]) == row


# -- cardinality, which is what ruins a Loki install ------------------------


def test_a_per_run_label_is_refused_with_the_reason():
    """One stream per run is the documented way to make Loki unusable."""
    with pytest.raises(shipper.ShipError) as exc:
        shipper.build_payload([({"run_id": "r-1"}, {"recorded_at": ""})])
    assert "stream per row" in str(exc.value)


def test_a_per_task_label_is_refused():
    with pytest.raises(shipper.ShipError):
        shipper.build_payload([({"task_id": "t-1"}, {"recorded_at": ""})])


def test_an_unknown_label_is_refused_rather_than_ignored():
    with pytest.raises(shipper.ShipError):
        shipper.build_payload([({"whatever": "x"}, {"recorded_at": ""})])


def test_the_forbidden_keys_are_all_actually_unique_per_row():
    """A guard listing something low-cardinality would refuse a useful label."""
    assert "project" not in shipper.FORBIDDEN_LABELS
    assert "outcome" not in shipper.FORBIDDEN_LABELS
    assert shipper.FORBIDDEN_LABELS.isdisjoint(shipper.ALLOWED_LABELS)


# -- the high-water mark ----------------------------------------------------


def test_a_successful_ship_sends_runs_and_tasks(tmp_path, send):
    rec = send()
    _run(tmp_path)
    summary = shipper.ship(tmp_path, url="http://loki:3100")
    assert summary["shipped"] == 3          # one run + two tasks
    sources = {s["stream"]["source"] for s in rec.payload["streams"]}
    assert sources == {"run", "task"}


def test_shipping_twice_sends_nothing_the_second_time(tmp_path, send):
    send()
    _run(tmp_path)
    shipper.ship(tmp_path, url="http://loki:3100")
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 0


def test_only_new_lines_are_sent_after_the_first_ship(tmp_path, send):
    send()
    _run(tmp_path, run_id="r-1")
    shipper.ship(tmp_path, url="http://loki:3100")
    send()
    _run(tmp_path, run_id="r-2")
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 3


def test_a_failed_push_does_not_advance_the_mark(tmp_path, send):
    """Otherwise the lines are marked shipped and lost -- there is no retry
    queue, on purpose, because the history is still on disk."""
    send(raises=shipper.urllib.error.URLError("refused"))
    _run(tmp_path)
    with pytest.raises(shipper.ShipError):
        shipper.ship(tmp_path, url="http://loki:3100")
    assert not (tmp_path / shipper.STATE_FILENAME).exists()

    send()
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 3


def test_a_dry_run_sends_nothing_and_records_nothing(tmp_path, send):
    rec = send()
    _run(tmp_path)
    summary = shipper.ship(tmp_path, url="http://loki:3100", dry_run=True)
    assert summary["shipped"] == 3
    assert rec.calls == []
    assert not (tmp_path / shipper.STATE_FILENAME).exists()
    # And the preview did not consume the batch.
    send()
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 3


def test_resend_ignores_the_mark(tmp_path, send):
    send()
    _run(tmp_path)
    shipper.ship(tmp_path, url="http://loki:3100")
    send()
    assert shipper.ship(tmp_path, url="http://loki:3100", resend=True)["shipped"] == 3


def test_an_unreadable_mark_reships_rather_than_skips(tmp_path, send):
    send()
    _run(tmp_path)
    shipper.ship(tmp_path, url="http://loki:3100")
    (tmp_path / shipper.STATE_FILENAME).write_text("{ broken")
    send()
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 3


def test_an_empty_factory_ships_nothing_and_does_not_call_loki(tmp_path, send):
    rec = send()
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 0
    assert rec.calls == []


# -- transport --------------------------------------------------------------


def test_the_push_path_is_appended_once():
    assert shipper.endpoint("http://loki:3100").endswith("/loki/api/v1/push")
    doubled = shipper.endpoint("http://loki:3100/loki/api/v1/push")
    assert doubled.count("/loki/api/v1/push") == 1


def test_no_url_is_refused_with_where_to_put_it(tmp_path, monkeypatch):
    monkeypatch.delenv("LOKI_URL", raising=False)
    _run(tmp_path)
    with pytest.raises(shipper.ShipError) as exc:
        shipper.ship(tmp_path)
    assert "LOKI_URL" in str(exc.value)


def test_credentials_come_from_the_environment(tmp_path, send, monkeypatch):
    """Environment, not the registry -- a token in a repository is one nobody
    re-reads before the day it leaks."""
    rec = send()
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("LOKI_USER", "12345")
    monkeypatch.setenv("LOKI_TOKEN", "secret")
    _run(tmp_path)
    shipper.ship(tmp_path)
    assert rec.calls[-1].get_header("Authorization", "").startswith("Basic ")


def test_no_auth_header_without_a_token(tmp_path, send):
    """A self-hosted Loki usually takes none, so both halves are optional."""
    rec = send()
    _run(tmp_path)
    shipper.ship(tmp_path, url="http://loki:3100")
    assert not rec.calls[-1].get_header("Authorization", "")


def test_an_http_error_becomes_a_ShipError_carrying_the_status(tmp_path, send):
    send(raises=shipper.urllib.error.HTTPError(
        "http://loki:3100", 400, "Bad Request", {}, None))
    _run(tmp_path)
    with pytest.raises(shipper.ShipError) as exc:
        shipper.ship(tmp_path, url="http://loki:3100")
    assert "400" in str(exc.value)


# -- agent records (runs/agents.jsonl) --------------------------------------


import re  # noqa: E402

from watermill import agentlog  # noqa: E402


def _agent(root, key="crew:demo-1", kind="mill-crew", outcome="landed",
           ended_at="2026-09-01T10:00:00+00:00", **over):
    rec = agentlog.make_record(
        key=key, agent_kind=kind, source="handoff", project="demo",
        outcome=outcome, ended_at=ended_at,
        detail={"sluice_rounds": 2, "landed_at": "2026-09-01"},
    )
    rec.update(over)
    path = root / agentlog.AGENTLOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def test_agent_kind_is_bucketed_to_a_closed_set():
    b = shipper.agent_kind_bucket
    assert b("mill-crew") == "mill-crew" and b("session") == "session"
    assert b("subagent:builder") == "subagent" and b("subagent") == "subagent"
    assert b("brand-new-kind") == "other" and b(None) == "other"


def test_an_agent_kind_outside_the_closed_set_is_refused_as_a_label():
    with pytest.raises(shipper.ShipError):
        shipper.build_payload([({"agent_kind": "subagent:builder"}, {"recorded_at": ""})])
    # and a per-record label is still refused
    with pytest.raises(shipper.ShipError):
        shipper.build_payload([({"key": "crew:x"}, {"recorded_at": ""})])


def test_agent_lines_are_filed_at_the_work_end_not_sweep_time():
    row = {"recorded_at": "2026-10-13T00:00:00+00:00",
           "ended_at": "2026-09-01T10:00:00+00:00"}
    out = shipper.build_payload([({"source": "agent"}, row)])
    assert out["streams"][0]["values"][0][0] == shipper.to_nanos("2026-09-01T10:00:00+00:00")
    # a task still uses recorded_at
    out = shipper.build_payload([({"source": "task"}, row)])
    assert out["streams"][0]["values"][0][0] == shipper.to_nanos(row["recorded_at"])


def test_agent_time_falls_back_to_landed_at_then_started_at():
    row = {"recorded_at": "2026-10-13", "ended_at": None,
           "detail": {"landed_at": "2026-09-02"}}
    assert shipper.line_time({"source": "agent"}, row) == "2026-09-02"
    row = {"recorded_at": "2026-10-13", "started_at": "2026-08-30"}
    assert shipper.line_time({"source": "agent"}, row) == "2026-08-30"


def test_agents_ship_with_bucketed_label_and_full_kind_in_the_line(tmp_path, send):
    rec = send()
    _agent(tmp_path, key="s:1", kind="subagent:builder")
    _agent(tmp_path)
    shipper.ship(tmp_path, url="http://loki:3100")
    streams = {s["stream"]["agent_kind"]: s for s in rec.payload["streams"]}
    assert set(streams) == {"mill-crew", "subagent"}
    assert streams["subagent"]["stream"]["source"] == "agent"
    assert json.loads(streams["subagent"]["values"][0][1])["agent_kind"] == "subagent:builder"


def test_a_resweep_does_not_ship_a_work_twice(tmp_path, send):
    send()
    _agent(tmp_path)
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 1
    # same content, and a changed-content re-append of the same key
    _agent(tmp_path)
    _agent(tmp_path, title="renamed")
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 0


def test_unlanded_then_landed_ships_once_when_it_lands(tmp_path, send):
    rec = send()
    _agent(tmp_path, outcome="unlanded", ended_at=None)
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 0
    assert not rec.calls
    _agent(tmp_path, outcome="landed")
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 1
    line = json.loads(rec.payload["streams"][0]["values"][0][1])
    assert line["outcome"] == "landed"
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 0


def test_an_old_state_file_without_agents_still_works(tmp_path, send):
    send()
    _run(tmp_path)
    shipper.ship(tmp_path, url="http://loki:3100")
    state = shipper.read_state(tmp_path)
    state.pop("agents", None)
    shipper.write_state(tmp_path, state)
    _agent(tmp_path)
    summary = shipper.ship(tmp_path, url="http://loki:3100")
    assert summary["shipped"] == 1          # the run/task marks were kept


def test_a_failed_push_does_not_mark_agents_shipped(tmp_path, send):
    send(status=500)
    _agent(tmp_path)
    with pytest.raises(shipper.ShipError):
        shipper.ship(tmp_path, url="http://loki:3100")
    send()
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 1


def test_dry_run_shows_agent_payload_and_records_nothing(tmp_path, send):
    rec = send()
    _agent(tmp_path)
    summary = shipper.ship(tmp_path, url="http://loki:3100", dry_run=True)
    assert summary["payload"]["streams"][0]["stream"]["source"] == "agent"
    assert not rec.calls and shipper.read_state(tmp_path) == {}


DASHBOARD = Path(__file__).resolve().parent.parent / "docs/grafana/agent-performance.json"


def _exprs():
    data = json.loads(DASHBOARD.read_text())
    return [t["expr"] for panel in data["panels"] for t in panel["targets"]]


#: Every stream label an agent line carries, read off a real payload rather than
#: ALLOWED_LABELS: `outcome` and `env` are allowed labels but no agent stream has
#: them, so a selector on them would silently match nothing.
_MATCHER = r"(\w+)\s*(=~|!~|!=|=)\s*\""


def _agent_stream_labels(tmp_path):
    _agent(tmp_path)
    payload = shipper.ship(tmp_path, dry_run=True)["payload"]
    return {k for s in payload["streams"] for k in s["stream"]}


def _check_dashboard_labels(exprs, emitted):
    for expr in exprs:
        selectors = re.findall(r"\{([^{}]*)\}", expr)
        assert selectors, expr
        for selector in selectors:
            matchers = re.findall(_MATCHER, selector)
            # every comma-separated matcher was parsed, whatever its operator
            assert len(matchers) == len([m for m in selector.split(",") if m.strip()]), selector
            assert {k for k, _ in matchers} <= emitted, (expr, matchers)
            assert ("source", "=") in matchers, expr
        for group in re.findall(r"\b(?:by|without)\s*\(([^)]*)\)", expr):
            for key in (k.strip() for k in group.split(",") if k.strip()):
                assert key in emitted, (expr, key)


def test_dashboard_queries_use_only_labels_the_shipper_emits(tmp_path):
    emitted = _agent_stream_labels(tmp_path)
    assert emitted == {"job", "project", "source", "agent_kind"}
    exprs = _exprs()
    assert exprs
    _check_dashboard_labels(exprs, emitted)
    for expr in exprs:
        assert 'source="agent"' in expr


@pytest.mark.parametrize("bad", [
    '{job="watermill", source="agent", bogus!="x"}[7d]',     # negative matcher
    '{job="watermill", source="agent", outcome="landed"}[7d]',  # allowed, never on agents
    'sum by(bogus) (count_over_time({job="watermill", source="agent"}[7d]))',
    'sum without (bogus) (count_over_time({job="watermill", source="agent"}[7d]))',
])
def test_the_dashboard_label_check_catches_an_unknown_label(tmp_path, bad):
    with pytest.raises(AssertionError):
        _check_dashboard_labels([bad], _agent_stream_labels(tmp_path))


def test_dashboard_label_values_are_in_the_closed_set():
    for expr in _exprs():
        for value in re.findall(r'agent_kind="([^"]+)"', expr):
            assert value in shipper.AGENT_KIND_BUCKETS


def test_dashboard_panels_say_what_they_exclude():
    data = json.loads(DASHBOARD.read_text())
    assert data["templating"]["list"][0]["type"] == "datasource"
    for panel in data["panels"]:
        assert panel["datasource"]["uid"] == "${datasource}"
        if any(w in panel["title"] for w in ("duration", "Cost", "approval", "Records")):
            assert "EXCLUDES" in panel["description"], panel["title"]


def test_the_dashboard_does_not_call_a_second_metric_keep_rate():
    # docs/OBSERVABILITY.md defines keep rate (completed / all tasks); one name,
    # one meaning.
    for panel in json.loads(DASHBOARD.read_text())["panels"]:
        assert "keep rate" not in panel["title"].lower()
        for target in panel["targets"]:
            assert "keep" not in target["legendFormat"].lower()


def test_unwrapped_crew_aggregations_are_grouped_not_one_series_per_bead():
    # `| json` makes every record its own label set; an unwrapped range
    # aggregation with no `by` returns one series per bead, not a mean.
    for expr in _exprs():
        for fn in ("avg_over_time", "max_over_time", "quantile_over_time"):
            for tail in expr.split(fn + "(")[1:]:
                assert re.search(r"\[7d\]\)\s*by\s*\(", tail), expr


def test_a_line_older_than_its_stream_already_holds_is_filed_at_the_floor(tmp_path, send):
    rec = send()
    _agent(tmp_path, key="crew:new", ended_at="2026-09-10T00:00:00+00:00")
    shipper.ship(tmp_path, url="http://loki:3100")
    # a bead that ended earlier lands later, into the same stream
    _agent(tmp_path, key="crew:old", ended_at="2026-09-01T00:00:00+00:00")
    shipper.ship(tmp_path, url="http://loki:3100")
    stamp, line = rec.payload["streams"][0]["values"][0]
    assert int(stamp) == int(shipper.to_nanos("2026-09-10T00:00:00+00:00"))
    assert json.loads(line)["ended_at"] == "2026-09-01T00:00:00+00:00"   # truth kept in the line
    # a fresh stream is not floored by another stream's mark
    _agent(tmp_path, key="s:1", kind="session", ended_at="2026-08-01T00:00:00+00:00")
    shipper.ship(tmp_path, url="http://loki:3100")
    assert rec.payload["streams"][0]["values"][0][0] == shipper.to_nanos("2026-08-01T00:00:00+00:00")


def test_a_malformed_agents_or_newest_mark_does_not_crash(tmp_path, send):
    send()
    _agent(tmp_path)
    (tmp_path / shipper.STATE_FILENAME).write_text('{"agents": 3, "newest": "x"}')
    assert shipper.ship(tmp_path, url="http://loki:3100")["shipped"] == 1
