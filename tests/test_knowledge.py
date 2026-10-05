"""The findings store: dates, supersession, and the quarantine boundary."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from watermill import knowledge

TODAY = date(2026, 8, 28)


def _record(root: Path, **overrides) -> dict:
    payload = {
        "cell": "zimmy",
        "kind": "lesson",
        "root_cause": "none",
        "tags": ("migrations",),
        "text": "An index over a new column belongs in MIGRATIONS, never in SCHEMA.",
    }
    payload.update(overrides)
    return knowledge.record(root, **payload)


def test_a_finding_carries_the_date_it_was_observed_not_the_date_it_was_typed(tmp_path: Path):
    """The whole staleness model rests on this, so it is the first assertion."""
    line = _record(tmp_path, observed_at="2026-03-04")
    assert line["observed_at"] == "2026-03-04"
    # Two separate fields, and the written-down date is a real timestamp rather
    # than a copy of the observation. A lesson learned in March and typed up in
    # August is five months old, not one day old.
    assert line["recorded_at"].startswith(knowledge.today().isoformat())
    assert "T" in line["recorded_at"]


def test_the_observation_date_is_in_the_id(tmp_path: Path):
    """A finding id turns up in commit messages and in other findings' edges,
    and in every one of those places the first question is how old it is."""
    assert _record(tmp_path, observed_at="2026-03-04")["id"].startswith("f-20260304-")


def test_an_undated_finding_is_dated_today(tmp_path: Path):
    line = _record(tmp_path)
    assert line["observed_at"] == knowledge.today().isoformat()


def test_a_malformed_date_is_refused_rather_than_stored(tmp_path: Path):
    with pytest.raises(knowledge.KnowledgeError):
        _record(tmp_path, observed_at="last March")


def test_an_unknown_kind_is_refused(tmp_path: Path):
    """A taxonomy whose members are whatever anybody typed cannot be counted."""
    with pytest.raises(knowledge.KnowledgeError):
        _record(tmp_path, kind="thought")


def test_an_unknown_destination_is_refused(tmp_path: Path):
    with pytest.raises(knowledge.KnowledgeError):
        _record(tmp_path, destination="somewhere")


def test_an_empty_finding_is_refused(tmp_path: Path):
    with pytest.raises(knowledge.KnowledgeError):
        _record(tmp_path, text="   ")


def test_an_absent_store_reads_as_empty_not_as_an_error(tmp_path: Path):
    assert knowledge.read(tmp_path) == []
    assert knowledge.last_review(tmp_path) is None
    assert knowledge.days_since_review(tmp_path) is None


def test_a_corrupt_line_does_not_hide_the_others(tmp_path: Path):
    """Same rule as the ledger: one bad write must not cost the whole history."""
    _record(tmp_path, text="one")
    (tmp_path / knowledge.KNOWLEDGE_FILENAME).open("a").write("{not json\n")
    _record(tmp_path, text="two")
    assert [r.text for r in knowledge.read(tmp_path)] == ["one", "two"]


def test_confirming_resets_the_clock_without_editing_the_finding(tmp_path: Path):
    line = _record(tmp_path, observed_at="2026-01-01")
    record = knowledge.read(tmp_path)[0]
    assert record.is_stale(TODAY)

    knowledge.confirm(tmp_path, line["id"], on="2026-08-20")
    record = knowledge.read(tmp_path)[0]
    assert not record.is_stale(TODAY)
    assert record.observed_at == "2026-01-01", "the original line is never rewritten"
    assert record.confirmed_at == "2026-08-20"


def test_staleness_uses_the_most_recent_thing_anybody_vouched_for(tmp_path: Path):
    line = _record(tmp_path, observed_at="2026-01-01")
    knowledge.confirm(tmp_path, line["id"], on="2026-02-01")
    knowledge.confirm(tmp_path, line["id"], on="2026-08-27")
    assert knowledge.read(tmp_path)[0].age_days(TODAY) == 1


def test_superseding_hides_the_old_finding_but_keeps_it(tmp_path: Path):
    """A finding that vanished when it stopped being true would take the reason
    with it. The edge points forward and both lines survive."""
    old = _record(tmp_path, text="Gurobi's academic licence is current.")
    new = _record(tmp_path, text="The academic licence expired; HiGHS is the fallback.")
    knowledge.supersede(tmp_path, old["id"], new["id"], note="licence lapsed")

    assert [r.id for r in knowledge.read(tmp_path)] == [new["id"]]
    everything = knowledge.read(tmp_path, include_superseded=True)
    assert [r.id for r in everything] == [old["id"], new["id"]]
    assert everything[0].status == knowledge.SUPERSEDED
    assert everything[0].superseded_by == new["id"]


def test_a_finding_cannot_supersede_itself(tmp_path: Path):
    line = _record(tmp_path)
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.supersede(tmp_path, line["id"], line["id"])


def test_an_agent_proposal_is_quarantined_until_a_person_decides(tmp_path: Path):
    line = knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="Something I noticed.", root_cause="none", tags=("t",))
    record = knowledge.get(tmp_path, line["id"])
    assert record.author == knowledge.AGENT
    assert record.status == knowledge.PROPOSED

    knowledge.decide(tmp_path, line["id"], promote=True)
    assert knowledge.get(tmp_path, line["id"]).status == knowledge.ACTIVE


def test_a_rejected_proposal_stays_rejected_and_stays_in_the_file(tmp_path: Path):
    line = knowledge.propose(tmp_path, cell="zimmy", kind="lesson", text="A guess.", root_cause="none", tags=("t",))
    knowledge.decide(tmp_path, line["id"], promote=False, why="not true")
    record = knowledge.get(tmp_path, line["id"])
    assert record.status == knowledge.REJECTED
    assert record.text == "A guess.", "rejection is a judgement, not a deletion"


def test_an_agent_cannot_file_a_proposal_as_a_human(tmp_path: Path):
    """`propose` drops any author the caller supplied. The provenance tier is
    the one thing the writer does not get to choose."""
    line = knowledge.propose(
        tmp_path, cell="zimmy", kind="lesson", text="x", author=knowledge.HUMAN,
        root_cause="none", tags=("t",),
    )
    assert line["author"] == knowledge.AGENT


def test_an_annotation_attaches_even_when_it_precedes_its_finding(tmp_path: Path):
    """Two machines' knowledge merged by git orders lines by hunk, not by time."""
    path = tmp_path / knowledge.KNOWLEDGE_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"kind_of_line": "confirm", "id": "f-1", "on": "2026-08-01"}\n'
        '{"kind_of_line": "finding", "id": "f-1", "cell": "z", "kind": "lesson",'
        ' "text": "t", "observed_at": "2026-01-01", "author": "human"}\n'
    )
    assert knowledge.read(tmp_path)[0].confirmed_at == "2026-08-01"


