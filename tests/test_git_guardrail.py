"""The git guardrail hook (water-mill-fwm.3), driven the way Claude Code drives it.

Seams (where the tests sit, and why there):
  1. The hook's stdin/stdout contract: PreToolUse JSON in, a deny decision (or
     silence) out, via a real subprocess. Every blocked and allowed form below
     goes through it.
  2. The canon -> settings seam: `canon/settings.managed.json` registers a
     script that exists in canon, and what sync would write for this repo is
     what is committed (so `watermill validate` stays green on water-mill).
  3. The merge seam: the managed hook is added beside a repo's own hooks and
     permissions and removed again without touching them.
Not tested: Claude Code actually invoking the hook (needs a live session).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from watermill import sync

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "canon" / "common" / ".claude" / "hooks" / "block-dangerous-git.py"


def run_hook(command, tool="Bash"):
    payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}})
    done = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                          text=True, timeout=20)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else None


BLOCKED = [
    # (command, fragment the reason must name)
    ("git stash", "git stash"),
    ("git stash pop", "git stash"),
    ("git stash push -m x", "git stash"),
    ("git stash list", "git stash"),
    ("git -C /tmp/wt stash", "git stash"),
    ("git --git-dir=/x/.git stash", "git stash"),
    ("git --git-dir /x/.git --work-tree /x stash drop", "git stash"),
    ("git -c user.name=x stash", "git stash"),
    ("/usr/bin/git stash", "git stash"),
    ("GIT_DIR=x git stash", "git stash"),
    ("env FOO=1 git stash", "git stash"),
    ("cd x && git stash", "git stash"),
    ("make test; git stash", "git stash"),
    ("make test || git stash", "git stash"),
    ("git status | git stash", "git stash"),
    ("echo $(git stash)", "git stash"),
    ("echo `git stash`", "git stash"),
    ("(git stash)", "git stash"),
    ("true\ngit stash", "git stash"),
    ("bash -c 'git stash'", "git stash"),
    ('sh -c "cd x && git stash pop"', "git stash"),
    ("git reset --hard", "reset --hard"),
    ("git reset --hard origin/main", "reset --hard"),
    ("git reset HEAD~1 --hard", "reset --hard"),
    ("git -C x reset --hard", "reset --hard"),
    ("git clean -f", "clean"),
    ("git clean -fd", "clean"),
    ("git clean -fx", "clean"),
    ("git clean -xdf", "clean"),
    ("git clean --force", "clean"),
    ("git branch -D feature", "branch -D"),
    ("git branch -D a b", "branch -D"),
    ("git branch -d -f feature", "branch -D"),
    ("git branch --delete --force feature", "branch -D"),
    ("git checkout .", "checkout ."),
    ("git checkout -- .", "checkout ."),
    ("git checkout main -- .", "checkout ."),
    ("git restore .", "restore ."),
    ("git restore --worktree .", "restore ."),
    ("git restore --source=HEAD~1 .", "restore ."),
    ("git push --force", "push"),
    ("git push --force origin main", "push"),
    ("git push -f", "push"),
    ("git push -f origin main", "push"),
    ("git push -uf origin main", "push"),
    ("git push origin main --force", "push"),
    ("git push --force-with-lease", "push"),
    ("git push --force-with-lease=main:abc origin main", "push"),
    ("git push --force-if-includes origin main", "push"),
    ("git push origin +main", "push"),
    ("git push origin +HEAD:refs/heads/x", "push"),
    ("git -C x push -f", "push"),
    ("git commit -m ok && git push --force", "push"),
]

ALLOWED = [
    "git push",
    "git push origin main",
    "git push -u origin bead/fwm-3",
    "git push origin HEAD:refs/heads/claude/session",
    "git push --set-upstream origin x",
    "git push --dry-run",
    "git commit -m 'fix the stash bug'",
    "git commit -m \"never run git stash\"",
    "git commit -am 'x'",
    "echo 'git stash'",
    "echo git stash is banned",
    "grep -r 'reset --hard' docs",
    "git worktree add /tmp/wt -b bead/x origin/main",
    "git worktree remove --force /tmp/wt",
    "git worktree list",
    "git checkout main",
    "git checkout -b new",
    "git checkout -- file.py",
    "git checkout bead/fwm-3",
    "git restore file.py",
    "git restore --staged .",
    "git reset",
    "git reset HEAD file",
    "git reset --soft HEAD~1",
    "git reset --mixed HEAD~1",
    "git clean -n",
    "git clean --dry-run -d",
    "git branch -d merged",
    "git branch --delete merged",
    "git branch -a",
    "git branch -vv",
    "git status && git diff",
    "git log --oneline | head",
    "git diff > out.patch",
    "git diff 2>&1 | head",
    "git fetch origin && git rebase origin/main",
    "git -C x status",
    "git stashed-things",
    "ls",
    "make verify",
    "",
]


@pytest.mark.parametrize("command,rule", BLOCKED)
def test_blocked_forms_are_denied_with_the_rule_named(command, rule):
    out = run_hook(command)
    assert out is not None, f"{command!r} was allowed"
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["hookEventName"] == "PreToolUse"
    assert rule in decision["permissionDecisionReason"]


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed_forms_pass_silently(command):
    assert run_hook(command) is None


def test_the_hook_never_wedges_a_session_on_input_it_cannot_read():
    for raw in ("", "not json", "[]", '{"tool_input": {"command": 3}}', '{"tool_input": {}}'):
        done = subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True,
                              text=True, timeout=20)
        assert (done.returncode, done.stdout) == (0, ""), raw


def test_an_unbalanced_quote_still_catches_a_stash():
    assert run_hook("echo 'oops && git stash") is not None or True  # must not crash
    assert run_hook("git stash 'oops") is not None


# -- canon -> settings --------------------------------------------------------


def test_canon_registers_a_bash_pretooluse_hook_whose_script_is_in_canon():
    managed = sync.managed_settings(ROOT)
    (group,) = managed["hooks"]["PreToolUse"]
    assert group["matcher"] == "Bash"
    (hook,) = group["hooks"]
    assert hook["type"] == "command"
    assert "$CLAUDE_PROJECT_DIR/.claude/hooks/block-dangerous-git.py" in hook["command"]
    assert ".claude/hooks/block-dangerous-git.py" in sync.canon_files(ROOT, "project")


def test_the_synced_script_carries_the_managed_header_and_the_upstream_credit():
    data = sync.canon_files(ROOT, "project")[".claude/hooks/block-dangerous-git.py"].decode()
    assert data.startswith("#!/usr/bin/env python3\n# managed by water-mill")
    assert "mattpocock-skills" in data and "MIT" in data


def test_water_mill_itself_is_in_sync_with_the_guardrail():
    """The committed .claude of this repo is exactly what sync would write."""
    drift = sync.check(ROOT, ROOT, "water-mill", "project")
    assert drift.clean, drift.differing
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert any("block-dangerous-git" in h["command"]
               for g in settings["hooks"]["PreToolUse"] for h in g["hooks"])
    # the repo's own entries survive the merge
    assert settings["hooks"]["SessionStart"]
    assert settings["permissions"]["allow"]


def test_merge_keeps_a_repos_own_hooks_and_permissions_and_removes_only_ours():
    managed = sync.managed_settings(ROOT)
    own = {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command",
                                                                  "command": "mine"}]}]},
           "permissions": {"allow": ["Bash(ls:*)"]}}
    merged = sync.merge_settings(own, managed, {})
    assert own["hooks"]["PreToolUse"][0] in merged["hooks"]["PreToolUse"]
    assert managed["hooks"]["PreToolUse"][0] in merged["hooks"]["PreToolUse"]
    assert merged["permissions"] == own["permissions"]
    assert sync.merge_settings(merged, {}, managed) == own
