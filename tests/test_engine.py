"""The run loop, driven against a real git repository with stub agents.

Every test here asserts on what reached the *repository*, not on what the
orchestrator recorded about itself. That is the whole thesis of the design: the
agent's report is not evidence, and neither is the engine's. The commit log is.

The stub agent covers each behaviour the engine has to survive -- a clean
success, an uncommitted mess, a commit that forgets the task id, a change to a
fenced path, a change that breaks the gate, an escalation, a hang, a crash, and
a run that reports no cost.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from watermill.caps import Caps
from watermill.engine import COMPLETED, ESCALATED, FAILED, Engine


def _log(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _tree_clean(repo: Path) -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    )
    return not out.stdout.strip()


def _queue_status(repo: Path, task_id: str) -> str:
    import json

    rows = json.loads((repo / "queue.json").read_text())
    return next(r["status"] for r in rows if r["id"] == task_id)


def _queue_comments(repo: Path, task_id: str) -> list[str]:
    import json

    rows = json.loads((repo / "queue.json").read_text())
    row = next(r for r in rows if r["id"] == task_id)
    return list(row.get("comments", []))


@pytest.fixture
def engine_for(project_for, contract_for, stub_agent_command, tmp_path):
    def _make(contract=None, caps=None, **kwargs):
        return Engine(
            project_for,
            contract or contract_for(),
            caps or Caps.resolve(None, {"max_spend_cents": 10_000}),
            tmp_path / "logs" / "run-1",
            agent_command=stub_agent_command,
            skip_gate=False,
            skip_backup=True,
            **kwargs,
        )

    return _make


# -- the happy path --------------------------------------------------------


def test_a_clean_task_is_committed_and_closed(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1", "title": "add a feature"})
    stub_env("succeed", STUB_TASK_ID="t-1")

    state = engine_for().run()

    assert state.tally.completed == 1
    assert state.tasks[0].outcome == COMPLETED
    assert any("t-1" in line for line in _log(fake_project))
    assert _queue_status(fake_project, "t-1") == "closed"
    assert _tree_clean(fake_project)


def test_kept_work_records_the_run_against_the_task(
    fake_project, set_tasks, stub_env, engine_for
):
    """A closed task has to say what closed it.

    Every discard left a comment explaining itself and every success left
    nothing, so the queue held a complete record of the work this factory threw
    away and no record of the work it kept. The commit existed only in the
    ledger, which is in another repository the project cannot see.
    """
    set_tasks({"id": "t-1", "title": "add a feature"})
    stub_env("succeed", STUB_TASK_ID="t-1")

    state = engine_for().run()

    comments = _queue_comments(fake_project, "t-1")
    assert comments, "a kept task left no record of the run that kept it"
    note = comments[-1]
    assert state.run_id in note
    # The commit itself, not just a claim that there was one -- the point of
    # the record is that somebody can go and look at what landed.
    assert any(line.split()[0] in note for line in _log(fake_project)[:1])
    assert state.anomalies == []


def test_a_project_with_no_comment_command_is_not_an_anomaly(
    fake_project, set_tasks, stub_env, engine_for, contract_for
):
    """Silence a contract never promised is not a failure to keep a promise.

    `WorkQueue.comment` returns False both when the project declared no comment
    command and when a declared one failed. Treating the first as an anomaly
    would put a spurious line in the report of every project that tracks work
    in something without comments.
    """
    contract = contract_for(queue={"comment": None})
    set_tasks({"id": "t-1", "title": "add a feature"})
    stub_env("succeed", STUB_TASK_ID="t-1")

    state = engine_for(contract=contract).run()

    assert state.tally.completed == 1
    assert state.anomalies == []


def test_the_run_stops_when_the_queue_empties(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1"}, {"id": "t-2"})
    stub_env("succeed", STUB_TASK_ID="t-1")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 99})

    state = engine_for(caps=caps).run()

    # The stub commits the same id both times; both still land and close.
    assert state.halt_reason == "queue exhausted"
    assert state.tally.attempted == 2


# -- the verifications that discard work -----------------------------------


def test_uncommitted_work_is_discarded(fake_project, set_tasks, stub_env, engine_for):
    set_tasks({"id": "t-1"})
    stub_env("dirty")

    state = engine_for().run()

    assert state.tasks[0].outcome == FAILED
    assert "uncommitted" in state.tasks[0].reason
    assert _tree_clean(fake_project)
    assert not (fake_project / "feature.txt").exists()


def test_a_commit_that_does_not_name_the_task_is_discarded(
    fake_project, set_tasks, stub_env, engine_for
):
    """Traceability is a hard requirement, not a nicety.

    A commit nobody can attribute to a task is one nobody can revert with
    confidence in the morning, which is the routine the whole direct-to-branch
    argument rests on.
    """
    set_tasks({"id": "t-1"})
    stub_env("no_task_id")
    before = _log(fake_project)

    state = engine_for().run()

    assert state.tasks[0].outcome == FAILED
    assert "does not name t-1" in state.tasks[0].reason
    assert _log(fake_project) == before


def test_a_fenced_path_discards_the_work(fake_project, set_tasks, stub_env, engine_for):
    """The fence is checked against the diff, not trusted to the prompt."""
    set_tasks({"id": "t-1"})
    stub_env("fenced", STUB_TASK_ID="t-1")
    before = _log(fake_project)

    state = engine_for().run()

    assert state.tasks[0].outcome == FAILED
    assert "PROTECTED.md" in state.tasks[0].reason
    assert _log(fake_project) == before
    assert (fake_project / "PROTECTED.md").read_text() == "do not touch\n"


def test_a_change_that_breaks_the_gate_is_discarded(
    fake_project, set_tasks, stub_env, engine_for
):
    """The agent exited zero and committed. The gate is what decides."""
    set_tasks({"id": "t-1"})
    stub_env("break_gate", STUB_TASK_ID="t-1")
    before = _log(fake_project)

    state = engine_for().run()

    assert state.tasks[0].outcome == FAILED
    assert "gate failed" in state.tasks[0].reason
    assert _log(fake_project) == before
    assert not (fake_project / "BROKEN").exists()


def test_an_agent_that_did_nothing_is_a_failure(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1"})
    stub_env("nothing")

    state = engine_for().run()

    assert state.tasks[0].outcome == FAILED
    assert "did nothing" in state.tasks[0].reason


def test_a_crashed_agent_is_a_failure_and_reports_no_cost(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1"})
    stub_env("crash")

    state = engine_for().run()

    assert state.tasks[0].outcome == FAILED
    assert state.tasks[0].cost_cents is None
    assert state.tally.unmetered == 1


def test_a_discarded_task_is_released_back_to_the_queue(
    fake_project, set_tasks, stub_env, engine_for
):
    """A claimed task is absent from the queue, so a failure must hand it back."""
    set_tasks({"id": "t-1"})
    stub_env("break_gate", STUB_TASK_ID="t-1")

    engine_for().run()

    assert _queue_status(fake_project, "t-1") == "open"


def test_a_failed_task_is_not_retried_in_the_same_run(
    fake_project, set_tasks, stub_env, engine_for
):
    """Releasing a claim puts the task straight back at the top of the queue.

    Without the skip, the loop retries one bad task until the failure cap halts
    it, while workable tasks sit untouched.
    """
    set_tasks({"id": "t-1"})
    stub_env("break_gate", STUB_TASK_ID="t-1")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 99})

    state = engine_for(caps=caps).run()

    assert state.tally.attempted == 1
    assert state.halt_reason == "queue exhausted"


# -- escalation ------------------------------------------------------------


def test_an_escalation_is_neither_a_success_nor_a_failure(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1"})
    stub_env("escalate")

    state = engine_for().run()

    assert state.tasks[0].outcome == ESCALATED
    assert state.tally.completed == 0
    assert state.tally.failed == 0
    assert state.tally.consecutive_failures == 0
    assert "two behaviours" in state.tasks[0].note


def test_an_escalation_releases_the_task_and_keeps_going(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1"}, {"id": "t-2"})
    stub_env("escalate")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 99})

    state = engine_for(caps=caps).run()

    assert state.tally.escalated == 2
    assert _queue_status(fake_project, "t-1") == "open"
    assert state.halt_reason == "queue exhausted"


# -- caps in the loop ------------------------------------------------------


def test_the_task_cap_stops_the_run(fake_project, set_tasks, stub_env, engine_for):
    set_tasks({"id": "t-1"}, {"id": "t-2"}, {"id": "t-3"})
    stub_env("succeed", STUB_TASK_ID="t-1")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 2})

    state = engine_for(caps=caps).run()

    assert state.tally.attempted == 2
    assert "task cap" in state.halt_reason


def test_an_escalation_storm_is_bounded_by_the_attempt_cap(
    fake_project, set_tasks, stub_env, engine_for
):
    """The 48-escalation runaway, end to end.

    Every task escalates, so nothing completes and nothing fails. Only a cap
    counting *attempts* stops this.
    """
    set_tasks(*[{"id": f"t-{n}"} for n in range(1, 11)])
    stub_env("escalate")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 3})

    state = engine_for(caps=caps).run()

    assert state.tally.escalated == 3
    assert "task cap" in state.halt_reason


def test_the_spend_cap_stops_the_run(fake_project, set_tasks, stub_env, engine_for):
    set_tasks(*[{"id": f"t-{n}"} for n in range(1, 6)])
    stub_env("succeed", STUB_TASK_ID="t-1", STUB_COST="0.60")
    caps = Caps.resolve(None, {"max_spend_cents": 100, "max_tasks": 99})

    state = engine_for(caps=caps).run()

    assert "spend cap" in state.halt_reason
    assert state.tally.spend_cents == 120  # reactive: overshoots by one task


def test_a_meter_that_stops_counting_halts_the_run(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks(*[{"id": f"t-{n}"} for n in range(1, 8)])
    stub_env("succeed", STUB_TASK_ID="t-1", STUB_NO_COST="1")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 99,
                               "max_unmetered_tasks": 3})

    state = engine_for(caps=caps).run()

    assert "meter stopped" in state.halt_reason
    assert state.to_dict()["under_counted"] is True


def test_consecutive_failures_halt_the_run(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks(*[{"id": f"t-{n}"} for n in range(1, 8)])
    stub_env("break_gate", STUB_TASK_ID="t-1")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000, "max_tasks": 99,
                               "max_consecutive_failures": 2})

    state = engine_for(caps=caps).run()

    assert "failure cap" in state.halt_reason
    assert state.tally.failed == 2


def test_a_hung_task_is_killed_at_the_timeout(
    fake_project, set_tasks, stub_env, engine_for
):
    set_tasks({"id": "t-1"})
    stub_env("hang")
    caps = Caps.resolve(None, {"max_spend_cents": 10_000,
                               "task_timeout_minutes": 2 / 60})

    state = engine_for(caps=caps).run()

    assert state.tasks[0].outcome == FAILED
    assert "timeout" in state.tasks[0].reason
    assert any("timeout" in a for a in state.anomalies)


# -- artifacts -------------------------------------------------------------


def test_a_run_writes_a_summary_even_when_every_task_failed(
    fake_project, set_tasks, stub_env, engine_for, tmp_path
):
    set_tasks({"id": "t-1"})
    stub_env("break_gate", STUB_TASK_ID="t-1")

    engine_for().run()

    summary = tmp_path / "logs" / "run-1" / "summary.json"
    assert summary.is_file()
    assert '"failed": 1' in summary.read_text()


def test_the_prompt_is_written_for_the_morning(
    fake_project, set_tasks, stub_env, engine_for, tmp_path
):
    """A task that went wrong is diagnosed from what it was actually asked."""
    set_tasks({"id": "t-1", "spec": "Rename the widget."})
    stub_env("succeed", STUB_TASK_ID="t-1")

    engine_for().run()

    prompt = (tmp_path / "logs" / "run-1" / "prompts" / "t-1.txt").read_text()
    assert "Rename the widget." in prompt
    assert "PROTECTED.md" in prompt  # the fence is stated as well as enforced


# -- the context graph, wired to a run -------------------------------------


def test_recall_is_not_wired_unless_the_run_asks_for_it(
    fake_project, set_tasks, stub_env, engine_for, tmp_path
):
    """Off by default. The seam has never met a real agent, and a default that
    changes the command every task is sent is not the place to find that out."""
    set_tasks({"id": "t-1", "title": "add a feature"})
    stub_env("succeed", STUB_TASK_ID="t-1")

    engine_for().run()

    prompt = (tmp_path / "logs" / "run-1" / "prompts" / "t-1.txt").read_text()
    assert "recall" not in prompt
    assert not (tmp_path / "logs" / "run-1" / "mcp").exists()


def test_recall_wires_the_tool_without_touching_the_project(
    fake_project, set_tasks, stub_env, engine_for, tmp_path
):
    """The config file goes in the run's log directory, never in the target.

    A file dropped in the project shows up in `git status`, and a task that
    leaves the tree dirty is discarded -- so wiring a tool would have failed
    the task it was meant to help.
    """
    set_tasks({"id": "t-1", "title": "add a feature"})
    stub_env("succeed", STUB_TASK_ID="t-1")

    state = engine_for(recall=True).run()

    assert [t.outcome for t in state.tasks] == [COMPLETED]
    assert _tree_clean(fake_project)
    config = tmp_path / "logs" / "run-1" / "mcp" / "t-1.json"
    assert config.is_file()
    assert not (fake_project / ".mcp.json").exists()

    document = json.loads(config.read_text())
    args = document["mcpServers"]["watermill"]["args"]
    assert args[1:3] == ["mcp", "--root"]
    assert "--cell" in args and "target" in args
    assert "t-1" in args, "the task is stamped by the engine, not claimed by the agent"


def test_a_wired_run_tells_the_agent_the_tool_exists(
    fake_project, set_tasks, stub_env, engine_for, tmp_path
):
    set_tasks({"id": "t-1", "title": "add a feature"})
    stub_env("succeed", STUB_TASK_ID="t-1")

    engine_for(recall=True).run()

    prompt = (tmp_path / "logs" / "run-1" / "prompts" / "t-1.txt").read_text()
    assert "`recall` tool" in prompt
    assert "propose" in prompt
