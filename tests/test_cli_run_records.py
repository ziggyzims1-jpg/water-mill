"""What one real run leaves behind on disk.

The unit suites cover the ledger and the task log in isolation. This covers the
line that connects them to a run -- which is the one that gets forgotten,
because forgetting it breaks nothing an assertion about either module would
notice. The run still works; the history simply stops accumulating, silently,
which is the failure mode both files exist to prevent.

Driven through `main()` against a real git repository and a real stub agent, so
what is asserted is the file on disk rather than a call that was made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from watermill import ledger, tasklog
from watermill.cli import main


@pytest.fixture
def factory(tmp_path, fake_project, contract_for, stub_agent_command):
    """A factory root with one registered project, contract vendored."""
    root = tmp_path / "factory"
    root.mkdir()

    import yaml

    queue = contract_for().queue
    (root / "demo.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "name": "demo",
                "commands": {"gate": "./gate.sh"},
                "git": {"base_branch": "main", "target": "direct"},
                "queue": {
                    "kind": "command",
                    "ready": queue.ready,
                    "stale": queue.stale,
                    "show": queue.show,
                    "claim": queue.claim,
                    "release": queue.release,
                    "close": queue.close,
                    "comment": queue.comment,
                },
                "fence": {"paths": ["PROTECTED.md", "gate.sh"]},
            },
            sort_keys=False,
        )
    )
    (root / "projects.yaml").write_text(
        "version: 1\n"
        "projects:\n"
        f"  - name: demo\n    path: {fake_project}\n    contract: demo.yaml\n"
    )
    return root


def _run(root: Path, agent: str, *extra: str) -> int:
    return main([
        "--root", str(root), "run", "demo",
        "--max-spend", "5", "--max-tasks", "1",
        "--agent", agent, "--skip-backup", *extra,
    ])


def test_a_kept_task_reaches_both_histories(
    factory, fake_project, set_tasks, stub_agent_command, stub_env, capsys
):
    set_tasks({"id": "t-1", "title": "one"})
    stub_env("succeed")

    assert _run(factory, stub_agent_command) == 0
    capsys.readouterr()

    assert len(ledger.read(factory)) == 1

    records = tasklog.read(factory)
    assert [r.outcome["task_id"] for r in records] == ["t-1"]
    assert records[0].outcome["outcome"] == "completed"
    # Honestly absent rather than guessed: nobody has judged this task yet.
    assert records[0].root_cause == ""


def test_a_discarded_task_records_why_it_was_discarded(
    factory, fake_project, set_tasks, stub_agent_command, stub_env, capsys
):
    """The reason is the mechanical one. The root cause is a person's job."""
    set_tasks({"id": "t-2", "title": "two"})
    stub_env("fenced")

    _run(factory, stub_agent_command)
    capsys.readouterr()

    record = tasklog.read(factory)[0]
    assert record.outcome["outcome"] == "failed"
    assert "fenced path" in record.outcome["reason"]
    assert record.outcome["hint"] == "weak-scope"
    assert record.root_cause == ""


def test_annotating_a_recorded_task_makes_it_countable(
    factory, fake_project, set_tasks, stub_agent_command, stub_env, capsys
):
    set_tasks({"id": "t-3", "title": "three"})
    stub_env("fenced")
    _run(factory, stub_agent_command)

    assert main([
        "--root", str(factory), "annotate", "demo", "t-3", "weak-scope",
        "--note", "the spec never mentioned the protected file",
    ]) == 0

    record = tasklog.read(factory)[0]
    assert record.root_cause == "weak-scope"
    assert tasklog.causes(tasklog.read(factory))["by_cause"] == {"weak-scope": 1}

    assert main(["--root", str(factory), "tasks"]) == 0
    out = capsys.readouterr().out
    assert "weak-scope" in out


def test_an_unknown_root_cause_lists_the_real_ones_rather_than_storing_it(
    factory, capsys
):
    assert main(["--root", str(factory), "annotate", "demo", "t-9", "friday"]) == 2
    out = capsys.readouterr().out
    assert "gate-hole" in out
    assert tasklog.read(factory) == []


def test_calibrate_creates_the_projects_record_from_the_template(factory, capsys):
    """Scaffolded per project, because what one repository teaches about
    writing tasks for it does not transfer whole to the next one."""
    template = factory / "docs" / "calibration" / "TEMPLATE.md"
    template.parent.mkdir(parents=True)
    template.write_text("# Calibration - PROJECT_NAME\n")

    assert main(["--root", str(factory), "calibrate", "demo"]) == 0
    capsys.readouterr()

    record = factory / "docs" / "calibration" / "demo.md"
    assert record.is_file()
    assert "# Calibration - demo" in record.read_text()


def test_calibrate_never_overwrites_a_record_that_has_findings_in_it(factory, capsys):
    """The findings are the deliverable. Re-running the scaffolder must not be
    able to erase eight watched tasks."""
    template = factory / "docs" / "calibration" / "TEMPLATE.md"
    template.parent.mkdir(parents=True)
    template.write_text("# Calibration - PROJECT_NAME\n")
    record = factory / "docs" / "calibration" / "demo.md"
    record.write_text("# Calibration - demo\n\nTask 1 failed: vague goal.\n")

    assert main(["--root", str(factory), "calibrate", "demo"]) == 0
    assert "vague goal" in record.read_text()
