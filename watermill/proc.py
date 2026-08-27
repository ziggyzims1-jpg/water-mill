"""Running other people's programs, and being able to stop them.

Every external command the orchestrator runs goes through here, for three
reasons that were each a bug in the shell version of this loop:

**A child gets its own process group, and killing it kills the group.** An
agent spawns a test runner which spawns a build; signalling only the direct
child leaves the grandchildren holding the CPU and the lock files. The shell
loop took five minutes to respond to Ctrl-C for this reason and now takes one
second.

**Nothing runs through a shell.** Commands from a contract are split with
`shlex` and executed as an argv list. A task id or a comment body is data, and
data that reaches a shell is an injection whether or not anyone meant it as
one.

**Output is streamed to a file, not buffered in memory.** A task transcript can
be tens of megabytes; a run that OOMs while capturing the evidence of what went
wrong has destroyed exactly the thing it existed to produce.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Result:
    """What one command did."""

    argv: tuple[str, ...]
    returncode: int
    duration_seconds: float
    timed_out: bool
    log_path: Path | None
    #: The tail of the output, kept for the report. Never the whole transcript
    #: unless the caller asked for it with `tail_lines=0` -- which the queue
    #: does, because a truncated payload is invalid JSON rather than a short one.
    tail: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def display(self) -> str:
        return " ".join(self.argv)


def split(command: str) -> list[str]:
    """Split a contract command string into argv."""
    return shlex.split(command)


def run(
    command: str | list[str],
    cwd: Path,
    log_path: Path | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
    tail_lines: int = 40,
) -> Result:
    """Run a command to completion, or kill its whole process group trying.

    `timeout` of None means wait indefinitely -- correct for a gate, whose
    duration is the project's business. A task's agent always carries one.

    `tail_lines=0` keeps the entire output rather than the last N. Callers that
    parse the result -- the queue, the meter -- must use it: truncating JSON
    does not produce shorter JSON, it produces a parse error that reads exactly
    like the tool being broken.
    """
    argv = split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise ValueError("empty command")

    started = time.monotonic()
    full_env = {**os.environ, **(env or {})}

    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8", errors="replace")
        stdout = log_handle
    else:
        stdout = subprocess.PIPE

    captured = ""
    timed_out = False
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=stdout,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            env=full_env,
            text=True,
            # A new session so the whole tree can be signalled at once. Without
            # it, a timeout kills the agent and leaves its test runner holding
            # the CPU.
            start_new_session=True,
        )
    except OSError as exc:
        # A command that does not exist is a *failed check*, not a crash. Every
        # caller here already handles a non-zero return -- preflight turns it
        # into a refusal naming the check, the gate discards the task -- and a
        # traceback instead skips all of that: `doctor` dies before it can
        # report the other checks, which is the one thing it exists to do.
        # 127 is the shell's own code for "command not found".
        if log_handle is not None:
            log_handle.write(str(exc))
            log_handle.close()
        return Result(
            argv=tuple(argv),
            returncode=127,
            duration_seconds=time.monotonic() - started,
            timed_out=False,
            log_path=log_path,
            tail=f"could not run {argv[0]!r}: {exc.strerror or exc}",
        )
    try:
        captured_out, _ = proc.communicate(input=stdin_text, timeout=timeout)
        captured = captured_out or ""
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_group(proc)
        try:
            captured_out, _ = proc.communicate(timeout=10)
            captured = captured_out or ""
        except subprocess.TimeoutExpired:  # pragma: no cover - the SIGKILL path
            proc.kill()
            proc.wait()
    except BaseException:
        # Ctrl-C, SIGTERM, anything. The child and its whole tree go first, then
        # the exception continues to the caller's cleanup. Without this the
        # operator's interrupt returns a prompt while an agent keeps working in
        # the background -- which is how the shell version took five minutes to
        # stop and left a test runner holding the tree it was about to clean.
        _terminate_group(proc)
        raise
    finally:
        if log_handle is not None:
            log_handle.close()

    duration = time.monotonic() - started
    tail = _tail(captured, log_path, tail_lines)
    return Result(
        argv=tuple(argv),
        returncode=proc.returncode if proc.returncode is not None else -1,
        duration_seconds=duration,
        timed_out=timed_out,
        log_path=log_path,
        tail=tail,
    )


def _terminate_group(proc: subprocess.Popen) -> None:
    """Ask the process group to stop, then insist.

    SIGTERM first so a well-behaved child can flush its logs -- which on a
    timeout is the output that explains why it hung. Two seconds is enough for
    a flush and short enough that a hung run is not made hungier by the
    courtesy.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:  # pragma: no cover - it already exited
        return
    for sig, wait in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 0.0)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        if wait:
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    return
                time.sleep(0.05)


def _tail(captured: str, log_path: Path | None, lines: int) -> str:
    if captured:
        text = captured
    elif log_path is not None and log_path.is_file():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover
            return ""
    else:
        return ""
    if lines <= 0:
        return text
    return "\n".join(text.splitlines()[-lines:])
