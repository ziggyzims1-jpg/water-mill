"""The morning report.

`compose` is pure, so every line the operator reads at 7am is asserted here
without a clock, a repository or a subprocess. The report is the entire
interface between a night of unattended work and the person responsible for it,
which makes it worth more test attention than its size suggests.
"""

from __future__ import annotations

from watermill.caps import Caps, Tally
from watermill.engine import COMPLETED, ESCALATED, FAILED, RunState, TaskRecord
from watermill.preflight import CheckResult, PreflightReport
from watermill.report import compose


def _state(**overrides) -> RunState:
    state = RunState(
        run_id="20260826-030000",
        project="demo",
        started_at="2026-08-26T03:00:00+00:00",
        caps=Caps.resolve(None, {"max_spend_cents": 1000}),
    )
    state.halt_reason = "queue exhausted"
    state.base_sha = "abc1234567"
    state.work_branch = "watermill/20260826-030000"
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def test_needs_a_decision_leads():
    """It is the only section that is work; everything below it is a record."""
    state = _state(tasks=[TaskRecord("t-1", "a", ESCALATED, note="which behaviour?")])
    text = compose(state)
    assert text.index("## Needs a decision") < text.index("## Summary")


def test_a_quiet_night_says_so_plainly():
    state = _state(tasks=[TaskRecord("t-1", "a", COMPLETED, commit="abc123 feat")])
    state.tally = Tally()
    state.tally.record_success(50)
    text = compose(state)
    assert "Nothing. Every attempted task either landed" in text


def test_escalations_and_failures_both_appear_in_the_decision_section():
    state = _state(tasks=[
        TaskRecord("t-1", "a", ESCALATED, note="ambiguous spec"),
        TaskRecord("t-2", "b", FAILED, reason="gate failed after the change"),
    ])
    section = compose(state).split("## Summary")[0]
    assert "t-1" in section and "ambiguous spec" in section
    assert "t-2" in section and "gate failed" in section


def test_anomalies_reach_the_decision_section():
    state = _state(anomalies=["could not release t-9"])
    assert "could not release t-9" in compose(state).split("## Summary")[0]


def test_under_counted_spend_is_flagged_rather_than_shown_as_a_total():
    """A run with no meter looks cheap right up until the invoice."""
    state = _state()
    state.tally.record_success(50)
    state.tally.record_success(None)
    text = compose(state)
    assert "under-counted" in text
    assert "1 task(s) reported no cost" in text


def test_a_clean_spend_is_shown_against_the_ceiling():
    state = _state()
    state.tally.record_success(250)
    assert "$2.50 of $10.00" in compose(state)


def test_an_unknown_cost_is_named_rather_than_shown_as_zero():
    state = _state(tasks=[TaskRecord("t-1", "a", FAILED, reason="crashed",
                                     cost_cents=None)])
    assert "unknown" in compose(state)


def test_a_dirty_tree_at_the_end_is_called_out():
    state = _state(tree_clean_at_end=False)
    assert "working tree is not clean" in compose(state)


def test_discarded_work_is_described_as_having_reached_nothing():
    state = _state(tasks=[TaskRecord("t-1", "a", FAILED, reason="fenced path")])
    text = compose(state)
    assert "## Discarded" in text
    assert "Nothing from these reached the repository." in text


def test_the_revert_routine_is_printed_every_time():
    """Reverting has to stay routine, so it is never something to go and look up."""
    assert "git revert" in compose(_state())


def test_a_refused_run_reports_only_the_refusal():
    state = _state(refused=True, halt_reason="preflight refused: clean tree -- x")
    state.preflight = PreflightReport(checks=[
        CheckResult("clean tree", False, "modified: a.py")
    ])
    text = compose(state)
    assert "refused at preflight. Nothing was modified" in text
    assert "## Kept" not in text
    assert "clean tree" in text


def test_the_preflight_table_records_what_was_skipped():
    """A skipped check must never read as a passed one."""
    state = _state()
    state.preflight = PreflightReport(checks=[
        CheckResult("baseline gate", True, "skipped by flag", skipped=True),
        CheckResult("clean tree", True, "nothing uncommitted"),
    ])
    text = compose(state)
    assert "| baseline gate | skipped |" in text
    assert "| clean tree | ok |" in text


def test_compose_is_pure():
    """Same state in, same text out -- no clock, no filesystem."""
    state = _state(tasks=[TaskRecord("t-1", "a", COMPLETED, commit="abc feat")])
    assert compose(state) == compose(state)
