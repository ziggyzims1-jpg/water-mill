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

#: Placeholders a review command template may use. Disjoint from the queue's on
#: purpose: these name a branch and a base, and a template that confuses the two
#: sets is a template that would have opened a pull request against a task id.
REVIEW_PLACEHOLDERS = {"branch", "base", "title", "body"}


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
        return _render(getattr(self, key, None) or "", f"queue.{key}", **params)


def _validate_template(
    template: str, where: str, placeholders: set[str] = QUEUE_PLACEHOLDERS
) -> None:
    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        raise ContractError(f"{where}: cannot parse command: {exc}") from exc
    if not tokens:
        raise ContractError(f"{where}: empty command")
    import re

    for name in re.findall(r"\{(\w+)\}", template):
        if name not in placeholders:
            raise ContractError(
                f"{where}: unknown placeholder {{{name}}}. "
                f"Known: {', '.join('{' + p + '}' for p in sorted(placeholders))}"
            )


def _render(template: str, where: str, **params: str) -> list[str]:
    """Render one command template into an argv list.

    Substitution happens *after* splitting, so a branch name, a title or a body
    containing a space, a quote or a semicolon becomes one argument rather than
    shell syntax. There is no shell involved at any point.
    """
    if not template:
        raise ContractError(f"{where} is not configured for this project")
    argv: list[str] = []
    for token in shlex.split(template):
        for name, value in params.items():
            token = token.replace("{" + name + "}", value)
        argv.append(token)
    return argv


@dataclass(frozen=True)
class Review:
    """Opening a pull request, waiting for it to go green, and merging it.

    Three commands, declared by the project because the forge is the project's
    business and not this orchestrator's: `gh`, `glab`, a curl, a script. Water
    Mill knows there are three steps and nothing about who performs them.

    **`verify` is required whenever `merge` is declared, and that is the whole
    safety argument for this block.** A contract that could merge without
    verifying would turn the merge gate into a formality that runs after the
    decision it was supposed to inform. `create` without `merge` is the useful
    and deliberately supported middle: the factory opens the pull request and
    proves it green, and a person presses the button.

    Nothing here runs during a run. Every command in this block talks to a
    third party, and a forge that is slow, rate-limited or down must not be
    able to hang a night or strand a claimed task -- the same reason `ship` is
    its own command. `watermill land` is where these are used.
    """

    create: str | None = None
    verify: str | None = None
    merge: str | None = None

    _FIELDS = {"create", "verify", "merge"}

    @property
    def enabled(self) -> bool:
        return bool(self.create)

    @classmethod
    def parse(cls, raw: Any) -> Review:
        got = _require_mapping(raw, "review")
        _reject_unknown(got, cls._FIELDS, "review")
        templates = {key: _opt_str(got.get(key)) for key in ("create", "verify", "merge")}
        for key, template in templates.items():
            if template is not None:
                _validate_template(template, f"review.{key}", REVIEW_PLACEHOLDERS)

        if any(templates.values()) and not templates["create"]:
            raise ContractError(
                "review.create is required when any other review command is set. "
                "There is nothing to verify or merge until something opened it."
            )
        if templates["merge"] and not templates["verify"]:
            raise ContractError(
                "review.verify is required when review.merge is set. Merging "
                "without it would make the merge gate advisory -- a check that "
                "runs after the decision it exists to inform."
            )
        return cls(**templates)

    def render(self, key: str, **params: str) -> list[str]:
        return _render(getattr(self, key, None) or "", f"review.{key}", **params)


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
            # removeprefix, never lstrip: `lstrip("./")` strips *every* leading
            # dot and slash, so `.github/workflows/verify.yml` becomes
            # `github/...` and a fence over `.github/` silently matches nothing.
            # Every protected dotfile path -- .github, .beads, .claude -- would
            # have been unguarded while the contract said otherwise.
            norm = str(path).strip().removeprefix("./")
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


#: A ceiling on the notes block. A prompt that grows without bound is one the
#: agent skims, and a lesson nobody reads is worse than no lesson because it
#: creates the belief that the knowledge is being applied. When the list is
#: full, the answer is not a bigger list: it is to promote the note into
#: something mechanical -- a fenced path, or a check the gate runs.
MAX_NOTES = 20
MAX_NOTE_CHARS = 500


