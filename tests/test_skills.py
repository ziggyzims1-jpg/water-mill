"""The 11 mattpocock-skills in canon, adapted for beads (water-mill-fwm.5).

Seams (where the tests sit, and why there):
  1. The canon folder itself (`canon/common/.claude/skills/`): the one master
     copy every target receives. Front matter, attribution and the absence of
     the upstream tracker wording are properties of those files.
  2. `watermill.sync.canon_files`: what a target actually receives after the
     managed header is added. A header placed before the front matter would
     silently stop Claude Code from loading the skill.
  3. `git check-ignore` on water-mill's own tree: a synced skill that a repo's
     .gitignore drops is never committed, so it never reaches a cloud session.
Not tested: Claude Code actually loading the skills (needs a live session).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from watermill import sync

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "canon" / "common" / ".claude" / "skills"
LICENSE = SKILLS / "MATTPOCOCK-SKILLS-LICENSE"

EXPECTED = sorted([
    "domain-modeling", "grill-with-docs", "grilling", "diagnosing-bugs", "code-review",
    "tdd", "codebase-design", "wayfinder", "wizard", "improve-codebase-architecture",
    "to-questionnaire",
])

# Wording of the upstream tracker integration. Each one was replaced with a `bd`
# equivalent; if any comes back, a skill tells an agent to use a tracker the
# repo does not have.
UPSTREAM_TRACKER_PHRASES = [
    "issue tracker", "issue-tracker", "docs/agents", "setup-matt-pocock-skills",
    "github issues", "gitlab", "closes #", ".scratch", "local-markdown",
    "tracker-specific", "tracker doc", "tracker's", "child issue", "native dependency relationship",
]


def front_matter(text: str) -> dict:
    """Parse the front matter the way a loader does: as YAML, or not at all."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no front matter"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), "front matter is not a YAML mapping"
    return data


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def all_skill_files():
    return sorted(p for p in SKILLS.rglob("*") if p.is_file())


def test_exactly_the_eleven_skills_are_in_canon():
    assert sorted(p.name for p in SKILLS.iterdir() if p.is_dir()) == EXPECTED


@pytest.mark.parametrize("name", EXPECTED)
def test_front_matter_names_the_skill_and_describes_it(name):
    fm = front_matter(skill_text(name))
    assert set(fm) <= {"name", "description", "disable-model-invocation"}, sorted(fm)
    assert fm["name"] == name
    assert isinstance(fm["description"], str) and len(fm["description"]) > 20


@pytest.mark.parametrize("name", EXPECTED)
def test_every_skill_carries_the_attribution_block(name):
    expected = (
        f"> **Attribution.** Adapted for beads from the `{name}` skill of "
        "[mattpocock/skills](https://github.com/mattpocock/skills), version 1.2.3, "
        "MIT License, Copyright (c) 2026 Matt Pocock. "
        "License text: `.claude/skills/MATTPOCOCK-SKILLS-LICENSE`."
    )
    assert expected in skill_text(name).splitlines()


def test_the_license_copy_is_the_upstream_mit_text():
    text = LICENSE.read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Matt Pocock" in text
    assert "Permission is hereby granted" in text


@pytest.mark.parametrize("name", EXPECTED)
def test_no_upstream_tracker_wording_remains(name):
    for path in (SKILLS / name).rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in UPSTREAM_TRACKER_PHRASES:
            assert phrase not in text, f"{path.relative_to(SKILLS)} still says {phrase!r}"


def test_cross_references_name_skills_that_ship():
    pattern = re.compile(
        r'Skill tool (?:twice, )?(?:for|with) ((?:"[\w-]+"(?:,? and |, )?)+)'
        r"|`/([\w-]+)` (?:skill|vocabulary|glossary)|the `([\w-]+)` skill"
    )
    seen = 0
    for path in all_skill_files():
        if path.suffix != ".md":
            continue
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            names = re.findall(r'"([\w-]+)"', m.group(1) or "") + [g for g in m.groups()[1:] if g]
            for ref in names:
                seen += 1
                assert ref in EXPECTED, f"{path.relative_to(SKILLS)} points at missing skill {ref!r}"
    assert seen >= 8  # the regex still finds the references it is meant to check


def test_wayfinder_is_expressed_in_bd():
    text = skill_text("wayfinder")
    for needle in ("bd create", "-t epic", "wayfinder:map", "--parent", "bd dep add",
                   "bd ready --parent", "bd update <ticket-id> --claim", "bd close",
                   "--no-inherit-labels"):
        assert needle in text, needle


def test_code_review_reads_the_spec_from_a_bead():
    text = skill_text("code-review")
    assert "bd show <id>" in text


def test_rendered_skills_keep_front_matter_first_and_scripts_keep_their_shebang():
    files = sync.canon_files(ROOT, "project")
    for name in EXPECTED:
        rendered = files[f".claude/skills/{name}/SKILL.md"].decode()
        assert rendered.startswith("---\nname: " + name + "\n")
        assert "managed by water-mill" in rendered
    for rel in (".claude/skills/wizard/template.sh",
                ".claude/skills/diagnosing-bugs/scripts/hitl-loop.template.sh"):
        assert files[rel].decode().startswith("#!/usr/bin/env bash\n# managed by water-mill")
    assert ".claude/skills/MATTPOCOCK-SKILLS-LICENSE" in files


def test_water_mills_own_copies_are_committed_not_ignored():
    paths = sorted(rel for rel in sync.canon_files(ROOT, "project")
                   if rel.startswith(".claude/skills/"))
    assert len(paths) == len(all_skill_files())  # every canon skill file, aux files too
    done = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", *paths],
                          capture_output=True)
    assert done.returncode == 1 and not done.stdout, (
        f"git ignores synced skill files and would drop them: {done.stdout.decode()}")
