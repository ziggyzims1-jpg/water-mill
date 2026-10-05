"""The `watermill` command line.

Every subcommand is a thin shell over the modules beside it. The logic worth
testing lives there; this file's job is argument parsing, exit codes, and one
thing that is genuinely a safety decision rather than plumbing:

**`--unattended` and the skip flags are mutually exclusive.** A skipped
baseline gate makes every later result in the run meaningless -- a failure
cannot be attributed to the agent when the tree was never known good. That is
fine when a human is watching and reading the diff, and it is not fine at 3am,
so the parser refuses the combination outright rather than warning about it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import (
    knowledge,
    land,
    ledger,
    mcp,
    publish,
    recall,
    report,
    review,
    shipper,
    tasklog,
    usage,
)
from .caps import Caps
from .contract import CONTRACT_FILENAME
from .engine import Engine
from .errors import PreflightRefusal, WatermillError
from .preflight import preflight
from .queue import WorkQueue
from .registry import REGISTRY_FILENAME, Registry

SCAFFOLD = (Path(__file__).parent / "scaffold" / "watermill.yaml").resolve()


def factory_root(explicit: str | None = None) -> Path:
    """Where the registry and the run logs live.

    Defaults to the repository this package is installed in, so `watermill`
    works from any directory -- including from inside a target project, which
    is where an operator naturally is when they want to run one.
    """
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parent.parent


def _run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# -- commands --------------------------------------------------------------


def cmd_projects(args) -> int:
    registry = Registry.load(factory_root(args.root))
    if not registry.projects:
        print("No projects registered. Add one:  watermill add <name> <path>")
        return 0
    for project in registry.projects:
        flags = []
        if not project.enabled:
            flags.append("disabled")
        if not project.exists:
            flags.append("MISSING")
        elif not project.is_git_repo:
            flags.append("NOT A GIT REPO")
        try:
            contract = project.load_contract()
            summary = f"gate: {contract.commands.gate}"
        except WatermillError as exc:
            summary = f"contract error: {exc}"
            flags.append("UNUSABLE")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"{project.name}{suffix}")
        print(f"    path: {project.path}")
        print(f"    {summary}")
    return 0


def cmd_validate(args) -> int:
    registry = Registry.load(factory_root(args.root))
    targets = [registry.get(args.project)] if args.project else list(registry.projects)
    failed = 0
    for project in targets:
        try:
            contract = project.load_contract()
        except WatermillError as exc:
            print(f"{project.name}: REFUSED -- {exc}")
            failed += 1
            continue
        print(f"{project.name}: ok ({contract.source})")
        print(f"    gate:    {contract.commands.gate}")
        print(f"    branch:  {contract.git.base_branch} (target: {contract.git.target})")
        print(f"    queue:   {contract.queue.kind}")
        print(f"    fence:   {len(contract.fence.paths)} path(s)")
        steps = [
            name for name in ("create", "verify", "merge")
            if getattr(contract.review, name)
        ]
        shape = " -> ".join(steps) if steps else "none -- watermill land will refuse"
        print(f"    review:  {shape}")
        if not contract.commands.backup_check:
            print("    note:    no backup_check -- this project cannot prove it is recoverable")
        if not contract.fence.paths:
            print("    note:    no fenced paths -- nothing is protected from a bad task")
    return 1 if failed else 0


def cmd_add(args) -> int:
    root = factory_root(args.root)
    path = root / REGISTRY_FILENAME
    target = Path(args.path).resolve()
    try:
        relative = target.relative_to(root)
        stored = str(relative)
    except ValueError:
        # A sibling checkout: keep it relative so the pair can move together.
        import os

        stored = os.path.relpath(target, root)

    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not existing.strip():
        existing = "version: 1\nprojects: []\n"
    if f"name: {args.name}\n" in existing:
        print(f"{args.name} is already registered")
        return 1
    block = f"  - name: {args.name}\n    path: {stored}\n"
    if args.contract:
        block += f"    contract: {args.contract}\n"
    if "projects: []" in existing:
        updated = existing.replace("projects: []\n", "projects:\n" + block)
    else:
        updated = existing.rstrip("\n") + "\n" + block
    path.write_text(updated, encoding="utf-8")
    print(f"registered {args.name} -> {stored}")
    print(f"Next:  watermill validate {args.name}")
    return 0


def cmd_init(args) -> int:
    """Write a starter contract into a project."""
    target = Path(args.path).resolve() / CONTRACT_FILENAME
    if target.exists() and not args.force:
        print(f"{target} already exists. Use --force to overwrite.")
        return 1
    template = SCAFFOLD.read_text(encoding="utf-8")
    template = template.replace("PROJECT_NAME", args.name or Path(args.path).resolve().name)
    target.write_text(template, encoding="utf-8")
    print(f"wrote {target}")
    print("Edit it, then:  watermill validate")
    return 0


def cmd_doctor(args) -> int:
    root = factory_root(args.root)
    registry = Registry.load(root)
    targets = [registry.get(args.project)] if args.project else list(registry.active)
    worst = 0
    for project in targets:
        print(f"\n{project.name}")
        try:
            contract = project.load_contract()
        except WatermillError as exc:
            print(f"  contract: REFUSED -- {exc}")
            worst = 2
            continue
        # Doctor never invokes an agent, so any ceiling satisfies the check that
        # one was set. Zero is honest about what this command is allowed to spend.
        caps = Caps.resolve(contract.caps, {"max_spend_cents": 0})
        result = preflight(
            project,
            contract,
            caps,
            agent_binary=args.agent,
            log_dir=root / "runs" / project.name / "doctor",
            skip_gate=not args.gate,
            skip_backup=args.skip_backup,
            require_queue=False,
        )
        print(result.render())
        if not result.ok:
            worst = 3
    print()
    if not args.gate:
        print("The baseline gate was not run. `watermill doctor --gate` runs it -- and")
        print("a real run always does, because it is the only thing that proves the")
        print("tree was good before the agent touched it.")
    return worst



def _resolve_recall(flag: bool | None, contract) -> bool:
    """The contract decides; an explicit flag overrides it either way.

    `None` means neither `--recall` nor `--no-recall` was given. Kept as its
    own function so the precedence is one line that a test can pin, rather
    than a fact spread across the parser and the engine call.
    """
    return contract.knowledge.recall if flag is None else flag

def cmd_run(args) -> int:
    root = factory_root(args.root)
    registry = Registry.load(root)
    project = registry.get(args.project)
    contract = project.load_contract()

    overrides = {
        "max_tasks": args.max_tasks,
        "max_hours": args.max_hours,
        "max_consecutive_failures": args.max_failures,
        "task_timeout_minutes": args.task_timeout,
        "max_spend_cents": None if args.max_spend is None else int(round(args.max_spend * 100)),
    }
    caps = Caps.resolve(contract.caps, overrides)

    run_id = _run_id()
    log_dir = root / "runs" / project.name / run_id

    pause = _supervised_pause if args.supervised else None
    recall = _resolve_recall(args.recall, contract)
    engine = Engine(
        project,
        contract,
        caps,
        log_dir,
        agent_command=args.agent,
        supervised=args.supervised,
        on_event=lambda message: print(message, flush=True),
        skip_gate=args.skip_gate,
        skip_backup=args.skip_backup,
        pause_between=pause,
        recall=recall,
    )

    print(f"Water Mill -- {contract.name} -- run {run_id}")
    print(f"logs: {log_dir}")
    print(f"recall: {'on' if recall else 'off'} "
          f"({'command line' if args.recall is not None else 'contract'})")
    print()

    try:
        state = engine.run()
        exit_code = 0
    except PreflightRefusal as exc:
        state = engine.state
        print(f"\nRefused: {exc}")
        exit_code = 3

    text = report.compose(state)
    (log_dir / "REPORT.md").write_text(text, encoding="utf-8")
    summary = state.to_dict()
    ledger.append(root, ledger.Entry.from_summary(summary, log_dir))
    tasklog.append_run(root, summary, log_dir)

    print()
    print(text)
    return exit_code


def _supervised_pause(state) -> bool:
    """Stop between tasks so a human can read what just happened.

    Returns whether to carry on. It used to raise `KeyboardInterrupt` on "n",
    which escaped `cmd_run` before the report, the ledger line and the task log
    were written -- so ending a supervised run the ordinary way left the work
    committed and the run itself unrecorded, invisible to `watermill status`
    and to everything `watermill ship` sends onward. The run's own history is
    the product here; it cannot be the thing that a normal exit drops.

    This is what calibration runs on. The thing being watched for is not
    whether the code is right -- the gate answers that -- it is *why* a task
    went wrong: a vague goal, an incomplete file list, an insufficient
    out-of-scope clause, or the finding that halts everything downstream, work
    that passes the gate and is still wrong.
    """
    last = state.tasks[-1] if state.tasks else None
    print()
    print("-" * 60)
    if last:
        print(f"{last.id}: {last.outcome}" + (f" -- {last.reason}" if last.reason else ""))
    print(f"attempted {state.tally.attempted}, spend ${state.tally.spend_cents / 100:.2f}")
    try:
        answer = input("Continue? [Y/n] ").strip().lower()
    except EOFError:
        # No terminal to ask. Stop rather than run on unwatched: --supervised
        # is an assertion that somebody is reading, and nobody is.
        answer = "n"
    return answer not in ("n", "no", "q", "quit")


def cmd_status(args) -> int:
    root = factory_root(args.root)
    registry = Registry.load(root)
    rows = ledger.read(root)
    for project in registry.projects:
        project_rows = [r for r in rows if r.get("project") == project.name]
        last = project_rows[-1] if project_rows else None
        print(f"{project.name}")
        if last:
            outcome = "refused" if last.get("refused") else last.get("halt_reason", "")
            print(f"    last run: {last.get('started_at', '?')} -- {outcome}")
            print(
                f"    kept {last.get('completed', 0)}, discarded {last.get('failed', 0)}, "
                f"escalated {last.get('escalated', 0)}, "
                f"${last.get('spend_cents', 0) / 100:.2f}"
            )
        else:
            print("    never run")
    if rows:
        overall = ledger.stats(rows)
        print()
        print("Across all projects:")
        print(f"    runs: {overall['runs']} ({overall['runs_refused']} refused at preflight)")
        if overall["keep_rate"] is not None:
            print(f"    keep rate: {overall['keep_rate']:.0%}")
            print(f"    escalation rate: {overall['escalation_rate']:.0%}")
        if overall["cents_per_kept_task"] is not None:
            print(f"    cost per kept task: ${overall['cents_per_kept_task'] / 100:.2f}")
        if overall["under_counted_runs"]:
            print(f"    under-counted runs: {overall['under_counted_runs']}")
    return 0


def cmd_release(args) -> int:
    root = factory_root(args.root)
    registry = Registry.load(root)
    project = registry.get(args.project)
    contract = project.load_contract()
    queue = WorkQueue(contract.queue, project.path)
    if not queue.enabled:
        print(f"{project.name} has no queue configured")
        return 1
    ok = queue.release(args.task_id)
    print(f"{'released' if ok else 'could not release'} {args.task_id}")
    return 0 if ok else 1


def cmd_land(args) -> int:
    """Open, verify and merge the pull request a finished run left behind.

    Its own command with its own exit code, and never part of `run`. Every step
    it takes talks to a forge, and a forge that is down must not be able to hang
    a night or hold a claimed task open across the outage.
    """
    root = factory_root(args.root)
    registry = Registry.load(root)
    project = registry.get(args.project)
    contract = project.load_contract()

    base = root / "runs" / project.name
    if args.run_id:
        target = base / args.run_id
    else:
        candidates = sorted(p for p in base.glob("*/summary.json"))
        if not candidates:
            print(f"{project.name} has never finished a run, so there is nothing to land")
            return 3
        target = candidates[-1].parent

    summary = land.read_summary(target / "summary.json")
    result = land.land(
        project, contract, summary, merge=not args.no_merge, on_event=print
    )
    print(result.render())
    (target / "land.json").write_text(
        json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    if result.refused:
        return 3
    return 1 if result.failed else 0


def cmd_report(args) -> int:
    root = factory_root(args.root)
    # Ask the registry before the filesystem. Reading `runs/<name>/` straight
    # off the argument answers a different question -- "has anything ever run
    # under this name" -- and so reports a typo as a fact about the factory's
    # history. `watermill report tasks` said "no runs recorded for tasks",
    # which is true of every word that is not a project, and reads like a
    # missing record rather than a name this factory has never heard of.
    Registry.load(root).get(args.project)
    base = root / "runs" / args.project
    if not base.is_dir():
        print(f"{args.project} is registered but has never run")
        return 1
    if args.run_id:
        target = base / args.run_id
    else:
        candidates = sorted(p for p in base.iterdir() if (p / "REPORT.md").is_file())
        if not candidates:
            print(f"no reports under {base}")
            return 1
        target = candidates[-1]
    path = target / "REPORT.md"
    if not path.is_file():
        print(f"no report at {path}")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_ledger(args) -> int:
    root = factory_root(args.root)
    rows = ledger.read(root, project=args.project, limit=args.limit)
    if not rows:
        print("no runs recorded")
        return 0
    for row in rows:
        marker = "refused" if row.get("refused") else (
            "supervised" if row.get("supervised") else "run"
        )
        print(
            f"{row.get('started_at', '?'):<26} {row.get('project', '?'):<24} "
            f"{marker:<11} kept {row.get('completed', 0):>2} "
            f"disc {row.get('failed', 0):>2} esc {row.get('escalated', 0):>2} "
            f"${row.get('spend_cents', 0) / 100:>6.2f}"
        )
    return 0


def cmd_tasks(args) -> int:
    """Every task the factory has attempted, and why each one went wrong."""
    root = factory_root(args.root)
    # Same reason as `report`: an unregistered name filters the log down to
    # nothing and prints that as though the history were empty.
    if args.project:
        Registry.load(root).get(args.project)
    records = tasklog.read(
        root, project=args.project, limit=args.limit, unannotated=args.unannotated
    )
    if not records:
        print("no tasks recorded" + (" without a root cause" if args.unannotated else ""))
        return 0

    for record in records:
        row = record.outcome
        cause = record.root_cause or (
            f"?{row.get('hint')}" if row.get("hint") else "-"
        )
        print(
            f"{row.get('recorded_at', '?'):<26} {row.get('project', '?'):<20} "
            f"{row.get('task_id', '?'):<26} {row.get('outcome', '?'):<10} "
            f"{cause:<18} {row.get('reason', '')[:40]}"
        )
        # The run and the commit, on their own line. Both have been written to
        # the task log since the first task and neither was ever printed, so
        # this command could say a task completed while showing neither which
        # run did it nor what reached the repository -- the two things a
        # morning needs in order to go and look.
        provenance = "  ".join(
            part
            for part in (
                f"run {row['run_id']}" if row.get("run_id") else "",
                str(row.get("commit", "")).strip(),
            )
            if part
        )
        if provenance:
            print(f"{'':26} {provenance[:120]}")
        if record.note:
            print(f"{'':26} {record.note[:100]}")

    stats = tasklog.causes(records)
    print()
    print(f"{stats['tasks']} tasks, {stats['annotated']} with a root cause recorded")
    for cause, count in stats["by_cause"].items():
        print(f"    {cause:<18} {count}")
    if stats["unannotated"]:
        # Said plainly rather than left to arithmetic. A taxonomy with most of
        # its mass unlabelled is a process nobody is following, and that is the
        # finding.
        print(f"    {'(no cause given)':<18} {stats['unannotated']}")
        print()
        print("A `?` prefix is the orchestrator's guess, not a judgement. Record one:")
        print("    watermill annotate <project> <task-id> <root-cause>")
    if stats["gate_holes"]:
        print()
        print(
            f"{stats['gate_holes']} task(s) passed the gate and were still wrong. "
            "That halts calibration -- the gate needs a new check before anything "
            "else proceeds."
        )
    return 0


def cmd_annotate(args) -> int:
    """Record why a task went the way it did. Appends; never edits."""
    root = factory_root(args.root)
    if args.root_cause not in tasklog.ROOT_CAUSES:
        print(f"unknown root cause: {args.root_cause}")
        print()
        for name, description in tasklog.ROOT_CAUSES.items():
            print(f"  {name:<18} {description}")
        return 2
    tasklog.annotate(
        root,
        project=args.project,
        task_id=args.task_id,
        root_cause=args.root_cause,
        note=args.note or "",
    )
    print(f"{args.project} {args.task_id}: {args.root_cause}")
    if args.root_cause == "gate-hole":
        print()
        print(tasklog.ROOT_CAUSES["gate-hole"])
    return 0


def cmd_calibrate(args) -> int:
    """Open a project's calibration record, creating it from the template."""
    root = factory_root(args.root)
    registry = Registry.load(root)
    project = registry.get(args.project)

    template = root / "docs" / "calibration" / "TEMPLATE.md"
    target = root / "docs" / "calibration" / f"{project.name}.md"
    if target.is_file():
        print(target)
        return 0
    if not template.is_file():
        print(f"no template at {template}")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        template.read_text(encoding="utf-8").replace("PROJECT_NAME", project.name),
        encoding="utf-8",
    )
    print(f"created {target}")
    print()
    print("Eight tasks, one at a time, watched live:")
    print(f"    ./bin/watermill run {project.name} --max-spend 5 --max-tasks 1 --supervised")
    return 0