def test_only_the_four_edge_types_are_stored(tmp_path: Path):
    """A typo'd edge type is an edge in the file and in no query -- the worst
    of both, so it is dropped at write time."""
    line = _record(tmp_path, refs={"paths": ["db.py"], "files": ["nope"], "tasks": "t-1"})
    assert line["refs"] == {"paths": ["db.py"], "tasks": ["t-1"]}


def test_a_recorded_sweep_is_what_makes_absence_visible(tmp_path: Path):
    assert knowledge.days_since_review(tmp_path, TODAY) is None
    knowledge.record_review(tmp_path, on="2026-08-01")
    assert knowledge.days_since_review(tmp_path, TODAY) == 27


def test_nothing_in_this_module_edits_a_stored_line(tmp_path: Path):
    """The file only ever grows. A correction is a new line, never an edit."""
    first = _record(tmp_path, text="one")
    knowledge.confirm(tmp_path, first["id"])
    second = _record(tmp_path, text="two")
    knowledge.supersede(tmp_path, first["id"], second["id"])
    knowledge.record_review(tmp_path)
    lines = (tmp_path / knowledge.KNOWLEDGE_FILENAME).read_text().splitlines()
    assert len(lines) == 5
    assert lines[0].count('"text": "one"') == 1


def test_a_line_too_long_to_append_atomically_is_refused(tmp_path: Path):
    """The bound is not a style rule. A line under the pipe buffer is appended
    atomically, which is what makes two agents writing at once safe without a
    lock -- so a line that would exceed it is refused rather than written."""
    with pytest.raises(knowledge.KnowledgeError):
        _record(tmp_path, text="x" * (knowledge.MAX_TEXT_CHARS + 1))
    with pytest.raises(knowledge.KnowledgeError):
        _record(tmp_path, detail="x" * (knowledge.MAX_DETAIL_CHARS + 1))
    assert knowledge.read(tmp_path) == []


