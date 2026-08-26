"""Reading a cost and a verdict out of the agent's own output."""

from __future__ import annotations

import json

from watermill.meter import read


def test_reads_a_plain_json_result():
    reading = read(json.dumps({"total_cost_usd": 0.42, "result": "done"}))
    assert reading.cost_cents == 42
    assert reading.text == "done"
    assert reading.parsed is True


def test_reads_stream_json_and_prefers_the_last_object():
    lines = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": "thinking"}),
        json.dumps({"type": "result", "total_cost_usd": 1.5, "result": "finished"}),
    ])
    reading = read(lines)
    assert reading.cost_cents == 150
    assert reading.text == "finished"


def test_survives_a_banner_before_the_json():
    raw = "Loading configuration...\n" + json.dumps({"total_cost_usd": 0.1, "result": "ok"})
    assert read(raw).cost_cents == 10


def test_unparseable_output_reports_no_cost_rather_than_zero():
    """A crashed agent must be countable, not free.

    Returning zero would be a lie in the direction that lets a run continue.
    None is what `caps.max_unmetered_tasks` halts on.
    """
    reading = read("Traceback (most recent call last):\n  RuntimeError: boom")
    assert reading.cost_cents is None
    assert reading.parsed is False


def test_empty_output_reports_no_cost():
    assert read("").cost_cents is None


def test_a_renamed_cost_field_reads_less_rather_than_raising():
    """This is someone else's output format and it will change.

    A rename should cost the meter its number -- countable, haltable -- not
    raise and take the run down.
    """
    reading = read(json.dumps({"grand_total_dollars": 9.99, "result": "done"}))
    assert reading.cost_cents is None
    assert reading.text == "done"


def test_alternative_cost_key_is_accepted():
    assert read(json.dumps({"cost_usd": 0.05, "result": "x"})).cost_cents == 5


def test_negative_cost_is_refused():
    assert read(json.dumps({"total_cost_usd": -1, "result": "x"})).cost_cents is None


def test_cost_rounds_up_so_a_run_is_never_told_it_spent_less():
    assert read(json.dumps({"total_cost_usd": 0.005, "result": "x"})).cost_cents == 1


def test_content_blocks_are_flattened_into_text():
    raw = json.dumps({
        "total_cost_usd": 0.1,
        "content": [{"type": "text", "text": "ESCALATE"}, {"type": "text", "text": "why"}],
    })
    assert read(raw).escalated is True


# -- escalation ------------------------------------------------------------


def test_escalation_is_detected_at_the_start_of_a_line():
    reading = read(json.dumps({
        "total_cost_usd": 0.1,
        "result": "I could not decide.\nESCALATE\nThe spec names two behaviours.",
    }))
    assert reading.escalated is True


def test_escalation_is_not_detected_mid_sentence():
    """An agent describing escalation in prose has not escalated.

    Without the line anchor, 'I considered whether to ESCALATE and decided not
    to' releases the task and reports a decision nobody needs to make -- which
    trains the operator to skim the one section of the report that matters.
    """
    reading = read(json.dumps({
        "total_cost_usd": 0.1,
        "result": "I considered whether to ESCALATE here but the spec was clear.",
    }))
    assert reading.escalated is False


def test_escalation_is_seen_even_when_the_agent_printed_no_json():
    """A plain-text agent that escalates must still be heard."""
    reading = read("ESCALATE\nThe database schema change needs a human.")
    assert reading.parsed is False
    assert reading.cost_cents is None
    assert reading.escalated is True


def test_reported_error_is_carried_through():
    assert read(json.dumps({"is_error": True, "result": "failed"})).reported_error is True