def cmd_recall(args) -> int:
    """Ask the context graph a question. The same read the agent's tool makes."""
    root = factory_root(args.root)

    if args.usage:
        return _print_usage(root, since=args.since or "")

    graph = recall.build(root)

    if args.detail:
        print(recall.detail(graph, args.detail))
        return 0

    answer = recall.search(
        graph,
        args.query or "",
        cell="" if args.everywhere else (args.cell or ""),
        since=args.since or "",
        cause=args.cause or "",
        limit=args.limit,
        include_proposed=args.include_proposed,
    )
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2))
        return 0
    print(answer.render())
    if answer.hits:
        print()
        print("Open one:  watermill recall --detail <id>")
    return 0


def _print_usage(root, since: str = "") -> int:
    """Whether the tool is being used, and what it could not answer.

    The unanswered list is the useful half. Everything else here is a
    percentage; that is a list of findings somebody should write, phrased by
    the agents that wanted them.
    """
    stats = usage.stats(usage.read(root, since=since))
    if not stats["calls"]:
        print(
            "The context graph has never been called."
            + (f" (since {since})" if since else "")
        )
        print("Runs give an agent the tool with:  watermill run <project> ... --recall")
        return 0

    rate = stats["hit_rate"]
    print(
        f"{stats['searches']} search(es), {stats['opened']} opened, "
        f"{stats['proposed']} proposed, across {stats['tasks']} task(s)"
    )
    if rate is not None:
        print(f"{rate:.0%} of searches returned something.")
    if stats["unanswered"]:
        print()
        print("Asked and not answered -- these are the findings worth writing:")
        for question, count in list(stats["unanswered"].items())[:15]:
            suffix = f"  (x{count})" if count > 1 else ""
            print(f"    {question[:100]}{suffix}")
    return 0


