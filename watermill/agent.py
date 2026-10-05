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
{recall_block}{notes_block}
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

## Before you sign off: the handoff

Whatever the outcome -- committed, escalated, or stuck -- end your final
message with a section headed

HANDOFF

that the morning reader and the next agent can act on: where things stand
(what is committed, whether the gate passed), what you tried that did not
work and why, the one thing to do next, and any question only a human can
answer. Name files and functions, not areas; no diffs. It is kept with this
task's log. Write it even when nothing surprising happened -- one line per
heading is fine -- and write it especially when something did.
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



#: What the prompt says about the tool, and all it says. The knowledge itself is
#: never pasted in here: a prompt that carries every finding costs tokens on
#: every task forever and gets worse as the factory learns more, which is the
#: reverse of what a memory is for. Six lines that make a query possible beat
#: sixty that answer a question nobody asked.
RECALL_BLOCK = """
## What this factory already knows

You have a `recall` tool over every failure, root cause and finding from every
project this factory drives. Call it when a gate fails for a reason you do not
recognise, before changing a file whose conventions you are guessing at, or
when the spec seems to assume something. It answers in a few lines; `detail`
opens one of them. If this task teaches you something the next agent would
want, `propose` it in one sentence, with a root_cause (`none` if it is not a
failure) and at least one tag -- a person reviews it before anyone reads
it, so an uncertain finding is worth filing rather than worth suppressing.
"""


def _recall_block(enabled: bool) -> str:
    """Rendered only when the tool is actually wired to this run.

    An agent told about a tool it does not have will spend a turn discovering
    that, and may conclude the whole prompt is describing a different setup
    than the one it is in.
    """
    return RECALL_BLOCK if enabled else ""


def _notes_block(contract: Contract) -> str:
    """The project's accumulated notes, or nothing at all.

    Rendered empty when there are none rather than as "no notes recorded". A
    heading with nothing under it invites the agent to wonder what it is
    missing, and every line of a prompt is paid for on every task.
    """
    if not contract.notes:
        return ""
    lines = "\n".join(f"  - {note}" for note in contract.notes.items)
    return (
        "\n## What this project has already cost someone\n"
        "\n"
        "Each line below was written after a task went wrong in this repository.\n"
        "They are advice, not rules -- nothing here is checked afterwards, and\n"
        "where one of them conflicts with the task in front of you, the task wins\n"
        "and the conflict is worth escalating.\n"
        "\n"
        f"{lines}\n"
    )


def build_prompt(
    task: Task, contract: Contract, spec: str = "", *, recall: bool = False
) -> str:
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
        recall_block=_recall_block(recall),
        notes_block=_notes_block(contract),
        task_id=task.id,
    )


def invoke(
    prompt: str,
    task: Task,
    cwd: Path,
    agent_command: str,
    timeout: float,
    log_path: Path | None = None,
    extra_args: str = "",
) -> Outcome:
    """Run the agent once on one task.

    The prompt goes in on stdin rather than as an argument: a task spec can be
    thousands of characters, and an argv limit is a truncation that looks like
    the agent misunderstanding a complete instruction.

    `extra_args` is appended to the command rather than merged into it. What
    goes there is the recall tool's wiring, which is the factory's business and
    not the contract's -- a project should not have to restate the agent
    command to gain a tool the orchestrator is offering it.

    The full JSON transcript is captured in memory to be metered and is written
    to `log_path` for the morning. It is not streamed to the log directly,
    because the meter needs the whole document and a half-written file on a
    timeout would parse as no cost when the agent in fact spent one.
    """
    result = run(
        f"{agent_command} {extra_args}".strip() if extra_args else agent_command,
        cwd=cwd,
        timeout=timeout,
        stdin_text=prompt,
        tail_lines=0,
    )
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.tail, encoding="utf-8", errors="replace")
    return Outcome(task=task, result=result, reading=read(result.tail))
