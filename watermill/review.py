"""The monthly sweep: what the factory knows that nobody has looked at lately.

Knowledge rots in a way code does not. A failing test announces itself; a
finding that quietly stopped being true keeps being returned by `recall`,
carries the same confident date it always had, and is read by an agent as
current. Nothing in the system can notice that on its own -- the world changed,
not the file.

So a person sweeps, monthly, and this module is what they read. It is a
**reader**: it opens no network connection, claims no task, and writes nothing
except the one line that records that the sweep happened.

That last line is the point of the design rather than an afterthought. A
monthly job that silently stopped running looks exactly like a month with
nothing to review -- both produce no output -- which is the same shape as the
backup drill that needed a separate job to notice it had stopped, and the Loki
alert on `count_over_time(...[24h]) == 0`. Third sighting of the rule, so it is
mechanised here rather than written down again: `sweep()` reports how long it
has been, and `--check` exits non-zero when the sweep itself is overdue.

**It never fixes anything.** Every section is a list of things a person has to
decide -- confirm, supersede, promote, reject, mechanise. Confirming a finding
because the sweep suggested it is a judgement; a machine doing it is a clock
resetting itself, which would make the whole staleness signal meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import knowledge, recall, tasklog, usage


@dataclass
class Sweep:
    """Everything one monthly review has to look at. Pure data."""

    today: str
    days_since_review: int | None = None
    stale: list[recall.Node] = field(default_factory=list)
    proposals: list[recall.Node] = field(default_factory=list)
    unmechanised: list[recall.Node] = field(default_factory=list)
    promotable: list[tuple[str, list[recall.Node]]] = field(default_factory=list)
    unstructured: list[recall.Node] = field(default_factory=list)
    unannotated: list[dict] = field(default_factory=list)
    findings: int = 0
    cells: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    unanswered: list[tuple[str, int]] = field(default_factory=list)

    @property
    def never_reviewed(self) -> bool:
        return self.days_since_review is None

    @property
    def overdue(self) -> bool:
        """True when the sweep itself has stopped happening.

        A factory that has never been swept is overdue only once it has
        something to sweep: reporting an overdue review on an empty store would
        be an alert that fires on day one and is therefore ignored by day two.
        """
        if self.never_reviewed:
            return self.findings > 0
        return (self.days_since_review or 0) > knowledge.SWEEP_AFTER_DAYS

    @property
    def actionable(self) -> int:
        return (
            len(self.stale)
            + len(self.proposals)
            + len(self.unmechanised)
            + len(self.promotable)
            + len(self.unstructured)
            + len(self.unannotated)
            + len(self.unanswered)
        )


def sweep(root: Path, as_of: date | None = None, unannotated_limit: int = 10) -> Sweep:
    """Assemble the month's review. Reads three files, writes nothing."""
    graph = recall.build(root, as_of=as_of)
    findings = [n for n in graph.nodes if n.kind == recall.FINDING]
    # The window is the last sweep, or a month, so each sweep reads the period
    # it is actually responsible for rather than the whole history again.
    elapsed = knowledge.days_since_review(root, as_of)
    since = knowledge.horizon(
        min(elapsed, 365) if elapsed else knowledge.SWEEP_AFTER_DAYS, as_of
    )
    pending = [
        record.outcome
        for record in tasklog.read(root, unannotated=True)
        if record.outcome.get("outcome") != "completed"
    ]
    calls = usage.stats(usage.read(root, since=since))
    return Sweep(
        today=(as_of or knowledge.today()).isoformat(),
        days_since_review=knowledge.days_since_review(root, as_of),
        stale=recall.stale(graph),
        proposals=recall.proposals(graph),
        unmechanised=recall.unmechanised(graph),
        promotable=recall.promotable(graph),
        unstructured=recall.missing_structure(graph),
        unannotated=pending[-unannotated_limit:],
        findings=len(findings),
        cells=graph.cells,
        usage=calls,
        unanswered=list(calls["unanswered"].items())[:8],
    )