def cmd_remember(args) -> int:
    """Record a finding. A person's judgement, dated, in the shared graph."""
    root = factory_root(args.root)
    if args.cell:
        # An unregistered cell name files the finding where no query will look
        # for it, which is indistinguishable from never having written it down.
        Registry.load(root).get(args.cell)
    try:
        line = knowledge.record(
            root,
            cell=args.cell or "",
            kind=args.kind,
            text=args.text,
            detail=args.detail or "",
            observed_at=args.on or "",
            root_cause=args.cause or "",
            destination=args.destination or "",
            tags=tuple(args.tag or ()),
            refs={"tasks": args.task or [], "runs": args.run or [],
                  "paths": args.path or [], "cells": args.also_in or []},
        )
    except knowledge.KnowledgeError as exc:
        print(f"refused: {exc}")
        return 2

    print(f"{line['id']}  [{line['kind']}] {line['cell'] or 'factory'}  {line['observed_at']}")
    if args.supersedes:
        older = knowledge.get(root, args.supersedes)
        if older is None:
            print(f"warning: no finding {args.supersedes} -- nothing was superseded")
        else:
            knowledge.supersede(root, args.supersedes, line["id"], note=args.why or "")
            print(f"supersedes {args.supersedes}, which is no longer returned by recall")
    if not line["destination"]:
        print()
        print(
            "Not mechanised. If a gate check or a fence path could carry this "
            "instead, that is worth more than a finding -- record it with "
            "--destination once it does."
        )
    return 0


