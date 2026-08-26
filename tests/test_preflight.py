"""Preflight, and the refusal path that destroyed the previous version of this loop.

The most important test in this file is
`test_a_refused_preflight_touches_nothing`. The shell version of this
orchestrator ran `git clean -fd` on *every* exit path, including a refused
preflight -- the one path where the tree was never the run's to touch -- and
deleted its own untracked script and the run's logs on the first attempt ever
made.

A cleanup routine is the most dangerous code in a program, because it runs on
the paths nobody tested. So this file tests them.
"""

from __future__ import annotations

import pytest

from watermill.caps import Caps
from watermill.engine import Engine
from watermill.errors import PreflightRefusal
from watermill.preflight import preflight


def _caps(**overrides):
    base = {"max_spend_cents": 1000}
    base.update(overrides)
    return Caps.resolve(None, base)


def _preflight(project, contract, tmp_path, **kwargs):
    kwargs.setdefault("agent_binary", "git")  # something that certainly exists
    kwargs.setdefault("log_dir", tmp_path / "logs")
    kwargs.setdefault("skip_backup", True)
    return preflight(project, contract, kwargs.pop("caps", _caps()), **kwargs)


def test_a_healthy_project_passes(project_for, contract_for, set_tasks, tmp_path):
    set_tasks({"id": "t-1"})
    report = _preflight(project_for, contract_for(), tmp_path)
    assert report.ok, report.render()


def test_no_spend_ceiling_refuses(project_for, contract_for, set_tasks, tmp_path):
    """The one cap that fails closed. There is no default and never will be."""
    set_tasks({"id": "t-1"})
    report = _preflight(project_for, contract_for(), tmp_path,
                        caps=Caps.resolve(None, None))
    assert not report.ok
    assert report.refusal.name == "spend ceiling"


def test_an_untracked_file_counts_as_a_dirty_tree(
    fake_project, project_for, contract_for, set_tasks, tmp_path
):
    """Untracked files are precisely what a `git clean` destroys.

    A run that starts with them present is a run that will delete something
    nobody asked it to, on its first failed task.
    """
    set_tasks({"id": "t-1"})
    (fake_project / "notes-i-was-writing.md").write_text("hours of work\n")

    report = _preflight(project_for, contract_for(), tmp_path)

    assert not report.ok
    assert report.refusal.name == "clean tree"
    assert "notes-i-was-writing.md" in report.refusal.detail


def test_an_empty_queue_refuses(project_for, contract_for, set_tasks, tmp_path):
    """Generate tasks; do not raise caps."""
    set_tasks()
    report = _preflight(project_for, contract_for(), tmp_path)
    assert not report.ok
    assert report.refusal.name == "work available"
    assert "do not raise caps" in report.refusal.detail


def test_a_stale_claim_refuses(project_for, contract_for, set_tasks, tmp_path):
    """A claimed task is absent from the queue, so a killed run shrinks it."""
    set_tasks({"id": "t-1", "status": "in_progress"}, {"id": "t-2"})
    report = _preflight(project_for, contract_for(), tmp_path)
    assert not report.ok
    assert report.refusal.name == "stale claims"
    assert "t-1" in report.refusal.detail


def test_a_production_marker_refuses(
    project_for, contract_for, set_tasks, tmp_path, monkeypatch
):
    set_tasks({"id": "t-1"})
    monkeypatch.setenv("FLASK_ENV", "production")
    report = _preflight(project_for, contract_for(), tmp_path)
    assert not report.ok
    assert report.refusal.name == "not production"


def test_a_contract_can_add_its_own_production_marker(
    project_for, contract_for, set_tasks, tmp_path, monkeypatch
):
    set_tasks({"id": "t-1"})
    monkeypatch.setenv("DEPLOY_TARGET", "pi")
    contract = contract_for(environment={"forbid_env": {"DEPLOY_TARGET": "pi"}})
    report = _preflight(project_for, contract, tmp_path)
    assert not report.ok
    assert report.refusal.name == "not production"


def test_a_remote_database_url_refuses(
    project_for, contract_for, set_tasks, tmp_path, monkeypatch
):
    set_tasks({"id": "t-1"})
    monkeypatch.setenv("DATABASE_URL", "postgres://user@db.example.com/prod")
    report = _preflight(project_for, contract_for(), tmp_path)
    assert not report.ok
    assert "DATABASE_URL" in report.refusal.detail


