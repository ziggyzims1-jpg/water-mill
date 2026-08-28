"""The context graph: what it returns, what it refuses to return, and its cost.

The assertions that matter most here are about *absence* -- a proposal that
must not come back, a superseded finding that must not come back, and a result
set that must not grow without bound. A retrieval layer fails silently in
exactly those three directions.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from watermill import knowledge, ledger, recall, tasklog

TODAY = date(2026, 8, 28)


def _finding(root: Path, text: str, cell: str = "zimmy", **kw) -> dict:
    kw.setdefault("observed_at", "2026-08-20")
    return knowledge.record(root, cell=cell, kind=kw.pop("kind", "lesson"), text=text, **kw)


def _task(root: Path, task_id: str, project: str = "zimmy", **kw) -> None:
    tasklog.append_run(
        root,
        {
            "run_id": kw.pop("run_id", "20260820-030000"),
            "project": project,
            "tasks": [{
                "id": task_id,
                "title": kw.pop("title", "a task"),
                "outcome": kw.pop("outcome", "failed"),
                "reason": kw.pop("reason", ""),
            }],
        },
        root / "logs",
    )


def test_an_empty_factory_says_so_rather_than_returning_nothing(tmp_path: Path):
    """"Nothing recorded" and "nothing matched" are different answers, and a
    new factory being told it is a quiet one is how a tool loses its user."""
    answer = recall.search(recall.build(tmp_path), "anything")
    assert "Nothing has been recorded yet" in answer.render()


def test_no_match_is_reported_as_no_match(tmp_path: Path):
    _finding(tmp_path, "Migrations are append-only.")
    assert "No match" in recall.search(recall.build(tmp_path), "zzzzz").render()


def test_a_query_finds_the_finding_that_is_about_it(tmp_path: Path):
    _finding(tmp_path, "An index over a new column belongs in MIGRATIONS, not SCHEMA.")
    _finding(tmp_path, "The Libby sentry host moved and role=pointer is required.")
    answer = recall.search(recall.build(tmp_path), "migrations schema index")
    assert len(answer.hits) >= 1
    assert "MIGRATIONS" in answer.hits[0].node.text


def test_a_file_path_is_a_usable_query(tmp_path: Path):
    """An agent about to edit db.py asks "db.py"."""
    _finding(tmp_path, "Schema changes crash on boot if the index ships in SCHEMA.",
             refs={"paths": ["db.py"]})
    _finding(tmp_path, "Something about the frontend.", refs={"paths": ["frontend/src"]})
    answer = recall.search(recall.build(tmp_path), "db.py")
    assert answer.hits[0].node.meta["refs"]["paths"] == ["db.py"]


def test_an_agent_proposal_is_never_returned_by_search(tmp_path: Path):
    """The quarantine is enforced here, in the one place every reader goes
    through, rather than in each caller that might forget."""
    knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="A guess about migrations.")
    graph = recall.build(tmp_path)
    assert recall.search(graph, "migrations").hits == []
    assert len(recall.proposals(graph)) == 1
    assert len(recall.search(graph, "migrations", include_proposed=True).hits) == 1


def test_a_promoted_proposal_becomes_visible(tmp_path: Path):
    line = knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="About migrations.")
    knowledge.decide(tmp_path, line["id"], promote=True)
    assert recall.search(recall.build(tmp_path), "migrations").hits


def test_a_superseded_finding_is_not_returned_but_is_still_findable_by_id(tmp_path: Path):
    old = _finding(tmp_path, "The academic solver licence is current.")
    new = _finding(tmp_path, "The solver licence expired; HiGHS is the fallback.")
    knowledge.supersede(tmp_path, old["id"], new["id"])
    graph = recall.build(tmp_path)

    hits = recall.search(graph, "solver licence").hits
    assert [h.node.id for h in hits] == [new["id"]]

    text = recall.detail(graph, old["id"])
    assert "SUPERSEDED" in text and new["id"] in text
    assert "HiGHS" in text, "somebody arriving with the old id is told what replaced it"


def test_a_stale_finding_is_returned_and_labelled_rather_than_hidden(tmp_path: Path):
    """It may be the only thing anybody knows. Weighed down, never dropped."""
    _finding(tmp_path, "Something learned long ago about the gate.", observed_at="2026-01-01")
    answer = recall.search(recall.build(tmp_path, as_of=TODAY), "gate")
    assert answer.hits
    assert "stale" in answer.render()


def test_confirming_a_finding_clears_the_stale_label(tmp_path: Path):
    line = _finding(tmp_path, "Something about the gate.", observed_at="2026-01-01")
    knowledge.confirm(tmp_path, line["id"], on="2026-08-25")
    assert "stale" not in recall.search(recall.build(tmp_path, as_of=TODAY), "gate").render()


def test_the_result_set_is_capped_however_much_is_known(tmp_path: Path):
    """The cost of asking must not grow with the size of what is remembered."""
    for index in range(60):
        _finding(tmp_path, f"A finding about the gate, number {index}.")
    answer = recall.search(recall.build(tmp_path), "gate")
    assert len(answer.hits) == recall.DEFAULT_LIMIT
    assert answer.matched == 60
    assert answer.truncated
    assert "more match" in answer.render()


def test_the_limit_has_a_ceiling_no_caller_can_raise(tmp_path: Path):
    for index in range(80):
        _finding(tmp_path, f"A finding about the gate, number {index}.")
    answer = recall.search(recall.build(tmp_path), "gate", limit=500)
    assert len(answer.hits) <= recall.MAX_LIMIT


def test_the_rendered_answer_stays_under_the_character_budget(tmp_path: Path):
    for index in range(40):
        _finding(tmp_path, "A very long finding about the gate " * 10 + str(index))
    answer = recall.search(recall.build(tmp_path), "gate", limit=20, budget_chars=600)
    body = "\n".join(h.line() for h in answer.hits)
    assert len(body) <= 600 + recall.LINE_CHARS
    assert answer.truncated


def test_one_hit_is_returned_even_when_it_exceeds_the_budget(tmp_path: Path):
    """An answer of nothing is worse than an answer of one line over budget."""
    _finding(tmp_path, "A very long finding about the gate " * 10)
    answer = recall.search(recall.build(tmp_path), "gate", budget_chars=10)
    assert len(answer.hits) == 1


def test_the_same_question_on_the_same_data_gives_the_same_answer(tmp_path: Path):
    for index in range(20):
        _finding(tmp_path, f"A finding about the gate, number {index}.")
    graph = recall.build(tmp_path)
    first = [h.node.id for h in recall.search(graph, "gate").hits]
    second = [h.node.id for h in recall.search(recall.build(tmp_path), "gate").hits]
    assert first == second


def test_a_human_finding_outranks_a_mechanical_outcome_at_equal_relevance(tmp_path: Path):
    _task(tmp_path, "t-1", title="fix the gate", reason="gate failed after the change")
    _finding(tmp_path, "The gate failed because make verify differs from CI.")
    hits = recall.search(recall.build(tmp_path), "gate failed").hits
    assert hits[0].node.kind == recall.FINDING


def test_task_outcomes_and_runs_are_searchable_too(tmp_path: Path):
    """The mechanical history is most of what exists before anybody writes a
    finding, and a graph that ignored it would be empty for months."""
    _task(tmp_path, "t-7", title="add the reading plan", reason="modified fenced path(s): db.py")
    ledger.append(
        tmp_path,
        ledger.Entry.from_summary(
            {"run_id": "20260820-030000", "project": "zimmy", "started_at": "2026-08-20T03:00:00",
             "ended_at": "", "halt_reason": "queue exhausted",
             "counts": {"attempted": 1, "completed": 0, "failed": 1}},
            tmp_path / "logs",
        ),
    )
    graph = recall.build(tmp_path)
    assert recall.search(graph, "fenced path db.py").hits[0].node.kind == recall.TASK
    assert any(n.kind == recall.RUN for n in graph.nodes)


def test_a_cell_scoped_query_still_sees_factory_wide_findings(tmp_path: Path):
    """A lesson about the factory itself is true in every cell."""
    _finding(tmp_path, "A gate that differs from CI is two gates.", cell="")
    _finding(tmp_path, "Something about another project's gate.", cell="other")
    hits = recall.search(recall.build(tmp_path), "gate", cell="zimmy").hits
    assert [h.node.cell for h in hits] == [""]


def test_the_same_lesson_in_two_cells_is_reported_as_promotable(tmp_path: Path):
    """Water Mill's filing rule -- twice, in two repositories -- as a query
    rather than as something somebody has to remember."""
    _finding(tmp_path, "A queue with no show command produces vague work.", cell="zimmy")
    _finding(tmp_path, "A queue with no show command produces vague work.", cell="cell-1b")
    groups = recall.promotable(recall.build(tmp_path))
    assert len(groups) == 1
    assert {n.cell for n in groups[0][1]} == {"zimmy", "cell-1b"}


def test_the_same_lesson_twice_in_one_cell_is_not_promotable(tmp_path: Path):
    """One project's frictions are indistinguishable from its idiosyncrasies."""
    _finding(tmp_path, "A queue with no show command produces vague work.", cell="zimmy")
    _finding(tmp_path, "A queue with no show command produces vague work.", cell="zimmy")
    assert recall.promotable(recall.build(tmp_path)) == []


def test_a_lesson_that_never_became_a_check_is_named(tmp_path: Path):
    _finding(tmp_path, "Never edit the schema directly.", destination="fence")
    _finding(tmp_path, "The queue must print the whole spec.")
    pending = recall.unmechanised(recall.build(tmp_path))
    assert [n.text for n in pending] == ["The queue must print the whole spec."]


def test_detail_returns_the_body_that_search_deliberately_does_not(tmp_path: Path):
    _finding(tmp_path, "Short version.", detail="The long version, " * 20)
    graph = recall.build(tmp_path)
    node_id = recall.search(graph, "short version").hits[0].node.id
    assert "The long version" in recall.detail(graph, node_id)
    assert "The long version" not in recall.search(graph, "short version").render()


def test_detail_on_an_unknown_id_says_so(tmp_path: Path):
    assert "No such id" in recall.detail(recall.build(tmp_path), "f-nope")
