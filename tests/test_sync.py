"""Canon sync (water-mill-fwm.2): distribution, the settings merge, drift, opt-outs.

Real git throughout: a bare repository stands in for the remote, so the branch
the sync pushes is read back from it rather than asserted from a mock. The only
seam replaced is the one that talks to GitHub (`open_pr`).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from watermill import sync
from watermill.cli import main
from watermill.errors import RegistryError
from watermill.registry import Registry

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT = "---\nname: x\n---\n\nbody\n"
CONTRACT = "version: 1\nname: app\ncommands:\n  gate: make verify\ngit:\n  base_branch: main\n"


def git(cwd, *args):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"],
           "HOME": str(cwd)}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True, env=env).stdout


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}.items():
        monkeypatch.setenv(k, v)


def make_factory(tmp_path, managed=None):
    root = tmp_path / "factory"
    agents = root / "canon/common/.claude/agents"
    agents.mkdir(parents=True)
    (agents / "crew.md").write_text(AGENT)
    if managed is not None:
        (root / "canon/settings.managed.json").write_text(json.dumps(managed))
    return root


def make_project(tmp_path, files=None):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    app = tmp_path / "app"
    subprocess.run(["git", "init", "-q", "-b", "main", str(app)], check=True)
    (app / "README.md").write_text("hi\n")
    for rel, text in (files or {}).items():
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / rel).write_text(text)
    git(app, "add", "-A")
    git(app, "commit", "-q", "-m", "init")
    git(app, "remote", "add", "origin", str(remote))
    git(app, "push", "-q", "origin", "main")
    return app, remote


class PR:
    """The GitHub seam: opening a PR and finding one by head branch."""

    def __init__(self, opened=None):
        self.calls = []
        self.opened = {} if opened is None else opened  # branch -> url, shared across runs

    def __call__(self, slug, branch, base, title, body):
        self.calls.append((slug, branch, base, title, body))
        self.opened[branch] = "https://example.test/pr/1"
        return self.opened[branch]

    def find(self, slug, branch):
        return self.opened.get(branch, "")


def run_sync(root, app, **kw):
    pr = kw.pop("open_pr", None) or PR(kw.pop("opened", None))
    out = sync.sync_project(root, "app", app, "main", open_pr=pr, find_pr=pr.find, **kw)
    return out, pr


def remote_file(remote, branch, rel):
    return subprocess.run(["git", "-C", str(remote), "show", f"{branch}:{rel}"],
                          capture_output=True, text=True).stdout


# -- rendering --------------------------------------------------------------


def test_header_goes_after_front_matter_so_the_file_still_parses():
    out = sync.render("canon/common/.claude/agents/crew.md", "x.md", AGENT.encode()).decode()
    assert out.startswith("---\nname: x\n---\n<!-- managed by water-mill")
    assert out.endswith("body\n")


def test_header_goes_after_a_shebang():
    out = sync.render("canon/common/h.sh", "h.sh", b"#!/bin/sh\necho\n").decode()
    assert out.splitlines()[0] == "#!/bin/sh"
    assert out.splitlines()[1].startswith("# managed by water-mill")


def test_json_cannot_carry_a_header_and_is_copied_as_is():
    assert sync.render("c", "a.json", b"{}") == b"{}"


# -- the settings merge -----------------------------------------------------

GUARD = {"matcher": "Bash", "hooks": [{"type": "command", "command": "guard.sh"}]}
MANAGED = {"hooks": {"PreToolUse": [GUARD]}, "permissions": {"allow": ["Bash(ls:*)"]}}


def test_merge_keeps_the_repos_own_entries_and_adds_ours():
    own = {"hooks": {"SessionStart": [{"hooks": []}], "PreToolUse": [{"matcher": "Edit"}]},
           "permissions": {"allow": ["Bash(make:*)"]}, "env": {"A": "1"}}
    merged = sync.merge_settings(own, MANAGED, {})
    assert merged["env"] == {"A": "1"}
    assert merged["hooks"]["SessionStart"] == own["hooks"]["SessionStart"]
    assert merged["hooks"]["PreToolUse"] == [{"matcher": "Edit"}, GUARD]
    assert merged["permissions"]["allow"] == ["Bash(make:*)", "Bash(ls:*)"]


def test_merge_is_idempotent():
    once = sync.merge_settings({}, MANAGED, {})
    assert sync.merge_settings(once, MANAGED, MANAGED) == once


def test_an_entry_dropped_from_canon_is_removed_and_the_repos_own_stays():
    once = sync.merge_settings({"permissions": {"allow": ["Bash(make:*)"]}}, MANAGED, {})
    gone = sync.merge_settings(once, {}, MANAGED)
    assert gone == {"permissions": {"allow": ["Bash(make:*)"]}}


def test_unparseable_settings_are_refused_not_overwritten(tmp_path):
    root = make_factory(tmp_path, MANAGED)
    with pytest.raises(sync.SyncError):
        sync.make_plan(root, lambda rel: b"{nope" if rel == sync.SETTINGS_REL else None, "project")


def test_canon_may_only_manage_hooks_and_permissions(tmp_path):
    root = make_factory(tmp_path, {"env": {"A": "1"}})
    with pytest.raises(sync.SyncError):
        sync.managed_settings(root)


def test_no_managed_entries_means_no_settings_file_and_no_manifest(tmp_path):
    root = make_factory(tmp_path)
    plan = sync.make_plan(root, lambda rel: None, "project")
    assert [c.rel for c in plan.changes] == [".claude/agents/crew.md"]


# -- sync_project -----------------------------------------------------------


def test_dry_run_writes_nothing_and_opens_nothing(tmp_path):
    root = make_factory(tmp_path)
    app, remote = make_project(tmp_path)
    out, pr = run_sync(root, app, dry_run=True)
    assert out.state == "would-change" and pr.calls == []
    assert "new      .claude/agents/crew.md" in "\n".join(out.lines)
    assert git(remote, "branch", "--format=%(refname:short)").split() == ["main"]
    assert git(app, "worktree", "list").count("\n") == 1


def test_sync_pushes_a_branch_and_opens_one_pr_leaving_main_alone(tmp_path):
    root = make_factory(tmp_path, MANAGED)
    own = json.dumps({"permissions": {"allow": ["Bash(make:*)"]}})
    app, remote = make_project(tmp_path, {".claude/settings.json": own})
    out, pr = run_sync(root, app)
    assert out.state == "proposed" and out.url == "https://example.test/pr/1"
    (slug, branch, base, _title, body), = pr.calls
    assert base == "main" and branch.startswith("sync/water-mill-")
    assert slug.endswith("remote")  # last path part of the bare repo's url
    assert git(remote, "rev-parse", "main") == git(app, "rev-parse", "HEAD")
    assert remote_file(remote, branch, ".claude/agents/crew.md").startswith(
        "---\nname: x\n---\n<!-- managed by water-mill")
    settings = json.loads(remote_file(remote, branch, ".claude/settings.json"))
    assert settings["permissions"]["allow"] == ["Bash(make:*)", "Bash(ls:*)"]
    manifest = json.loads(remote_file(remote, branch, sync.MANIFEST_REL))
    assert manifest["files"] == [".claude/agents/crew.md"]
    assert ".claude/agents/crew.md" in body
    assert git(app, "worktree", "list").count("\n") == 1  # scratch worktree cleaned up


def test_running_twice_proposes_once(tmp_path):
    root = make_factory(tmp_path)
    app, _ = make_project(tmp_path)
    opened = {}
    run_sync(root, app, opened=opened)
    out, pr = run_sync(root, app, opened=opened)
    assert out.state == "already-proposed" and pr.calls == []
    assert out.url == "https://example.test/pr/1"


def test_a_branch_pushed_without_its_pr_gets_the_pr_next_run(tmp_path):
    """The push landed and opening the PR failed: a rerun must open it, not call it proposed."""
    root = make_factory(tmp_path)
    app, remote = make_project(tmp_path)

    def broken(*_a):
        raise sync.SyncError("opening the pull request failed: 502")

    with pytest.raises(sync.SyncError):
        sync.sync_project(root, "app", app, "main", open_pr=broken, find_pr=lambda s, b: "")
    assert "sync/water-mill-" in git(remote, "branch")
    out, pr = run_sync(root, app)
    assert out.state == "proposed" and len(pr.calls) == 1


def test_a_local_branch_left_by_a_failed_push_does_not_block_the_next_run(tmp_path):
    root = make_factory(tmp_path)
    app, _ = make_project(tmp_path)
    branch = "sync/water-mill-" + sync.make_plan(
        root, sync.git_reader(app, "origin/main"), "project").digest()
    git(app, "branch", branch)  # what a run whose push was refused leaves behind
    out, pr = run_sync(root, app)
    assert out.state == "proposed" and pr.calls[0][1] == branch


def test_settings_that_are_not_an_object_are_refused_not_crashed_on(tmp_path):
    root = make_factory(tmp_path, MANAGED)
    for raw in (b"[]", b"null", b'{"hooks": {"PreToolUse": {}}}',
                b'{"permissions": {"allow": "Bash"}}'):
        with pytest.raises(sync.SyncError):
            sync.make_plan(root, lambda rel, raw=raw: raw if rel == sync.SETTINGS_REL else None,
                           "project")


def test_a_synced_project_is_up_to_date(tmp_path):
    root = make_factory(tmp_path)
    app, _ = make_project(
        tmp_path,
        {".claude/agents/crew.md": sync.render(
            "canon/common/.claude/agents/crew.md", "crew.md", AGENT.encode()).decode()})
    out, pr = run_sync(root, app)
    assert out.state == "up-to-date" and pr.calls == []


def test_exempt_paths_are_skipped_and_reported(tmp_path):
    root = make_factory(tmp_path)
    app, _ = make_project(tmp_path)
    out, pr = run_sync(root, app, exempt={".claude/agents/*": "uses the workshop copy"})
    assert out.state == "up-to-date" and pr.calls == []
    assert "exempt" in "\n".join(out.lines) and "uses the workshop copy" in "\n".join(out.lines)


def test_a_file_that_left_canon_is_removed_only_if_we_put_it_there(tmp_path):
    root = make_factory(tmp_path, MANAGED)
    manifest = json.dumps({"files": [".claude/agents/old.md", ".claude/agents/theirs.md"],
                           "settings": MANAGED})
    present = {".claude/agents/old.md": "x", ".claude/agents/theirs-own.md": "y",
               sync.MANIFEST_REL: manifest}
    plan = sync.make_plan(root, lambda rel: present.get(rel, "").encode() or None, "project")
    removed = [c.rel for c in plan.changes if c.status == "removed"]
    assert removed == [".claude/agents/old.md"]  # theirs.md is absent; theirs-own.md unlisted


def test_a_file_we_put_there_is_kept_once_the_project_is_exempt_from_it(tmp_path):
    root = make_factory(tmp_path, MANAGED)
    manifest = json.dumps({"files": [".claude/agents/old.md"], "settings": MANAGED})
    present = {".claude/agents/old.md": "x", sync.MANIFEST_REL: manifest}
    plan = sync.make_plan(root, lambda rel: present.get(rel, "").encode() or None, "project",
                          {".claude/agents/old.md": "kept by hand"})
    assert [c.rel for c in plan.changes if c.status == "removed"] == []


def test_slug_forms():
    assert sync.repo_slug("https://github.com/o/n") == "o/n"
    assert sync.repo_slug("git@github.com:o/n.git") == "o/n"
    assert sync.repo_slug("http://local_proxy@127.0.0.1:1/git/o/n") == "o/n"


# -- workshop ---------------------------------------------------------------


def test_workshop_is_skipped_in_the_cloud(tmp_path, monkeypatch):
    root = make_factory(tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    ws = tmp_path / "ws"
    (ws / ".claude").mkdir(parents=True)
    monkeypatch.setenv("WATERMILL_WORKSHOP", str(ws))
    out = sync.sync_workshop(root)
    assert out.state == "skipped" and "cloud" in out.lines[0]
    assert not (ws / ".claude/agents").exists()


def test_workshop_is_skipped_when_absent(tmp_path, monkeypatch):
    root = make_factory(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setenv("WATERMILL_WORKSHOP", str(tmp_path / "nope"))
    assert sync.sync_workshop(root).state == "skipped"


def test_workshop_is_written_directly_on_the_laptop(tmp_path, monkeypatch):
    root = make_factory(tmp_path)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    ws = tmp_path / "ws"
    (ws / ".claude").mkdir(parents=True)
    monkeypatch.setenv("WATERMILL_WORKSHOP", str(ws))
    assert sync.sync_workshop(root, dry_run=True).state == "would-change"
    assert not (ws / ".claude/agents").exists()
    assert sync.sync_workshop(root).state == "written"
    assert (ws / ".claude/agents/crew.md").read_text().startswith("---\nname: x")
    assert sync.sync_workshop(root).state == "up-to-date"


# -- validate and drift -----------------------------------------------------


def factory_with_app(tmp_path, extra=""):
    root = make_factory(tmp_path)
    app = tmp_path / "app"
    (app / ".claude/agents").mkdir(parents=True)
    (app / "watermill.yaml").write_text(CONTRACT)
    (root / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: app\n    path: ../app\n" + extra)
    sync.apply_plan(app, sync.make_plan(root, sync.fs_reader(app), "project"))
    sync.apply_plan(root, sync.make_plan(root, sync.fs_reader(root), "project"))
    return root, app


def test_matching_copies_validate(tmp_path):
    root, app = factory_with_app(tmp_path)
    assert main(["--root", str(root), "validate"]) == 0


def test_an_edited_copy_fails_validate(tmp_path, capsys):
    root, app = factory_with_app(tmp_path)
    (app / ".claude/agents/crew.md").write_text("edited here\n")
    assert main(["--root", str(root), "validate"]) == 1
    assert "synced files DIFFER from canon: .claude/agents/crew.md" in capsys.readouterr().out


def test_a_missing_copy_fails_validate(tmp_path):
    root, app = factory_with_app(tmp_path)
    (app / ".claude/agents/crew.md").unlink()
    assert sync.check(root, app, "app").differing == (".claude/agents/crew.md (missing)",)


def test_the_factorys_own_copy_is_checked_too(tmp_path):
    root, app = factory_with_app(tmp_path)
    (root / ".claude/agents/crew.md").write_text("edited in water-mill\n")
    assert main(["--root", str(root), "validate"]) == 1


def test_an_exempt_project_reports_but_passes(tmp_path, capsys):
    root, app = factory_with_app(
        tmp_path, "    sync_exempt:\n      '.claude/agents/*': keeps a local crew\n")
    (app / ".claude/agents/crew.md").write_text("local\n")
    assert main(["--root", str(root), "validate"]) == 0
    assert "exempt from sync: keeps a local crew" in capsys.readouterr().out


def test_an_unregistered_path_is_report_only(tmp_path, capsys):
    root, _ = factory_with_app(tmp_path)
    other = tmp_path / "workshop"
    (other / ".claude/agents").mkdir(parents=True)
    (other / ".claude/agents/crew.md").write_text("different\n")
    assert main(["--root", str(root), "validate", "--sync-path", str(other)]) == 0
    assert "unregistered, report only" in capsys.readouterr().out


def test_the_real_factory_matches_its_own_canon():
    assert sync.check(REPO_ROOT, REPO_ROOT, "water-mill").clean


# -- registry and register --------------------------------------------------


def test_the_crew_exemption_key_is_gone(tmp_path):
    (tmp_path / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: a\n    path: a\n    crew_exempt: old\n")
    with pytest.raises(RegistryError, match="crew_exempt"):
        Registry.load(tmp_path)


def test_sync_exempt_needs_a_reason(tmp_path):
    (tmp_path / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: a\n    path: a\n    sync_exempt:\n      'x/*': ''\n")
    with pytest.raises(RegistryError, match="reason"):
        Registry.load(tmp_path)


def test_hillel_is_registered_without_an_exemption():
    reg = Registry.load(REPO_ROOT)
    assert reg.get("hillel-programming").sync_exempt == {}
    assert all(p.sync_exempt == {} for p in reg.projects)


def test_add_runs_sync_last_and_no_sync_skips_it(tmp_path, monkeypatch, capsys):
    root = make_factory(tmp_path)
    (root / "projects.yaml").write_text("version: 1\nprojects: []\n")
    app, _ = make_project(tmp_path)
    (app / "watermill.yaml").write_text(CONTRACT)
    git(app, "add", "-A")
    git(app, "commit", "-q", "-m", "contract")
    git(app, "push", "-q", "origin", "main")
    seen = []
    monkeypatch.setattr(
        sync, "open_pull_request", lambda *a: seen.append(a) or "https://example.test/pr/2")
    assert main(["--root", str(root), "add", "other", str(app), "--no-sync"]) == 0
    assert seen == []
    (root / "projects.yaml").write_text("version: 1\nprojects: []\n")
    assert main(["--root", str(root), "add", "app", str(app)]) == 0
    assert len(seen) == 1
    out = capsys.readouterr().out
    assert out.index("registered app") < out.index("app: proposed")


# -- fwm.9: a settings hook must never point at a file the PR does not ship --
# Seen 2026-10-14 in zimmy (#228/#229/#230): .gitignore had `.claude/*`, so the sync
# PR carried settings.json but not the hook script; python3 on a missing script
# exits 2, which Claude Code reads as "block", so every Bash call was refused.

HOOK_CANON = REPO_ROOT / "canon/common/.claude/hooks/block-dangerous-git.py"
DENY_STDIN = json.dumps({"tool_input": {"command": "git stash"}})
OK_STDIN = json.dumps({"tool_input": {"command": "git status"}})


def managed_hook_command():
    data = json.loads((REPO_ROOT / "canon/settings.managed.json").read_text())
    return data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def run_hook(project_dir, stdin):
    # The command string exactly as settings.json carries it, through a real shell.
    return subprocess.run(
        ["sh", "-c", managed_hook_command()], input=stdin, capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(project_dir)})


def test_sync_refuses_when_a_file_it_writes_is_gitignored_and_opens_no_pr(tmp_path):
    root = make_factory(tmp_path, MANAGED)  # settings.json ships, the agent does not: zimmy's case
    ignore = ".claude/*\n!.claude/settings.json\n"
    app, remote = make_project(tmp_path, {".gitignore": ignore})
    with pytest.raises(sync.SyncRefusal) as err:
        run_sync(root, app)
    assert ".gitignore:1:.claude/*" in str(err.value)
    assert ".claude/agents/crew.md" in str(err.value)
    assert ".claude/settings.json" not in str(err.value)  # re-included by `!`, so not ignored
    assert git(remote, "branch", "--format=%(refname:short)").split() == ["main"]
    assert git(app, "branch", "--format=%(refname:short)").split() == ["main"]
    assert git(app, "worktree", "list").count("\n") == 1



def test_a_refusal_keeps_a_local_sync_branch_it_did_not_create(tmp_path):
    # A branch left by an earlier run whose push failed is not the refusal's to delete.
    root = make_factory(tmp_path, MANAGED)
    app, _ = make_project(tmp_path, {".gitignore": ".claude/*\n!.claude/settings.json\n"})
    git(app, "fetch", "-q", "origin", "main")
    plan = sync.make_plan(root, sync.git_reader(app, "origin/main"), "project", None)
    branch = f"sync/water-mill-{plan.digest()}"
    git(app, "branch", branch)
    with pytest.raises(sync.SyncRefusal):
        run_sync(root, app)
    assert branch in git(app, "branch", "--format=%(refname:short)").split()

def test_sync_is_not_refused_when_the_gitignore_re_includes_what_it_writes(tmp_path):
    root = make_factory(tmp_path)
    app, _ = make_project(tmp_path, {".gitignore": ".claude/*\n!.claude/agents/\n"})
    out, pr = run_sync(root, app)
    assert out.state == "proposed" and len(pr.calls) == 1


def test_the_managed_hook_fails_open_when_its_script_is_missing(tmp_path):
    res = run_hook(tmp_path, DENY_STDIN)
    assert (res.returncode, res.stdout) == (0, "")


def test_the_managed_hook_still_denies_through_its_json_when_the_script_exists(tmp_path):
    hooks = tmp_path / ".claude/hooks"
    hooks.mkdir(parents=True)
    (hooks / "block-dangerous-git.py").write_bytes(HOOK_CANON.read_bytes())
    denied = run_hook(tmp_path, DENY_STDIN)
    assert denied.returncode == 0
    assert json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    allowed = run_hook(tmp_path, OK_STDIN)
    assert (allowed.returncode, allowed.stdout) == (0, "")


def test_validate_flags_a_settings_hook_pointing_at_a_missing_file(tmp_path, capsys):
    root, app = factory_with_app(tmp_path)
    (app / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": managed_hook_command()}]}
    ]}}))
    assert main(["--root", str(root), "validate"]) == 1
    assert "app: settings hook points at a missing file: .claude/hooks/block-dangerous-git.py" \
        in capsys.readouterr().out
    hooks = app / ".claude/hooks"
    hooks.mkdir()
    (hooks / "block-dangerous-git.py").write_text("#!/usr/bin/env python3\n")
    assert main(["--root", str(root), "validate"]) == 0


# The _git seam (water-mill-faw): stdin and accepted exit codes, so gitignored() does
# not need its own subprocess call. check-ignore exits 1 for "nothing ignored" and 128
# for a real failure; check=False alone cannot tell them apart.
def test_git_feeds_input_on_stdin(tmp_path):
    git(tmp_path, "init", "-q")
    out = sync._git(tmp_path, "check-ignore", "--stdin", input="a\nb\n", ok=(0, 1))
    assert out == ""  # nothing ignored: exit 1, accepted, empty stdout


def test_git_accepts_only_the_listed_exit_codes(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("x\n")
    assert sync._git(tmp_path, "check-ignore", "x", ok=(0, 1)) == "x\n"
    with pytest.raises(sync.SyncError, match="check-ignore"):
        sync._git(tmp_path / "no-such-dir", "check-ignore", "x", ok=(0, 1))  # exit 128
    with pytest.raises(sync.SyncError):
        sync._git(tmp_path, "check-ignore", "y")  # exit 1 is not in the default (0,)
