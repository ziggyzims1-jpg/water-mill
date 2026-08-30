"""The contract is the coupling surface, so its refusals are the tests that matter.

Almost every case here asserts that something is *rejected*. That is the point:
a contract that parses leniently turns a typo into a silently absent fence, and
the fence is the only thing standing between a confused agent and the files a
project cannot afford to lose.
"""

from __future__ import annotations

import pytest

from watermill import contract as contract_mod
from watermill.contract import Contract, Fence, Queue
from watermill.errors import ContractError

MINIMAL = {
    "version": 1,
    "name": "demo",
    "commands": {"gate": "make verify"},
    "git": {"base_branch": "main"},
}


def test_minimal_contract_parses():
    contract = Contract.parse(MINIMAL)
    assert contract.name == "demo"
    assert contract.commands.gate == "make verify"
    assert contract.git.base_branch == "main"


def test_defaults_are_conservative():
    """An unstated preference must resolve to the careful answer, not a blank."""
    contract = Contract.parse(MINIMAL)
    # Branch, not direct: a project the factory has never driven has not earned
    # commits straight onto its base branch.
    assert contract.git.target == "branch"
    assert contract.queue.enabled is False
    assert contract.fence.paths == ()
    assert contract.environment.min_free_gb == 2.0


def test_gate_is_required():
    raw = {**MINIMAL, "commands": {"install": "make install"}}
    with pytest.raises(ContractError, match="commands.gate is required"):
        Contract.parse(raw)


def test_base_branch_is_required():
    raw = {**MINIMAL, "git": {"target": "direct"}}
    with pytest.raises(ContractError, match="git.base_branch is required"):
        Contract.parse(raw)


def test_unknown_top_level_key_is_refused():
    """The whole reason validation is strict: a typo must not become a default."""
    raw = {**MINIMAL, "fench": {"paths": ["db.py"]}}
    with pytest.raises(ContractError, match="unknown key"):
        Contract.parse(raw)


def test_unknown_nested_key_is_refused():
    raw = {**MINIMAL, "git": {"base_branch": "main", "brnach": "oops"}}
    with pytest.raises(ContractError, match="unknown key"):
        Contract.parse(raw)


def test_misspelled_fence_key_does_not_silently_empty_the_fence():
    """The exact failure strict parsing exists to prevent.

    Written as its own test because the generic 'unknown key' case does not
    convey the consequence: a lenient parser would accept this, report a fence
    of zero paths, and let a task delete the schema.
    """
    raw = {**MINIMAL, "fence": {"path": ["db.py"]}}
    with pytest.raises(ContractError):
        Contract.parse(raw)


def test_unsupported_version_is_refused_rather_than_guessed():
    raw = {**MINIMAL, "version": 2}
    with pytest.raises(ContractError, match="not supported"):
        Contract.parse(raw)


def test_git_target_must_be_known():
    raw = {**MINIMAL, "git": {"base_branch": "main", "target": "yolo"}}
    with pytest.raises(ContractError, match="direct.*branch|branch.*direct"):
        Contract.parse(raw)


def test_spend_ceiling_cannot_be_set_in_a_contract():
    """It is an operator decision per run, not a property of a project."""
    raw = {**MINIMAL, "caps": {"max_spend_usd": 50}}
    with pytest.raises(ContractError):
        Contract.parse(raw)


def test_negative_cap_is_refused():
    raw = {**MINIMAL, "caps": {"max_tasks": -1}}
    with pytest.raises(ContractError, match="must not be negative"):
        Contract.parse(raw)


# -- queue -----------------------------------------------------------------


def test_queue_requires_the_lifecycle_commands():
    """A queue that can claim but not release strands a task on the first failure."""
    with pytest.raises(ContractError, match="queue.release is required"):
        Queue.parse({"kind": "beads", "ready": "bd ready --json",
                     "claim": "bd update {id} --claim", "close": "bd close {id}"})


def test_queue_rejects_an_unknown_placeholder():
    with pytest.raises(ContractError, match="unknown placeholder"):
        Queue.parse({"kind": "beads", "ready": "bd ready --json",
                     "claim": "bd update {issue} --claim",
                     "release": "bd update {id} --status open",
                     "close": "bd close {id}"})


def test_queue_render_substitutes_after_splitting():
    """A task id or comment containing shell syntax stays one argument.

    Substituting before splitting would let a comment body of `; rm -rf .`
    become two commands. There is no shell in the path at all, but the argv
    boundary still has to be right.
    """
    queue = Queue.parse({
        "kind": "beads",
        "ready": "bd ready --json",
        "claim": "bd update {id} --claim",
        "release": "bd update {id} --status open",
        "close": "bd close {id}",
        "comment": "bd comment {id} {text}",
    })
    argv = queue.render("comment", id="a-1", text="failed; rm -rf . && echo hi")
    assert argv == ["bd", "comment", "a-1", "failed; rm -rf . && echo hi"]


def test_queue_excludes_epics_by_default():
    """Handing a container to an agent produces a task that silently does nothing."""
    assert Queue.parse({"kind": "none"}).exclude_types == ("epic",)


def test_queue_none_needs_no_commands():
    assert Queue.parse({"kind": "none"}).enabled is False


# -- fence -----------------------------------------------------------------


def test_fence_matches_an_exact_path():
    assert Fence.parse({"paths": ["db.py"]}).violations(["db.py", "app.py"]) == ["db.py"]


