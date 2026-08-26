"""Git operations on a target repository.

Named `gitwork` rather than `git` so that `import git` inside this package can
never resolve here by accident and shadow a real dependency.

The one rule worth stating up front: **this module never discards work unless
the caller names the run that produced it.** `discard()` takes an explicit list
of protected paths and refuses to run at all when the caller has not confirmed
the run actually started. That is the fix for the single most dangerous bug in
the shell version -- cleanup ran `git clean -fd` on every exit path *including
a refused preflight*, and deleted the untracked loop script and the run's own
logs. A cleanup routine is the most dangerous code in a program, because it
runs on the paths nobody tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .proc import run


@dataclass(frozen=True)
class TreeState:
    """Whether a working tree has anything in it that is not committed."""

    modified: tuple[str, ...]
    untracked: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.modified and not self.untracked

    @property
    def all_paths(self) -> tuple[str, ...]:
        return self.modified + self.untracked

    def describe(self, limit: int = 10) -> str:
        parts = []
        if self.modified:
            parts.append(f"modified: {', '.join(self.modified[:limit])}")
        if self.untracked:
            parts.append(f"untracked: {', '.join(self.untracked[:limit])}")
        return "; ".join(parts) or "clean"


def _git(cwd: Path, *args: str, timeout: float = 120.0):
    return run(["git", *args], cwd=cwd, timeout=timeout, tail_lines=0)


def status(cwd: Path, ignore: tuple[str, ...] = ()) -> TreeState:
    """Read the working tree state.

    Untracked files count as dirty. They are precisely what a `git clean`
    destroys on the first failed task, so a run that starts with them present
    is a run that will delete something nobody asked it to.

    `ignore` names path prefixes to exclude -- the run's own log directory,
    which is created before the first task and would otherwise make every
    check after the first one report a dirty tree.
    """
    result = _git(cwd, "status", "--porcelain")
    modified: list[str] = []
    untracked: list[str] = []
    for line in result.tail.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].strip().strip('"')
        if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in ignore):
            continue
        (untracked if code == "??" else modified).append(path)
    return TreeState(modified=tuple(modified), untracked=tuple(untracked))


def current_branch(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").tail.strip()


def head_sha(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "HEAD").tail.strip()


def changed_paths(cwd: Path, since_sha: str | None = None) -> list[str]:
    """Every path this task touched: staged, unstaged, untracked and committed.

    All four categories, deliberately. A fence check that reads only the
    working tree misses a change the agent already committed, and one that
    reads only the commit misses a change it left staged -- and either miss
    turns the fence from evidence back into a request.
    """
    paths: set[str] = set()
    for args in (("diff", "--name-only"), ("diff", "--name-only", "--cached")):
        paths.update(p for p in _git(cwd, *args).tail.splitlines() if p.strip())
    paths.update(
        p for p in _git(cwd, "ls-files", "--others", "--exclude-standard").tail.splitlines()
        if p.strip()
    )
    if since_sha:
        result = _git(cwd, "diff", "--name-only", f"{since_sha}..HEAD")
        if result.ok:
            paths.update(p for p in result.tail.splitlines() if p.strip())
    return sorted(paths)


def commits_since(cwd: Path, sha: str) -> list[str]:
    result = _git(cwd, "log", "--oneline", f"{sha}..HEAD")
    return [line for line in result.tail.splitlines() if line.strip()] if result.ok else []


def last_commit_message(cwd: Path) -> str:
    return _git(cwd, "log", "-1", "--pretty=%B").tail.strip()


def create_branch(cwd: Path, name: str) -> bool:
    return _git(cwd, "checkout", "-b", name).ok


def checkout(cwd: Path, ref: str) -> bool:
    return _git(cwd, "checkout", ref).ok


def commit_all(cwd: Path, message: str) -> bool:
    if not _git(cwd, "add", "-A").ok:
        return False
    return _git(cwd, "commit", "-m", message).ok


def push(cwd: Path, remote: str, branch: str) -> bool:
    return _git(cwd, "push", "-u", remote, branch, timeout=300.0).ok


def reset_to(cwd: Path, sha: str) -> bool:
    """Move HEAD back to a known commit, discarding anything after it."""
    return _git(cwd, "reset", "--hard", sha).ok


def discard(cwd: Path, protect: tuple[str, ...], run_started: bool) -> bool:
    """Throw away uncommitted work in a target tree.

    `run_started` must be True. It is not a convenience flag: it is the caller
    asserting that this orchestrator put the changes there and so has standing
    to remove them. On a refused preflight the tree was never the run's to
    touch, and the shell version's habit of cleaning anyway is what deleted its
    own script.

    `protect` names paths excluded from the clean -- always the run's log
    directory, since discarding a failure's evidence along with the failure is
    how a run erases the reason it stopped.
    """
    if not run_started:
        return False
    if not _git(cwd, "checkout", "--", ".").ok:
        return False
    args = ["clean", "-fd"]
    for path in protect:
        args += ["-e", path.rstrip("/")]
    return _git(cwd, *args).ok
