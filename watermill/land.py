"""Opening a run's pull request, proving it green, and merging it.

**This never runs during a run**, and that is the point of it being a module of
its own rather than four more lines at the end of `engine._finish`. Every step
here talks to a forge -- a third party that can be slow, rate-limited, down, or
simply waiting on a twenty-minute CI queue. A night that blocked on any of
those would hold a claimed task open across the outage, and the first thing the
morning would have to untangle is which of the two systems was actually broken.
`ship` is kept off the run loop for the same reason and this is the second
sighting of that rule.

The order is fixed and the middle step is the one that matters:

    create  ->  verify  ->  merge

`verify` is not advisory. If it fails, this module stops and **never calls
merge**, whatever the forge reported about mergeability. That is the same
argument the engine makes about the gate: the check has to run before the
decision it informs, or it is decoration. `review.merge` without `review.verify`
is refused at contract-parse time so the combination cannot be expressed.

`create` **is** advisory, for the mirror-image reason: create is not evidence,
verify is. A create that fails because the branch already has a pull request --
what a second `land` of the same run meets -- must not strand that run, and a
create that failed for a real reason is followed by a verify that fails too.

A verify that fails inside a short settle window is retried rather than
believed, because a forge does not register its checks synchronously with the
pull request. That window is the fix for the first real land this factory ever
performed; see `_verify_when_the_forge_is_ready`.

What this module deliberately does not do:

- **Decide the work is good.** The gate did that, twice, during the run. This
  proves that what CI sees agrees with what the gate saw locally, which is a
  different claim and a weaker one.
- **Push.** The engine already pushed the branch at the end of the run. If the
  branch is not on the remote this refuses rather than pushing on its own,
  because a branch that failed to push is a symptom and re-pushing it here
  would hide which run produced the failure.
- **Discard anything.** Nothing in this file removes work. A land that fails
  leaves the branch exactly where the run left it, which is the state a person
  can look at.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import gitwork
from .contract import Contract
from .proc import run
from .registry import Project

#: How long to wait on each step. `verify` gets its own, much larger, budget
#: because it is the one that waits on somebody else's build queue.
CREATE_TIMEOUT = 120.0
MERGE_TIMEOUT = 300.0
VERIFY_TIMEOUT = 3600.0

#: How long to keep asking for checks that are not there yet, and how often.
#: A forge does not register its checks synchronously with the pull request, so
#: the first verify after a create routinely arrives before there is anything to
#: watch. Small and total: a build that really does fail instantly costs this
#: once and is then reported as the failure it is.
SETTLE_SECONDS = 90.0
POLL_SECONDS = 10.0


@dataclass
class Step:
    """One command, and what it did. Recorded whether or not it succeeded.

    `advisory` marks a step whose failure does not fail the landing. Only
    `create` is one, and the reason is the same argument this program makes
    everywhere else: **create is not evidence, verify is.** A `create` that
    fails because the pull request is already open -- which is exactly what a
    second `land` of the same run meets -- must not strand that run forever,
    and a `create` that failed for a real reason will be followed by a `verify`
    that fails too.
    """

    name: str
    argv: list[str] = field(default_factory=list)
    ok: bool = False
    skipped: bool = False
    advisory: bool = False
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "argv": self.argv,
            "ok": self.ok,
            "skipped": self.skipped,
            "advisory": self.advisory,
            "detail": self.detail[:2000],
        }


@dataclass
class LandResult:
    """What happened, in the shape the CLI turns into an exit code.

    `refused` and `failed` are different, and carry the different exit codes the
    rest of this program uses: a refusal means a precondition did not hold and
    nothing was attempted, a failure means something was attempted and did not
    work. A cron wrapper that cannot tell them apart cannot tell a
    misconfiguration from a red build.
    """

    project: str
    run_id: str
    branch: str = ""
    base: str = ""
    refused: str = ""
    steps: list[Step] = field(default_factory=list)
    merged: bool = False

    @property
    def failed(self) -> bool:
        return not self.refused and any(
            not step.ok and not step.skipped and not step.advisory
            for step in self.steps
        )

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "run_id": self.run_id,
            "branch": self.branch,
            "base": self.base,
            "refused": self.refused,
            "merged": self.merged,
            "steps": [step.to_dict() for step in self.steps],
        }

    def render(self) -> str:
        lines = [f"{self.project} -- landing {self.run_id}"]
        if self.refused:
            lines.append(f"  [REFUSE] {self.refused}")
            return "\n".join(lines)
        for step in self.steps:
            mark = "  skip" if step.skipped else ("    ok" if step.ok else "FAILED")
            lines.append(f"  [{mark}] {step.name:<8} {step.detail[:96]}")
        if self.merged:
            lines.append(f"  merged {self.branch} into {self.base}")
        elif not self.failed:
            # Said plainly. A green verify with no merge command is a success
            # and looks exactly like a half-finished job unless it says so.
            lines.append(f"  {self.branch} is green and waiting for a human to merge")
        return "\n".join(lines)


def read_summary(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def land(
    project: Project,
    contract: Contract,
    summary: dict,
    *,
    merge: bool = True,
    on_event=None,
    settle_seconds: float = SETTLE_SECONDS,
    poll_seconds: float = POLL_SECONDS,
) -> LandResult:
    """Open, verify and merge the pull request for one finished run.

    `merge=False` stops after a green verify. It is the same shape as a contract
    that declares no `review.merge`, and exists so an operator can watch the
    first few land without handing over the button at the same time.
    """
    emit = on_event or (lambda message: None)
    result = LandResult(
        project=contract.name,
        run_id=str(summary.get("run_id", "")),
        base=contract.git.base_branch,
    )

    refusal = _refuse(project, contract, summary)
    if refusal:
        result.refused = refusal
        return result

    result.branch = str(summary.get("work_branch", ""))
    params = {
        "branch": result.branch,
        "base": contract.git.base_branch,
        "title": _title(summary),
        "body": _body(summary),
    }

    create = _step(project, contract, "create", params, CREATE_TIMEOUT, emit)
    create.advisory = True
    result.steps.append(create)
    if not create.ok:
        # Not fatal, and not ignored either. The commonest cause is a pull
        # request this branch already has -- a second `land` of a run whose
        # first attempt failed at verify -- and refusing there would mean a run
        # could never be landed by the tool once anything went wrong. `verify`
        # is the step that proves a pull request exists and is green, so let it
        # answer. A create that failed for a real reason fails there too.
        emit("   create: failed -- continuing, verify decides whether a PR is there")

    verify = _verify_when_the_forge_is_ready(
        project, contract, params, emit, settle_seconds, poll_seconds
    )
    result.steps.append(verify)
    if not verify.ok:
        # Nothing after this point runs. The forge may well consider the branch
        # mergeable; that is not the question this step asked.
        return result

    if not merge or not contract.review.merge:
        result.steps.append(
            Step(name="merge", skipped=True, ok=True, detail=_why_not_merged(contract, merge))
        )
        return result

    merged = _step(project, contract, "merge", params, MERGE_TIMEOUT, emit)
    result.steps.append(merged)
    result.merged = merged.ok
    # Back to the base branch, because the next run's preflight checks it and a
    # repository parked on a merged branch refuses -- correctly, and for a
    # reason that reads like a bug the first time you meet it.
    if merged.ok and not gitwork.checkout(project.path, contract.git.base_branch):
        result.steps.append(
            Step(
                name="return",
                ok=False,
                detail=(
                    f"merged, but could not check out {contract.git.base_branch} "
                    "-- the next run will refuse at preflight until you do"
                ),
            )
        )
    return result


def _refuse(project: Project, contract: Contract, summary: dict) -> str:
    """Everything that must hold before a single forge call is made.

    Ordered cheapest-first and stated as separate sentences, because "could not
    land" is not actionable and "the run kept nothing" is.
    """
    if not contract.review.enabled:
        return (
            "this project declares no review.create command, so there is no "
            "pull request to open. See docs/CONTRACT.md"
        )
    if contract.git.target != "branch":
        return (
            f"git.target is {contract.git.target!r}: the work is already on "
            f"{contract.git.base_branch} and there is nothing to land"
        )
    if not summary:
        return "no run summary to land -- has this project ever run?"
    if summary.get("refused"):
        return f"run {summary.get('run_id')} was refused at preflight and did no work"
    branch = str(summary.get("work_branch", ""))
    if not branch:
        return f"run {summary.get('run_id')} recorded no work branch"
    if not summary.get("commits"):
        return f"run {summary.get('run_id')} kept nothing, so the branch has no work on it"

    tree = gitwork.status(project.path)
    if not tree.clean:
        # Not this module's to clean. Something else put it there, and landing
        # a pull request out from under uncommitted work is how you lose it.
        return f"the working tree is dirty ({tree.describe()}) -- resolve it first"
    if not gitwork.branch_exists(project.path, branch):
        return f"branch {branch} is gone from this checkout"
    if not gitwork.branch_exists_on_remote(project.path, contract.git.remote, branch):
        return (
            f"branch {branch} is not on {contract.git.remote}. The run pushes it "
            "when it ends; that this one did not is the thing worth looking at"
        )
    return ""


def _verify_when_the_forge_is_ready(
    project, contract, params, emit, settle_seconds: float, poll_seconds: float
) -> Step:
    """Run `verify`, tolerating the window before the forge registers checks.

    This factory's first real land opened a pull request and asked about its
    checks in the same second. `gh pr checks` answered "no checks reported on
    the 'watermill/20260827-060430' branch" and exited non-zero -- and the
    check that had not yet appeared went green two minutes later. **A tool that
    was not ready was reported as a red build**, which is the one confusion
    this program spends most of its refusals avoiding, and it is the same
    mistake as `make typecheck` exiting zero to mean "no type checker".

    So a verify that fails *inside* the settle window is retried rather than
    believed, and outside it is believed. The window is bounded and total, so a
    build that genuinely fails instantly -- a workflow whose YAML does not parse
    -- costs it once and is then reported as the failure it is. A real build
    under `--watch` takes minutes and never reaches this path.

    Retrying a *failing* check is deliberate and would be wrong anywhere else.
    It is right here only because the window is short enough that no real
    verdict fits inside it.
    """
    deadline = time.monotonic() + settle_seconds
    attempts = 0
    while True:
        attempts += 1
        step = _step(project, contract, "verify", params, VERIFY_TIMEOUT, emit)
        if step.ok or time.monotonic() >= deadline:
            if attempts > 1:
                step.detail = f"{step.detail} (after {attempts} attempts)"
            return step
        emit(f"   verify: nothing reported yet, asking again in {poll_seconds:g}s")
        time.sleep(poll_seconds)


def _step(project, contract, key, params, timeout, emit) -> Step:
    argv = contract.review.render(key, **params)
    emit(f"   {key}: {' '.join(argv[:6])}")
    result = run(argv, cwd=project.path, timeout=timeout, tail_lines=0)
    detail = (result.tail or "").strip().splitlines()
    return Step(
        name=key,
        argv=argv,
        ok=result.ok,
        detail=(detail[-1] if detail else ("ok" if result.ok else "no output")),
    )


def _why_not_merged(contract: Contract, merge: bool) -> str:
    if not merge:
        return "--no-merge: stopped after a green verify"
    return "this project declares no review.merge command"


def _title(summary: dict) -> str:
    """One line naming what the run did, for the pull request.

    Built from the tasks rather than the commits: a task id is the thing the
    queue, the task log and the calibration record all agree on, and a reader
    who wants the commits can open the branch.
    """
    tasks = [t for t in summary.get("tasks", []) if t.get("outcome") == "completed"]
    run_id = summary.get("run_id", "?")
    if len(tasks) == 1:
        return f"{tasks[0].get('id', '?')}: {tasks[0].get('title', '')}".strip().rstrip(":")
    return f"Water Mill run {run_id}: {len(tasks)} tasks"


def _body(summary: dict) -> str:
    """The pull request description: what landed, what did not, and what it cost.

    Includes the discards. A pull request that lists only the kept work reads
    like a clean run even when three tasks were thrown away, and the discards
    are the more interesting half -- they are what calibration is looking for.
    """
    lines = [f"Opened by Water Mill from run `{summary.get('run_id', '?')}`.", ""]

    kept = [t for t in summary.get("tasks", []) if t.get("outcome") == "completed"]
    if kept:
        lines.append("**Kept**")
        for task in kept:
            lines.append(f"- `{task.get('id', '?')}` {task.get('title', '')}")
        lines.append("")

    dropped = [t for t in summary.get("tasks", []) if t.get("outcome") != "completed"]
    if dropped:
        lines.append("**Attempted and discarded** (nothing from these is in this branch)")
        for task in dropped:
            reason = task.get("reason") or task.get("outcome", "?")
            lines.append(f"- `{task.get('id', '?')}` {task.get('title', '')} -- {reason}")
        lines.append("")

    counts = summary.get("counts", {})
    spend = summary.get("spend_cents")
    lines.append(
        f"Attempted {counts.get('attempted', 0)}, kept {counts.get('completed', 0)}, "
        f"discarded {counts.get('failed', 0)}, escalated {counts.get('escalated', 0)}"
        + (f", ${spend / 100:.2f}" if isinstance(spend, int) else "")
    )
    if summary.get("halt_reason"):
        lines.append(f"Halted because: {summary['halt_reason']}")
    lines.append("")
    lines.append(
        "The gate ran twice per task inside the run -- once on unmodified code, "
        "once after. This pull request exists so CI says the same thing "
        "independently."
    )
    if summary.get("anomalies"):
        lines.append("")
        lines.append("**Anomalies**")
        for note in summary["anomalies"]:
            lines.append(f"- {note}")
    return "\n".join(lines)
