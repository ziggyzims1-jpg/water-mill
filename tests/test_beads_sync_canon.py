"""The beads-sync pair travels by canon (water-mill-mcn).

Cloud sessions push bead changes only as .beads/issues.jsonl commits on a
claude/* branch; the workflow plus scripts/beads_merge.py land them on main.
"""
from __future__ import annotations

import json
import os
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


def _script(tmp_path):
    script = tmp_path / "beads_merge.py"
    script.write_bytes(sync.canon_files(ROOT, "project")[SCRIPT])
    return script


def test_a_missing_base_is_empty_so_the_first_sync_creates_mains_file(tmp_path):
    # bd init ran on the claude/* branch: main has no .beads/ at all yet.
    script = _script(tmp_path)
    incoming = tmp_path / "branch.jsonl"
    incoming.write_text(bead("x-1", "2026-10-27T00:00:00Z") + "\n"
                        + bead("x-2", "2026-10-27T00:00:01Z") + "\n")
    base = tmp_path / "main" / ".beads" / "issues.jsonl"
    done = subprocess.run([sys.executable, str(script), str(base), str(incoming)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert base.read_bytes() == incoming.read_bytes()
    assert "x-1 x-2" in done.stderr


def test_a_missing_base_still_refuses_a_malformed_line_and_creates_nothing(tmp_path):
    script = _script(tmp_path)
    bad = tmp_path / "bad.jsonl"
    bad.write_text(bead("x-1", "2026-10-27T00:00:00Z") + "\n{not json\n")
    base = tmp_path / "issues.jsonl"
    done = subprocess.run([sys.executable, str(script), str(base), str(bad)],
                          capture_output=True, text=True)
    assert done.returncode == 2
    assert not base.exists()


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def test_the_synced_workflow_commits_a_new_issues_jsonl_onto_a_main_without_one(tmp_path):
    """Run the workflow's own script against a local origin (claudiverse, 2026-10-27)."""
    files = sync.canon_files(ROOT, "project")
    run = yaml.safe_load(files[WORKFLOW].decode())["jobs"]["sync"]["steps"][1]["run"]
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    _git(seed, "config", "user.name", "t")
    _git(seed, "config", "user.email", "t@example.invalid")
    (seed / "scripts").mkdir()
    (seed / SCRIPT).write_bytes(files[SCRIPT])
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "main without .beads")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    _git(seed, "checkout", "-q", "-b", "claude/session")
    (seed / ".beads").mkdir()
    branch_file = bead("x-1", "2026-10-27T00:00:00Z") + "\n"
    (seed / ".beads" / "issues.jsonl").write_text(branch_file)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "bd init")
    _git(seed, "push", "-q", "origin", "claude/session")

    runner = tmp_path / "runner"
    _git(tmp_path, "clone", "-q", str(origin), str(runner))
    temp = tmp_path / "runner-temp"
    temp.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "BRANCH": "claude/session",
           "RUNNER_TEMP": str(temp), "GIT_CONFIG_NOSYSTEM": "1"}

    def workflow():
        done = subprocess.run(["bash", "-e", "-c", run], cwd=runner, env=env,
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
        return done

    workflow()
    assert _git(origin, "show", "main:.beads/issues.jsonl") == branch_file
    head = _git(origin, "rev-parse", "main")
    again = workflow()  # idempotent: nothing new, nothing committed
    assert "main already has everything" in again.stdout
    assert _git(origin, "rev-parse", "main") == head


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
