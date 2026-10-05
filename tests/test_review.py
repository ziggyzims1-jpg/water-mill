"""The monthly sweep, and the thing that notices the sweep stopped happening.

`render` is pure -- a Sweep in, the exact text out -- so every line the person
doing the review reads is asserted here without a clock or a filesystem, the
same rule the morning report follows.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from watermill import knowledge, review, tasklog

TODAY = date(2026, 8, 28)


def _finding(root: Path, text: str, cell: str = "zimmy", **kw) -> dict:
    kw.setdefault("observed_at", "2026-08-20")
    kw.setdefault("root_cause", "none")
    kw.setdefault("tags", ("t",))
    return knowledge.record(root, cell=cell, kind=kw.pop("kind", "lesson"), text=text, **kw)


def test_an_empty_factory_is_not_overdue_for_a_review(tmp_path: Path):
    """An alert that fires on day one is an alert nobody reads by day two."""
    state = review.sweep(tmp_path, as_of=TODAY)
    assert state.never_reviewed
    assert not state.overdue
    assert "Nothing to do" in review.render(state)


def test_findings_with_no_sweep_on_record_are_overdue(tmp_path: Path):
    _finding(tmp_path, "Something worth knowing.")
    state = review.sweep(tmp_path, as_of=TODAY)
    assert state.overdue
    assert "No sweep has ever been recorded" in review.render(state)


def test_a_recent_sweep_is_not_overdue(tmp_path: Path):
    _finding(tmp_path, "Something worth knowing.")
    knowledge.record_review(tmp_path, on="2026-08-20")
    state = review.sweep(tmp_path, as_of=TODAY)
    assert not state.overdue
    assert "Last swept 8 days ago" in review.render(state)


def test_a_sweep_that_stopped_happening_is_the_finding(tmp_path: Path):
    """A monthly job that silently stopped looks exactly like a month with
    nothing to review. Both produce no output, so absence is measured."""
    _finding(tmp_path, "Something worth knowing.")
    knowledge.record_review(tmp_path, on="2026-06-01")
    state = review.sweep(tmp_path, as_of=TODAY)
    assert state.days_since_review == 88
    assert state.overdue
    assert "past the" in review.render(state)


def test_stale_findings_are_listed_with_their_age(tmp_path: Path):
    _finding(tmp_path, "A finding from January.", observed_at="2026-01-05")
    _finding(tmp_path, "A finding from last week.", observed_at="2026-08-24")
    state = review.sweep(tmp_path, as_of=TODAY)
    assert [n.text for n in state.stale] == ["A finding from January."]
    # Scoped to the stale section: the recent one still appears further down
    # under "still only advice", which is a different question about it.
    stale_section = review.render(state).split("## Stale")[1].split("## ")[0]
    assert "A finding from January." in stale_section
    assert "A finding from last week." not in stale_section


def test_a_confirmed_finding_leaves_the_stale_list(tmp_path: Path):
    line = _finding(tmp_path, "A finding from January.", observed_at="2026-01-05")
    knowledge.confirm(tmp_path, line["id"], on="2026-08-01")
    assert review.sweep(tmp_path, as_of=TODAY).stale == []


def test_a_superseded_finding_is_not_swept_again(tmp_path: Path):
    """It is no longer believed, so nobody has to keep re-confirming it."""
    old = _finding(tmp_path, "The old belief.", observed_at="2026-01-05")
    new = _finding(tmp_path, "What replaced it.")
    knowledge.supersede(tmp_path, old["id"], new["id"])
    assert review.sweep(tmp_path, as_of=TODAY).stale == []


def test_proposals_awaiting_a_person_are_named(tmp_path: Path):
    knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="An agent's guess.", root_cause="none", tags=("t",))
    state = review.sweep(tmp_path, as_of=TODAY)
    assert len(state.proposals) == 1
    assert "quarantine" in review.render(state)


def test_a_lesson_in_two_cells_is_raised_for_promotion(tmp_path: Path):
    _finding(tmp_path, "A queue with no show command produces vague work.", cell="zimmy")
    _finding(tmp_path, "A queue with no show command produces vague work.", cell="cell-1b")
    text = review.render(review.sweep(tmp_path, as_of=TODAY))
    assert "Twice, in two cells" in text
    assert "cell-1b, zimmy" in text


def test_advice_that_never_became_a_check_is_raised_every_month(tmp_path: Path):
    _finding(tmp_path, "Never touch the schema.", destination="fence")
    _finding(tmp_path, "The queue must print the whole spec.")
    text = review.render(review.sweep(tmp_path, as_of=TODAY))
    assert "Still only advice" in text
    assert "whole spec" in text
    assert "Never touch the schema" not in text


def test_tasks_with_no_root_cause_are_listed_but_completions_are_not(tmp_path: Path):
    """A completed task needs no post-mortem; a discarded one is the whole
    point of the taxonomy."""
    tasklog.append_run(
        tmp_path,
        {"run_id": "r1", "project": "zimmy", "tasks": [
            {"id": "t-1", "title": "worked", "outcome": "completed"},
            {"id": "t-2", "title": "did not", "outcome": "failed", "reason": "gate failed"},
        ]},
        tmp_path / "logs",
    )
    state = review.sweep(tmp_path, as_of=TODAY)
    assert [row["task_id"] for row in state.unannotated] == ["t-2"]


def test_an_annotated_task_leaves_the_list(tmp_path: Path):
    tasklog.append_run(
        tmp_path,
        {"run_id": "r1", "project": "zimmy", "tasks": [
            {"id": "t-2", "title": "did not", "outcome": "failed", "reason": "gate failed"}]},
        tmp_path / "logs",
    )
    tasklog.annotate(tmp_path, "zimmy", "t-2", "too-large")
    assert review.sweep(tmp_path, as_of=TODAY).unannotated == []


def test_the_sweep_writes_nothing(tmp_path: Path):
    """It is a reader. The only line it may ever add is the one recording that
    it happened, and that is a separate call a person makes."""
    _finding(tmp_path, "Something.")
    before = (tmp_path / knowledge.KNOWLEDGE_FILENAME).read_text()
    review.render(review.sweep(tmp_path, as_of=TODAY))
    assert (tmp_path / knowledge.KNOWLEDGE_FILENAME).read_text() == before


def test_nothing_needing_a_decision_says_so_and_asks_for_the_record(tmp_path: Path):
    knowledge.record_review(tmp_path, on="2026-08-20")
    text = review.render(review.sweep(tmp_path, as_of=TODAY))
    assert "Nothing needs a decision" in text
    assert "watermill review --record" in text


def test_what_needs_a_decision_leads(tmp_path: Path):
    """Same rule as the morning report: the only section that is work goes
    first, so a month of accumulating debt is visible rather than buried."""
    _finding(tmp_path, "An old finding.", observed_at="2026-01-01")
    knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="A guess.", root_cause="none", tags=("t",))
    knowledge.record_review(tmp_path, on="2026-08-20")
    text = review.render(review.sweep(tmp_path, as_of=TODAY))
    assert text.index("## Stale") < text.index("## Proposed")


def test_the_heartbeat_tells_three_cases_apart(tmp_path: Path):
    """Overdue, healthy, and nothing-to-sweep-yet are three different answers,
    and only the first may fail. Printing "last run None days ago" for the
    third reads as a broken tool rather than as a correct one."""
    line, code = review.check_line(review.sweep(tmp_path, as_of=TODAY))
    assert code == 0 and "nothing recorded to sweep" in line

    _finding(tmp_path, "Something.")
    knowledge.record_review(tmp_path, on="2026-08-20")
    line, code = review.check_line(review.sweep(tmp_path, as_of=TODAY))
    assert code == 0 and "8 days ago" in line

    knowledge.record_review(tmp_path, on="2026-06-01")
    line, code = review.check_line(review.sweep(tmp_path, as_of=TODAY))
    assert code == 1 and "overdue" in line


def test_the_sweep_reports_what_the_tool_could_not_answer(tmp_path: Path):
    """A percentage is a health check; the list of unanswered questions is
    work. Both are in the sweep because only one of them is actionable."""
    from watermill import usage

    _finding(tmp_path, "A finding about the gate.")
    usage.record(tmp_path, tool="recall", query="gate", hits=1, run_id="r1", task_id="t-1")
    usage.record(tmp_path, tool="recall", query="upstream rate limits", hits=0,
                 run_id="r1", task_id="t-1")
    knowledge.record_review(tmp_path, on="2026-08-20")

    state = review.sweep(tmp_path, as_of=TODAY)
    assert state.usage["searches"] == 2
    assert state.usage["hit_rate"] == 0.5

    text = review.render(state)
    assert "## The tool itself" in text
    assert "50% of them answered" in text
    assert "upstream rate limits" in text


def test_a_tool_nobody_called_adds_no_section(tmp_path: Path):
    """Silence here is reported by `recall --usage`, not by inventing a
    section that says nothing every month."""
    _finding(tmp_path, "A finding.")
    knowledge.record_review(tmp_path, on="2026-08-20")
    assert "## The tool itself" not in review.render(review.sweep(tmp_path, as_of=TODAY))


def test_missing_structure_lists_findings_until_annotated(tmp_path: Path):
    import json

    path = tmp_path / knowledge.KNOWLEDGE_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "kind_of_line": "finding", "id": "f-old", "cell": "zimmy", "kind": "lesson",
        "text": "An old finding with no structure.", "observed_at": "2026-08-20",
        "author": "human",
    }) + "\n")
    _finding(tmp_path, "A structured one.")

    text = review.render(review.sweep(tmp_path, as_of=TODAY))
    assert "Missing structure -- 1 finding(s)" in text
    assert "f-old" in text and "no cause or tags" in text
    assert "A structured one" not in text.split("Missing structure")[1]

    knowledge.annotate(tmp_path, "f-old", root_cause="none")
    assert "no tags" in review.render(review.sweep(tmp_path, as_of=TODAY))
    knowledge.annotate(tmp_path, "f-old", tags=["x"])
    assert "Missing structure" not in review.render(review.sweep(tmp_path, as_of=TODAY))
