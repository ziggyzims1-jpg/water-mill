"""The bolter role (water-mill-fwm.4): the crew is canon's agents, and every reader of roles knows it."""

from __future__ import annotations

import re
from pathlib import Path

from watermill import agentcompare, crewlog, recorded, sessionlog

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "canon" / "common" / ".claude" / "agents"


def canon_agents() -> set[str]:
    return {p.stem for p in AGENTS.glob("*.md")}


def test_the_crew_is_exactly_the_agents_canon_ships():
    assert set(recorded.CREW_ROLES) == canon_agents()
    assert recorded.CREW_ROLES == ("millstone", "bolter", "sluice", "tailrace")  # pipeline order


def test_every_role_reader_shares_the_one_crew_list():
    assert sessionlog.CREW_ROLES == agentcompare.CREW_ROLES == recorded.CREW_ROLES
    assert set(recorded.CREW_ROLES) <= set(recorded.ROLES)


def test_a_bolter_transcript_is_a_crew_run():
    assert sessionlog._role("bolter") == "bolter"
    assert sessionlog._role("Bolter-3") == "bolter"
    rec = recorded.build(None, role="bolter", project="demo", bead="demo-abc", pr=3)
    assert rec["agent_kind"] == "mill-crew" and rec["detail"]["crew_key"] == "crew:demo-abc"
    assert rec["detail"]["role"] == "bolter"


def test_crew_bolter_is_a_comparison_group():
    mine = {"agent_kind": "mill-crew", "detail": {"role": "bolter"}}
    other = {"agent_kind": "mill-crew", "detail": {"role": "sluice"}}
    assert agentcompare._matches("crew:bolter", mine)
    assert not agentcompare._matches("crew:bolter", other)


def test_a_handoff_counts_its_bolter_rounds(tmp_path):
    text = ("# Handoff -- demo-abc\n\n## Millstone (2026-10-14)\n\nx\n\n"
            "## Bolter (2026-10-14)\n\nBlocking: none\n\n"
            "## Sluice (2026-10-14)\n\n**Verdict: approve.** nothing pushed.\n")
    assert crewlog._bolter_rounds(text) == 1
    # a Bolter section is not a Sluice round, and does not leak into the Sluice text
    rounds, sluice = crewlog._sluice_text(text)
    assert rounds == 1 and "Blocking" not in sluice


def test_the_bolter_cannot_push_and_sluice_is_the_only_pusher():
    bolter = (AGENTS / "bolter.md").read_text()
    assert "report-only" in bolter.lower()
    assert not re.search(r"^\s*\d+[a-z]?\.\s.*git push origin <branch>", bolter, re.M)
    assert "--role bolter" in bolter and "--tag bolter" in bolter
    assert "mattpocock-skills 1.2.3" in bolter and "MIT" in bolter
    sluice = (AGENTS / "sluice.md").read_text()
    assert "sole pusher" in sluice and "auto-mill" in sluice and "Red before green" in sluice
    assert "Red before green" in (AGENTS / "millstone.md").read_text()
    assert "auto-mill" in (AGENTS / "tailrace.md").read_text()


def test_no_crew_file_hardcodes_the_handoff_directory_for_every_repo():
    """water-mill keeps handoffs in HANDOFF-mill/, so the path is defined once, as $HANDOFFS."""
    for p in AGENTS.glob("*.md"):
        text = p.read_text()
        assert "`$HANDOFFS` is where the repo keeps" in text, p.name
        assert "HANDOFF-mill/" in text, p.name
        for line in text.splitlines():
            if "brain/handoffs/mill" in line:
                assert "`$HANDOFFS` is where the repo keeps" in line, (p.name, line[:80])
