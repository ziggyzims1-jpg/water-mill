"""Landing a run's work: open a pull request, prove it green, merge it.

The forge is a stub that records every call it receives, so these tests assert
on **what was actually asked of the forge** rather than on what the module
reported about itself. That is the same rule the engine's tests follow about the
repository: the orchestrator's own account of its behaviour is not evidence.

The test this file exists for is
`test_a_failed_verify_never_reaches_the_merge`. Everything else here is a
precondition around it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watermill import land  # noqa: E402
from watermill.errors import ContractError  # noqa: E402

STUB_FORGE = '''#!/usr/bin/env python3
"""A forge that records what it was asked to do and fails on request."""
import json, os, pathlib, sys

step = sys.argv[1]
log = pathlib.Path(os.environ["FORGE_LOG"])
calls = json.loads(log.read_text()) if log.exists() else []
calls.append([step, *sys.argv[2:]])
log.write_text(json.dumps(calls))
print(f"{step}: stub forge")
sys.exit(1 if step in os.environ.get("FORGE_FAIL", "").split(",") else 0)
'''


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


@pytest.fixture
def forge(fake_project, tmp_path, monkeypatch):
    """A stub forge, plus the log of everything it was asked to do."""
    script = fake_project / "stub_forge.py"
    script.write_text(STUB_FORGE)
    log = tmp_path / "forge-calls.json"
    monkeypatch.setenv("FORGE_LOG", str(log))

    def calls() -> list[list[str]]:
        return json.loads(log.read_text()) if log.exists() else []

    calls.script = script  # type: ignore[attr-defined]
    return calls


@pytest.fixture
def review_contract(contract_for, fake_project):
    def _make(**overrides):
        script = fake_project / "stub_forge.py"
        review = {
            "create": f"{sys.executable} {script} create --base {{base}} "
                      f"--head {{branch}} --title {{title}} --body {{body}}",
            "verify": f"{sys.executable} {script} verify {{branch}}",
            "merge": f"{sys.executable} {script} merge {{branch}}",
        }
        review.update(overrides.pop("review", {}))
        git = {"target": "branch", "base_branch": "main", "remote": "origin"}
        git.update(overrides.pop("git", {}))
        return contract_for(git=git, review=review, **overrides)

    return _make


@pytest.fixture
def pushed_branch(fake_project, tmp_path):
    """A work branch with a commit on it, present on a real remote."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True,
                   capture_output=True)
    _git(fake_project, "remote", "add", "origin", str(remote))
    _git(fake_project, "push", "-u", "origin", "main")

    branch = "watermill/run-1"
    _git(fake_project, "checkout", "-b", branch)
    (fake_project / "feature.txt").write_text("work\n")
    _git(fake_project, "add", "-A")
    _git(fake_project, "commit", "-m", "feat: the thing (t-1)")
    _git(fake_project, "push", "-u", "origin", branch)
    return branch


def _summary(branch: str = "watermill/run-1", **overrides) -> dict:
    summary = {
        "run_id": "run-1",
        "work_branch": branch,
        "commits": ["abc1234 feat: the thing (t-1)"],
        "refused": False,
        "counts": {"attempted": 1, "completed": 1, "failed": 0, "escalated": 0},
        "spend_cents": 250,
        "halt_reason": "queue exhausted",
        "tasks": [{"id": "t-1", "title": "the thing", "outcome": "completed"}],
        "anomalies": [],
    }
    summary.update(overrides)
    return summary


# -- the one this file exists for ------------------------------------------


def test_a_failed_verify_never_reaches_the_merge(
    project_for, review_contract, forge, pushed_branch, monkeypatch
):
    """A red build stops the landing, whatever the forge thinks of the branch.

    This is the same argument the engine makes about the gate: a check that runs
    after the decision it informs is decoration. If this ever passes while
    `merge` appears in the call log, the merge gate has become advisory and the
    whole review block is worth less than nothing -- it would be automation that
    looks like verification.
    """
    monkeypatch.setenv("FORGE_FAIL", "verify")

    result = land.land(project_for, review_contract(), _summary())

    assert result.failed
    assert not result.merged
    steps = [call[0] for call in forge()]
    assert steps == ["create", "verify"], f"the forge was asked to {steps}"
    assert "merge" not in steps


def test_a_failed_create_never_reaches_the_verify(
    project_for, review_contract, forge, pushed_branch, monkeypatch
):
    monkeypatch.setenv("FORGE_FAIL", "create")

    result = land.land(project_for, review_contract(), _summary())

    assert result.failed
    assert [call[0] for call in forge()] == ["create"]


# -- the happy path ---------------------------------------------------------


