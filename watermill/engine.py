"""The run loop: claim a task, work it, verify it independently, keep or discard.

This is the part that would be dangerous if it were clever, so it is not. Every
decision it makes is one of four, and the fourth is the only one that keeps
anything:

1. A cap has been reached -> halt and report.
2. The agent escalated -> release the task, count nothing against it, move on.
3. Any verification failed -> discard the work, release the task, count a failure.
4. Everything verified -> keep the commit, close the task.

**The agent's own exit code is not evidence.** After it finishes, the
orchestrator re-runs the gate itself, checks the diff against the fence, checks
the tree is clean, and checks the commit names the task. Any of those failing
discards the work regardless of what the agent reported, because a confident
summary and a working change are different things and only one of them is
checkable.

**A task that fails is not retried in the same run.** Releasing a claim puts it
straight back at the top of the queue, so without the skip the loop retries one
bad task until the failure cap halts it while workable tasks sit untouched.
"""

from __future__ import annotations

import contextlib
import json
import shlex
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import gitwork, mcp
from .agent import DEFAULT_AGENT_COMMAND, build_prompt, invoke
from .caps import Caps, Tally, check
from .contract import Contract
from .errors import PreflightRefusal
from .preflight import PreflightReport, preflight
from .proc import run
from .queue import QueueError, Task, WorkQueue
from .registry import Project

#: How a task ended. `escalated` is deliberately neither of the other two.
COMPLETED = "completed"
FAILED = "failed"
ESCALATED = "escalated"


@dataclass
class TaskRecord:
    """What happened to one task, as the report will print it."""

    id: str
    title: str
    outcome: str
    reason: str = ""
    cost_cents: int | None = None
    duration_seconds: float = 0.0
    commit: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "outcome": self.outcome,
            "reason": self.reason,
            "cost_cents": self.cost_cents,
            "duration_seconds": round(self.duration_seconds, 1),
            "commit": self.commit,
            "note": self.note,
        }


@dataclass
class RunState:
    """Everything one run produced. Serialized whole into `summary.json`."""

    run_id: str
    project: str
    started_at: str
    caps: Caps
    tally: Tally = field(default_factory=Tally)
    tasks: list[TaskRecord] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    halt_reason: str = ""
    preflight: PreflightReport | None = None
    refused: bool = False
    started_work: bool = False
    base_sha: str = ""
    work_branch: str = ""
    commits: list[str] = field(default_factory=list)
    ended_at: str = ""
    tree_clean_at_end: bool = True
    supervised: bool = False

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "project": self.project,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "supervised": self.supervised,
            "refused": self.refused,
            "halt_reason": self.halt_reason,
            "caps": {
                "max_tasks": self.caps.max_tasks,
                "max_hours": self.caps.max_hours,
                "max_consecutive_failures": self.caps.max_consecutive_failures,
                "task_timeout_minutes": self.caps.task_timeout_minutes,
                "max_unmetered_tasks": self.caps.max_unmetered_tasks,
                "max_spend_cents": self.caps.max_spend_cents,
            },
            "counts": {
                "attempted": self.tally.attempted,
                "completed": self.tally.completed,
                "failed": self.tally.failed,
                "escalated": self.tally.escalated,
                "unmetered": self.tally.unmetered,
            },
            "spend_cents": self.tally.spend_cents,
            "under_counted": self.tally.unmetered > 0,
            "base_sha": self.base_sha,
            "work_branch": self.work_branch,
            "commits": self.commits,
            "tree_clean_at_end": self.tree_clean_at_end,
            "tasks": [t.to_dict() for t in self.tasks],
            "anomalies": self.anomalies,
            "preflight": [
                {"name": c.name, "ok": c.ok, "skipped": c.skipped, "detail": c.detail}
                for c in (self.preflight.checks if self.preflight else [])
            ],
        }


class Interrupted(Exception):
    """The operator asked the run to stop."""


