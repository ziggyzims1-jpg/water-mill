"""Everything that must hold before a run is allowed to start.

Preflight is the largest single body of code in this orchestrator and that is
the correct proportion. A run that begins on a red baseline cannot distinguish
its own damage from damage that was already there, which makes every commit it
produces unreviewable -- so the expensive check (running the project's whole
gate on unmodified code) is not optional and not skippable.

Every check answers one question and refuses with a sentence naming what to do
about it. A refusal is not a failure: nothing has been modified when preflight
declines, no claim has been taken, and no agent has been invoked.

The checks are ordered cheapest-first, and preflight stops at the first
refusal. Running a six-minute gate to discover afterwards that the spend
ceiling was unset wastes the operator's evening for no information.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import gitwork
from .caps import Caps
from .contract import Contract
from .proc import run, split
from .queue import QueueError, WorkQueue
from .registry import Project

#: Environment variables whose value, if it looks like production, refuses the
#: run outright. A project may add more through `environment.forbid_env`.
PRODUCTION_MARKERS = {
    "FLASK_ENV": "production",
    "NODE_ENV": "production",
    "APP_ENV": "production",
    "ENVIRONMENT": "production",
    "RAILS_ENV": "production",
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False

    @property
    def symbol(self) -> str:
        if self.skipped:
            return "skip"
        return "ok" if self.ok else "REFUSE"


@dataclass
class PreflightReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok or check.skipped for check in self.checks)

    @property
    def refusal(self) -> CheckResult | None:
        for check in self.checks:
            if not check.ok and not check.skipped:
                return check
        return None

    def render(self) -> str:
        width = max((len(c.name) for c in self.checks), default=0)
        lines = []
        for check in self.checks:
            line = f"  [{check.symbol:>6}] {check.name.ljust(width)}"
            if check.detail:
                line += f"  {check.detail}"
            lines.append(line)
        return "\n".join(lines)


def preflight(
    project: Project,
    contract: Contract,
    caps: Caps,
    *,
    agent_binary: str,
    log_dir: Path,
    skip_gate: bool = False,
    skip_backup: bool = False,
    require_queue: bool = True,
) -> PreflightReport:
    """Run every check, stopping at the first refusal.

    `skip_gate` and `skip_backup` exist to test this orchestrator and to make a
    `watermill doctor` run cheap. Neither is available on an unattended run --
    the CLI refuses to pass them alongside `--unattended` -- because a skipped
    baseline is the one shortcut that makes every later result meaningless.
    """
    report = PreflightReport()

    def add(name: str, ok: bool, detail: str = "", skipped: bool = False) -> bool:
        report.checks.append(CheckResult(name, ok, detail, skipped))
        return ok or skipped

    cwd = project.path

    if not add("project exists", project.exists, str(cwd)):
        return report
    if not add("git repository", project.is_git_repo, str(cwd / ".git")):
        return report

    if not add(
        "spend ceiling",
        caps.max_spend_cents is not None,
        "set --max-spend; there is no default, on purpose"
        if caps.max_spend_cents is None
        else f"${caps.max_spend_cents / 100:.2f}",
    ):
        return report

    missing_tools = [
        tool
        for tool in _required_tools(contract, agent_binary)
        if shutil.which(tool) is None
    ]
    if not add(
        "tooling",
        not missing_tools,
        f"missing: {', '.join(missing_tools)}" if missing_tools else "all present",
    ):
        return report

    forbidden = _production_markers(contract)
    if not add(
        "not production",
        not forbidden,
        "; ".join(forbidden) if forbidden else "no production markers",
    ):
        return report

    free_gb = _free_gb(cwd)
    if not add(
        "disk space",
        free_gb >= contract.environment.min_free_gb,
        f"{free_gb:.1f} GB free, needs {contract.environment.min_free_gb:.1f} GB",
    ):
        return report

    branch = gitwork.current_branch(cwd)
    if not add(
        "on base branch",
        branch == contract.git.base_branch,
        f"on {branch!r}, contract expects {contract.git.base_branch!r}",
    ):
        return report

    # The run's own log directory lives under the factory, not the target, so
    # nothing here needs excluding -- but a project that redirects logs into its
    # own tree would, and the parameter is where that would go.
    tree = gitwork.status(cwd)
    if not add(
        "clean tree",
        tree.clean,
        tree.describe() if not tree.clean else "nothing uncommitted",
    ):
        return report

    queue = WorkQueue(contract.queue, cwd)
    if queue.enabled:
        try:
            stuck = queue.stale()
        except QueueError as exc:
            add("stale claims", False, str(exc))
            return report
        if not add(
            "stale claims",
            not stuck,
            f"{len(stuck)} claimed: {', '.join(t.id for t in stuck[:5])}. "
            "Release them before running -- a claimed task is absent from the "
            "queue, so a killed run quietly shrinks it"
            if stuck
            else "none",
        ):
            return report

        try:
            ready = queue.ready()
        except QueueError as exc:
            add("work available", False, str(exc))
            return report
        if not add(
            "work available",
            bool(ready) or not require_queue,
            f"{len(ready)} ready"
            if ready
            else "queue is empty -- generate tasks, do not raise caps",
        ):
            return report
    else:
        add("queue", True, "disabled by contract (queue.kind: none)", skipped=True)

    if contract.commands.backup_check and not skip_backup:
        result = run(contract.commands.backup_check, cwd=cwd, timeout=600.0)
        if not add(
            "verified restore",
            result.ok,
            "no recently verified restore. A run that can damage data without a "
            f"proven restore is the combination this refuses. Run: "
            f"{contract.commands.backup_run or 'the project backup drill'}"
            if not result.ok
            else "recent",
        ):
            return report
    elif skip_backup:
        add("verified restore", True, "skipped by flag", skipped=True)
    else:
        add(
            "verified restore",
            True,
            "no backup_check in the contract -- this project cannot prove it is "
            "recoverable",
            skipped=True,
        )

    if skip_gate:
        add("baseline gate", True, "skipped by flag", skipped=True)
    else:
        gate_log = log_dir / "gate" / "baseline.log"
        result = run(contract.commands.gate, cwd=cwd, log_path=gate_log)
        add(
            "baseline gate",
            result.ok,
            f"{contract.commands.gate} in {result.duration_seconds:.0f}s"
            if result.ok
            else f"{contract.commands.gate} fails on unmodified code. See {gate_log}",
        )

    return report


def _required_tools(contract: Contract, agent_binary: str) -> list[str]:
    """The executables every command in this contract will reach for."""
    tools = {"git", split(agent_binary)[0]}
    for command in (
        contract.commands.gate,
        contract.commands.backup_check,
        contract.queue.ready,
        contract.queue.claim,
    ):
        if command:
            head = split(command)[0]
            # A path rather than a name is checked for existence by the command
            # itself; `which` would report it missing whenever it is relative.
            if "/" not in head:
                tools.add(head)
    return sorted(tools)


def _production_markers(contract: Contract) -> list[str]:
    """Named variables currently holding a value that means production."""
    checks = dict(PRODUCTION_MARKERS)
    checks.update(contract.environment.forbid_env)
    hits = []
    for name, forbidden in checks.items():
        actual = os.environ.get(name)
        if actual and actual.strip().lower() == str(forbidden).strip().lower():
            hits.append(f"{name}={actual}")
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url and not _looks_local(database_url):
        hits.append("DATABASE_URL does not look local")
    return hits


def _looks_local(url: str) -> bool:
    lowered = url.lower()
    return any(
        marker in lowered
        for marker in ("localhost", "127.0.0.1", "::1", "sqlite", "file:", "/tmp/")
    )


def _free_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(path)
    except OSError:  # pragma: no cover
        return 0.0
    return usage.free / (1024**3)
