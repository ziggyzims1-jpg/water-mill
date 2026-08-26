"""The morning report.

`compose` is pure: a RunState in, the exact markdown out. No clock, no
filesystem, no database. Every line the operator reads at 7am is therefore
testable, which matters more here than almost anywhere else in this package --
the report is the entire interface between a night of unattended work and the
person responsible for it.

**"Needs a decision" leads.** It is the only section that is *work*; everything
below it is a record. If that section is long every morning, the task
specifications need work rather than the caps needing raising -- and putting it
first is what makes that pattern visible instead of buried under a table of
successes.
"""

from __future__ import annotations

from .engine import COMPLETED, ESCALATED, FAILED, RunState


def _money(cents: int | None) -> str:
    return "unknown" if cents is None else f"${cents / 100:.2f}"


def compose(state: RunState) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# {state.project} -- run {state.run_id}")
    add("")

    if state.refused:
        add("**The run was refused at preflight. Nothing was modified.**")
        add("")
        add(f"> {state.halt_reason}")
        add("")
        add(_preflight_table(state))
        return "\n".join(lines) + "\n"

    escalations = [t for t in state.tasks if t.outcome == ESCALATED]
    failures = [t for t in state.tasks if t.outcome == FAILED]
    completions = [t for t in state.tasks if t.outcome == COMPLETED]

    add("## Needs a decision")
    add("")
    if not escalations and not failures and not state.anomalies:
        add("Nothing. Every attempted task either landed or was cleanly discarded.")
    else:
        for task in escalations:
            add(f"- **{task.id}** escalated -- {_first_line(task.note)}")
        for task in failures:
            add(f"- **{task.id}** discarded -- {task.reason}")
        for anomaly in state.anomalies:
            add(f"- anomaly: {anomaly}")
    add("")

    add("## Summary")
    add("")
    add(f"- Halted because: {state.halt_reason or 'unknown'}")
    add(
        f"- Attempted {state.tally.attempted} "
        f"({len(completions)} kept, {len(failures)} discarded, "
        f"{len(escalations)} escalated)"
    )
    spend = _money(state.tally.spend_cents)
    if state.tally.unmetered:
        spend += (
            f" -- **under-counted**, {state.tally.unmetered} task(s) reported no cost"
        )
    add(f"- Spend: {spend} of {_money(state.caps.max_spend_cents)}")
    add(f"- Branch: {state.work_branch or 'none'} (from {state.base_sha[:8] or 'unknown'})")
    if not state.tree_clean_at_end:
        add("- **The working tree is not clean.** Inspect before running again.")
    add("")

    if completions:
        add("## Kept")
        add("")
        add("| Task | Cost | Minutes | Commit |")
        add("|---|---|---|---|")
        for task in completions:
            add(
                f"| {task.id} | {_money(task.cost_cents)} | "
                f"{task.duration_seconds / 60:.0f} | {task.commit or '-'} |"
            )
        add("")

    if failures:
        add("## Discarded")
        add("")
        add("Nothing from these reached the repository.")
        add("")
        for task in failures:
            add(f"- **{task.id}** ({_money(task.cost_cents)}) -- {task.reason}")
        add("")

    if escalations:
        add("## Escalated")
        add("")
        add(
            "An escalation is the right outcome, not a failure. Each of these is "
            "a specification that needs a decision before the task can run."
        )
        add("")
        for task in escalations:
            add(f"### {task.id}")
            add("")
            add(task.note.strip() or "_no reason given_")
            add("")

    add("## If something is wrong")
    add("")
    add("Reverting has to stay routine. It is three commands:")
    add("")
    add("```")
    add("git revert <sha>")
    add("watermill release <project> <task-id>")
    add("```")
    add("")
    add(
        "Then diagnose which layer failed -- the specification, the gate, or the "
        "agent -- before running again. **Any revert halts the ramp.**"
    )
    add("")
    add(_preflight_table(state))

    return "\n".join(lines) + "\n"


def _preflight_table(state: RunState) -> str:
    if not state.preflight or not state.preflight.checks:
        return ""
    lines = ["## Preflight", "", "| Check | Result | Detail |", "|---|---|---|"]
    for check in state.preflight.checks:
        result = "skipped" if check.skipped else ("ok" if check.ok else "**REFUSED**")
        lines.append(f"| {check.name} | {result} | {check.detail} |")
    return "\n".join(lines)


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:160]
    return "no reason given"
