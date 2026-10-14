"""The beads-sync pair travels by canon (water-mill-mcn).

Cloud sessions push bead changes only as .beads/issues.jsonl commits on a
claude/* branch; the workflow plus scripts/beads_merge.py land them on main.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from watermill import sync

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ".github/workflows/beads-sync.yml"
SCRIPT = "scripts/beads_merge.py"


def bead(id_, updated, title="t"):
    return json.dumps({"id": id_, "title": title, "updated_at": updated})


def test_canon_carries_both_files_for_git_projects_not_the_workshop():
    project = sync.canon_files(ROOT, "project")
    assert WORKFLOW in project and SCRIPT in project
    assert WORKFLOW not in sync.canon_files(ROOT, "workshop")


def test_the_synced_workflow_is_still_valid_yaml_with_its_header_first():
    text = sync.canon_files(ROOT, "project")[WORKFLOW].decode()
    assert text.startswith("# managed by water-mill (canon/project/")
    doc = yaml.safe_load(text)
    assert doc["jobs"]["sync"]["steps"][1]["run"].count("scripts/beads_merge.py") == 1
    assert doc[True]["push"]["branches"] == ["claude/**"]  # `on` loads as True


def test_the_synced_script_merges_a_claude_branch_without_dropping_mains_beads(tmp_path):
    script = tmp_path / "beads_merge.py"
    script.write_bytes(sync.canon_files(ROOT, "project")[SCRIPT])
    main_file = tmp_path / "main.jsonl"
    branch_file = tmp_path / "branch.jsonl"
    main_file.write_text("\n".join([
        bead("x-1", "2026-10-01T00:00:00Z", "old title"),
        bead("x-2", "2026-10-02T00:00:00Z"),      # only on main: must survive
        bead("x-3", "2026-10-09T00:00:00Z", "main newer"),
    ]) + "\n")
    branch_file.write_text("\n".join([
        bead("x-1", "2026-10-05T00:00:00Z", "changed on branch"),   # changed
        bead("x-3", "2026-10-03T00:00:00Z", "branch older"),         # stale: ignored
        bead("x-4", "2026-10-06T00:00:00Z"),                          # new
    ]) + "\n")
    done = subprocess.run([sys.executable, str(script), str(main_file), str(branch_file)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    merged = {r["id"]: r for r in map(json.loads, main_file.read_text().splitlines())}
    assert list(merged) == ["x-1", "x-2", "x-3", "x-4"]
    assert merged["x-1"]["title"] == "changed on branch"
    assert merged["x-3"]["title"] == "main newer"


def test_the_synced_script_refuses_a_malformed_line_and_leaves_main_alone(tmp_path):
    script = tmp_path / "beads_merge.py"
    script.write_bytes(sync.canon_files(ROOT, "project")[SCRIPT])
    base = tmp_path / "main.jsonl"
    base.write_text(bead("x-1", "2026-10-01T00:00:00Z") + "\n")
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not json\n")
    done = subprocess.run([sys.executable, str(script), str(base), str(bad)],
                          capture_output=True, text=True)
    assert done.returncode == 2
    assert base.read_text() == bead("x-1", "2026-10-01T00:00:00Z") + "\n"


def test_a_project_can_opt_out_of_the_pair_with_sync_exempt():
    plan = sync.make_plan(ROOT, lambda rel: None, "project",
                          {".github/workflows/*": "own CI", "scripts/beads_merge.py": "own copy"})
    rels = [c.rel for c in plan.changes]
    assert WORKFLOW not in rels and SCRIPT not in rels
    assert {r for r, _ in plan.exempt} >= {WORKFLOW, SCRIPT}


def test_a_gitignore_that_drops_the_pair_is_refused_naming_the_rule(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("scripts/\n")
    hits = sync.gitignored(tmp_path, [WORKFLOW, SCRIPT])
    assert [rel for rel, _ in hits] == [SCRIPT]
    assert "scripts/" in hits[0][1]
