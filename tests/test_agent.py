"""The prompt. It is the product, so it is what gets asserted on.

`build_prompt` is pure -- a task, a contract and a spec in, the exact text out
-- so every line the agent reads is testable without a clock, a database or a
subprocess.
"""

from __future__ import annotations

from watermill.agent import build_prompt
from watermill.contract import Contract
from watermill.queue import Task

TASK = Task(id="t-1", title="Rename the widget", type="task", raw={})


def _contract(**overrides) -> Contract:
    raw = {
        "version": 1,
        "name": "demo",
        "commands": {"gate": "make verify"},
        "git": {"base_branch": "main"},
    }
    raw.update(overrides)
    return Contract.parse(raw)


def test_a_project_with_no_notes_gets_no_notes_heading():
    """Not "no notes recorded". A heading with nothing under it invites the
    agent to wonder what it is missing, and every line is paid for per task."""
    prompt = build_prompt(TASK, _contract(), "t-1: do the thing")
    assert "already cost someone" not in prompt


def test_every_note_reaches_the_prompt():
    contract = _contract(notes=["Fixtures live in tests/fixtures.", "Stop the dev server first."])
    prompt = build_prompt(TASK, contract, "t-1: do the thing")
    assert "Fixtures live in tests/fixtures." in prompt
    assert "Stop the dev server first." in prompt


def test_notes_are_marked_as_advice_rather_than_as_rules():
    """The distinction the whole field rests on: everything else in a contract
    is a mechanism checked afterwards, and this one is not."""
    prompt = build_prompt(TASK, _contract(notes=["a lesson"]), "t-1: x")
    assert "advice, not rules" in prompt


def test_a_note_cannot_displace_the_task():
    """Where a note and the task disagree, the task wins -- otherwise stale
    advice quietly overrides the thing the run was started to do."""
    prompt = build_prompt(TASK, _contract(notes=["never touch the parser"]), "t-1: x")
    # Normalised: the sentence matters, the column it wraps at does not.
    assert "the task wins" in " ".join(prompt.split())


def test_the_fence_is_still_stated_when_notes_exist():
    contract = _contract(fence={"paths": ["db.py"]}, notes=["a lesson"])
    prompt = build_prompt(TASK, contract, "t-1: x")
    assert "db.py" in prompt
    assert "a lesson" in prompt


def test_the_spec_is_included_verbatim():
    prompt = build_prompt(TASK, _contract(), "t-1: Rename it\n\nFull spec here.")
    assert "Full spec here." in prompt


def test_a_spec_that_never_names_the_task_gets_the_id_prepended():
    """The commit must name the id, and an agent cannot use what it never saw."""
    prompt = build_prompt(TASK, _contract(), "Do the thing.")
    assert "Task id: t-1" in prompt


def test_the_gate_command_is_named():
    prompt = build_prompt(TASK, _contract(commands={"gate": "./run-ci.sh"}), "t-1: x")
    assert "./run-ci.sh" in prompt


def test_the_agent_is_told_to_sign_off_with_a_handoff():
    """Every agent ends with a handoff -- also, and especially, when stuck."""
    prompt = build_prompt(TASK, _contract())
    assert "\nHANDOFF\n" in prompt
    assert "did not\nwork" in prompt
    tail = prompt.split("HANDOFF", 1)[1]
    assert "stuck" in prompt.split("## Before you sign off", 1)[1]
    assert "Name files and functions" in tail
