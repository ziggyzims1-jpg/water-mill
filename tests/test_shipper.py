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
