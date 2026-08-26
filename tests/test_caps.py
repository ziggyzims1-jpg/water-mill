"""The caps, and the two counting rules that were measured bugs rather than choices."""

from __future__ import annotations

from watermill.caps import DEFAULTS, Caps, Tally, check
from watermill.contract import Caps as ContractCaps


def _caps(**overrides) -> Caps:
    base = {"max_spend_cents": 1000}
    base.update(overrides)
    return Caps.resolve(None, base)


def test_task_cap_counts_attempts_not_completions():
    """The 48-escalation runaway.

    A completion cap looks equivalent to an attempt cap and is not: in a run
    where every task escalates, `completed` never increments, so a cap on
    completions never fires and the loop works through the entire queue. This
    was measured at 48 escalations against a limit of 1.
    """
    caps = _caps(max_tasks=3)
    tally = Tally()
    for _ in range(3):
        tally.record_escalation(10)
    assert tally.completed == 0
    assert check(caps, tally) is not None
    assert "task cap" in check(caps, tally)


def test_escalation_does_not_spend_the_failure_budget():
    """The agent recognised a judgement call. That is the behaviour being asked for."""
    caps = _caps(max_consecutive_failures=2, max_tasks=99)
    tally = Tally()
    for _ in range(5):
        tally.record_escalation(1)
    assert tally.consecutive_failures == 0
    assert check(caps, tally) is None


def test_a_success_resets_the_consecutive_failure_run():
    caps = _caps(max_consecutive_failures=3, max_tasks=99)
    tally = Tally()
    tally.record_failure(1)
    tally.record_failure(1)
    tally.record_success(1)
    tally.record_failure(1)
    assert tally.consecutive_failures == 1
    assert check(caps, tally) is None


def test_consecutive_failures_halt():
    caps = _caps(max_consecutive_failures=3, max_tasks=99)
    tally = Tally()
    for _ in range(3):
        tally.record_failure(1)
    assert "failure cap" in check(caps, tally)


def test_spend_cap_halts_once_crossed():
    caps = _caps(max_spend_cents=100, max_tasks=99)
    tally = Tally()
    tally.record_success(60)
    assert check(caps, tally) is None
    tally.record_success(60)
    reason = check(caps, tally)
    assert "spend cap" in reason
    # Reactive, not preventive: it overshoots by up to one task, and says so.
    assert "$1.20" in reason


def test_a_meter_that_stops_counting_halts_the_run():
    """A crashed agent reports no cost, and a run with no meter looks cheap."""
    caps = _caps(max_unmetered_tasks=3, max_tasks=99)
    tally = Tally()
    for _ in range(3):
        tally.record_failure(None)
    reason = check(caps, tally)
    assert "meter stopped" in reason
    assert tally.spend_cents == 0


def test_unmetered_tasks_do_not_silently_count_as_free():
    tally = Tally()
    tally.record_success(None)
    tally.record_success(50)
    assert tally.unmetered == 1
    assert tally.spend_cents == 50


def test_wall_clock_halts():
    caps = _caps(max_hours=1.0, max_tasks=99)
    tally = Tally()
    tally.started_at = 0.0
    assert "wall clock" in check(caps, tally, now=3601)


def test_wall_clock_does_not_halt_early():
    caps = _caps(max_hours=1.0, max_tasks=99)
    tally = Tally()
    tally.started_at = 0.0
    assert check(caps, tally, now=3000) is None


# -- resolution ------------------------------------------------------------


def test_defaults_apply_when_nothing_overrides():
    caps = Caps.resolve(None, {"max_spend_cents": 500})
    assert caps.max_tasks == DEFAULTS["max_tasks"]
    assert caps.max_hours == DEFAULTS["max_hours"]


def test_contract_overrides_defaults_and_cli_overrides_contract():
    contract = ContractCaps.parse({"max_tasks": 5, "max_hours": 3})
    caps = Caps.resolve(contract, {"max_tasks": 2, "max_spend_cents": 100})
    assert caps.max_tasks == 2       # the command line won
    assert caps.max_hours == 3.0     # the contract won over the default
    assert caps.max_consecutive_failures == DEFAULTS["max_consecutive_failures"]


def test_an_unset_field_means_no_opinion_not_zero():
    """A contract that omits a cap must not silently set it to zero."""
    contract = ContractCaps.parse({"max_tasks": 5})
    caps = Caps.resolve(contract, {"max_spend_cents": 100})
    assert caps.max_hours == DEFAULTS["max_hours"]
    assert caps.task_timeout_minutes == DEFAULTS["task_timeout_minutes"]


def test_there_is_no_default_spend_ceiling():
    """Preflight refuses on this. The spend cap is the one that fails closed."""
    assert Caps.resolve(None, None).max_spend_cents is None