def test_the_bound_covers_every_writer_not_just_findings(tmp_path: Path):
    """`supersede` and `record_review` take free text too, and they are the
    ones nobody thinks to bound."""
    a, b = _record(tmp_path, text="one"), _record(tmp_path, text="two")
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.supersede(tmp_path, a["id"], b["id"], note="x" * 5000)


def test_every_written_line_fits_the_atomic_append_budget(tmp_path: Path):
    line = _record(
        tmp_path,
        text="x" * knowledge.MAX_TEXT_CHARS,
        detail="y" * knowledge.MAX_DETAIL_CHARS,
        refs={"paths": [f"a/very/long/path/number/{i}" for i in range(10)]},
    )
    written = (tmp_path / knowledge.KNOWLEDGE_FILENAME).read_bytes()
    assert len(written) <= knowledge.MAX_LINE_BYTES
    assert line["id"] in written.decode()


def test_concurrent_writers_do_not_lose_or_corrupt_a_line(tmp_path: Path):
    """The claim the whole no-database design rests on.

    Real processes, not threads: the atomicity being relied on is `O_APPEND`'s,
    which is a property of the kernel and the filesystem rather than of the
    GIL, and a thread pool would prove nothing about it. Several agents
    proposing at the same moment interleave whole lines -- no lock, no busy
    timeout, and nothing to be locked out of.
    """
    import subprocess
    import sys

    script = '''
import sys
sys.path.insert(0, "REPO_ROOT")
from pathlib import Path
from watermill import knowledge

index = int(sys.argv[1])
for step in range(20):
    knowledge.propose(
        Path(sys.argv[2]), cell=f"cell-{index % 3}", kind="lesson",
        text=f"Concurrent finding {index}/{step}.", detail="x" * 400,
        root_cause="none", tags=("t",),
    )
'''.replace("REPO_ROOT", str(Path(__file__).resolve().parent.parent))

    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(index), str(tmp_path)])
        for index in range(10)
    ]
    assert [p.wait() for p in processes] == [0] * 10

    raw = (tmp_path / knowledge.KNOWLEDGE_FILENAME).read_text().splitlines()
    records = knowledge.read(tmp_path)
    assert len(raw) == 200, "every write landed"
    assert len(records) == 200, "and every line still parses"
    assert len({r.id for r in records}) == 200, "no id collided"


# -- structure: required at write time, added later by annotation ------------


def _raw_finding(root: Path, fid: str = "f-old", **extra) -> None:
    """A pre-structure finding, as the 118 on disk were written."""
    import json

    path = root / knowledge.KNOWLEDGE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"kind_of_line": "finding", "id": fid, "cell": "z", "kind": "lesson",
           "text": "old", "observed_at": "2026-01-01", "author": "human", **extra}
    with path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def test_a_finding_without_a_root_cause_is_refused(tmp_path: Path):
    with pytest.raises(knowledge.KnowledgeError, match="root cause"):
        _record(tmp_path, root_cause="")
    with pytest.raises(knowledge.KnowledgeError, match="unknown root cause"):
        _record(tmp_path, root_cause="bad-luck")
    assert _record(tmp_path, root_cause="none")["root_cause"] == "none"