def cmd_confirm(args) -> int:
    """Say a finding still holds. Resets its clock without editing it."""
    root = factory_root(args.root)
    record = knowledge.get(root, args.finding_id)
    if record is None:
        print(f"no finding {args.finding_id}")
        return 1
    if record.status == knowledge.SUPERSEDED:
        print(f"{args.finding_id} was superseded by {record.superseded_by}. Confirm that instead.")
        return 1
    knowledge.confirm(root, args.finding_id, on=args.on or "", by=args.by or "")
    print(f"{args.finding_id} confirmed. Next review due in {knowledge.REVIEW_AFTER_DAYS} days.")
    return 0


def cmd_proposals(args) -> int:
    """Agent findings in quarantine, and the decision on them."""
    root = factory_root(args.root)
    if args.promote or args.reject:
        target = args.promote or args.reject
        record = knowledge.get(root, target)
        if record is None:
            print(f"no finding {target}")
            return 1
        if record.status != knowledge.PROPOSED:
            print(f"{target} is {record.status}, not a pending proposal")
            return 1
        knowledge.decide(root, target, promote=bool(args.promote), why=args.why or "")
        verb = "promoted -- agents can now recall it" if args.promote else "rejected"
        print(f"{target} {verb}")
        return 0

    pending = recall.proposals(recall.build(root))
    if not pending:
        print("No proposals waiting. Nothing an agent wrote is being withheld.")
        return 0
    for node in pending:
        print(f"{node.id}  [{node.label}] {node.cell or 'factory'}  {node.date}")
        print(f"    {node.text[:150]}")
    print()
    print(f"{len(pending)} waiting. None is visible to any agent until promoted:")
    print("    watermill proposals --promote <id>")
    print("    watermill proposals --reject <id> --why \"...\"")
    return 0