def test_a_green_run_is_created_verified_and_merged(
    project_for, review_contract, forge, pushed_branch, fake_project
):
    result = land.land(project_for, review_contract(), _summary())

    assert not result.failed
    assert result.merged
    assert [call[0] for call in forge()] == ["create", "verify", "merge"]
    # Back on the base branch: the next run's preflight checks it, and a
    # repository parked on a merged branch refuses in a way that reads like a
    # bug the first time you meet it.
    assert _git(fake_project, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_the_branch_and_base_reach_the_forge_as_arguments(
    project_for, review_contract, forge, pushed_branch
):
    """Substitution happens after splitting, so a title with spaces is one argv.

    The title is built from the task and routinely contains spaces, quotes and
    the occasional colon. If any of that reached a shell the command would
    either break or, worse, not break.
    """
    land.land(project_for, review_contract(), _summary())

    create = next(call for call in forge() if call[0] == "create")
    assert "--base" in create and "main" in create
    assert "watermill/run-1" in create
    title = create[create.index("--title") + 1]
    assert title == "t-1: the thing"


def test_no_merge_stops_after_a_green_verify(
    project_for, review_contract, forge, pushed_branch
):
    result = land.land(project_for, review_contract(), _summary(), merge=False)

    assert not result.failed
    assert not result.merged
    assert [call[0] for call in forge()] == ["create", "verify"]
    assert "green and waiting" in result.render()


def test_a_contract_with_no_merge_command_verifies_and_stops(
    project_for, review_contract, forge, pushed_branch
):
    """Open and prove green, and leave the button to a person.

    The deliberately supported middle of the ramp, not a broken configuration.
    """
    contract = review_contract(review={"merge": None})

    result = land.land(project_for, contract, _summary())

    assert not result.failed
    assert not result.merged
    assert [call[0] for call in forge()] == ["create", "verify"]


# -- the refusals -----------------------------------------------------------


def test_a_project_with_no_review_block_refuses_rather_than_guessing(
    project_for, contract_for, forge, pushed_branch
):
    result = land.land(project_for, contract_for(git={"target": "branch"}), _summary())

    assert result.refused
    assert "review.create" in result.refused
    assert forge() == [], "a refusal must not touch the forge"


def test_direct_commits_have_nothing_to_land(
    project_for, review_contract, forge, pushed_branch
):
    contract = review_contract(git={"target": "direct", "base_branch": "main"})

    result = land.land(project_for, contract, _summary())

    assert result.refused
    assert "nothing to land" in result.refused
    assert forge() == []


def test_a_run_that_kept_nothing_is_not_landed(
    project_for, review_contract, forge, pushed_branch
):
    result = land.land(project_for, review_contract(), _summary(commits=[]))

    assert result.refused
    assert "kept nothing" in result.refused
    assert forge() == []


def test_a_refused_run_is_not_landed(project_for, review_contract, forge, pushed_branch):
    result = land.land(project_for, review_contract(), _summary(refused=True))

    assert result.refused
    assert "refused at preflight" in result.refused
    assert forge() == []


def test_a_branch_that_never_reached_the_remote_refuses(
    project_for, review_contract, forge, pushed_branch, fake_project
):
    """The push failing is the finding; opening a pull request would bury it."""
    _git(fake_project, "push", "origin", "--delete", pushed_branch)

    result = land.land(project_for, review_contract(), _summary())

    assert result.refused
    assert "not on origin" in result.refused
    assert forge() == []


def test_a_dirty_tree_refuses_before_anything_is_opened(
    project_for, review_contract, forge, pushed_branch, fake_project
):
    (fake_project / "README.md").write_text("edited by somebody\n")

    result = land.land(project_for, review_contract(), _summary())

    assert result.refused
    assert "dirty" in result.refused
    assert forge() == []


# -- what the contract will not let you express ----------------------------


def test_merge_without_verify_is_refused_at_parse_time(contract_for, fake_project):
    """The dangerous combination is unrepresentable, not merely discouraged.

    Checked in the schema rather than in `land`, so a contract that could merge
    without verifying fails `watermill validate` in the morning instead of at
    3am on the one night it matters.
    """
    with pytest.raises(ContractError, match="review.verify is required"):
        contract_for(review={"create": "gh pr create", "merge": "gh pr merge"})


def test_a_review_command_with_an_unknown_placeholder_is_refused(contract_for):
    with pytest.raises(ContractError, match="unknown placeholder"):
        contract_for(review={"create": "gh pr create --head {id}"})


def test_verify_without_create_is_refused(contract_for):
    with pytest.raises(ContractError, match="review.create is required"):
        contract_for(review={"verify": "gh pr checks"})