def test_fence_matches_everything_under_a_directory():
    fence = Fence.parse({"paths": ["brain/"]})
    assert fence.violations(["brain/time.md", "brain/handoffs/a.md"]) == [
        "brain/time.md",
        "brain/handoffs/a.md",
    ]


def test_fence_directory_does_not_match_a_similar_prefix():
    """`brain/` must not protect `brainstorm.md`."""
    assert Fence.parse({"paths": ["brain/"]}).violations(["brainstorm.md"]) == []


def test_fence_matches_a_glob():
    fence = Fence.parse({"paths": [".github/workflows/*.yml"]})
    assert fence.violations([".github/workflows/verify.yml"]) == [
        ".github/workflows/verify.yml"
    ]


def test_fence_accepts_a_bare_list():
    assert Fence.parse(["db.py", "brain/"]).paths == ("db.py", "brain/")


def test_fence_refuses_an_absolute_pattern():
    with pytest.raises(ContractError, match="absolute"):
        Fence.parse({"paths": ["/etc/passwd"]})


def test_fence_normalises_a_leading_dot_slash():
    assert Fence.parse({"paths": ["db.py"]}).violations(["./db.py"]) == ["db.py"]


def test_fence_protects_dotfile_directories():
    """Regression: normalising with `lstrip('./')` unguards every dotfile path.

    `lstrip` takes a character set, not a prefix, so `.github/workflows/x.yml`
    normalised to `github/workflows/x.yml` and a fence over `.github/` matched
    nothing. The contract said those paths were protected and they were not --
    which is worse than declaring no fence at all, because nobody would check.
    """
    fence = Fence.parse({"paths": [".github/", ".beads/", ".claude/"]})
    assert fence.violations([".github/workflows/verify.yml"]) == [
        ".github/workflows/verify.yml"
    ]
    assert fence.violations([".beads/issues.jsonl"]) == [".beads/issues.jsonl"]
    assert fence.violations(["./.claude/settings.json"]) == [".claude/settings.json"]


def test_empty_fence_permits_everything():
    assert Fence.parse(None).violations(["db.py", "brain/x.md"]) == []


# -- notes -----------------------------------------------------------------


def _with_notes(notes):
    return {
        "version": 1,
        "name": "demo",
        "commands": {"gate": "make verify"},
        "git": {"base_branch": "main"},
        "notes": notes,
    }


def test_a_contract_with_no_notes_has_an_empty_one():
    contract = Contract.parse(_with_notes(None))
    assert not contract.notes
    assert len(contract.notes) == 0


def test_notes_round_trip_in_order():
    contract = Contract.parse(_with_notes(["first thing", "second thing"]))
    assert contract.notes.items == ("first thing", "second thing")


def test_a_single_string_is_one_note():
    """What a YAML block scalar produces, and it cannot have meant anything else."""
    assert Contract.parse(_with_notes("just the one")).notes.items == ("just the one",)


def test_a_note_is_collapsed_to_one_line():
    """A folded YAML scalar arrives with newlines; the prompt renders bullets."""
    contract = Contract.parse(_with_notes(["wrapped\nover\ntwo lines"]))
    assert contract.notes.items == ("wrapped over two lines",)


def test_blank_notes_are_dropped_rather_than_rendered_as_empty_bullets():
    assert Contract.parse(_with_notes(["real", "", "   "])).notes.items == ("real",)


def test_a_note_that_is_not_a_string_is_refused():
    with pytest.raises(ContractError):
        Contract.parse(_with_notes([{"lesson": "no"}]))


def test_notes_that_are_not_a_list_are_refused():
    with pytest.raises(ContractError):
        Contract.parse(_with_notes({"one": "two"}))


def test_too_many_notes_are_refused_with_what_to_do_instead():
    """The cap is the point: a prompt the agent skims teaches it nothing while
    costing every task, so the answer is to promote them, not to lengthen it."""
    with pytest.raises(ContractError) as exc:
        Contract.parse(_with_notes([f"note {n}" for n in range(contract_mod.MAX_NOTES + 1)]))
    assert "fence.paths" in str(exc.value)


def test_a_note_longer_than_the_limit_is_refused():
    with pytest.raises(ContractError):
        Contract.parse(_with_notes(["x" * (contract_mod.MAX_NOTE_CHARS + 1)]))


def test_a_misspelled_notes_key_is_refused_like_any_other():
    with pytest.raises(ContractError):
        Contract.parse({
            "version": 1, "name": "demo",
            "commands": {"gate": "make verify"},
            "git": {"base_branch": "main"},
            "note": ["singular is a typo"],
        })


# --- knowledge --------------------------------------------------------------


def test_a_contract_with_no_knowledge_section_keeps_recall_off():
    """Off is the default: a new contract has not proven the seam."""
    assert Contract.parse(MINIMAL).knowledge.recall is False


def test_knowledge_recall_true_round_trips():
    raw = {**MINIMAL, "knowledge": {"recall": True}}
    assert Contract.parse(raw).knowledge.recall is True


def test_knowledge_recall_must_be_a_bool():
    """YAML's `recall: yes` is a bool, but `recall: "true"` is a string and a
    string is not a decision."""
    with pytest.raises(ContractError, match="knowledge.recall"):
        Contract.parse({**MINIMAL, "knowledge": {"recall": "true"}})


def test_knowledge_refuses_unknown_keys():
    with pytest.raises(ContractError, match="unknown key"):
        Contract.parse({**MINIMAL, "knowledge": {"recal": True}})
