"""Invoking the agent, and the prompt that fences it.

Each task is a **fresh invocation**, not a continuing conversation. Accumulated
context from task 3 causes confusion on task 9, and a session primed by the
project's own session hook plus the task's spec is both more reliable and
cheaper than one carrying eight tasks of history.

`build_prompt` is pure -- a task, a contract and a gate command in, the exact
text out -- so every line the agent reads is testable without a clock, a
database or a subprocess. That is the same rule the digest in the first project
this factory drives already follows, and for the same reason: the text is the
product, so the text is what gets asserted on.

**The fence is stated here and enforced elsewhere.** Naming the protected paths
in the prompt is a courtesy that makes the agent's job possible; the check that
decides whether work is kept reads the diff (`gitwork.changed_paths` against
`contract.fence`). An instruction is a request. A diff is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contract import Contract
from .meter import Reading, read
from .proc import Result, run
from .queue import Task

#: Print mode, JSON output so the meter has a cost, and edits accepted without
#: a prompt -- an unattended run has nobody to answer one. The permission model
#: is not what makes this safe; the fence, the gate and the discard are.
DEFAULT_AGENT_COMMAND = "claude -p --output-format json --permission-mode acceptEdits"

PROMPT_TEMPLATE = """\
You are working on one task in the {project} repository, unattended.

## The task

{task_block}

## How this run judges your work

After you exit, this orchestrator independently re-runs the gate, checks the
working tree, and checks the diff against a fence. Your own exit code is not
evidence and your summary is not evidence. Only those three things decide
whether your work is kept or discarded.

The gate is:

    {gate}

Run it yourself before you finish. If it fails, make **one** attempt to fix it
and run it again.

## Fence -- files you must not modify

{fence_block}

Also, in any repository: never weaken, skip, delete or mark-as-expected a test
in order to get a green gate. A test that fails is either a bug you introduced
or a bug you found. Both are worth more than a green run.

## Scope

Do only what this task names. Do not refactor code you happened to read, do not
fix unrelated problems you noticed, and do not widen the change because it
looked easy. Anything else you find is worth filing, not fixing.

## When you are done

If the task is complete and the gate passes, commit your work. The commit
message must contain the task id `{task_id}` -- a commit without it is treated
as a failed task and discarded.

If the task needs a judgement call that is not yours to make -- an ambiguous
spec, a product decision, a change that would touch a fenced path, a gate
failure you cannot fix without one -- then **do not guess**. Leave the tree
clean, write the single word

ESCALATE

on a line of its own, and follow it with what you need decided and why. An
escalation is the right outcome, not a failure: it costs this run nothing and
it is how a bad specification gets fixed instead of silently absorbed.
"""


@dataclass(frozen=True)
class Outcome:
    """One agent invocation's result, before the orchestrator verifies anything."""

    task: Task
    result: Result
    reading: Reading

    @property
    def timed_out(self) -> bool:
        return self.result.timed_out

    @property
    def escalated(self) -> bool:
        return self.reading.escalated

    @property
    def cost_cents(self) -> int | None:
        return self.reading.cost_cents


def build_prompt(task: Task, contract: Contract, spec: str = "") -> str:
    """The exact text handed to the agent for one task.

    `spec` is whatever the queue's `show` command printed. It is included
    verbatim and is the task's real specification; the title alone is never
    enough to work from, and a run whose queue has no `show` command will
    produce vague work for exactly that reason.
    """
    task_block = spec.strip() if spec.strip() else f"{task.id}: {task.title}".strip()
    if spec.strip() and task.id not in spec:
        task_block = f"Task id: {task.id}\n\n{task_block}"

    if contract.fence.paths:
        fence_block = "\n".join(f"  - {path}" for path in contract.fence.paths)
        fence_block = (
            "These paths are protected. A change to any of them discards this "
            "task's work, whatever else you did:\n\n" + fence_block
        )
    else:
        fence_block = (
            "This project declares no fenced paths. That is not permission to "
            "range widely -- see Scope below."
        )

    return PROMPT_TEMPLATE.format(
        project=contract.name,
        task_block=task_block,
        gate=contract.commands.gate,
        fence_block=fence_block,
        task_id=task.id,
    )


def invoke(
    prompt: str,
    task: Task,
    cwd: Path,
    agent_command: str,
    timeout: float,
    log_path: Path | None = None,
) -> Outcome:
    """Run the agent once on one task.

    The prompt goes in on stdin rather than as an argument: a task spec can be
    thousands of characters, and an argv limit is a truncation that looks like
    the agent misunderstanding a complete instruction.

    The full JSON transcript is captured in memory to be metered and is written
    to `log_path` for the morning. It is not streamed to the log directly,
    because the meter needs the whole document and a half-written file on a
    timeout would parse as no cost when the agent in fact spent one.
    """
    result = run(
        agent_command,
        cwd=cwd,
        timeout=timeout,
        stdin_text=prompt,
        tail_lines=0,
    )
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.tail, encoding="utf-8", errors="replace")
    return Outcome(task=task, result=result, reading=read(result.tail))
