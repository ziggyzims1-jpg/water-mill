"""A disposable project for the orchestrator to drive.

Every engine test runs against a real git repository with a real gate command
and a real queue, built fresh in a temp directory. Nothing is mocked at the
subprocess boundary, because that boundary is where four of the five bugs in
the previous version of this loop lived: a cleanup that ran on the wrong exit
path, a pipe race, a filter matching text the tool does not print, and a signal
that could not interrupt a foreground child. A test suite that mocks
`subprocess` cannot see any of them.

The agent is a stub. That tests the orchestrator's control flow, not how a real
agent behaves inside it -- a gap this suite cannot close and does not pretend
to. Closing it is what supervised calibration is for.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watermill.contract import Contract  # noqa: E402
from watermill.registry import Project  # noqa: E402

#: A stub agent, parameterised entirely by environment variables so one script
#: covers every behaviour the engine has to handle.
STUB_AGENT = '''#!/usr/bin/env python3
import json, os, subprocess, sys, time

sys.stdin.read()  # consume the prompt; the engine sends it on stdin
mode = os.environ.get("STUB_MODE", "succeed")
cost = os.environ.get("STUB_COST", "0.10")
task = os.environ.get("STUB_TASK_ID", "t-1")

def commit(message):
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", message], check=True,
                   stdout=subprocess.DEVNULL)

if mode == "succeed":
    open("feature.txt", "a").write("work\\n")
    commit(f"feat: do the thing ({task})")
elif mode == "no_task_id":
    open("feature.txt", "a").write("work\\n")
    commit("feat: do the thing but forget to say which")
elif mode == "dirty":
    open("feature.txt", "a").write("uncommitted\\n")
elif mode == "nothing":
    pass
elif mode == "fenced":
    open("PROTECTED.md", "a").write("touched\\n")
    commit(f"feat: touch the fence ({task})")
elif mode == "break_gate":
    open("BROKEN", "w").write("1")
    commit(f"feat: break it ({task})")
elif mode == "escalate":
    print(json.dumps({
        "total_cost_usd": float(cost),
        "result": "ESCALATE\\nThe spec does not say which of two behaviours is wanted.",
    }))
    sys.exit(0)
elif mode == "hang":
    time.sleep(600)
elif mode == "crash":
    sys.stderr.write("boom\\n")
    sys.exit(1)

payload = {"total_cost_usd": float(cost), "result": f"done {task}", "is_error": False}
if os.environ.get("STUB_NO_COST"):
    payload.pop("total_cost_usd")
print(json.dumps(payload))
'''

#: A queue backed by one JSON file. Supports the six contract commands.
STUB_QUEUE = '''#!/usr/bin/env python3
import json, sys
from pathlib import Path

STORE = Path(__file__).parent / "queue.json"

def load():
    return json.loads(STORE.read_text()) if STORE.is_file() else []

def save(rows):
    STORE.write_text(json.dumps(rows, indent=2))

action = sys.argv[1]
rows = load()

if action == "ready":
    print(json.dumps([r for r in rows if r["status"] == "open"]))
elif action == "stale":
    print(json.dumps([r for r in rows if r["status"] == "in_progress"]))
elif action == "show":
    for r in rows:
        if r["id"] == sys.argv[2]:
            print(f"{r['id']}: {r['title']}\\n\\n{r.get('spec', '')}")
            break
elif action in ("claim", "release", "close"):
    target = {"claim": "in_progress", "release": "open", "close": "closed"}[action]
    for r in rows:
        if r["id"] == sys.argv[2]:
            r["status"] = target
    save(rows)
elif action == "comment":
    for r in rows:
        if r["id"] == sys.argv[2]:
            r.setdefault("comments", []).append(sys.argv[3])
    save(rows)
'''


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def fake_project(tmp_path: Path):
    """A git repository with a gate, a queue, a fenced file and one commit."""
    repo = tmp_path / "target"
    repo.mkdir()

    # A gate that passes unless a sentinel file exists. That gives a test a way
    # to make the gate fail *because of the agent's change* rather than by
    # patching the orchestrator -- which is the only version of the check that
    # proves anything.
    gate = repo / "gate.sh"
    gate.write_text("#!/bin/sh\ntest ! -f BROKEN\n")
    gate.chmod(0o755)

    (repo / "PROTECTED.md").write_text("do not touch\n")
    (repo / "README.md").write_text("target\n")

    agent = repo / "stub_agent.py"
    agent.write_text(STUB_AGENT)
    agent.chmod(0o755)

    queue_script = repo / "stub_queue.py"
    queue_script.write_text(STUB_QUEUE)
    queue_script.chmod(0o755)
    (repo / "queue.json").write_text(json.dumps([]))

    # Written before the first commit, deliberately. The queue's state and the
    # stub agent change constantly and are not the project's code; committing
    # them first and ignoring them second leaves them *tracked*, so every
    # claim would show as a modified file and preflight would refuse every run
    # on a dirty tree. A real project's queue state has the same property.
    (repo / ".gitignore").write_text("queue.json\nstub_agent.py\nstub_queue.py\n")

    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Water Mill Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")

    return repo


@pytest.fixture
def set_tasks(fake_project):
    def _set(*tasks):
        rows = []
        for index, task in enumerate(tasks, start=1):
            if isinstance(task, str):
                task = {"id": task}
            rows.append(
                {
                    "id": task.get("id", f"t-{index}"),
                    "title": task.get("title", "a task"),
                    "spec": task.get("spec", "Do the thing described here."),
                    "issue_type": task.get("issue_type", "task"),
                    "status": task.get("status", "open"),
                }
            )
        (fake_project / "queue.json").write_text(json.dumps(rows, indent=2))
        return rows

    return _set


@pytest.fixture
def contract_for(fake_project):
    def _make(**overrides):
        queue_script = fake_project / "stub_queue.py"
        raw = {
            "version": 1,
            "name": "target",
            "commands": {"gate": "./gate.sh"},
            "git": {"base_branch": "main", "target": "direct"},
            "queue": {
                "kind": "command",
                "ready": f"{sys.executable} {queue_script} ready",
                "stale": f"{sys.executable} {queue_script} stale",
                "show": f"{sys.executable} {queue_script} show {{id}}",
                "claim": f"{sys.executable} {queue_script} claim {{id}}",
                "release": f"{sys.executable} {queue_script} release {{id}}",
                "close": f"{sys.executable} {queue_script} close {{id}}",
                "comment": f"{sys.executable} {queue_script} comment {{id}} {{text}}",
            },
            "fence": {"paths": ["PROTECTED.md", "gate.sh"]},
        }
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(raw.get(key), dict):
                raw[key] = {**raw[key], **value}
            else:
                raw[key] = value
        return Contract.parse(raw)

    return _make


@pytest.fixture
def project_for(fake_project, tmp_path):
    return Project(
        name="target",
        path=fake_project,
        contract_path=None,
        enabled=True,
        root=tmp_path,
    )


@pytest.fixture
def stub_agent_command(fake_project):
    return f"{sys.executable} {fake_project / 'stub_agent.py'}"


@pytest.fixture
def stub_env(monkeypatch):
    """Configure the stub agent's behaviour for one test."""

    def _set(mode: str, **extra):
        monkeypatch.setenv("STUB_MODE", mode)
        for key, value in extra.items():
            monkeypatch.setenv(key, str(value))

    # Clear anything a previous test in the same process left behind.
    for key in ("STUB_MODE", "STUB_COST", "STUB_TASK_ID", "STUB_NO_COST"):
        monkeypatch.delenv(key, raising=False)
    return _set


@pytest.fixture(autouse=True)
def _no_production_markers(monkeypatch):
    """The suite must not inherit a marker that refuses every run."""
    for name in ("FLASK_ENV", "NODE_ENV", "APP_ENV", "ENVIRONMENT", "RAILS_ENV",
                 "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")


@pytest.fixture(autouse=True)
def _no_real_home(tmp_path_factory, monkeypatch):
    """`agents sweep` defaults to ~/.claude/projects, which holds private
    transcripts; no test may reach them by forgetting --sessions-dir."""
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
