"""`run` takes recall from the contract unless a flag says otherwise.

The precedence is the whole feature: a project that has proven the seam keeps
the tool on without anyone remembering a flag, and a person can still switch
it either way for one run.
"""
from watermill import cli
from watermill.contract import Contract

MINIMAL = {
    "version": 1,
    "name": "demo",
    "commands": {"gate": "make verify"},
    "git": {"base_branch": "main"},
}


def _contract(recall: bool | None):
    raw = dict(MINIMAL)
    if recall is not None:
        raw["knowledge"] = {"recall": recall}
    return Contract.parse(raw)


def test_no_flag_takes_the_contract_value():
    assert cli._resolve_recall(None, _contract(True)) is True
    assert cli._resolve_recall(None, _contract(False)) is False
    assert cli._resolve_recall(None, _contract(None)) is False


def test_recall_flag_wins_over_a_contract_that_says_off():
    assert cli._resolve_recall(True, _contract(False)) is True


def test_no_recall_flag_wins_over_a_contract_that_says_on():
    assert cli._resolve_recall(False, _contract(True)) is False


def test_the_parser_leaves_recall_unset_when_no_flag_is_given():
    parser = cli.build_parser()
    assert parser.parse_args(["run", "demo", "--max-spend", "1"]).recall is None
    assert parser.parse_args(["run", "demo", "--max-spend", "1", "--recall"]).recall is True
    assert parser.parse_args(["run", "demo", "--max-spend", "1", "--no-recall"]).recall is False
