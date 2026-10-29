"""The one LANDED rule and bead-id resolution, shared by landed.py and crewlog.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from watermill import crewlog, landed


def _note(tmp_path: Path, body: str, title: str = "zimmy-life-tracker-abc") -> Path:
    path = tmp_path / "abc.md"
    path.write_text(f"# Handoff — {title}\n\n## Tailrace (2026-10-02)\n\n{body}\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "body",
    ["**LANDED**", "**LANDED.** PR #12 merged", "- **LANDED** PR #12", "  **LANDED — PR #12**"],
)
def test_every_form_tailrace_writes_counts_as_landed(tmp_path: Path, body: str):
    found = landed.parse(_note(tmp_path, body), "zimmy-life-tracker")
    assert found is not None and found.bead == "zimmy-life-tracker-abc"
    assert found.landed_on is not None and found.landed_on.isoformat() == "2026-10-02"


@pytest.mark.parametrize(
    "body", ["not LANDED", "will be **LANDED** once CI is green", "Not yet **LANDED**.", "LANDED"]
)
def test_prose_that_mentions_the_word_is_not_landed(tmp_path: Path, body: str):
    assert landed.parse(_note(tmp_path, body), "zimmy-life-tracker") is None


def test_crewlog_uses_the_same_rule(tmp_path: Path):
    for body, want in [("**LANDED.** PR #1", True), ("will be **LANDED** once", False)]:
        rec = crewlog.parse_record(_note(tmp_path, body), "zimmy-life-tracker", {}, {})
        assert rec is not None and (rec["detail"].get("landed_at") is not None) is want


def test_a_role_prefixed_title_resolves_through_the_repos_beads(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".beads").mkdir(parents=True)
    (repo / ".beads" / "issues.jsonl").write_text(
        json.dumps({"id": "Zimmy Life Tracker-9i7.1"}) + "\n", encoding="utf-8"
    )
    path = _note(tmp_path, "**LANDED.** PR #1", title="Millstone, Zimmy Life Tracker-9i7.1")
    found = landed.parse(path, "zimmy-life-tracker", landed.load_beads(repo))
    assert found is not None and found.bead == "zimmy-life-tracker-9i7.1"
    # without the repo's beads the title cannot be resolved (the old behaviour)
    assert landed.parse(path, "zimmy-life-tracker").bead == "millstone-zimmy-life-tracker-9i7.1"