@dataclass(frozen=True)
class Notes:
    """Hard-won knowledge about this project, in the agent's own prompt.

    Everything else in a contract is a *mechanism*: the gate re-runs, the fence
    is checked against a diff, a cap halts the loop. Notes are the exception --
    they are advice, and advice is a request rather than evidence. That makes
    the boundary the important part of this type rather than its contents:

    **A rule that can be mechanised does not belong here.** "Never edit db.py"
    is a fence path, and stating it as a note instead converts an enforced
    guarantee into a suggestion the agent may reasonably weigh against the task
    in front of it. What belongs here is what no mechanism can express -- where
    a project keeps a thing, which of two plausible idioms it actually uses,
    the trap that a reasonable agent falls into precisely because it is
    reasonable.

    **A note earns its place by having cost something.** These are written
    after a task went wrong, not before one is attempted; a note guessed in
    advance is a style preference, and the prompt is not the place for those.
    """

    items: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @classmethod
    def parse(cls, value: Any) -> Notes:
        if value is None:
            return cls()
        # A single string is accepted as one note: it is what a YAML block
        # scalar produces and there is no other thing it could have meant.
        raw = [value] if isinstance(value, str) else value
        if not isinstance(raw, list):
            raise ContractError(
                f"notes: expected a list of strings, got {type(value).__name__}"
            )
        items: list[str] = []
        for index, entry in enumerate(raw):
            if not isinstance(entry, str):
                raise ContractError(
                    f"notes[{index}]: expected a string, got {type(entry).__name__}"
                )
            text = " ".join(entry.split())
            if not text:
                continue
            if len(text) > MAX_NOTE_CHARS:
                raise ContractError(
                    f"notes[{index}] is {len(text)} characters, over the "
                    f"{MAX_NOTE_CHARS} limit. A note that long is documentation; "
                    "put it in the repository and leave one sentence here saying "
                    "where."
                )
            items.append(text)
        if len(items) > MAX_NOTES:
            raise ContractError(
                f"notes: {len(items)} entries, over the limit of {MAX_NOTES}. "
                "The list is capped because a prompt the agent skims teaches it "
                "nothing while costing every task. Promote the mechanical ones "
                "into fence.paths or into the gate, and drop the rest."
            )
        return cls(items=tuple(items))


@dataclass(frozen=True)
class Knowledge:
    """Whether a run offers the agent the context graph as a tool.

    `recall` is the one wiring decision the graph needs from a contract, and
    it lives here rather than in the CLI's defaults because it is a property
    of the project, not of the person typing the command: a project whose seam
    has been proven by a real run keeps it on, one that has not keeps it off,
    and the command line overrides either way (`--recall` / `--no-recall`).
    Off is the default for a new contract for the reason `docs/KNOWLEDGE.md`
    gives -- a flag that changes the command every task is sent is not where
    you discover the flag is wrong.
    """

    recall: bool = False

    _KEYS = {"recall"}

    @classmethod
    def parse(cls, raw: Any) -> Knowledge:
        got = _require_mapping(raw, "knowledge")
        _reject_unknown(got, cls._KEYS, "knowledge")
        recall = got.get("recall", False)
        if not isinstance(recall, bool):
            raise ContractError(
                f"knowledge.recall: expected true or false, got {recall!r}"
            )
        return cls(recall=recall)


@dataclass(frozen=True)
class Contract:
    """A validated project contract."""

    name: str
    commands: Commands
    git: Git
    queue: Queue = field(default_factory=Queue)
    review: Review = field(default_factory=Review)
    fence: Fence = field(default_factory=Fence)
    environment: Environment = field(default_factory=Environment)
    caps: Caps = field(default_factory=Caps)
    notes: Notes = field(default_factory=Notes)
    knowledge: Knowledge = field(default_factory=Knowledge)
    description: str = ""
    source: Path | None = None

    _TOP = {
        "version", "name", "description", "commands", "git", "queue",
        "review", "fence", "environment", "caps", "notes", "knowledge",
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
            review=Review.parse(got.get("review")),
            fence=Fence.parse(got.get("fence")),
            environment=Environment.parse(got.get("environment")),
            caps=Caps.parse(got.get("caps")),
            notes=Notes.parse(got.get("notes")),
            knowledge=Knowledge.parse(got.get("knowledge")),
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