def test_a_finding_without_a_tag_is_refused(tmp_path: Path):
    with pytest.raises(knowledge.KnowledgeError, match="tag"):
        _record(tmp_path, tags=())
    with pytest.raises(knowledge.KnowledgeError, match="tag"):
        _record(tmp_path, tags=("  ",))


def test_a_proposal_needs_the_same_structure(tmp_path: Path):
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.propose(tmp_path, cell="z", kind="lesson", text="x", tags=("t",))
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.propose(tmp_path, cell="z", kind="lesson", text="x", root_cause="none")
    assert knowledge.read(tmp_path) == []


def test_an_old_unstructured_finding_still_loads(tmp_path: Path):
    _raw_finding(tmp_path)
    record = knowledge.read(tmp_path)[0]
    assert (record.root_cause, record.tags, record.destination) == ("", [], "")
    assert not record.structured


def test_annotation_is_append_only_and_merges_latest_per_field(tmp_path: Path):
    _raw_finding(tmp_path, tags=["a"], destination="note")
    path = tmp_path / knowledge.KNOWLEDGE_FILENAME
    before = path.read_bytes()

    knowledge.annotate(tmp_path, "f-old", root_cause="missing-context", tags=["b", "a"])
    knowledge.annotate(tmp_path, "f-old", root_cause="gate-hole", tags=["c"], destination="gate")
    knowledge.annotate(tmp_path, "f-old", tags=["d"])  # no cause: must not blank the cause

    after = path.read_bytes()
    assert after.startswith(before), "the file only grew; no stored line was touched"
    record = knowledge.get(tmp_path, "f-old")
    assert record.root_cause == "gate-hole", "latest wins per field"
    assert record.destination == "gate"
    assert record.tags == ["a", "b", "c", "d"], "tags union, first-seen order"
    assert record.structured
    assert record.to_dict()["root_cause"] == "gate-hole"
    assert knowledge.read(tmp_path)[0].root_cause == "gate-hole"


def test_an_annotation_is_validated_and_must_say_something(tmp_path: Path):
    _raw_finding(tmp_path)
    for kwargs in ({}, {"root_cause": "x"}, {"destination": "x"}, {"tags": [" "]}):
        with pytest.raises(knowledge.KnowledgeError):
            knowledge.annotate(tmp_path, "f-old", **kwargs)
    assert len((tmp_path / knowledge.KNOWLEDGE_FILENAME).read_text().splitlines()) == 1


def test_the_line_cap_covers_annotations(tmp_path: Path):
    _raw_finding(tmp_path)
    with pytest.raises(knowledge.KnowledgeError):
        knowledge.annotate(tmp_path, "f-old", tags=[f"{i}" + "x" * 50 for i in range(100)])
    assert knowledge.get(tmp_path, "f-old").tags == []


def test_concurrent_annotators_do_not_lose_or_corrupt_a_line(tmp_path: Path):
    import subprocess
    import sys

    _raw_finding(tmp_path)
    script = '''
import sys
sys.path.insert(0, "REPO_ROOT")
from pathlib import Path
from watermill import knowledge

index = int(sys.argv[1])
for step in range(20):
    knowledge.annotate(Path(sys.argv[2]), "f-old", tags=[f"t{index}-{step}"],
                       root_cause="none", by="x" * 300)
'''.replace("REPO_ROOT", str(Path(__file__).resolve().parent.parent))
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(i), str(tmp_path)])
        for i in range(10)
    ]
    assert [p.wait() for p in processes] == [0] * 10
    assert len((tmp_path / knowledge.KNOWLEDGE_FILENAME).read_text().splitlines()) == 201
    assert len(knowledge.get(tmp_path, "f-old").tags) == 200