def cmd_review(args) -> int:
    """The monthly sweep over everything the factory believes."""
    root = factory_root(args.root)
    state = review.sweep(
        root, lag_since=args.lag_since or review.LAG_SINCE,
        lag_after_days=args.lag_days,
    )

    if args.lag:
        # Just the list, for a hook or the lander. Prints nothing but the
        # beads, and never fails: `--check` is the thing that gates.
        text = "\n".join(review.render_lag(state)).strip()
        print(text or "no landed bead is waiting on a finding")
        return 0

    if args.check:
        # The heartbeat, for cron. A sweep that stopped happening looks exactly
        # like a month with nothing to sweep, so this is the only thing here
        # that can fail -- and it fails on the absence, not on the findings.
        line, code = review.check_line(state)
        print(line)
        return code

    if args.record:
        knowledge.record_review(root, by=args.by or "", note=args.note or "")
        print(f"sweep recorded. Next due within {knowledge.SWEEP_AFTER_DAYS} days.")
        return 0

    print(review.render(state))
    return 0


def cmd_mcp(args) -> int:
    """Serve the context graph over stdio. Started by the engine, not by hand."""
    server = mcp.Server(
        root=factory_root(args.root),
        cell=args.cell or "",
        run_id=args.run or "",
        task_id=args.task or "",
        read_only=args.read_only,
    )
    return mcp.serve(server)