def test_a_local_database_url_is_fine(
    project_for, contract_for, set_tasks, tmp_path, monkeypatch
):
    set_tasks({"id": "t-1"})
    monkeypatch.setenv("DATABASE_URL", "sqlite:///data/app.db")
    assert _preflight(project_for, contract_for(), tmp_path).ok


def test_a_failing_baseline_gate_refuses(
    fake_project, project_for, contract_for, set_tasks, tmp_path
):
    """A run that begins on a red baseline cannot attribute its own damage."""
    set_tasks({"id": "t-1"})
    (fake_project / "BROKEN").write_text("1")
    import subprocess

    subprocess.run(["git", "add", "-A"], cwd=fake_project, check=True)
    subprocess.run(["git", "commit", "-m", "break it"], cwd=fake_project,
                   check=True, stdout=subprocess.DEVNULL)

    report = _preflight(project_for, contract_for(), tmp_path, skip_gate=False)

    assert not report.ok
    assert report.refusal.name == "baseline gate"


def test_a_missing_backup_check_is_reported_not_hidden(
    project_for, contract_for, set_tasks, tmp_path
):
    """A project that cannot prove it is recoverable is allowed to run and told so."""
    set_tasks({"id": "t-1"})
    report = _preflight(project_for, contract_for(), tmp_path, skip_backup=False)
    check = next(c for c in report.checks if c.name == "verified restore")
    assert check.skipped
    assert "cannot prove it is recoverable" in check.detail


def test_a_failing_backup_check_refuses(
    project_for, contract_for, set_tasks, tmp_path
):
    set_tasks({"id": "t-1"})
    contract = contract_for(commands={"gate": "./gate.sh", "backup_check": "false"})
    report = _preflight(project_for, contract, tmp_path, skip_backup=False)
    assert not report.ok
    assert report.refusal.name == "verified restore"


def test_preflight_stops_at_the_first_refusal(
    fake_project, project_for, contract_for, set_tasks, tmp_path
):
    """Running a six-minute gate to discover the ceiling was unset wastes an evening."""
    set_tasks({"id": "t-1"})
    (fake_project / "stray.txt").write_text("x")

    report = _preflight(project_for, contract_for(), tmp_path,
                        caps=Caps.resolve(None, None))

    assert report.refusal.name == "spend ceiling"
    assert not any(c.name == "baseline gate" for c in report.checks)


# -- the refusal path ------------------------------------------------------


def test_a_refused_preflight_touches_nothing(
    fake_project, project_for, contract_for, set_tasks, stub_agent_command, tmp_path
):
    """The bug that deleted the previous version of this loop.

    Its cleanup ran `git clean -fd` on every exit path including a refused
    preflight, removing the untracked loop script and the run's own logs. Here
    the refusal is caused by an untracked file, and the assertion is that the
    file is still there afterwards -- along with everything else.
    """
    set_tasks({"id": "t-1"})
    precious = fake_project / "untracked-and-precious.md"
    precious.write_text("three hours of notes\n")

    engine = Engine(
        project_for,
        contract_for(),
        _caps(),
        tmp_path / "logs" / "run-1",
        agent_command=stub_agent_command,
        skip_backup=True,
    )
    with pytest.raises(PreflightRefusal):
        engine.run()

    assert precious.read_text() == "three hours of notes\n"
    assert engine.state.refused is True
    assert engine.state.started_work is False


def test_a_refusal_still_writes_a_summary(
    project_for, contract_for, set_tasks, stub_agent_command, tmp_path
):
    """A refused run is a fact worth recording -- a silent one looks like a crash."""
    set_tasks()
    engine = Engine(
        project_for,
        contract_for(),
        _caps(),
        tmp_path / "logs" / "run-1",
        agent_command=stub_agent_command,
        skip_backup=True,
    )
    with pytest.raises(PreflightRefusal):
        engine.run()

    summary = tmp_path / "logs" / "run-1" / "summary.json"
    assert summary.is_file()
    assert '"refused": true' in summary.read_text()
