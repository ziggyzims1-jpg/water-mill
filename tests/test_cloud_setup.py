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

Cost: every run with beads repos does a real Dolt init per repo (~10s), so the
no-database run is shared by every test that only reads its result
(`first_run`), and the tests about the env file and `make install` run in a
parent with no beads repo at all (`bare_world`), which takes well under a second.
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
    # Compact, as `bd export` writes it: the script reads ids with a pattern
    # (`{"_type":"issue","id":"...`), and json.dumps' default ", " and ": "
    # would never match it, so every prefix would silently fall back to the
    # directory name.
    return json.dumps({
        "_type": "issue", "id": f"{prefix}-{suffix}", "title": f"issue {suffix}",
        "status": "open", "priority": 2, "issue_type": "task",
        "created_at": "2026-10-05T21:31:19Z", "updated_at": "2026-10-05T21:31:19Z",
    }, separators=(",", ":"))


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


def _build_world(tmp_path, repos=REPOS):
    """A parent dir of clones (each with an origin), a stub .venv, and a fake make."""
    parent = tmp_path / "parent"
    parent.mkdir()
    for name, prefix, spelling in repos:
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
    scripts.mkdir(parents=True)
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
    # A git identity of its own: `bd init` commits, and with HOME emptied git
    # falls back to guessing one from the host name, which works on a CI
    # runner and fails on a host whose name has no domain (a cloud container),
    # leaving bd init's files staged.
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for k in ("CLAUDE_CODE_REMOTE", "CLAUDE_ENV_FILE", "BD_DOLT_AUTO_PUSH", "BEADS_DIR"):
        env.pop(k, None)
    return {"parent": parent, "env": env, "tmp": tmp_path, "repos": list(repos)}


@pytest.fixture
def world(tmp_path):
    return _build_world(tmp_path)


@pytest.fixture
def bare_world(tmp_path):
    """No sibling carries .beads, so a run does no Dolt work: for the env-file
    and make-install contracts, which do not depend on any repo."""
    return _build_world(tmp_path, repos=())


@pytest.fixture(scope="module")
def first_run(tmp_path_factory):
    """One no-database run, shared by the tests that only read its outcome.

    Two hard cases ride along: a sibling whose .git is broken (sorted first, so
    the rest must still be set up after it fails), and a zimmy-life-tracker
    whose ids are mostly "Zimmy Life Tracker-*" (its laptop prefix, which bd
    init rejects as a database name) beside older zimmy-life-tracker-* ones.
    """
    w = _build_world(tmp_path_factory.mktemp("cloud-setup"))
    broken = w["parent"] / "aaa-broken"
    (broken / ".beads").mkdir(parents=True)
    (broken / ".git").write_text("gitdir: /nonexistent\n")
    zimmy = w["parent"] / "zimmy-life-tracker"
    lines = [_issue("zimmy-life-tracker", s) for s in ("a1", "c3", "c3.1")]
    lines += [_issue("Zimmy Life Tracker", s) for s in ("x1", "x2", "x3", "x4")]
    (zimmy / ".beads" / "issues.jsonl").write_text("\n".join(lines) + "\n")
    _git(zimmy, "commit", "-qam", "renamed prefix")
    # A repo bd init cannot set up at all (no id prefix and no directory name
    # is a valid database name): its config.yaml must still come back intact.
    bad_src = w["tmp"] / "src" / "bad name"
    (bad_src / ".beads").mkdir(parents=True)
    _git(bad_src, "init", "-q", "-b", "main")
    (bad_src / ".beads" / "config.yaml").write_text("# beads config\n" + NESTED.format(name="bad"))
    _write_issues(bad_src, "Bad Name", ["a1"])
    _git(bad_src, "add", "-A")
    _git(bad_src, "commit", "-qm", "initial")
    _git(w["tmp"], "clone", "-q", str(bad_src), str(w["parent"] / "bad name"))
    bad = {"config": (w["parent"] / "bad name" / ".beads" / "config.yaml").read_bytes()}
    before = _snapshot(w)
    proc = _run(w)
    # Everything the tests read is taken now, before the probes below add an
    # issue to each db, so no test depends on the order the others run in.
    counts = {r.name: (_db_count(r, w["env"]), _jsonl_count(r)) for r in _repos(w)}
    after = _snapshot(w)
    remotes = {r.name: subprocess.run(["bd", "dolt", "remote", "list"], cwd=r, env=w["env"],
                                      capture_output=True, text=True).stdout for r in _repos(w)}
    # The prefix a new issue gets is what the db was initialised with.
    probes = {r.name: json.loads(subprocess.run(
        ["bd", "create", "probe", "-t", "task", "--json"], cwd=r, env=w["env"],
        capture_output=True, text=True, check=True).stdout)["id"] for r in _repos(w)}
    bad_repo = w["parent"] / "bad name"
    bad["config_after"] = (bad_repo / ".beads" / "config.yaml").read_bytes()
    bad["diff_after"] = _git(bad_repo, "status", "--porcelain", "--untracked-files=no")
    return {**w, "before": before, "after": after, "proc": proc, "counts": counts,
            "remotes": remotes, "probes": probes, "bad": bad}