def cmd_ship(args) -> int:
    """Send the ledger and the task log to Loki."""
    root = factory_root(args.root)
    try:
        summary = shipper.ship(
            root, url=args.url or "", user=args.user or "", token=args.token or "",
            job=args.job, dry_run=args.dry_run, resend=args.resend,
        )
    except shipper.ShipError as exc:
        # Exit 1, not 3: shipping was attempted and did not land. A refusal is
        # for a precondition, and nothing here modified anything.
        print(f"ship failed: {exc}")
        return 1

    if not summary["shipped"]:
        print("nothing new to ship")
        return 0
    if summary["dry_run"]:
        print(json.dumps(summary["payload"], indent=2))
        print()
        print(f"dry run -- {summary['shipped']} line(s) in "
              f"{summary['streams']} stream(s), nothing sent and nothing recorded")
        return 0
    print(f"shipped {summary['shipped']} line(s) in {summary['streams']} stream(s)")
    return 0


def cmd_publish(args) -> int:
    """PUT a status snapshot of every project to the Zimmy Life Tracker.

    A reader, like `ship`: never part of a run, never a write to a target
    repository or to the ledger. A missing URL or key is a refusal (3) and
    nothing is sent; a push that was attempted and did not land is a failure
    (1). Both messages name what to set and neither prints the key.
    """
    root = factory_root(args.root)
    summary = publish.publish(
        root, url=args.to, key_env=args.key_env, project=args.project,
        dry_run=args.dry_run, out=Path(args.out) if args.out else None,
    )
    if summary["dry_run"]:
        if summary["out"] is not None:
            print(f"wrote {summary['out']}")
        else:
            print(summary["text"], end="")
        return 0
    snapshot = summary["snapshot_id"]
    print(
        f"published snapshot {snapshot if snapshot is not None else '(no id returned)'} "
        f"at {summary['published_at']} ({summary['status']})"
    )
    return 0


