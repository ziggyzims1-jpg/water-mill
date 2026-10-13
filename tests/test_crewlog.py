"""Mill crew history: parsing handoffs into agents.jsonl records, idempotently."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from watermill import agentlog, cli, crewlog

LANDED_NOTE = """# Handoff — Zimmy Life Tracker-qyz

## Millstone (2026-10-01)

- branch `bead/qyz`, PR #218 (https://example/pull/218). Not blocked.

## Sluice (2026-10-02)

- **Verdict: approve_after_fixes.** I pushed one commit.

## Sluice (2026-10-02)

- **Verdict: approve.** Nothing to fix. Cites f-20261001-abc123.

## Tailrace (2026-10-02)

**LANDED** — PR #218 MERGED.

- **Findings:** none -- nothing surprising
"""

UNLANDED_NOTE = """# Handoff — zimmy-life-tracker-abc

## Millstone (2026-10-03)

- branch `bead/abc`. Blocked.
"""


def _factory(tmp_path: Path, notes: dict[str, str], beads: list[dict] | None = None,
             present: bool = True) -> Path:
    root = tmp_path / "factory"
    root.mkdir()
    checkout = tmp_path / "zimmy-life-tracker"
    (root / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: zimmy-life-tracker\n"
        "    path: ../zimmy-life-tracker\n"
    )
    if present:
        d = checkout / "brain" / "handoffs" / "mill"
        d.mkdir(parents=True)
        for name, text in notes.items():
            (d / name).write_text(text)
        (checkout / ".beads").mkdir()
        (checkout / ".beads" / "issues.jsonl").write_text(
            "\n".join(json.dumps(b) for b in beads or []) + "\n"
        )
    return root


BEAD = {
    "id": "Zimmy Life Tracker-qyz", "title": "Fix the thing",
    "created_at": "2026-09-30T10:00:00Z", "started_at": "2026-10-01T09:00:00Z",
    "closed_at": "2026-10-02T12:00:00Z",
}


def _records(root: Path) -> dict[str, dict]:
    found, _ = crewlog.collect(root)
    return {r["key"]: r for r in found["zimmy-life-tracker"]}


def test_a_landed_note_becomes_one_full_record(tmp_path):
    root = _factory(tmp_path, {"qyz.md": LANDED_NOTE}, [BEAD])
    rec = _records(root)["crew:zimmy-life-tracker-qyz"]
    assert rec["agent_kind"] == "mill-crew"
    assert rec["outcome"] == "landed"
    assert rec["title"] == "Fix the thing"
    assert rec["started_at"] == "2026-10-01T09:00:00Z"
    assert rec["ended_at"] == "2026-10-02T12:00:00Z"
    d = rec["detail"]
    assert d["pr_number"] == 218 and d["landed_at"] == "2026-10-02"
    assert d["sluice_rounds"] == 2 and d["sluice_pushed_fixes"] is True
    assert d["sluice_verdict"] == "approve"
    assert d["findings_waived"] is True and d["findings_count"] == 1
    assert "detail.pr_number" in rec["fields_inferred"]


def test_an_unlanded_note_is_recorded_as_unlanded_with_no_sluice(tmp_path):
    root = _factory(tmp_path, {"abc.md": UNLANDED_NOTE})
    rec = _records(root)["crew:zimmy-life-tracker-abc"]
    assert rec["outcome"] == "unlanded"
    assert rec["detail"]["sluice_rounds"] == 0
    assert rec["detail"]["sluice_pushed_fixes"] is None
    assert rec["started_at"] is None and rec["ended_at"] is None


def test_bold_landed_with_a_full_stop_counts(tmp_path):
    note = LANDED_NOTE.replace("**LANDED** —", "**LANDED.** Squash-merged")
    rec = _records(_factory(tmp_path, {"qyz.md": note}))["crew:zimmy-life-tracker-qyz"]
    assert rec["outcome"] == "landed"


def test_cost_and_duration_are_null_not_guessed(tmp_path):
    rec = _records(_factory(tmp_path, {"qyz.md": LANDED_NOTE}, [BEAD]))[
        "crew:zimmy-life-tracker-qyz"
    ]
    assert rec["cost_usd"] is None and rec["duration_seconds"] is None


def test_stated_cost_is_taken_and_marked_inferred(tmp_path):
    note = LANDED_NOTE + "\nTotal cost: $1.25 for the run.\n"
    rec = _records(_factory(tmp_path, {"qyz.md": note}))["crew:zimmy-life-tracker-qyz"]
    assert rec["cost_usd"] == 1.25 and "cost_usd" in rec["fields_inferred"]


def test_bead_ids_normalise_so_spaced_and_hyphenated_match(tmp_path):
    # The note is titled with spaces; the bead row uses hyphens.
    bead = dict(BEAD, id="zimmy-life-tracker-qyz")
    rec = _records(_factory(tmp_path, {"qyz.md": LANDED_NOTE}, [bead]))[
        "crew:zimmy-life-tracker-qyz"
    ]
    assert rec["title"] == "Fix the thing"


def test_a_missing_checkout_is_reported_not_raised(tmp_path):
    root = _factory(tmp_path, {}, present=False)
    found, missing = crewlog.collect(root)
    assert "zimmy-life-tracker" not in found
    assert missing == ["zimmy-life-tracker"]


def test_the_factorys_own_handoff_mill_is_read(tmp_path):
    root = _factory(tmp_path, {}, present=False)
    (root / "HANDOFF-mill").mkdir()
    (root / "HANDOFF-mill" / "a7z.md").write_text(
        "# Handoff -- water-mill-a7z\n\n## Millstone (2026-10-13)\n\n- ok\n"
    )
    found, _ = crewlog.collect(root)
    assert found["water-mill"][0]["key"] == "crew:water-mill-a7z"


def test_a_second_sweep_appends_nothing(tmp_path, capsys):
    root = _factory(tmp_path, {"qyz.md": LANDED_NOTE, "abc.md": UNLANDED_NOTE}, [BEAD])
    assert cli.main(["--root", str(root), "agents", "sweep"]) == 0
    first = (root / "runs" / "agents.jsonl").read_text()
    assert len(first.splitlines()) == 2
    cli.main(["--root", str(root), "agents", "sweep"])
    assert (root / "runs" / "agents.jsonl").read_text() == first
    assert "0 record(s) new" in capsys.readouterr().out


def test_dry_run_writes_nothing(tmp_path, capsys):
    root = _factory(tmp_path, {"qyz.md": LANDED_NOTE})
    cli.main(["--root", str(root), "agents", "sweep", "--dry-run"])
    assert not (root / "runs" / "agents.jsonl").exists()
    assert "1 record(s) new" in capsys.readouterr().out


def test_a_bead_that_lands_later_supersedes_without_destroying(tmp_path):
    root = _factory(tmp_path, {"abc.md": UNLANDED_NOTE})
    cli.main(["--root", str(root), "agents", "sweep"])
    note = root.parent / "zimmy-life-tracker/brain/handoffs/mill/abc.md"
    note.write_text(UNLANDED_NOTE + "\n## Tailrace (2026-10-04)\n\n**LANDED** PR #9\n")
    cli.main(["--root", str(root), "agents", "sweep"])
    assert len(agentlog.read_all(root)) == 2
    (only,) = agentlog.read(root)
    assert only["outcome"] == "landed"


@pytest.mark.parametrize("junk", ["not json", "[1]", '{"no": "key"}'])
def test_corrupt_lines_are_skipped(tmp_path, junk):
    p = tmp_path / "runs"
    p.mkdir()
    (p / "agents.jsonl").write_text(junk + "\n")
    assert agentlog.read(tmp_path) == []


@pytest.mark.parametrize("line", [
    "Not **LANDED** yet: CI is red.",
    "It will be **LANDED** once CI settles.",
    "The lander marks the file `**LANDED**`.",
])
def test_landed_mentioned_in_prose_is_not_a_landing(tmp_path, line):
    note = UNLANDED_NOTE + "\n" + line + "\n"
    rec = _records(_factory(tmp_path, {"abc.md": note}))["crew:zimmy-life-tracker-abc"]
    assert rec["outcome"] == "unlanded"


def _sluice_only(body: str) -> str:
    return UNLANDED_NOTE + "\n## Sluice (2026-10-04)\n\n" + body + "\n"


@pytest.mark.parametrize("body, verdict, pushed", [
    ("**Verdict: approve.** Nothing found to fix, nothing pushed.", "approve", False),
    ("- **Verdict: approve** (no fixes pushed).", "approve", False),
    # The verdict outranks prose: here "pushed" is about the implementer.
    ("**Verdict: approve.** Millstone pushed a docs commit before review.", "approve", False),
    ("### Verdict: approve_after_fixes\n\nCommit `83f2c31` pushed.", "approve_after_fixes", True),
    ("**Verdict still approve_after_fixes on all four**", "approve_after_fixes", True),
    ("**Verdict: do_not_merge.** I pushed one fix; the race remains.", "do_not_merge", True),
    ("**Verdict: do_not_merge.** Nothing was pushed.", "do_not_merge", False),
    ("No verdict line. I pushed no fix.", None, False),
])
def test_sluice_verdict_and_pushed_fixes(tmp_path, body, verdict, pushed):
    rec = _records(_factory(tmp_path, {"abc.md": _sluice_only(body)}))[
        "crew:zimmy-life-tracker-abc"
    ]
    assert rec["detail"]["sluice_verdict"] == verdict
    assert rec["detail"]["sluice_pushed_fixes"] is pushed
    assert "detail.sluice_pushed_fixes" in rec["fields_inferred"]


def test_a_title_with_a_role_prefix_still_finds_its_bead(tmp_path):
    note = LANDED_NOTE.replace("# Handoff — Zimmy Life Tracker-qyz",
                               "# Handoff — Millstone, Zimmy Life Tracker-qyz")
    recs = _records(_factory(tmp_path, {"qyz-1.md": note}, [BEAD]))
    assert recs["crew:zimmy-life-tracker-qyz"]["title"] == "Fix the thing"