def _run(world, script=None, extra_env=None, args=("--force",)):
    script = script or world["parent"] / "water-mill" / "scripts" / "cloud-setup.sh"
    env = {**world["env"], **(extra_env or {})}
    return subprocess.run(["bash", str(script), *args], env=env, cwd=world["tmp"],
                          capture_output=True, text=True, timeout=300)


def _repos(world):
    return [world["parent"] / n for n, _, _ in world["repos"]]


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


def test_without_a_database_it_is_built_from_the_jsonl_alone(first_run):
    assert first_run["proc"].returncode == 0, first_run["proc"].stderr
    before, after = first_run["before"], first_run["after"]
    for n, (db, jsonl) in first_run["counts"].items():
        assert after[n]["diff"] == "", f"{n}: tracked files changed:\n{after[n]['diff']}"
        assert after[n]["head"] == before[n]["head"], f"{n}: HEAD moved (a new commit)"
        assert after[n]["log"] == before[n]["log"], f"{n}: history changed"
        assert after[n]["config"] == before[n]["config"], f"{n}: config.yaml not byte-identical"
        assert db == jsonl, f"{n}: db count {db} != jsonl count {jsonl}"


def test_one_repo_failing_does_not_stop_the_rest_and_is_reported(first_run):
    # aaa-broken sorts first; every real repo after it must still be built.
    assert "aaa-broken: setup failed" in first_run["proc"].stderr
    assert all(db == jsonl for db, jsonl in first_run["counts"].values())


def test_config_yaml_is_restored_even_when_bd_init_fails(first_run):
    assert "bad name: bd init failed" in first_run["proc"].stderr
    bad = first_run["bad"]
    assert bad["config_after"] == bad["config"], "config.yaml left with sync.remote stripped"
    assert bad["diff_after"] == ""


def test_the_prefix_comes_from_the_issue_ids_not_the_directory_name(first_run):
    """cheme-solver's ids are cheme-*: a new issue in its db must get cheme-."""
    assert first_run["probes"]["cheme-solver"].startswith("cheme-")
    assert not first_run["probes"]["cheme-solver"].startswith("cheme-solver-")


def test_a_prefix_bd_init_rejects_is_skipped_even_when_it_is_the_majority(first_run):
    assert first_run["probes"]["zimmy-life-tracker"].startswith("zimmy-life-tracker-")


def test_siblings_without_a_beads_dir_are_ignored(first_run):
    assert list((first_run["parent"] / "no-beads").iterdir()) == []


def test_a_dolt_remote_is_never_wired_so_nothing_can_push(first_run):
    for name, out in first_run["remotes"].items():
        assert "example.invalid" not in out, f"{name}: a Dolt remote was wired: {out}"


def test_an_empty_env_file_variable_is_warned_about(first_run):
    assert "CLAUDE_ENV_FILE is empty" in first_run["proc"].stderr


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



def test_auto_push_is_forced_off_through_the_env_file_once(bare_world):
    envfile = bare_world["tmp"] / "envfile"
    for _ in range(2):
        assert _run(bare_world, extra_env={"CLAUDE_ENV_FILE": str(envfile)}).returncode == 0
    assert envfile.read_text().splitlines().count("export BD_DOLT_AUTO_PUSH=false") == 1


def test_make_install_runs_only_when_there_is_no_venv(bare_world):
    calls = bare_world["tmp"] / "make.calls"
    assert _run(bare_world).returncode == 0
    assert not calls.exists()
    (bare_world["parent"] / "water-mill" / ".venv" / "bin" / "python").unlink()
    assert _run(bare_world).returncode == 0
    assert calls.read_text().startswith("-C ") and calls.read_text().strip().endswith("install")


def test_it_does_nothing_outside_a_cloud_session_without_force(world):
    before = _snapshot(world)
    proc = _run(world, args=())
    assert proc.returncode == 0
    assert _snapshot(world) == before
    assert not any((r / ".beads" / "dolt").exists() or (r / ".beads" / "embeddeddolt").exists()
                   for r in _repos(world))