# -- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watermill",
        description="A multi-project orchestrator for supervised and unattended agent work.",
    )
    parser.add_argument("--root", help="factory root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("projects", help="list registered projects")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("add", help="register a project")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("--contract", help="vendored contract path, if the project has none")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("init", help="write a starter contract into a project")
    p.add_argument("path")
    p.add_argument("--name")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="parse and explain a project's contract")
    p.add_argument("project", nargs="?")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("doctor", help="run the preflight checks without working")
    p.add_argument("project", nargs="?")
    p.add_argument("--gate", action="store_true", help="also run the project's gate")
    p.add_argument("--skip-backup", action="store_true")
    p.add_argument("--agent", default="claude")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("run", help="work the queue")
    p.add_argument("project")
    p.add_argument("--max-spend", type=float, required=True,
                   help="ceiling in dollars. No default, on purpose")
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--max-hours", type=float)
    p.add_argument("--max-failures", type=int)
    p.add_argument("--task-timeout", type=float, help="minutes")
    p.add_argument("--supervised", action="store_true",
                   help="stop and report between tasks")
    p.add_argument("--unattended", action="store_true",
                   help="assert nobody is watching; refuses every skip flag")
    p.add_argument("--skip-gate", action="store_true",
                   help="skip the baseline gate (never on an unattended run)")
    p.add_argument("--skip-backup", action="store_true")
    p.add_argument("--agent", default=None)
    recall_group = p.add_mutually_exclusive_group()
    recall_group.add_argument(
        "--recall", dest="recall", action="store_const", const=True, default=None,
        help="give the agent the context graph as a tool, whatever the contract "
             "says (see docs/KNOWLEDGE.md)")
    recall_group.add_argument(
        "--no-recall", dest="recall", action="store_const", const=False,
        help="withhold the tool, whatever the contract says")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="readiness and recent history per project")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("land", help="open, verify and merge a run's pull request")
    p.add_argument("project")
    p.add_argument("run_id", nargs="?", help="default: the most recent finished run")
    p.add_argument(
        "--no-merge",
        action="store_true",
        help="stop after a green verify and leave the merge to a person",
    )
    p.set_defaults(func=cmd_land)

    p = sub.add_parser("report", help="print a run's report")
    p.add_argument("project")
    p.add_argument("run_id", nargs="?")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("ledger", help="run history across projects")
    p.add_argument("project", nargs="?")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("tasks", help="per-task history and root causes")
    p.add_argument("project", nargs="?")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--unannotated", action="store_true",
                   help="only tasks with no root cause recorded yet")
    p.set_defaults(func=cmd_tasks)

    p = sub.add_parser("annotate", help="record why a task went the way it did")
    p.add_argument("project")
    p.add_argument("task_id")
    p.add_argument("root_cause", help="one of: " + ", ".join(sorted(tasklog.ROOT_CAUSES)))
    p.add_argument("--note", help="a sentence for the next person")
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("calibrate", help="open a project's calibration record")
    p.add_argument("project")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("recall", help="ask the context graph what the factory knows")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--cell", help="restrict to one project")
    p.add_argument("--everywhere", action="store_true", help="every cell, not just one")
    p.add_argument("--limit", type=int, default=recall.DEFAULT_LIMIT)
    p.add_argument("--detail", metavar="ID", help="open one result in full")
    p.add_argument("--since", metavar="YYYY-MM-DD", help="only what was observed since")
    p.add_argument("--cause", help="only findings filed under one root cause")
    p.add_argument("--usage", action="store_true",
                   help="what agents asked the graph, and what it could not answer")
    p.add_argument("--include-proposed", action="store_true",
                   help="include agent proposals, which no agent can see")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("remember", help="record a finding in the context graph")
    p.add_argument("cell", help="the project it is about, or '' for the factory itself")
    p.add_argument("kind", choices=sorted(knowledge.KINDS))
    p.add_argument("text", help="one sentence")
    p.add_argument("--detail", help="a paragraph, returned only by --detail")
    p.add_argument("--on", metavar="YYYY-MM-DD",
                   help="when it was observed, if not today")
    p.add_argument("--cause", help="a root cause bucket, if it maps to one")
    p.add_argument("--destination", choices=sorted(knowledge.DESTINATIONS),
                   help="where this lesson was mechanised")
    p.add_argument("--supersedes", metavar="ID", help="the finding this replaces")
    p.add_argument("--why", help="with --supersedes, what changed")
    p.add_argument("--task", action="append", help="repeatable")
    p.add_argument("--run", action="append", help="repeatable")
    p.add_argument("--path", action="append", help="repeatable")
    p.add_argument("--also-in", action="append", metavar="CELL", help="repeatable")
    p.add_argument("--tag", action="append", help="repeatable")
    p.set_defaults(func=cmd_remember)

    p = sub.add_parser("confirm", help="say a finding still holds")
    p.add_argument("finding_id")
    p.add_argument("--on", metavar="YYYY-MM-DD")
    p.add_argument("--by")
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("proposals", help="agent findings waiting on a person")
    p.add_argument("--promote", metavar="ID")
    p.add_argument("--reject", metavar="ID")
    p.add_argument("--why")
    p.set_defaults(func=cmd_proposals)

    p = sub.add_parser("review", help="the monthly sweep over what the factory believes")
    p.add_argument("--record", action="store_true", help="record that the sweep happened")
    p.add_argument("--check", action="store_true",
                   help="exit non-zero if the sweep itself is overdue")
    p.add_argument("--lag", action="store_true",
                   help="only the beads landed without a finding")
    p.add_argument("--lag-days", type=int, default=review.LAG_AFTER_DAYS,
                   help="--check fails on a bead landed more than this many days ago")
    p.add_argument("--lag-since", type=date.fromisoformat, metavar="YYYY-MM-DD",
                   help="ignore beads landed before this (default "
                   f"{review.LAG_SINCE})")
    p.add_argument("--by")
    p.add_argument("--note")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("mcp", help="serve the context graph over stdio (started by a run)")
    p.add_argument("--cell")
    p.add_argument("--run")
    p.add_argument("--task")
    p.add_argument("--read-only", action="store_true")
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("ship", help="send the ledger and task log to Loki")
    p.add_argument("--url", help="Loki base URL (default: $LOKI_URL)")
    p.add_argument("--user", help="basic-auth user (default: $LOKI_USER)")
    p.add_argument("--token", help="basic-auth token (default: $LOKI_TOKEN)")
    p.add_argument("--job", default="watermill", help="the job label")
    p.add_argument("--dry-run", action="store_true",
                   help="print the payload; send nothing, record nothing")
    p.add_argument("--resend", action="store_true",
                   help="ignore the high-water mark and re-send everything")
    p.set_defaults(func=cmd_ship)

    p = sub.add_parser("publish", help="push a status snapshot to the Zimmy Life Tracker")
    p.add_argument("--to", help=f"Zimmy base URL (default: ${publish.URL_ENV})")
    p.add_argument("--key-env", metavar="NAME",
                   help=f"environment variable holding the API key (default: {publish.KEY_ENV})")
    p.add_argument("--dry-run", action="store_true",
                   help="print the document; send nothing")
    p.add_argument("--out", metavar="FILE", help="with --dry-run, write the document here")
    p.add_argument("--project", help="only this project (default: every registered one)")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("release", help="hand a stuck task back to the queue")
    p.add_argument("project")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_release)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        if args.agent is None:
            from .agent import DEFAULT_AGENT_COMMAND

            args.agent = DEFAULT_AGENT_COMMAND
        if args.unattended and (args.skip_gate or args.skip_backup):
            parser.error(
                "--unattended refuses --skip-gate and --skip-backup. A skipped "
                "baseline makes every result in the run unattributable, which is "
                "acceptable only while somebody is reading the diff."
            )
        if args.unattended and args.supervised:
            parser.error("--unattended and --supervised are opposites")

    try:
        return args.func(args)
    except WatermillError as exc:
        print(f"watermill: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
