"""The cross-project run history."""

from __future__ import annotations

from pathlib import Path

from watermill import ledger


def _summary(**overrides) -> dict:
    base = {
        "run_id": "20260826-030000",
        "project": "demo",
        "started_at": "2026-08-26T03:00:00+00:00",
        "ended_at": "2026-08-26T04:00:00+00:00",
        "refused": False,
        "supervised": False,
        "halt_reason": "queue exhausted",
        "counts": {"attempted": 4, "completed": 3, "failed": 1, "escalated": 0},
        "spend_cents": 420,
        "under_counted": False,
    }
    base.update(overrides)
    return base


def test_a_run_round_trips(tmp_path: Path):
    ledger.append(tmp_path, ledger.Entry.from_summary(_summary(), tmp_path / "logs"))
    rows = ledger.read(tmp_path)
    assert len(rows) == 1
    assert rows[0]["project"] == "demo"
    assert rows[0]["completed"] == 3
    assert rows[0]["recorded_at"]


def test_appends_never_overwrite(tmp_path: Path):
    """Append-only: a correction is a new line, not an edit to an old one."""
    for run_id in ("a", "b", "c"):
        ledger.append(
            tmp_path,
            ledger.Entry.from_summary(_summary(run_id=run_id), tmp_path / run_id),
        )
    assert [r["run_id"] for r in ledger.read(tmp_path)] == ["a", "b", "c"]


def test_filters_by_project(tmp_path: Path):
    ledger.append(tmp_path, ledger.Entry.from_summary(_summary(project="a"), tmp_path))
    ledger.append(tmp_path, ledger.Entry.from_summary(_summary(project="b"), tmp_path))
    assert [r["project"] for r in ledger.read(tmp_path, project="a")] == ["a"]


def test_limit_returns_the_most_recent(tmp_path: Path):
    for run_id in ("a", "b", "c"):
        ledger.append(
            tmp_path, ledger.Entry.from_summary(_summary(run_id=run_id), tmp_path)
        )
    assert [r["run_id"] for r in ledger.read(tmp_path, limit=2)] == ["b", "c"]


def test_a_corrupt_line_does_not_make_the_rest_unreadable(tmp_path: Path):
    """One line lost to a power cut must not cost the other ninety-nine."""
    ledger.append(tmp_path, ledger.Entry.from_summary(_summary(run_id="a"), tmp_path))
    path = tmp_path / ledger.LEDGER_FILENAME
    with path.open("a") as handle:
        handle.write('{"run_id": "b", trunca\n')
    ledger.append(tmp_path, ledger.Entry.from_summary(_summary(run_id="c"), tmp_path))

    assert [r["run_id"] for r in ledger.read(tmp_path)] == ["a", "c"]


def test_an_absent_ledger_is_an_empty_history_not_an_error(tmp_path: Path):
    assert ledger.read(tmp_path) == []


# -- stats -----------------------------------------------------------------


def test_stats_exclude_refused_runs_from_the_rates():
    """A refused run attempted nothing, so counting it drags every rate down."""
    rows = [
        _flat(_summary(refused=True, counts={"attempted": 0, "completed": 0,
                                             "failed": 0, "escalated": 0},
                       spend_cents=0)),
        _flat(_summary()),
    ]
    stats = ledger.stats(rows)
    assert stats["runs"] == 2
    assert stats["runs_refused"] == 1
    assert stats["attempted"] == 4
    assert stats["keep_rate"] == 0.75


def test_stats_report_cost_per_kept_task():
    """The number that decides whether this is worth running at all."""
    stats = ledger.stats([_flat(_summary())])
    assert stats["cents_per_kept_task"] == 140


def test_stats_on_an_empty_history_report_none_rather_than_zero():
    """Zero percent kept and no runs at all are different facts."""
    stats = ledger.stats([])
    assert stats["keep_rate"] is None
    assert stats["cents_per_kept_task"] is None


def _flat(summary: dict) -> dict:
    counts = summary.pop("counts")
    return {**summary, **counts}
