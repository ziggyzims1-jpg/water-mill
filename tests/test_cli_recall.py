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


def test_annotate_finding_cli_batch_is_all_or_nothing(tmp_path, capsys):
    import json

    from watermill import knowledge

    knowledge.record(tmp_path, cell="", kind="lesson", text="one",
                     root_cause="none", tags=("t",))
    fid = knowledge.read(tmp_path)[0].id
    path = tmp_path / knowledge.KNOWLEDGE_FILENAME
    size = path.stat().st_size

    batch = tmp_path / "batch.jsonl"
    batch.write_text(json.dumps({"id": fid, "cause": "gate-hole"}) + "\n"
                     + json.dumps({"id": "f-nope", "tags": ["x"]}) + "\n")
    assert cli.main(["--root", str(tmp_path), "annotate-finding", "--batch", str(batch)]) == 1
    assert path.stat().st_size == size, "a bad row refuses the whole batch"

    batch.write_text(json.dumps({"id": fid, "cause": "gate-hole", "tags": ["x"]}) + "\n")
    assert cli.main(["--root", str(tmp_path), "annotate-finding", "--batch", str(batch),
                     "--json"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])[0]["id"] == fid
    assert knowledge.get(tmp_path, fid).root_cause == "gate-hole"

    assert cli.main(["--root", str(tmp_path), "annotate-finding", fid,
                     "--destination", "gate"]) == 0
    assert knowledge.get(tmp_path, fid).destination == "gate"
    assert cli.main(["--root", str(tmp_path), "annotate-finding", fid]) == 2
