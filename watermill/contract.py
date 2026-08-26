"""The project contract: everything the orchestrator needs to know about a target.

Water Mill knows nothing about any particular project. It knows how to claim a
task, run a gate, check a diff and write a report; *which* commands do those
things is declared by the target in a `watermill.yaml`. That file is the entire
coupling surface between the factory and a project, and it is deliberately
small enough to read in one screen.

Two rules shape the schema:

**Unknown keys are an error, not a warning.** A typo in `fence` means the run
believes it has a fence and does not. Every misspelling this schema can catch
at load time is one that cannot become a silent absence at 3am, so validation
is strict and total: the whole contract parses or none of it applies.

**Only `name`, `commands.gate` and `git.base_branch` are required.** Everything
else defaults, because a project that cannot yet answer a question should get
the conservative answer rather than a blank. The conservative answer is
occasionally "refuse": there is no default spend ceiling and no default backup
check, and a project declaring neither is allowed to run only when the operator
says so explicitly.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ContractError

CONTRACT_VERSION = 1

#: Filename looked for inside a target repository.
CONTRACT_FILENAME = "watermill.yaml"

#: Placeholders a queue command template may use. Any other `{...}` is an error,
#: because an unsubstituted placeholder would reach the shell as a literal brace
#: and the command would fail in a way that reads like the queue being empty.
QUEUE_PLACEHOLDERS = {"id", "text"}


def _require_mapping(value: Any, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f"{where}: expected a mapping, got {type(value).__name__}")
    return value


def _reject_unknown(got: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(got) - allowed)
    if unknown:
        raise ContractError(
            f"{where}: unknown key(s) {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}. "
            "Unknown keys are refused rather than ignored -- a misspelled key is "
            "indistinguishable from a missing one once the run has started."
        )


@dataclass(frozen=True)
class Commands:
    """Shell commands the orchestrator runs inside the target's working tree.

    `gate` is the only one that is required, and it is the only one whose exit
    status is treated as evidence about the code. Water Mill runs it twice per
    task -- once as a baseline before any work, once after -- and a task whose
    gate does not pass is discarded regardless of what the agent reported.
    """

    gate: str
    install: str | None = None
    backup_check: str | None = None
    backup_run: str | None = None

    @classmethod
    def parse(cls, raw: Any) -> Commands:
        got = _require_mapping(raw, "commands")
        _reject_unknown(got, {"gate", "install", "backup_check", "backup_run"}, "commands")
        gate = got.get("gate")
        if not gate or not str(gate).strip():
            raise ContractError(
                "commands.gate is required. It is the merge gate -- the one "
                "command whose result decides whether a task's work is kept."
            )
        return cls(
            gate=str(gate).strip(),
            install=_opt_str(got.get("install")),
            backup_check=_opt_str(got.get("backup_check")),
            backup_run=_opt_str(got.get("backup_run")),
        )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class Git:
    """How work reaches the repository.

    `target: direct` commits onto `base_branch`; `target: branch` opens
    `watermill/<run-id>` and pushes it. Direct is not the default here even
    though it is the right answer for a mature project, because a project the
    factory has never driven has not yet earned it -- see docs/SAFETY.md.
    """

    base_branch: str
    target: str = "branch"
    remote: str = "origin"

    @classmethod
    def parse(cls, raw: Any) -> Git:
        got = _require_mapping(raw, "git")
        _reject_unknown(got, {"base_branch", "target", "remote"}, "git")
        base = _opt_str(got.get("base_branch"))
        if not base:
            raise ContractError("git.base_branch is required")
        target = _opt_str(got.get("target")) or "branch"
        if target not in ("direct", "branch"):
            raise ContractError(f"git.target must be 'direct' or 'branch', got {target!r}")
        return cls(base_branch=base, target=target, remote=_opt_str(got.get("remote")) or "origin")


@dataclass(frozen=True)
class Queue:
    """The work queue adapter.

    Beads is the queue Water Mill was built against, but nothing in the
    orchestrator imports it: the queue is six shell commands and a JSON shape.
    `kind: none` disables the queue entirely, which is what a project uses
    while it still has a human handing it one task at a time.

    `ready` and `stale` must emit JSON -- a list of objects, or an object with a
    list under `issues`/`items`/`results`. Parsing a rendered table was how the
    original loop silently handed epics to an agent as work, and how a
    `grep -q` race under `pipefail` convinced it the queue was empty while 27
    tasks sat in it. JSON is not a preference here; it is the fix for two
    measured bugs.
    """

    kind: str = "none"
    ready: str | None = None
    stale: str | None = None
    show: str | None = None
    claim: str | None = None
    release: str | None = None
    close: str | None = None
    comment: str | None = None
    #: Issue types that are containers rather than work. Filtered out of `ready`.
    exclude_types: tuple[str, ...] = ("epic",)

    _FIELDS = {
        "kind", "ready", "stale", "show", "claim", "release", "close",
        "comment", "exclude_types",
    }

    @classmethod
    def parse(cls, raw: Any) -> Queue:
        got = _require_mapping(raw, "queue")
        _reject_unknown(got, cls._FIELDS, "queue")
        kind = _opt_str(got.get("kind")) or "none"
        if kind not in ("beads", "command", "none"):
            raise ContractError(
                f"queue.kind must be 'beads', 'command' or 'none', got {kind!r}"
            )

        templates = {
            key: _opt_str(got.get(key))
            for key in ("ready", "stale", "show", "claim", "release", "close", "comment")
        }
        for key, template in templates.items():
            if template is not None:
                _validate_template(template, f"queue.{key}")

        if kind != "none":
            for key in ("ready", "claim", "release", "close"):
                if not templates[key]:
                    raise ContractError(
                        f"queue.{key} is required when queue.kind is {kind!r}. "
                        "A queue that can claim but not release strands a task on "
                        "the first failure."
                    )

        excl = got.get("exclude_types", ("epic",))
        if isinstance(excl, str):
            excl = [excl]
        if not isinstance(excl, (list, tuple)):
            raise ContractError("queue.exclude_types must be a list of strings")

        return cls(
            kind=kind,
            exclude_types=tuple(str(x).strip().lower() for x in excl if str(x).strip()),
            **templates,
        )

    @property
    def enabled(self) -> bool:
        return self.kind != "none"

    def render(self, key: str, **params: str) -> list[str]:
        """Render one queue command into an argv list.

        Substitution happens *after* splitting, so a task id or a comment body
        containing a space, a quote or a semicolon becomes one argument rather
        than shell syntax. There is no shell involved at any point.
        """
        template = getattr(self, key, None)
        if not template:
            raise ContractError(f"queue.{key} is not configured for this project")
        argv: list[str] = []
        for token in shlex.split(template):
            for name, value in params.items():
                token = token.replace("{" + name + "}", value)
            argv.append(token)
        return argv


def _validate_template(template: str, where: str) -> None:
    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        raise ContractError(f"{where}: cannot parse command: {exc}") from exc
    if not tokens:
        raise ContractError(f"{where}: empty command")
    import re

    for name in re.findall(r"\{(\w+)\}", template):
        if name not in QUEUE_PLACEHOLDERS:
            raise ContractError(
                f"{where}: unknown placeholder {{{name}}}. "
                f"Known: {', '.join('{' + p + '}' for p in sorted(QUEUE_PLACEHOLDERS))}"
            )


@dataclass(frozen=True)
class Fence:
    """Paths a task may never modify, checked against the diff.

    The original loop fenced by prose in the agent's prompt. That is a request.
    This is the same list, declared once and enforced twice: named in the
    prompt so the agent knows, and checked against `git diff --name-only` after
    the agent exits so the run does not depend on it having listened.

    Patterns are `fnmatch` globs against repository-relative paths, plus a
    directory shorthand: a pattern ending in `/` matches everything beneath it.
    """

    paths: tuple[str, ...] = ()

    @classmethod
    def parse(cls, raw: Any) -> Fence:
        if raw is None:
            return cls()
        if isinstance(raw, list):
            got: dict[str, Any] = {"paths": raw}
        else:
            got = _require_mapping(raw, "fence")
        _reject_unknown(got, {"paths"}, "fence")
        paths = got.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list):
            raise ContractError("fence.paths must be a list of path patterns")
        cleaned = []
        for item in paths:
            text = str(item).strip()
            if not text:
                continue
            if text.startswith("/"):
                raise ContractError(
                    f"fence.paths: {text!r} is absolute. Patterns are relative to "
                    "the repository root."
                )
            cleaned.append(text)
        return cls(paths=tuple(cleaned))

    def violations(self, changed_paths) -> list[str]:
        """Return the changed paths this fence forbids, in input order."""
        from fnmatch import fnmatch

        hits = []
        for path in changed_paths:
            norm = str(path).strip().lstrip("./")
            if not norm:
                continue
            for pattern in self.paths:
                if pattern.endswith("/"):
                    if norm == pattern.rstrip("/") or norm.startswith(pattern):
                        hits.append(norm)
                        break
                elif fnmatch(norm, pattern) or norm == pattern:
                    hits.append(norm)
                    break
        return hits


@dataclass(frozen=True)
class Environment:
    """Guards that decide the machine is safe to work on.

    `forbid_env` refuses when a named variable holds a named value -- the
    production check. `min_free_gb` refuses on a full disk, because a gate that
    fails for want of space is indistinguishable from a gate that fails for the
    code, and the loop would read it as the agent's fault.
    """

    forbid_env: dict[str, str] = field(default_factory=dict)
    min_free_gb: float = 2.0

    @classmethod
    def parse(cls, raw: Any) -> Environment:
        got = _require_mapping(raw, "environment")
        _reject_unknown(got, {"forbid_env", "min_free_gb"}, "environment")
        forbid = _require_mapping(got.get("forbid_env"), "environment.forbid_env")
        try:
            min_free = float(got.get("min_free_gb", 2.0))
        except (TypeError, ValueError) as exc:
            raise ContractError("environment.min_free_gb must be a number") from exc
        if min_free < 0:
            raise ContractError("environment.min_free_gb must not be negative")
        return cls(
            forbid_env={str(k): str(v) for k, v in forbid.items()},
            min_free_gb=min_free,
        )


@dataclass(frozen=True)
class Caps:
    """Per-project cap overrides.

    Defaults live in `caps.py`; a project may tighten or loosen them. The spend
    ceiling is deliberately absent from the contract: it is an operator
    decision made per run, not a property of a project, and a ceiling checked
    into a repository is one nobody re-reads before the night it matters.
    """

    max_tasks: int | None = None
    max_hours: float | None = None
    max_consecutive_failures: int | None = None
    task_timeout_minutes: float | None = None
    max_unmetered_tasks: int | None = None

    _FIELDS = {
        "max_tasks", "max_hours", "max_consecutive_failures",
        "task_timeout_minutes", "max_unmetered_tasks",
    }

    @classmethod
    def parse(cls, raw: Any) -> Caps:
        got = _require_mapping(raw, "caps")
        _reject_unknown(got, cls._FIELDS, "caps")
        if "max_spend_usd" in got:  # pragma: no cover - guarded by _reject_unknown
            raise ContractError("caps.max_spend_usd is set per run, not per project")
        values: dict[str, Any] = {}
        for key in cls._FIELDS:
            if key not in got or got[key] is None:
                continue
            try:
                number = float(got[key])
            except (TypeError, ValueError) as exc:
                raise ContractError(f"caps.{key} must be a number") from exc
            if number < 0:
                raise ContractError(f"caps.{key} must not be negative")
            values[key] = number if key in ("max_hours", "task_timeout_minutes") else int(number)
        return cls(**values)


@dataclass(frozen=True)
class Contract:
    """A validated project contract."""

    name: str
    commands: Commands
    git: Git
    queue: Queue = field(default_factory=Queue)
    fence: Fence = field(default_factory=Fence)
    environment: Environment = field(default_factory=Environment)
    caps: Caps = field(default_factory=Caps)
    description: str = ""
    source: Path | None = None

    _TOP = {
        "version", "name", "description", "commands", "git", "queue",
        "fence", "environment", "caps",
    }

    @classmethod
    def parse(cls, raw: Any, source: Path | None = None) -> Contract:
        got = _require_mapping(raw, "contract")
        if not got:
            raise ContractError(f"{source or 'contract'}: file is empty")
        _reject_unknown(got, cls._TOP, "contract")

        version = got.get("version", CONTRACT_VERSION)
        try:
            version = int(version)
        except (TypeError, ValueError) as exc:
            raise ContractError("version must be an integer") from exc
        if version != CONTRACT_VERSION:
            raise ContractError(
                f"contract version {version} is not supported by this Water Mill "
                f"(expects {CONTRACT_VERSION}). Refusing rather than guessing which "
                "fields moved."
            )

        name = _opt_str(got.get("name"))
        if not name:
            raise ContractError("name is required")

        return cls(
            name=name,
            description=str(got.get("description") or "").strip(),
            commands=Commands.parse(got.get("commands")),
            git=Git.parse(got.get("git")),
            queue=Queue.parse(got.get("queue")),
            fence=Fence.parse(got.get("fence")),
            environment=Environment.parse(got.get("environment")),
            caps=Caps.parse(got.get("caps")),
            source=source,
        )

    @classmethod
    def load(cls, path: Path) -> Contract:
        path = Path(path)
        if not path.is_file():
            raise ContractError(f"no contract at {path}")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ContractError(f"{path}: {exc}") from exc
        return cls.parse(raw, source=path)