def render(state: Sweep) -> str:
    """The sweep, as the person doing it reads it.

    Pure -- a Sweep in, the exact text out -- for the same reason the morning
    report is pure: this text is the entire interface between a month of
    accumulated knowledge and the person responsible for it, so every line of
    it is testable without a clock or a filesystem.

    **What needs a decision leads.** Everything below it is a count.
    """
    lines: list[str] = []
    add = lines.append

    add(f"# Knowledge sweep -- {state.today}")
    add("")

    if state.never_reviewed:
        add(
            "**No sweep has ever been recorded.** "
            + (
                f"There {'is' if state.findings == 1 else 'are'} {state.findings} "
                f"finding{'' if state.findings == 1 else 's'} to look at."
                if state.findings
                else "There is nothing recorded yet, which is the correct state for a "
                "factory that has not run. Nothing to do."
            )
        )
    elif state.overdue:
        add(
            f"**The last sweep was {state.days_since_review} days ago**, past the "
            f"{knowledge.SWEEP_AFTER_DAYS}-day interval. Findings are being read by "
            "agents that nobody has vouched for since then."
        )
    else:
        add(f"Last swept {state.days_since_review} days ago.")
    add("")

    if not state.actionable:
        add("Nothing needs a decision. Record the sweep:")
        add("")
        add("    watermill review --record")
        return "\n".join(lines) + "\n"

    if state.stale:
        add(f"## Stale -- {len(state.stale)} finding(s) nobody has vouched for")
        add("")
        add(
            f"Each has gone {knowledge.REVIEW_AFTER_DAYS}+ days unconfirmed. Confirm it, "
            "or supersede it with what is true now. Both are one line and neither "
            "deletes anything."
        )
        add("")
        for node in state.stale:
            add(f"- `{node.id}` [{node.cell or 'factory'}] {node.date}, "
                f"{node.meta.get('age_days')}d: {_clip(node.text)}")
        add("")
        add("    watermill confirm <id>")
        add("    watermill remember <cell> <kind> \"...\" --supersedes <id>")
        add("")

    if state.proposals:
        add(f"## Proposed -- {len(state.proposals)} agent finding(s) in quarantine")
        add("")
        add(
            "An agent wrote each of these during a run. None of them has been "
            "returned to any other agent and none will be until it is promoted."
        )
        add("")
        for node in state.proposals:
            add(f"- `{node.id}` [{node.cell or 'factory'}] {node.date}: {_clip(node.text)}")
        add("")
        add("    watermill proposals --promote <id>      # or --reject <id> --why \"...\"")
        add("")

    if state.promotable:
        add(f"## Twice, in two cells -- {len(state.promotable)} lesson(s)")
        add("")
        add(
            "Water Mill's filing rule says a lesson is promoted into the "
            "orchestrator when it has appeared in a second repository. These have."
        )
        add("")
        for text, cluster in state.promotable:
            cells = ", ".join(sorted({n.cell for n in cluster if n.cell}))
            add(f"- {_clip(text)}")
            add(f"  seen in: {cells} -- {', '.join(n.id for n in cluster)}")
        add("")

    if state.unmechanised:
        add(f"## Still only advice -- {len(state.unmechanised)} lesson(s)")
        add("")
        add(
            "None of these became a gate check or a fence path. Advice is a "
            "request; a gate is not. Mechanise it, or record why it cannot be."
        )
        add("")
        for node in state.unmechanised:
            add(f"- `{node.id}` [{node.cell or 'factory'}]: {_clip(node.text)}")
        add("")

    lines.extend(_render_missing_structure(state))

    if state.unannotated:
        add(f"## No root cause yet -- {len(state.unannotated)} task(s)")
        add("")
        for row in state.unannotated:
            add(
                f"- {row.get('project', '?')} {row.get('task_id', '?')} "
                f"({row.get('outcome', '?')}): {_clip(str(row.get('reason', '')))}"
            )
        add("")
        add("    watermill annotate <project> <task-id> <root-cause>")
        add("")

    if state.usage.get("searches") or state.unanswered:
        rate = state.usage.get("hit_rate")
        add("## The tool itself")
        add("")
        add(
            f"{state.usage.get('searches', 0)} search(es) across "
            f"{state.usage.get('tasks', 0)} task(s) since the last sweep"
            + (f", {rate:.0%} of them answered." if rate is not None else ".")
        )
        if state.unanswered:
            add("")
            add(
                "These came back empty. That is not a failure report -- it is "
                "what the agents wanted to know and nobody had written down, in "
                "their own words:"
            )
            add("")
            for question, count in state.unanswered:
                suffix = f"  (x{count})" if count > 1 else ""
                add(f"- {_clip(question)}{suffix}")
            add("")
            add("    watermill remember <cell> lesson \"...\"")
        add("")

    add("When you are done, record that the sweep happened:")
    add("")
    add("    watermill review --record")
    return "\n".join(lines) + "\n"


def _render_missing_structure(state: Sweep) -> list[str]:
    """The 'Missing structure' section: findings with no cause or no tags."""
    if not state.unstructured:
        return []
    out = [
        f"## Missing structure -- {len(state.unstructured)} finding(s)",
        "",
        "Each lacks a person-judged root cause (blank or `pending`) or a tag, so "
        "the graph can reach it only by its words. Add what is missing; it is a new line and edits nothing.",
        "",
    ]
    for node in state.unstructured:
        has_cause = node.meta.get("root_cause") not in ("", None, knowledge.PENDING_CAUSE)
        missing = [
            label for label, present in (
                ("cause", has_cause), ("tags", node.meta.get("tags")),
            ) if not present
        ]
        out.append(f"- `{node.id}` [{node.cell or 'factory'}] no {' or '.join(missing)}: "
                   f"{_clip(node.text)}")
    out += ["", "    watermill annotate-finding <id> --cause <root-cause> --tag <tag>", ""]
    return out


def check_line(state: Sweep) -> tuple[str, int]:
    """The heartbeat, for cron: one line and an exit code.

    The three cases are genuinely different and the first version of this
    printed "last run None days ago" for the third, which reads as a bug in
    the tool rather than as the correct answer for a factory with nothing to
    sweep yet.
    """
    if state.overdue:
        since = "never" if state.never_reviewed else f"{state.days_since_review} days ago"
        return f"knowledge sweep overdue -- last swept {since}", 1
    if state.never_reviewed:
        return "no knowledge sweep recorded, and nothing recorded to sweep", 0
    return f"knowledge sweep last run {state.days_since_review} days ago", 0


def _clip(text: str, width: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 3] + "..."
