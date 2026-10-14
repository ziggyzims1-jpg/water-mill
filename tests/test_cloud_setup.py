"""scripts/cloud-setup.sh, driven with --force against temp git clones.

The script's job is a contract about what it leaves behind in each sibling
checkout, so every test builds a real parent directory of real clones, runs the
real script with the real `bd`, and then asserts on the repos themselves rather
than on anything the script printed:

  * the database holds exactly as many issues as .beads/issues.jsonl,
  * no tracked file changed (the work tree is clean of tracked edits),
  * HEAD did not move (bd init's own commit is dropped),
  * .beads/config.yaml is byte-identical.

The script under test is `CLOUD_SETUP_SCRIPT` (default: this repo's), so the
suite can be pointed at an older copy to prove it goes red there.

Never runs against ~/Documents/code: the script is copied into a temp
`water-mill/scripts/`, and its sibling scan covers only that temp parent.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = Path(os.environ.get("CLOUD_SETUP_SCRIPT", REPO / "scripts" / "cloud-setup.sh"))
BUILDER_SRC = REPO / "scripts" / "cloud-setup.sh"  # always the current script: builds a "db present" starting state

pytestmark = pytest.mark.skipif(
    shutil.which("bd") is None or shutil.which("git") is None,
    reason="needs real bd and git",
)

NESTED = 'sync:\n    remote: "git+https://example.invalid/{name}.git"\n'
FLAT = 'sync.remote: "git+https://example.invalid/{name}.git"\n'

# (directory name, issue-id prefix, config.yaml spelling). Prefixes with hyphens
# and a dotted child suffix are the realistic hard cases.
REPOS = [
    ("water-mill", "water-mill", NESTED),
    ("zimmy-life-tracker", "zimmy-life-tracker", NESTED),
    ("cheme-solver", "cheme", FLAT),
]


def _git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def _issue(prefix, suffix):
    return json.dumps({
        "_type": "issue", "id": f"{prefix}-{suffix}", "title": f"issue {suffix}",
        "status": "open", "priority": 2, "issue_type": "task",
        "created_at": "2026-10-05T21:31:19Z", "updated_at": "2026-10-05T21:31:19Z",
    })


def _write_issues(repo, prefix, suffixes):
    (repo / ".beads" / "issues.jsonl").write_text(
        "\n".join(_issue(prefix, s) for s in suffixes) + "\n")


def _jsonl_count(repo):
    return sum(1 for ln in (repo / ".beads" / "issues.jsonl").read_text().splitlines() if ln.strip())


def _db_count(repo, env):
    proc = subprocess.run(["bd", "list", "--all", "-n", "0", "--json"], cwd=repo, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"{repo.name}: bd list failed: {proc.stderr}"
    return len(json.loads(proc.stdout))


@pytest.fixture
def world(tmp_path):
    """A parent dir of clones (each with an origin), a stub .venv, and a fake make."""
    parent = tmp_path / "parent"
    parent.mkdir()
    origins = tmp_path / "origins"
    origins.mkdir()
    for name, prefix, spelling in REPOS:
        src = tmp_path / "src" / name
        (src / ".beads").mkdir(parents=True)
        _git(src, "init", "-q", "-b", "main")
        (src / ".beads" / "config.yaml").write_text("# beads config\n" + spelling.format(name=name))
        (src / ".beads" / ".gitignore").write_text("dolt/\n")
        (src / "README.md").write_text(name)
        _write_issues(src, prefix, ["a1", "b2", "c3", "c3.1"])
        _git(src, "add", "-A")
        _git(src, "commit", "-qm", "initial")
        _git(tmp_path, "clone", "-q", str(src), str(parent / name))
    # A sibling with no .beads must be left alone.
    (parent / "no-beads").mkdir()
    # water-mill's own script lives in the clone, as in a cloud container.
    scripts = parent / "water-mill" / "scripts"
    scripts.mkdir()
    shutil.copy(SCRIPT, scripts / "cloud-setup.sh")
    # Copied beside it, never run from the real checkout: the script scans the
    # siblings of the checkout it lives in.
    shutil.copy(BUILDER_SRC, scripts / "builder-setup.sh")
    # make install is stubbed: the venv "exists" unless a test removes it.
    py = parent / "water-mill" / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("#!/bin/sh\n")
    py.chmod(py.stat().st_mode | stat.S_IXUSR)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    make = fakebin / "make"
    make.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/make.calls"\n')
    make.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}"}
    for k in ("CLAUDE_CODE_REMOTE", "CLAUDE_ENV_FILE", "BD_DOLT_AUTO_PUSH", "BEADS_DIR"):
        env.pop(k, None)
    return {"parent": parent, "env": env, "tmp": tmp_path}


def _run(world, script=None, extra_env=None, args=("--force",)):
    script = script or world["parent"] / "water-mill" / "scripts" / "cloud-setup.sh"
    env = {**world["env"], **(extra_env or {})}
    return subprocess.run(["bash", str(script), *args], env=env, cwd=world["tmp"],
                          capture_output=True, text=True, timeout=300)


def _repos(world):
    return [world["parent"] / n for n, _, _ in REPOS]


def _snapshot(world):
    return {r.name: {
        "head": _git(r, "rev-parse", "HEAD"),
        "config": (r / ".beads" / "config.yaml").read_bytes(),
        "diff": _git(r, "status", "--porcelain", "--untracked-files=no"),
        "log": _git(r, "log", "--format=%H %s"),
    } for r in _repos(world)}


def _assert_contract(world, before):
    after = _snapshot(world)
    for repo in _repos(world):
        n = repo.name
        assert after[n]["diff"] == "", f"{n}: tracked files changed:\n{after[n]['diff']}"
        assert after[n]["head"] == before[n]["head"], f"{n}: HEAD moved (a new commit)"
        assert after[n]["log"] == before[n]["log"], f"{n}: history changed"
        assert after[n]["config"] == before[n]["config"], f"{n}: config.yaml not byte-identical"
        assert _db_count(repo, world["env"]) == _jsonl_count(repo), f"{n}: db count != jsonl count"


def test_without_a_database_it_is_built_from_the_jsonl_alone(world):
    before = _snapshot(world)
    proc = _run(world)
    assert proc.returncode == 0, proc.stderr
    _assert_contract(world, before)


def test_a_stale_database_is_brought_up_to_the_checked_out_jsonl(world):
    assert _run(world, script=world["parent"] / "water-mill" / "scripts" / "builder-setup.sh").returncode == 0
    # HEAD's jsonl moves on past the container's database (the first cloud run:
    # 27 issues in the db, 29 in the file, `bd show` said "not found").
    for repo, (_, prefix, _) in zip(_repos(world), REPOS, strict=True):
        _write_issues(repo, prefix, ["a1", "b2", "c3", "c3.1", "d4", "e5"])
        _git(repo, "commit", "-qam", "more issues")
    before = _snapshot(world)
    assert all(_db_count(r, world["env"]) == 4 for r in _repos(world))
    proc = _run(world)
    assert proc.returncode == 0, proc.stderr
    assert all(_db_count(r, world["env"]) == 6 for r in _repos(world))
    _assert_contract(world, before)


def test_a_database_that_is_present_is_left_correct_and_a_rerun_changes_nothing(world):
    assert _run(world, script=world["parent"] / "water-mill" / "scripts" / "builder-setup.sh").returncode == 0
    before = _snapshot(world)
    for _ in range(2):
        proc = _run(world)
        assert proc.returncode == 0, proc.stderr
        _assert_contract(world, before)
    assert "beads database present" in proc.stderr


def test_the_prefix_comes_from_the_issue_ids_not_the_directory_name(world):
    """cheme-solver's ids are cheme-*: a db for it must accept a new cheme- issue."""
    assert _run(world).returncode == 0
    repo = world["parent"] / "cheme-solver"
    out = subprocess.run(["bd", "create", "probe", "-t", "task", "--json"], cwd=repo,
                         env=world["env"], capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["id"].startswith("cheme-")


def test_siblings_without_a_beads_dir_are_ignored(world):
    assert _run(world).returncode == 0
    assert list((world["parent"] / "no-beads").iterdir()) == []


def test_a_dolt_remote_is_never_wired_so_nothing_can_push(world):
    assert _run(world).returncode == 0
    for repo in _repos(world):
        out = subprocess.run(["bd", "dolt", "remote", "list"], cwd=repo, env=world["env"],
                             capture_output=True, text=True).stdout
        assert "example.invalid" not in out, f"{repo.name}: a Dolt remote was wired: {out}"


def test_auto_push_is_forced_off_through_the_env_file_once(world):
    envfile = world["tmp"] / "envfile"
    for _ in range(2):
        assert _run(world, extra_env={"CLAUDE_ENV_FILE": str(envfile)}).returncode == 0
    assert envfile.read_text().splitlines().count("export BD_DOLT_AUTO_PUSH=false") == 1


def test_an_empty_env_file_variable_is_warned_about(world):
    proc = _run(world)
    assert "CLAUDE_ENV_FILE is empty" in proc.stderr


def test_make_install_runs_only_when_there_is_no_venv(world):
    calls = world["tmp"] / "make.calls"
    assert _run(world).returncode == 0
    assert not calls.exists()
    (world["parent"] / "water-mill" / ".venv" / "bin" / "python").unlink()
    assert _run(world).returncode == 0
    assert calls.read_text().startswith("-C ") and calls.read_text().strip().endswith("install")


def test_it_does_nothing_outside_a_cloud_session_without_force(world):
    before = _snapshot(world)
    proc = _run(world, args=())
    assert proc.returncode == 0
    assert _snapshot(world) == before
    assert not any((r / ".beads" / "dolt").exists() or (r / ".beads" / "embeddeddolt").exists()
                   for r in _repos(world))
