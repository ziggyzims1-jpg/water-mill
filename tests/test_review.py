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
    knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="An agent's guess.")
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
    knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="A guess.")
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


# -- landed without a finding ---------------------------------------------------


def _checkout(root: Path, name: str = "proj") -> Path:
    """A registered sibling under tmp_path, with a handoff directory."""
    (root / "projects.yaml").write_text(
        f"version: 1\nprojects:\n  - name: {name}\n    path: ../{name}-checkout\n",
        encoding="utf-8",
    )
    handoffs = root.parent / f"{name}-checkout" / "brain" / "handoffs" / "mill"
    handoffs.mkdir(parents=True, exist_ok=True)
    return handoffs


def _landed(handoffs: Path, slug: str, on: str, extra: str = "", title_id: str | None = None):
    title = title_id or f"Proj {slug}"
    (handoffs / f"{slug}.md").write_text(
        f"# Handoff — {title}\n\n**LANDED** (PR #1)\n\n## Millstone (2026-10-01)\n\n"
        f"- done\n{extra}\n## Tailrace ({on})\n\n**LANDED** merged.\n",
        encoding="utf-8",
    )


LAG_TODAY = date(2026, 10, 10)


def _root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "mill"
    root.mkdir()
    return root, _checkout(root)


def test_a_landed_bead_with_no_finding_is_lag(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "abc", "2026-10-06")
    state = review.sweep(root, as_of=LAG_TODAY)
    assert [item.bead for item in state.lag] == ["proj-abc"]
    out = review.render(state)
    assert "## Landed without a finding -- 1 bead(s)" in out
    assert "proj-abc [proj] landed 2026-10-06" in out
    assert str(handoffs / "abc.md") in out


def test_a_finding_citing_the_bead_covers_it_whatever_the_spelling(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "abc", "2026-10-06", title_id="Proj Name-abc")
    _landed(handoffs, "def", "2026-10-06", title_id="proj-def")
    _finding(root, "x", refs={"tasks": ["proj-name-abc"]})
    _finding(root, "y", refs={"tasks": ["Proj-Def"]})
    assert review.sweep(root, as_of=LAG_TODAY).lag == []


def test_a_none_marker_with_a_reason_covers_it_and_without_does_not(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "ok", "2026-10-06", "\n**Findings:** none -- pure refactor\n")
    _landed(handoffs, "bare", "2026-10-06", "\n**Findings:** none\n")
    assert [i.bead for i in review.sweep(root, as_of=LAG_TODAY).lag] == ["proj-bare"]


def test_beads_landed_before_the_cutoff_do_not_count(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "old", "2026-10-04")
    _landed(handoffs, "new", "2026-10-05")
    assert [i.bead for i in review.sweep(root, as_of=LAG_TODAY).lag] == ["proj-new"]
    custom = review.sweep(root, as_of=LAG_TODAY, lag_since=date(2026, 10, 1))
    assert len(custom.lag) == 2


def test_an_unlanded_handoff_is_not_lag(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    (handoffs / "wip.md").write_text("# Handoff — proj-wip\n\n## Millstone (2026-10-06)\n")
    assert review.sweep(root, as_of=LAG_TODAY).lag == []


def test_a_missing_checkout_is_reported_not_an_error(tmp_path: Path):
    root, _ = _root(tmp_path)
    (root / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: gone\n    path: ../nowhere\n", encoding="utf-8"
    )
    state = review.sweep(root, as_of=LAG_TODAY)
    assert state.lag == [] and state.lag_missing == ["gone"]
    assert "Checkout not found, so not checked: gone" in "\n".join(review.render_lag(state))
    assert review.check_line(state)[1] == 0


def test_check_fails_only_on_lag_past_the_grace_period(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "abc", "2026-10-09")  # one day ago: inside the grace
    state = review.sweep(root, as_of=LAG_TODAY)
    assert state.lag and not state.lagging
    assert review.check_line(state)[1] == 0

    _landed(handoffs, "abc", "2026-10-07")  # three days ago
    state = review.sweep(root, as_of=LAG_TODAY)
    line, code = review.check_line(state)
    assert code == 1 and "proj-abc" in line

    assert review.check_line(review.sweep(root, as_of=LAG_TODAY, lag_after_days=5))[1] == 0


def test_a_bare_slug_covers_only_on_a_finding_filed_against_that_cell(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "abc", "2026-10-06", title_id="proj-abc")
    _landed(handoffs, "def", "2026-10-06", title_id="proj-def")
    _finding(root, "x", cell="proj", refs={"tasks": ["abc"]})
    _finding(root, "y", cell="other", refs={"tasks": ["def"]})
    assert [i.bead for i in review.sweep(root, as_of=LAG_TODAY).lag] == ["proj-def"]


def test_a_none_marker_with_nothing_after_the_dash_does_not_cover(tmp_path: Path):
    """The reason must be on the marker's own line, not the next heading."""
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "empty", "2026-10-06", "\n**Findings:** none --\n- next bullet\n")
    _landed(handoffs, "bare", "2026-10-06", "\n**Findings:** none\n- next bullet\n")
    lag = [i.bead for i in review.sweep(root, as_of=LAG_TODAY).lag]
    assert lag == ["proj-bare", "proj-empty"]


def test_the_landing_date_is_the_last_tailrace_heading(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    (handoffs / "two.md").write_text(
        "# Handoff — proj-two\n\n## Tailrace (2026-10-01)\n\nVERIFY_FAILED\n\n"
        "## Tailrace (2026-10-06)\n\n**LANDED** merged.\n",
        encoding="utf-8",
    )
    assert [i.landed_on for i in review.sweep(root, as_of=LAG_TODAY).lag] == [
        date(2026, 10, 6)
    ]


def test_a_landed_handoff_with_no_tailrace_date_is_reported_and_fails_check(tmp_path: Path):
    """Undatable is not the same as unlanded: dropping it would hide an absence."""
    root, handoffs = _root(tmp_path)
    (handoffs / "nodate.md").write_text(
        "# Handoff — proj-nodate\n\n## Millstone (2026-08-01)\n\n**LANDED** by hand.\n",
        encoding="utf-8",
    )
    state = review.sweep(root, as_of=LAG_TODAY)
    assert [i.bead for i in state.lagging] == ["proj-nodate"]
    assert "proj-nodate [proj] landed on an unknown date" in review.render(state)
    assert review.check_line(state)[1] == 1


def test_lag_is_due_only_strictly_more_than_the_grace_days_after_landing(tmp_path: Path):
    root, handoffs = _root(tmp_path)
    _landed(handoffs, "abc", "2026-10-08")  # exactly two days ago
    assert review.check_line(review.sweep(root, as_of=LAG_TODAY))[1] == 0
