"""The six caps, and the bookkeeping that decides when one has been reached.

A cap is not an error path. It is the system working: a run that halts on a cap
did what it was told. `Caps.check()` therefore returns a halt *reason* rather
than raising, and the engine records it in the report as an ordinary outcome.

Three properties are worth stating because each was a measured bug rather than
a design preference:

**The task cap counts attempts, not completions.** A completion cap looks
equivalent and is not: in a run where every task escalates, `completed` never
increments, so the cap never fires and the run works through the entire queue.
That was measured at 48 escalations against a limit of 1.

**Caps are checked between tasks, never during one.** Halting mid-task risks a
partial commit, which is worse than overshooting: the spend ceiling is reactive
for exactly this reason and will overshoot by up to one task. The per-task
timeout is what bounds how far.

**A meter that stops counting halts the run.** An agent that crashes reports no
cost, and a run with no meter looks cheap right up until the invoice. Past
`max_unmetered_tasks` the run stops and the report says it under-counted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

#: Platform defaults. A project contract may tighten or loosen any of these;
#: `max_spend_usd` is deliberately not among them -- see `contract.Caps`.
DEFAULTS = {
    "max_tasks": 15,
    "max_hours": 6.0,
    "max_consecutive_failures": 3,
    "task_timeout_minutes": 30.0,
    "max_unmetered_tasks": 3,
}


@dataclass
class Caps:
    """Resolved limits for one run."""

    max_tasks: int = DEFAULTS["max_tasks"]
    max_hours: float = DEFAULTS["max_hours"]
    max_consecutive_failures: int = DEFAULTS["max_consecutive_failures"]
    task_timeout_minutes: float = DEFAULTS["task_timeout_minutes"]
    max_unmetered_tasks: int = DEFAULTS["max_unmetered_tasks"]
    #: Cents. There is no default: a run with no ceiling is refused at preflight.
    max_spend_cents: int | None = None

    @classmethod
    def resolve(cls, contract_caps=None, overrides: dict | None = None) -> Caps:
        """Layer platform defaults, then the contract, then the command line.

        Later layers win, and `None` never overrides -- an unset field in a
        contract means "no opinion", not "zero".
        """
        values = dict(DEFAULTS)
        spend: int | None = None
        for layer in (contract_caps, overrides):
            if layer is None:
                continue
            items = dict(layer) if isinstance(layer, dict) else dict(vars(layer))
            for key, value in items.items():
                if value is None:
                    continue
                if key == "max_spend_cents":
                    spend = int(value)
                elif key in values:
                    values[key] = value
        return cls(
            max_tasks=int(values["max_tasks"]),
            max_hours=float(values["max_hours"]),
            max_consecutive_failures=int(values["max_consecutive_failures"]),
            task_timeout_minutes=float(values["task_timeout_minutes"]),
            max_unmetered_tasks=int(values["max_unmetered_tasks"]),
            max_spend_cents=spend,
        )

    @property
    def task_timeout_seconds(self) -> float:
        return self.task_timeout_minutes * 60.0


@dataclass
class Tally:
    """What the run has done so far.

    `attempted` is the number the task cap reads. `completed`, `failed` and
    `escalated` are reported but never capped on, because an escalation is
    neither a success nor a failure: the agent recognised a judgement call and
    stopped, which is the behaviour being asked for. It must not spend the
    consecutive-failure budget and must not inflate the night's output.
    """

    attempted: int = 0
    completed: int = 0
    failed: int = 0
    escalated: int = 0
    consecutive_failures: int = 0
    unmetered: int = 0
    spend_cents: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def record_success(self, cost_cents: int | None) -> None:
        self.attempted += 1
        self.completed += 1
        self.consecutive_failures = 0
        self._meter(cost_cents)

    def record_failure(self, cost_cents: int | None) -> None:
        self.attempted += 1
        self.failed += 1
        self.consecutive_failures += 1
        self._meter(cost_cents)

    def record_escalation(self, cost_cents: int | None) -> None:
        self.attempted += 1
        self.escalated += 1
        # Deliberately does not touch consecutive_failures: the agent was right.
        self._meter(cost_cents)

    def _meter(self, cost_cents: int | None) -> None:
        if cost_cents is None:
            self.unmetered += 1
        else:
            self.spend_cents += int(cost_cents)

    def elapsed_seconds(self, now: float | None = None) -> float:
        return (time.monotonic() if now is None else now) - self.started_at


def check(caps: Caps, tally: Tally, now: float | None = None) -> str | None:
    """Return the halt reason if a cap has been reached, else None.

    Order matters only for which reason gets reported when two fire on the same
    boundary; spend leads because it is the one the operator most needs to see.
    """
    if caps.max_spend_cents is not None and tally.spend_cents >= caps.max_spend_cents:
        return (
            f"spend cap: ${tally.spend_cents / 100:.2f} reached the "
            f"${caps.max_spend_cents / 100:.2f} ceiling"
        )
    if tally.unmetered >= caps.max_unmetered_tasks:
        return (
            f"meter stopped: {tally.unmetered} task(s) reported no cost. "
            "The run is under-counted, so it stops rather than continuing blind"
        )
    if tally.attempted >= caps.max_tasks:
        return f"task cap: {tally.attempted} attempt(s) of {caps.max_tasks}"
    if tally.consecutive_failures >= caps.max_consecutive_failures:
        return (
            f"failure cap: {tally.consecutive_failures} consecutive failures. "
            "Something is wrong with the specs, the gate or the agent"
        )
    if tally.elapsed_seconds(now) >= caps.max_hours * 3600:
        return f"wall clock: {caps.max_hours}h elapsed"
    return None