class Engine:
    """One run against one project."""

    def __init__(
        self,
        project: Project,
        contract: Contract,
        caps: Caps,
        log_dir: Path,
        *,
        agent_command: str = DEFAULT_AGENT_COMMAND,
        supervised: bool = False,
        on_event=None,
        skip_gate: bool = False,
        skip_backup: bool = False,
        pause_between=None,
        recall: bool = False,
    ):
        self.project = project
        self.contract = contract
        self.caps = caps
        self.log_dir = Path(log_dir)
        self.agent_command = agent_command
        self.supervised = supervised
        self.on_event = on_event or (lambda message: None)
        self.skip_gate = skip_gate
        self.skip_backup = skip_backup
        self.pause_between = pause_between
        self.recall = recall
        self.queue = WorkQueue(contract.queue, project.path)
        self._interrupted = False
        self._claimed: str | None = None

        self.state = RunState(
            run_id=self.log_dir.name,
            project=contract.name,
            started_at=_now(),
            caps=caps,
            supervised=supervised,
        )

    # -- lifecycle ---------------------------------------------------------

    def run(self) -> RunState:
        """Preflight, then work until a cap or the queue stops it."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        previous = self._install_signal_handlers()
        try:
            self.state.preflight = preflight(
                self.project,
                self.contract,
                self.caps,
                agent_binary=self.agent_command,
                log_dir=self.log_dir,
                skip_gate=self.skip_gate,
                skip_backup=self.skip_backup,
            )
            self._emit(self.state.preflight.render())
            refusal = self.state.preflight.refusal
            if refusal is not None:
                self.state.refused = True
                self.state.halt_reason = f"preflight refused: {refusal.name} -- {refusal.detail}"
                # Nothing was modified, so nothing is discarded. This is the path
                # the shell version cleaned anyway, and deleted itself doing it.
                raise PreflightRefusal(self.state.halt_reason)

            self._begin_work()
            self._work_loop()
        except PreflightRefusal:
            raise
        except Interrupted:
            self.state.halt_reason = "interrupted by operator"
            self._release_claim("run interrupted by the operator")
            self._discard("interrupted")
        finally:
            self._restore_signal_handlers(previous)
            self._finish()
        return self.state

    def _begin_work(self) -> None:
        self.state.started_work = True
        self.state.base_sha = gitwork.head_sha(self.project.path)
        if self.contract.git.target == "branch":
            branch = f"watermill/{self.state.run_id}"
            if gitwork.create_branch(self.project.path, branch):
                self.state.work_branch = branch
                self._emit(f"working on {branch}, off {self.contract.git.base_branch}")
            else:
                self.state.anomalies.append(f"could not create branch {branch}")
        else:
            self.state.work_branch = self.contract.git.base_branch
            self._emit(f"committing directly to {self.contract.git.base_branch}")

    def _work_loop(self) -> None:
        tried: set[str] = set()
        while True:
            self._raise_if_interrupted()
            halt = check(self.caps, self.state.tally)
            if halt:
                self.state.halt_reason = halt
                self._emit(f"halting -- {halt}")
                return

            task = self._next_task(tried)
            if task is None:
                self.state.halt_reason = "queue exhausted"
                self._emit("no more ready work")
                return

            tried.add(task.id)
            base_sha = gitwork.head_sha(self.project.path)
            try:
                self._work_one(task, base_sha)
            except Interrupted:
                raise
            except Exception as exc:
                # An unexpected error in one task is a failed task, not a failed
                # run. Crashing here would leave the claim held, the tree
                # whatever the agent made it, and no report -- three residues to
                # untangle in the morning instead of one line saying what broke.
                # The consecutive-failure cap still bounds a systemic problem.
                self.state.anomalies.append(
                    f"{task.id} raised {type(exc).__name__}: {exc}"
                )
                self._fail(task, f"orchestrator error: {exc}", None, 0.0, base_sha)

            if self.pause_between is not None and self.pause_between(self.state) is False:
                # A stop asked for at the pause is not an interrupt. Ctrl-C
                # means "something is wrong, throw the work away" and takes the
                # `Interrupted` path below, which discards and releases; "n" at
                # the prompt means "that is enough for tonight" and every task
                # already kept stays kept. Routing the second through the first
                # discarded a task that had passed the gate and was committed.
                # Compared against False rather than truthiness, so a pause that
                # returns nothing -- every one before this did -- still means
                # carry on.
                self.state.halt_reason = "stopped by the operator between tasks"
                self._emit("stopping -- operator")
                return

    def _next_task(self, tried: set[str]) -> Task | None:
        try:
            ready = self.queue.ready()
        except QueueError as exc:
            self.state.anomalies.append(f"queue read failed: {exc}")
            return None
        for task in ready:
            if task.id not in tried:
                return task
        return None

    # -- one task ----------------------------------------------------------

    def _work_one(self, task: Task, base_sha: str) -> None:
        started = time.monotonic()
        self._emit(f"-> {task.label}")

        if not self.queue.claim(task.id):
            self.state.anomalies.append(f"could not claim {task.id}")
            self.state.tasks.append(
                TaskRecord(task.id, task.title, FAILED, reason="could not claim")
            )
            self.state.tally.record_failure(None)
            return
        self._claimed = task.id

        spec = self.queue.show(task.id)
        # Wired before the prompt is built, and the prompt is told what actually
        # got wired. An agent promised a tool it does not have spends a turn
        # discovering that and may distrust the rest of the prompt with it.
        recall_args = self._recall_args(task)
        prompt = build_prompt(task, self.contract, spec, recall=bool(recall_args))
        (self.log_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (self.log_dir / "prompts" / f"{_safe(task.id)}.txt").write_text(
            prompt, encoding="utf-8"
        )

        outcome = invoke(
            prompt,
            task,
            cwd=self.project.path,
            agent_command=self.agent_command,
            timeout=self.caps.task_timeout_seconds,
            log_path=self.log_dir / "tasks" / f"{_safe(task.id)}.json",
            extra_args=recall_args,
        )
        duration = time.monotonic() - started
        cost = outcome.cost_cents

        if outcome.timed_out:
            self.state.anomalies.append(
                f"{task.id} hit the {self.caps.task_timeout_minutes:g}m task timeout"
            )
            self._fail(task, "task timeout", cost, duration, base_sha)
            return

        if outcome.escalated:
            note = _escalation_note(outcome.reading.text)
            self._discard(f"escalation on {task.id}")
            self._release_claim(f"escalated: {note[:400]}")
            self.state.tasks.append(
                TaskRecord(task.id, task.title, ESCALATED, cost_cents=cost,
                           duration_seconds=duration, note=note)
            )
            self.state.tally.record_escalation(cost)
            self._emit(f"   escalated: {note.splitlines()[0][:100] if note else ''}")
            return

        verdict = self._verify(task, base_sha)
        if verdict is not None:
            self._fail(task, verdict, cost, duration, base_sha)
            return

        commit = gitwork.commits_since(self.project.path, base_sha)
        self.state.commits.extend(commit)
        # A task that failed says why, in a comment, and a task that succeeded
        # said nothing at all -- so the queue recorded every discard and no
        # kept work, which is exactly backwards. The commit that did the work
        # lived only in this factory's ledger, where the project cannot see it.
        # Written before the close, because a close is the last write some
        # queues accept on a task.
        recorded = self.queue.comment(task.id, _kept_note(self.state.run_id, commit))
        if self.queue.can_comment and not recorded:
            self.state.anomalies.append(
                f"kept {task.id} but could not record the run against it"
            )
        if not self.queue.close(task.id):
            self.state.anomalies.append(f"work kept but could not close {task.id}")
        self._claimed = None
        self.state.tasks.append(
            TaskRecord(task.id, task.title, COMPLETED, cost_cents=cost,
                       duration_seconds=duration, commit=commit[0] if commit else "")
        )
        self.state.tally.record_success(cost)
        self._emit(f"   kept: {commit[0] if commit else 'no commit recorded'}")

    def _recall_args(self, task: Task) -> str:
        """Wire the context graph to this task's agent, or return nothing.

        The config file is written into **this run's log directory**, never
        into the target repository: a file dropped in the project shows up in
        `git status`, and a task that leaves the tree dirty is discarded. The
        fence would eventually catch it; the tree check catches it at once, and
        neither should ever have to.

        Every failure here degrades to running without the tool. A missing
        tool disables a feature, never the run -- and the prompt is built from
        what this returned, so it never advertises a tool that is not there.
        """
        if not self.recall:
            return ""
        entry = Path(self.project.root) / "bin" / "watermill"
        # `--root` is a *global* option and has to precede the subcommand.
        # Spelled the other way round this parsed as an unrecognised argument,
        # argparse exited 2 before a single frame was read, and the agent saw
        # only `CONNECTION_CLOSED` -- a wiring failure that looks from the
        # transcript exactly like an agent that chose not to call the tool.
        command = [
            sys.executable, str(entry),
            "--root", str(self.project.root),
            "mcp",
            "--cell", self.contract.name,
            "--run", self.state.run_id,
            "--task", task.id,
        ]
        path = self.log_dir / "mcp" / f"{_safe(task.id)}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(mcp.config_document(command), indent=2), encoding="utf-8"
            )
        except OSError as exc:
            self.state.anomalies.append(f"could not wire recall for {task.id}: {exc}")
            return ""
        tools = ",".join(
            f"mcp__{mcp.SERVER_NAME}__{name}" for name in ("recall", "detail", "propose")
        )
        return f"--mcp-config {shlex.quote(str(path))} --allowedTools {tools}"

    def _verify(self, task: Task, base_sha: str) -> str | None:
        """Independent checks. Returns a refusal reason, or None to keep the work.

        Order is cheapest-first and each is a separate sentence in the report,
        because "the task failed" is not actionable and "it modified a fenced
        path" is.
        """
        cwd = self.project.path

        fenced = self.contract.fence.violations(gitwork.changed_paths(cwd, base_sha))
        if fenced:
            return f"modified fenced path(s): {', '.join(sorted(set(fenced))[:5])}"

        commits = gitwork.commits_since(cwd, base_sha)
        if not commits:
            tree = gitwork.status(cwd)
            if tree.clean:
                return "no commit and no changes -- the agent did nothing"
            return f"left work uncommitted ({tree.describe()})"

        tree = gitwork.status(cwd)
        if not tree.clean:
            return f"committed, but left the tree dirty ({tree.describe()})"

        message = gitwork.last_commit_message(cwd)
        if task.id not in message:
            return f"commit message does not name {task.id}"

        gate_log = self.log_dir / "gate" / f"{_safe(task.id)}.log"
        result = run(self.contract.commands.gate, cwd=cwd, log_path=gate_log)
        if not result.ok:
            return f"gate failed after the change (see {gate_log.name})"

        return None

    def _fail(self, task: Task, reason: str, cost, duration: float, base_sha: str) -> None:
        self._emit(f"   discarded: {reason}")
        self._reset_to(base_sha)
        self._discard(f"failed task {task.id}")
        self._release_claim(f"discarded by Water Mill: {reason}")
        self.state.tasks.append(
            TaskRecord(task.id, task.title, FAILED, reason=reason,
                       cost_cents=cost, duration_seconds=duration)
        )
        self.state.tally.record_failure(cost)

    # -- cleanup -----------------------------------------------------------

    def _reset_to(self, sha: str) -> None:
        if not sha or gitwork.head_sha(self.project.path) == sha:
            return
        if not gitwork.reset_to(self.project.path, sha):
            self.state.anomalies.append(f"could not reset to {sha[:8]}")

    def _discard(self, why: str) -> None:
        """Throw away uncommitted work -- only ever after work actually began.

        `started_work` is the guard. On a refused preflight the tree was never
        this run's to touch, and cleaning it anyway is the bug that deleted the
        previous version of this program along with its own logs.
        """
        if not self.state.started_work:
            return
        gitwork.discard(self.project.path, protect=(), run_started=True)

    def _release_claim(self, note: str) -> None:
        if not self._claimed:
            return
        task_id, self._claimed = self._claimed, None
        if note:
            self.queue.comment(task_id, note)
        if not self.queue.release(task_id):
            self.state.anomalies.append(
                f"could not release {task_id} -- it will block the next preflight"
            )

    def _finish(self) -> None:
        self.state.ended_at = _now()
        if self.state.started_work:
            self._release_claim("run ended with this task still claimed")
            self.state.tree_clean_at_end = gitwork.status(self.project.path).clean
            if (
                self.state.work_branch
                and self.contract.git.target == "branch"
                and self.state.commits
            ):
                gitwork.push(
                    self.project.path,
                    self.contract.git.remote,
                    self.state.work_branch,
                )
        (self.log_dir / "summary.json").write_text(
            json.dumps(self.state.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    # -- signals -----------------------------------------------------------

    def _install_signal_handlers(self):
        previous = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Not the main thread: a library caller gets no handler and the
            # engine still runs. Losing the interrupt is worse than raising here
            # would be, so it is recorded rather than silent.
            with contextlib.suppress(ValueError, OSError):
                previous[sig] = signal.signal(sig, self._on_signal)
        return previous

    def _restore_signal_handlers(self, previous) -> None:
        for sig, handler in previous.items():
            with contextlib.suppress(ValueError, OSError):  # pragma: no cover
                signal.signal(sig, handler)

    def _on_signal(self, signum, frame) -> None:
        self._interrupted = True
        self._emit("interrupt received -- stopping after the current step")
        raise Interrupted()

    def _raise_if_interrupted(self) -> None:
        if self._interrupted:
            raise Interrupted()

    def _emit(self, message: str) -> None:
        self.on_event(message)
        try:
            with (self.log_dir / "run.log").open("a", encoding="utf-8") as handle:
                handle.write(f"{_now()} {message}\n")
        except OSError:  # pragma: no cover
            pass


def _kept_note(run_id: str, commits: list[str]) -> str:
    """What a kept task leaves behind in the tracker.

    The run id and the commits, and nothing that reads as praise. This is the
    only place the factory's own identifiers cross into the project's tracker,
    so it names the run rather than describing it: `watermill report` and the
    task log can be found from a run id, and cannot be found from an adjective.
    """
    if not commits:
        return f"Kept by Water Mill run {run_id}, which recorded no commit."
    body = "\n".join(f"  {line}" for line in commits)
    plural = "commit" if len(commits) == 1 else "commits"
    return f"Kept by Water Mill run {run_id}. {len(commits)} {plural}:\n{body}"


def _escalation_note(text: str) -> str:
    """The agent's reasoning, from the ESCALATE line onward."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("ESCALATE"):
            rest = "\n".join(lines[index:]).strip()
            return rest[len("ESCALATE"):].strip() or "no reason given"
    return text.strip()[:800]


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in text)[:120]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
