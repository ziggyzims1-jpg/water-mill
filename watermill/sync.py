"""Canon: the one copy of what every project shares, and how it reaches them.

`canon/` in water-mill holds the files that are kept identical everywhere (today
the three crew agents; later skills, a git guardrail hook, a workshop
CLAUDE.md). `watermill sync <project>` distributes them; `watermill validate`
checks they have not drifted. Layout, chosen over making `.claude/agents` the
canon because the canon must also hold things that are not agents (skills,
hook scripts, managed settings entries, the workshop's files), and a separate
folder says "edit here" without that folder also being water-mill's own
configuration:

    canon/common/<path>            -> <target>/<path>, every target
    canon/project/<path>           -> <target>/<path>, git projects only
    canon/workshop/<path>          -> <workshop>/<path>, the workshop only
    canon/settings.managed.json    -> merged into <target>/.claude/settings.json

Water-mill is a target of its own canon (its `.claude/agents` are rendered
copies), so a copy that was edited in place is drift like any other.

Rules that came out of the design and are pinned by tests:

- A copied file carries a "managed by water-mill, edit there" header, placed
  after front matter or a shebang so the file still parses. A file type that
  cannot carry a comment (JSON) is copied as is.
- `.claude/settings.json` is never overwritten. Only entries listed in
  `canon/settings.managed.json` are merged in; the repo's own entries are left
  alone. What was merged is recorded in `.claude/watermill-managed.json`, so an
  entry dropped from canon is removed next time and nothing else is.
- Git projects receive a pull request, never a push to their base branch. The
  PR branch is named from a digest of the content, so running sync twice
  proposes once. Nothing here merges.
- A project may opt out of paths with `sync_exempt:` (glob -> reason) in the
  registry; an exemption is reported by validate and does not fail it.
- The workshop folder is not a git repository and is written directly, on the
  laptop only.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import proc
from .errors import WatermillError

CANON_DIR = "canon"
SETTINGS_REL = ".claude/settings.json"
MANIFEST_REL = ".claude/watermill-managed.json"
MANAGED_SETTINGS = "settings.managed.json"
WORKSHOP_DEFAULT = "~/Documents/code"
HEADER_TEXT = "managed by water-mill ({rel}); edit it there, then run `watermill sync`"
PERMISSION_KEYS = ("allow", "deny", "ask")


class SyncError(WatermillError):
    exit_code = 1


class SyncRefusal(WatermillError):
    exit_code = 3


Reader = Callable[[str], "bytes | None"]


# -- canon ------------------------------------------------------------------


def _layer(root: Path, name: str) -> dict[str, bytes]:
    base = Path(root) / CANON_DIR / name
    out: dict[str, bytes] = {}
    if base.is_dir():
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            if path.name == ".gitkeep":
                continue
            out[path.relative_to(base).as_posix()] = path.read_bytes()
    return out


def canon_files(root: Path, kind: str) -> dict[str, bytes]:
    """Canon files for a target kind ('project' or 'workshop'), rendered."""
    out: dict[str, bytes] = {}
    for layer in ("common", kind):
        for rel, data in _layer(root, layer).items():
            out[rel] = render(f"{CANON_DIR}/{layer}/{rel}", rel, data)
    return out


def managed_settings(root: Path) -> dict:
    path = Path(root) / CANON_DIR / MANAGED_SETTINGS
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SyncError(f"{path}: not valid JSON: {exc}") from exc
    extra = sorted(set(data) - {"hooks", "permissions"})
    if extra:
        raise SyncError(f"{path}: only `hooks` and `permissions` can be managed, not {extra}")
    return data


def render(source: str, rel: str, data: bytes) -> bytes:
    """The file as a target receives it: canon plus the managed header."""
    header = HEADER_TEXT.format(rel=source)
    suffix = Path(rel).suffix
    text = data.decode("utf-8")
    if suffix == ".md":
        comment = f"<!-- {header} -->\n"
        match = re.match(r"---\n.*?\n---\n", text, re.S)
        if match:
            end = match.end()
            return (text[:end] + comment + text[end:]).encode("utf-8")
        return (comment + text).encode("utf-8")
    if suffix in {".sh", ".py", ".yaml", ".yml"}:
        comment = f"# {header}\n"
        if text.startswith("#!"):
            first, _, rest = text.partition("\n")
            return (first + "\n" + comment + rest).encode("utf-8")
        return (comment + text).encode("utf-8")
    return data


# -- settings merge ----------------------------------------------------------


def merge_settings(existing: dict, managed: dict, previous: dict) -> dict:
    """`existing` with the previously managed entries removed and `managed` added.

    Anything not equal to an entry in `previous` is the repo's own and is kept
    in place. Hook entries are whole matcher groups, compared by value.
    """
    if not isinstance(existing, dict):
        raise SyncError("settings.json: not a JSON object, refusing to touch it")
    out = json.loads(json.dumps(existing))

    hooks = out.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise SyncError("settings.json: `hooks` is not an object")
    hooks = hooks or {}
    events = set(hooks) | set(managed.get("hooks", {})) | set(previous.get("hooks", {}))
    for event in sorted(events):
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise SyncError(f"settings.json: `hooks.{event}` is not a list")
        groups = list(groups)
        gone = previous.get("hooks", {}).get(event, [])
        groups = [g for g in groups if g not in gone]
        for group in managed.get("hooks", {}).get(event, []):
            if group not in groups:
                groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if hooks:
        out["hooks"] = hooks
    else:
        out.pop("hooks", None)

    perms = out.get("permissions")
    if perms is not None and not isinstance(perms, dict):
        raise SyncError("settings.json: `permissions` is not an object")
    perms = perms or {}
    for key in PERMISSION_KEYS:
        items = perms.get(key, [])
        if not isinstance(items, list):
            raise SyncError(f"settings.json: `permissions.{key}` is not a list")
        items = list(items)
        gone = previous.get("permissions", {}).get(key, [])
        items = [i for i in items if i not in gone]
        for item in managed.get("permissions", {}).get(key, []):
            if item not in items:
                items.append(item)
        if items:
            perms[key] = items
        else:
            perms.pop(key, None)
    if perms:
        out["permissions"] = perms
    else:
        out.pop("permissions", None)
    return out


def _settings_is_empty(managed: dict) -> bool:
    return not any(managed.get("hooks", {}).values()) and not any(
        managed.get("permissions", {}).values()
    )


# -- the plan ----------------------------------------------------------------


@dataclass
class Change:
    rel: str
    status: str  # new | changed | removed
    content: bytes | None  # None for removed


@dataclass
class Plan:
    changes: list[Change] = field(default_factory=list)
    exempt: list[tuple[str, str]] = field(default_factory=list)  # (rel, reason)

    @property
    def clean(self) -> bool:
        return not self.changes

    def digest(self) -> str:
        h = hashlib.sha256()
        for c in sorted(self.changes, key=lambda c: c.rel):
            h.update(c.rel.encode())
            h.update(c.content if c.content is not None else b"\0removed")
        return h.hexdigest()[:8]


def _exemption(rel: str, exempt: dict[str, str]) -> str | None:
    for pattern, reason in exempt.items():
        if fnmatch.fnmatch(rel, pattern):
            return reason or "exempt"
    return None


def make_plan(root: Path, read: Reader, kind: str, exempt: dict[str, str] | None = None) -> Plan:
    """What would change in a target whose files `read` returns (None = absent)."""
    exempt = exempt or {}
    plan = Plan()
    wanted = canon_files(root, kind)

    def note(rel: str, reason: str) -> None:
        plan.exempt.append((rel, reason))

    for rel, data in sorted(wanted.items()):
        reason = _exemption(rel, exempt)
        if reason is not None:
            note(rel, reason)
            continue
        have = read(rel)
        if have != data:
            plan.changes.append(Change(rel, "new" if have is None else "changed", data))

    manifest_raw = read(MANIFEST_REL)
    try:
        manifest = json.loads(manifest_raw) if manifest_raw else {}
    except ValueError as exc:
        raise SyncError(f"{MANIFEST_REL}: not valid JSON: {exc}") from exc
    # A file that left canon is removed, but only if we put it there.
    for rel in manifest.get("files", []):
        if rel not in wanted and _exemption(rel, exempt) is None and read(rel) is not None:
            plan.changes.append(Change(rel, "removed", None))

    managed = managed_settings(root)
    previous = manifest.get("settings", {})
    settings_reason = _exemption(SETTINGS_REL, exempt)
    if settings_reason is not None:
        note(SETTINGS_REL, settings_reason)
    elif not _settings_is_empty(managed) or not _settings_is_empty(previous):
        raw = read(SETTINGS_REL)
        try:
            existing = json.loads(raw) if raw else {}
        except ValueError as exc:
            raise SyncError(f"{SETTINGS_REL}: not valid JSON, refusing to touch it: {exc}") from exc
        merged = merge_settings(existing, managed, previous)
        if merged != existing:
            plan.changes.append(
                Change(SETTINGS_REL, "new" if raw is None else "changed",
                       (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            )
    if not _settings_is_empty(managed) or manifest_raw is not None:
        new_manifest = {
            "managed_by": "water-mill",
            "files": sorted(r for r in wanted if _exemption(r, exempt) is None),
            "settings": managed,
        }
        data = (json.dumps(new_manifest, indent=2) + "\n").encode("utf-8")
        if manifest_raw != data:
            plan.changes.append(
                Change(MANIFEST_REL, "new" if manifest_raw is None else "changed", data)
            )
    return plan


def fs_reader(base: Path) -> Reader:
    def read(rel: str) -> bytes | None:
        try:
            return (Path(base) / rel).read_bytes()
        except OSError:
            return None

    return read


def git_reader(repo: Path, ref: str) -> Reader:
    def read(rel: str) -> bytes | None:
        res = _git(repo, "show", f"{ref}:{rel}", check=False, text=False)
        return res if res is not None else None

    return read


def apply_plan(base: Path, plan: Plan) -> None:
    for change in plan.changes:
        path = Path(base) / change.rel
        if change.status == "removed":
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(change.content)
        if change.rel.endswith(".sh"):
            path.chmod(0o755)


# -- git ---------------------------------------------------------------------


def _git(repo: Path, *args: str, check: bool = True, text: bool = True):
    """Run git; stdout as str (bytes with text=False); None if check=False and it failed."""
    import subprocess

    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=False,
        stdin=subprocess.DEVNULL,
    )
    if done.returncode != 0:
        if not check:
            return None
        err = done.stderr.decode("utf-8", "replace").strip()
        raise SyncError(f"git {' '.join(args)} failed in {repo}: {err}")
    return done.stdout.decode("utf-8", "replace") if text else done.stdout


def repo_slug(url: str) -> str:
    """`owner/name` from a remote URL (https, ssh, or the cloud proxy's path form)."""
    cleaned = url.strip().removesuffix("/").removesuffix(".git")
    parts = re.split(r"[/:]", cleaned)
    if len(parts) < 2 or not parts[-1] or not parts[-2]:
        raise SyncError(f"cannot read an owner/name from remote url {url!r}")
    return f"{parts[-2]}/{parts[-1]}"


def find_pull_request(slug: str, branch: str) -> str:
    """The URL of a PR (any state) whose head is `branch`, or "" if there is none. REST."""
    owner = slug.split("/", 1)[0]
    res = proc.run(
        ["gh", "api", "-X", "GET", f"repos/{slug}/pulls",
         "-f", f"head={owner}:{branch}", "-f", "state=all", "--jq", ".[0].html_url // \"\""],
        cwd=Path.cwd(), tail_lines=0,
    )
    if not res.ok:
        raise SyncError(f"looking up the pull request for {branch} failed: {res.tail.strip()}")
    return res.tail.strip()


def open_pull_request(slug: str, branch: str, base: str, title: str, body: str) -> str:
    """Open the PR over REST (`gh pr create` is GraphQL, which the cloud proxy refuses)."""
    res = proc.run(
        ["gh", "api", "-X", "POST", f"repos/{slug}/pulls",
         "-f", f"title={title}", "-f", f"head={branch}", "-f", f"base={base}",
         "-f", f"body={body}", "--jq", ".html_url"],
        cwd=Path.cwd(), tail_lines=0,
    )
    if not res.ok:
        raise SyncError(f"opening the pull request failed: {res.tail.strip()}")
    return res.tail.strip()


@dataclass
class Outcome:
    target: str
    state: str  # up-to-date | would-change | proposed | already-proposed | skipped | written
    lines: list[str] = field(default_factory=list)
    url: str = ""


def _describe(plan: Plan) -> list[str]:
    out = [f"    {c.status:8} {c.rel}" for c in plan.changes]
    out += [f"    exempt   {rel} -- {why}" for rel, why in plan.exempt]
    return out


def sync_project(
    root: Path,
    name: str,
    path: Path,
    base_branch: str,
    remote: str = "origin",
    exempt: dict[str, str] | None = None,
    dry_run: bool = False,
    open_pr: Callable[..., str] | None = None,
    find_pr: Callable[[str, str], str] | None = None,
) -> Outcome:
    """Plan against the project's remote base, then (unless dry) open a PR."""
    path = Path(path)
    if not (path / ".git").exists():
        raise SyncRefusal(f"{name}: {path} is not a git checkout")
    _git(path, "fetch", "--quiet", remote, base_branch)
    ref = f"{remote}/{base_branch}"
    plan = make_plan(root, git_reader(path, ref), "project", exempt)
    out = Outcome(name, "up-to-date", _describe(plan))
    if plan.clean:
        return out
    branch = f"sync/water-mill-{plan.digest()}"
    if dry_run:
        out.state = "would-change"
        out.lines.append(f"    would open a PR from {branch} onto {base_branch}")
        return out
    slug = repo_slug(_git(path, "remote", "get-url", remote).strip())
    title = "chore(sync): water-mill canon"
    body = (
        "Files managed by water-mill (`watermill sync`). Edit the master in "
        "water-mill's `canon/`, not here.\n\n"
        + "\n".join(f"- {c.status} `{c.rel}`" for c in plan.changes)
        + "\n\nThis PR is CI-gated like any other; sync never merges it."
    )
    if _git(path, "ls-remote", "--heads", remote, branch).strip():
        # Pushed before. If the PR was never opened (it failed after the
        # push), open it now rather than reporting a proposal nobody can see.
        existing = (find_pr or find_pull_request)(slug, branch)
        if existing:
            out.state = "already-proposed"
            out.url = existing
            out.lines.append(f"    {branch} is already proposed: {existing}")
            return out
        out.url = (open_pr or open_pull_request)(slug, branch, base_branch, title, body)
        out.state = "proposed"
        out.lines.append(f"    {branch} was pushed but had no PR; opened {out.url}")
        return out

    scratch = Path(tempfile.mkdtemp(prefix="wm-sync-"))
    wt = scratch / "wt"
    try:
        # -B: a local branch left by a run whose push failed is reset, not an error.
        _git(path, "worktree", "add", "-B", branch, str(wt), ref)
        apply_plan(wt, plan)
        _git(wt, "add", "-A")
        _git(wt, "commit", "-q", "-m",
             f"chore(sync): water-mill canon ({len(plan.changes)} file(s))\n\n"
             "Managed by water-mill. Edit the canon copy in water-mill, not these files.")
        _git(wt, "push", "-q", "-u", remote, branch)
        out.url = (open_pr or open_pull_request)(slug, branch, base_branch, title, body)
        out.state = "proposed"
        out.lines.append(f"    opened {out.url}")
    finally:
        _git(path, "worktree", "remove", "--force", str(wt), check=False)
        shutil.rmtree(scratch, ignore_errors=True)
    return out


def workshop_root() -> Path:
    return Path(os.environ.get("WATERMILL_WORKSHOP") or WORKSHOP_DEFAULT).expanduser()


def sync_workshop(root: Path, dry_run: bool = False) -> Outcome:
    """Write canon into the workshop folder directly. Laptop only."""
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        return Outcome("workshop", "skipped", [
            "    skipped: a cloud session cannot reach the workshop folder; "
            "run `watermill sync workshop` on the laptop"])
    ws = workshop_root()
    if not (ws / ".claude").is_dir():
        return Outcome("workshop", "skipped", [
            f"    skipped: {ws}/.claude does not exist on this machine; set "
            "WATERMILL_WORKSHOP if the workshop lives elsewhere"])
    plan = make_plan(root, fs_reader(ws), "workshop")
    out = Outcome("workshop", "up-to-date", _describe(plan))
    if plan.clean:
        return out
    if dry_run:
        out.state = "would-change"
        return out
    apply_plan(ws, plan)
    out.state = "written"
    return out


# -- drift (validate) --------------------------------------------------------


@dataclass(frozen=True)
class Drift:
    label: str
    differing: tuple[str, ...]
    exempt: tuple[tuple[str, str], ...] = ()

    @property
    def clean(self) -> bool:
        return not self.differing


def check(root: Path, target: Path, label: str, kind: str = "project",
          exempt: dict[str, str] | None = None) -> Drift:
    """Drift of a checked-out target against canon (the working tree, not a remote)."""
    plan = make_plan(root, fs_reader(target), kind, exempt)
    differing = tuple(
        c.rel if c.status != "new" else f"{c.rel} (missing)" for c in plan.changes
    )
    return Drift(label, differing, tuple(plan.exempt))
