"""Publishing a status snapshot of every project to the Zimmy Life Tracker.

`watermill status` answers "where is the factory" to somebody sitting at this
checkout. This module answers the same question to a web page: one JSON document
describing every registered project -- its queue, its run history, its open
pull requests and what needs a person's attention -- assembled here and PUT to
Zimmy, which stores it and draws a "Water Mill" tab.

It is a **reader**, in exactly the sense `shipper.py` is. It never runs during
a run, never modifies a target repository, and never writes to the ledger. Every
command it invokes is a query (`git rev-parse`, `git remote get-url`, `bd list
--readonly`, `gh pr list`), and the only thing it writes anywhere is the
document, to Zimmy or -- with `--dry-run` -- to stdout.

Three rules shape the document:

**Unknown is omitted, never zeroed.** A `bd` that is not installed and a queue
with nothing in it both produce "no rows" from the outside, and a dashboard
that draws the first as `0 open` is lying in the direction that makes a broken
tool look like a finished project. So a source that fails leaves its keys out
of the document entirely and adds an `attention` item of kind `drift` saying
what it said, and the page draws a gap rather than a number.

**Secrets never reach the output.** The API key comes from the environment,
goes into one request header, and is never printed, not even on failure.

**Sending is a failure; a missing precondition is a refusal.** No URL or no
key exits 3 before anything is assembled or sent, in the same sense a
preflight refusal does: nothing happened. A 500 or an unreachable host exits 1:
the push was attempted and did not land.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import ledger, tasklog
from .contract import Contract
from .errors import WatermillError
from .queue import WorkQueue, _load_json, _parse_rows
from .registry import Project, Registry

SCHEMA = 1
PUBLISHER = "watermill publish"
API_PATH = "/api/watermill"
DEFAULT_TIMEOUT = 20.0
COMMAND_TIMEOUT = 120.0
URL_ENV = "ZIMMY_URL"
KEY_ENV = "ZIMMY_API_KEY"
RECENT_RUNS = 10
RECENT_TASKS = 15
PR_LIMIT = 30

#: `bd list` with every flag that makes it a query and nothing else.
#: `--readonly` blocks writes and `--sandbox` blocks Dolt's auto-push, because
#: this command runs from cron against a repository a run may own tonight, and
#: "list" must not be the thing that changes it. `--flat -n 0` because the
#: default is a tree of fifty, and a page counting an epic's children needs
#: every row, not the first screen of them.
BD_LIST = ["bd", "list", "--json", "--all", "--flat", "-n", "0", "--readonly", "--sandbox"]

class PublishRefusal(WatermillError):
    """A precondition did not hold. Nothing was assembled or sent."""

    exit_code = 3


class PublishError(WatermillError):
    """The push was attempted and did not land."""

    exit_code = 1


# -- running commands ------------------------------------------------------


@dataclass(frozen=True)
class Output:
    """What one query command said. stderr is kept apart from stdout because
    the JSON parsers here read one and the drift items quote the other."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def first_error_line(self) -> str:
        for line in (self.stderr or self.stdout).splitlines():
            if line.strip():
                return line.strip()
        return f"exit {self.returncode}"


Runner = Callable[[list[str], Path], Output]


def run_command(argv: list[str], cwd: Path) -> Output:
    """Run one query as argv -- never through a shell -- and capture both
    streams separately. The same seam every test replaces.

    Not `proc.run`, deliberately: that merges stderr into stdout so a gate's
    transcript reads in order, and here the two have different jobs -- stdout
    is parsed and stderr is quoted. A `bd` warning on stderr would otherwise be
    inside the JSON payload rather than beside it.
    """
    try:
        done = subprocess.run(  # noqa: S603 - argv, no shell, from this module
            argv, cwd=str(cwd), capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=COMMAND_TIMEOUT, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"},
        )
    except OSError as exc:
        return Output(127, "", f"could not run {argv[0]!r}: {exc.strerror or exc}")
    except subprocess.TimeoutExpired:
        return Output(-1, "", f"{argv[0]} timed out after {COMMAND_TIMEOUT:g}s")
    return Output(done.returncode, done.stdout or "", done.stderr or "")


# -- per-source assembly (pure over a runner) ------------------------------


def repo_from_remote(url: str) -> str | None:
    """`owner/name` from the ssh or https spelling of a GitHub remote."""
    text = (url or "").strip()
    if not text:
        return None
    text = text.removesuffix(".git").rstrip("/")
    match = re.search(r"[:/]([^/:]+)/([^/:]+)$", text)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def identity(project: Project, contract: Contract, runner: Runner) -> dict:
    """Name, repository, version and the base branch's head."""
    doc: dict = {"name": project.name, "target": contract.git.target}
    version_file = project.path / "VERSION"
    if version_file.is_file():
        with contextlib.suppress(OSError):
            doc["version"] = version_file.read_text(encoding="utf-8").strip()
    if project.is_git_repo:
        sha = runner(["git", "rev-parse", "--short", contract.git.base_branch], project.path)
        if sha.ok and sha.stdout.strip():
            doc["main_sha"] = sha.stdout.strip()
        remote = runner(["git", "remote", "get-url", contract.git.remote], project.path)
        repo = repo_from_remote(remote.stdout) if remote.ok else None
        if repo:
            doc["repo"] = repo
            doc["url"] = f"https://github.com/{repo}"
    caps = {
        key: getattr(contract.caps, key)
        for key in ("max_tasks", "max_hours", "task_timeout_minutes")
        if getattr(contract.caps, key) is not None
    }
    if caps:
        doc["caps"] = caps
    return doc


def queue_counts(project: Project, contract: Contract, runner: Runner) -> tuple[dict, list]:
    """Ready and in-progress from the contract's own queue commands, totals and
    the per-epic breakdown from `bd list`. Returns (queue, attention)."""
    queue: dict = {}
    attention: list[dict] = []
    if not contract.queue.enabled:
        return queue, attention

    work = WorkQueue(contract.queue, project.path)
    ready = runner(contract.queue.render("ready"), project.path)
    if ready.ok and _load_json(ready.stdout) is not None:
        queue["ready"] = len(work.ready_from(ready.stdout))
    else:
        attention.append(_drift(f"queue.ready: {ready.first_error_line}"))

    stale_tasks = None
    if contract.queue.stale:
        stale = runner(contract.queue.render("stale"), project.path)
        if stale.ok and _load_json(stale.stdout) is not None:
            stale_tasks = _parse_rows(stale.stdout)
            queue["in_progress"] = len(stale_tasks)
        else:
            attention.append(_drift(f"queue.stale: {stale.first_error_line}"))

    if contract.queue.kind == "beads":
        listing = runner(BD_LIST, project.path)
        rows = _load_json(listing.stdout) if listing.ok else None
        if isinstance(rows, dict):
            rows = rows.get("issues") or rows.get("items")
        if listing.ok and isinstance(rows, list):
            queue.update(_beads_totals(rows))
            if listing.stderr.strip():
                # Noise, not failure: the rows parsed. Said once so it is seen.
                attention.append(_drift(f"bd: {listing.first_error_line}"))
        else:
            attention.append(_drift(f"bd list: {listing.first_error_line}"))

    for task in stale_tasks or []:
        attention.append({
            "kind": "stale_claim",
            "text": f"{task.id} is claimed: {task.title}",
        })
    return queue, attention


def _beads_totals(rows: list) -> dict:
    """Status totals and the per-epic open/closed split."""
    rows = [r for r in rows if isinstance(r, dict)]
    totals: dict = {"open": 0, "blocked": 0, "deferred": 0, "closed": 0}
    for row in rows:
        status = str(row.get("status") or "")
        if status in totals:
            totals[status] += 1
    epics = [r for r in rows if r.get("issue_type") == "epic"]
    breakdown = []
    for epic in epics:
        epic_id = str(epic.get("id") or "")
        children = [
            r for r in rows
            if r is not epic and (
                str(r.get("parent") or "") == epic_id
                or str(r.get("id") or "").startswith(epic_id + ".")
            )
        ]
        breakdown.append({
            "id": epic_id,
            "title": str(epic.get("title") or ""),
            "open": sum(1 for c in children if c.get("status") != "closed"),
            "closed": sum(1 for c in children if c.get("status") == "closed"),
        })
    totals["epics"] = breakdown
    return totals


def run_history(rows: list[dict]) -> tuple[dict, list[dict]]:
    """One project's ledger rows, oldest first, folded to totals and a tail."""
    if not rows:
        return {}, []
    real = [r for r in rows if not r.get("refused")]
    last = rows[-1]
    runs = {
        "total": len(rows),
        "refused": len(rows) - len(real),
        "kept": sum(int(r.get("completed", 0)) for r in real),
        "discarded": sum(int(r.get("failed", 0)) for r in real),
        "escalated": sum(int(r.get("escalated", 0)) for r in real),
        "spend_cents": sum(int(r.get("spend_cents", 0)) for r in real),
        "last_started_at": str(last.get("started_at", "")),
        "last_outcome": "refused" if last.get("refused") else str(last.get("halt_reason", "")),
    }
    recent = [
        {
            "run_id": str(r.get("run_id", "")),
            "started_at": str(r.get("started_at", "")),
            "supervised": bool(r.get("supervised")),
            "refused": bool(r.get("refused")),
            "halt_reason": str(r.get("halt_reason", "")),
            "completed": int(r.get("completed", 0)),
            "failed": int(r.get("failed", 0)),
            "escalated": int(r.get("escalated", 0)),
            "spend_cents": int(r.get("spend_cents", 0)),
        }
        for r in rows[-RECENT_RUNS:]
    ]
    return runs, recent


def task_history(records: list[tasklog.Record]) -> tuple[list[dict], int]:
    """The task log's tail, and how many kept tasks nobody has judged yet."""
    recent = [
        {
            "run_id": str(r.outcome.get("run_id", "")),
            "task_id": str(r.outcome.get("task_id", "")),
            "title": str(r.outcome.get("title", "")),
            "outcome": str(r.outcome.get("outcome", "")),
            "reason": str(r.outcome.get("reason", "")),
            "cost_cents": r.outcome.get("cost_cents"),
            "duration_seconds": float(r.outcome.get("duration_seconds") or 0.0),
            "commit": str(r.outcome.get("commit", "")),
            "annotated": bool(r.root_cause),
        }
        for r in records[-RECENT_TASKS:]
    ]
    unannotated = sum(
        1 for r in records
        if r.outcome.get("outcome") == "completed" and not r.root_cause
    )
    return recent, unannotated


def task_id_in(text: str, project: str) -> str | None:
    """The first token that looks like one of this project's bead ids.

    Beads names ids `<project>-<3 chars>` with `.<n>` for a child, and one
    epic in the first target was created as "Zimmy Life Tracker-9i7" -- the
    project's display name, spaces and capitals included -- so the prefix is
    matched with either separator and without regard to case.
    """
    if not text or not project:
        return None
    prefix = r"[-_ ]".join(re.escape(part) for part in re.split(r"[-_ ]+", project) if part)
    pattern = rf"(?<![\w.]){prefix}-[a-z0-9]{{3}}(?:\.\d+)?(?![\w.])"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(0) if match else None


_FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
_PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def checks_state(rollup) -> str:
    """One word for a GitHub statusCheckRollup: pending, passing, failing or none.

    A failing check anywhere is `failing` whatever else is still running,
    because that is the one a person has to look at; anything not yet
    concluded is `pending`; only a rollup where every check concluded well is
    `passing`. `none` is an empty rollup, which is what a branch with no
    workflows reports, and it is not the same thing as passing.
    """
    if not isinstance(rollup, list) or not rollup:
        return "none"
    pending = False
    for check in rollup:
        if not isinstance(check, dict):
            continue
        verdict = str(check.get("conclusion") or check.get("state") or "").upper()
        status = str(check.get("status") or "").upper()
        if verdict in _FAILED:
            return "failing"
        if verdict in _PASSED:
            continue
        if status and status != "COMPLETED" or verdict in ("PENDING", "EXPECTED", ""):
            pending = True
    return "pending" if pending else "passing"


def pull_requests(project: Project, repo: str | None, runner: Runner) -> tuple[list | None, list]:
    """Open pull requests from `gh`, or None with a drift item when it failed."""
    if not repo:
        return None, [_drift("no GitHub remote, so open pull requests are unknown")]
    argv = [
        "gh", "pr", "list", "--repo", repo, "--state", "open", "--json",
        "number,title,headRefName,url,updatedAt,statusCheckRollup",
        "--limit", str(PR_LIMIT),
    ]
    out = runner(argv, project.path)
    rows = _load_json(out.stdout) if out.ok else None
    if not out.ok or not isinstance(rows, list):
        return None, [_drift(f"gh pr list: {out.first_error_line}")]
    prs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        branch = str(row.get("headRefName") or "")
        prs.append({
            "number": row.get("number"),
            "title": title,
            "branch": branch,
            "state": "open",
            "checks": checks_state(row.get("statusCheckRollup")),
            "url": str(row.get("url") or ""),
            "updated_at": str(row.get("updatedAt") or ""),
            "task_id": task_id_in(title, project.name) or task_id_in(branch, project.name),
        })
    return prs, []


def attention_for(doc: dict) -> list[dict]:
    """The rules that turn a project's numbers into things a person should do."""
    items: list[dict] = []
    runs = doc.get("runs", {})
    if runs.get("unannotated"):
        items.append({
            "kind": "unannotated",
            "text": f"{runs['unannotated']} kept task(s) have no root cause recorded",
        })
    for pr in doc.get("prs") or []:
        label = f"#{pr['number']} {pr['title']}".strip()
        if pr["checks"] == "passing":
            items.append({"kind": "pr_waiting", "text": f"{label} is green and waiting"})
        elif pr["checks"] == "failing":
            items.append({"kind": "verify_failed", "text": f"{label} has a failing check"})
    queue = doc.get("queue", {})
    max_tasks = doc.get("caps", {}).get("max_tasks")
    if "ready" in queue and max_tasks is not None and queue["ready"] < max_tasks:
        items.append({
            "kind": "queue_low",
            "text": f"{queue['ready']} ready task(s), fewer than the {max_tasks} a night may take",
        })
    return items


def _drift(text: str) -> dict:
    return {"kind": "drift", "text": text}


# -- the document ----------------------------------------------------------


def project_snapshot(
    project: Project,
    root: Path,
    runner: Runner = run_command,
    ledger_rows: list[dict] | None = None,
    task_records: list[tasklog.Record] | None = None,
) -> dict:
    """Everything the page shows about one project."""
    attention: list[dict] = []
    try:
        contract = project.load_contract()
    except WatermillError as exc:
        return {"name": project.name, "attention": [_drift(f"contract: {exc}")]}

    doc = identity(project, contract, runner)
    if not project.exists:
        attention.append(_drift(f"checkout missing at {project.path}"))

    if project.exists:
        queue, queue_attention = queue_counts(project, contract, runner)
        attention.extend(queue_attention)
        if queue:
            doc["queue"] = queue

    rows = ledger_rows if ledger_rows is not None else ledger.read(root, project=project.name)
    runs, recent_runs = run_history(rows)
    records = (
        task_records if task_records is not None
        else tasklog.read(root, project=project.name)
    )
    recent_tasks, unannotated = task_history(records)
    if records:
        runs["unannotated"] = unannotated
    if runs:
        doc["runs"] = runs
    if recent_runs:
        doc["recent_runs"] = recent_runs
    if recent_tasks:
        doc["recent_tasks"] = recent_tasks

    prs, pr_attention = pull_requests(project, doc.get("repo"), runner)
    attention.extend(pr_attention)
    if prs is not None:
        doc["prs"] = prs

    stale = [a for a in attention if a["kind"] == "stale_claim"]
    drift = [a for a in attention if a["kind"] != "stale_claim"]
    doc["attention"] = stale + attention_for(doc) + drift
    return doc


def overall(rows: list[dict], records: list[tasklog.Record]) -> dict:
    """The cross-project numbers `watermill status` prints, plus the task counts."""
    stats = ledger.stats(rows)
    out = {
        key: stats[key]
        for key in ("runs", "runs_refused", "keep_rate", "escalation_rate",
                    "cents_per_kept_task", "spend_cents")
        if stats.get(key) is not None
    }
    out["kept_tasks"] = stats["completed"]
    out["discarded_tasks"] = stats["failed"]
    out["unannotated_tasks"] = sum(
        1 for r in records
        if r.outcome.get("outcome") == "completed" and not r.root_cause
    )
    return out


def assemble(
    root: Path,
    project: str | None = None,
    runner: Runner = run_command,
    now: datetime | None = None,
) -> dict:
    """The whole document, for every registered project or one named one."""
    root = Path(root)
    registry = Registry.load(root)
    targets = [registry.get(project)] if project else list(registry.projects)
    rows = ledger.read(root)
    records = tasklog.read(root)
    projects = [
        project_snapshot(
            target, root, runner,
            ledger_rows=[r for r in rows if r.get("project") == target.name],
            task_records=[r for r in records if r.outcome.get("project") == target.name],
        )
        for target in targets
    ]
    moment = now or datetime.now(UTC)
    return {
        "schema": SCHEMA,
        "published_at": moment.isoformat(timespec="seconds"),
        "publisher": PUBLISHER,
        "overall": overall(rows, records),
        "projects": projects,
        "notes": "",
    }


# -- transport -------------------------------------------------------------


def endpoint(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    return base if base.endswith(API_PATH) else base + API_PATH


def push(document: dict, url: str, key: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """PUT the document. Returns what Zimmy answered, parsed if it was JSON.

    The key travels as `X-API-Key`, which is one of the two spellings Zimmy's
    `presented_key` accepts and the one that cannot collide with a session's
    own `Authorization` header. stdlib urllib, for the reason `ship` gives:
    one runtime dependency, and one PUT does not earn a second.
    """
    body = json.dumps(document, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - http(s) URL from operator config
        endpoint(url), data=body, method="PUT",
        headers={"Content-Type": "application/json", "X-API-Key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = response.status
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.read().decode("utf-8", "replace")
        raise PublishError(
            f"Zimmy answered {exc.code}: {_first_line(detail) or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise PublishError(f"could not reach Zimmy: {exc.reason}") from exc
    except TimeoutError as exc:
        raise PublishError(f"Zimmy timed out after {timeout:g}s") from exc
    if not 200 <= status < 300:
        raise PublishError(f"Zimmy answered {status}: {_first_line(text)}")
    parsed = _load_json(text)
    return {"status": status, "body": parsed if isinstance(parsed, dict) else {}}


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:300]
    return ""


def credentials(url: str | None, key_env: str | None) -> tuple[str, str]:
    """Where to send and what to present, or a refusal naming the variable."""
    url = (url or os.environ.get(URL_ENV, "")).strip()
    name = key_env or KEY_ENV
    key = os.environ.get(name, "").strip()
    if not url:
        raise PublishRefusal(
            f"no Zimmy URL. Set {URL_ENV} or pass --to. Nothing was sent."
        )
    if not key:
        raise PublishRefusal(
            f"no API key in ${name}. Mint an admin key in Zimmy's Settings and "
            f"export it as {name}. Nothing was sent."
        )
    return url, key


def publish(
    root: Path,
    url: str | None = None,
    key_env: str | None = None,
    project: str | None = None,
    dry_run: bool = False,
    out: Path | None = None,
    runner: Runner = run_command,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Assemble and, unless this is a dry run, send.

    Credentials are checked *before* assembly on a real push, so a missing key
    refuses in milliseconds rather than after a minute of `gh` and `bd` calls.
    Returns a summary; the CLI decides what to print.
    """
    if not dry_run:
        url, key = credentials(url, key_env)
    document = assemble(root, project=project, runner=runner)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if dry_run:
        if out is not None:
            Path(out).write_text(text, encoding="utf-8")
        return {"dry_run": True, "document": document, "text": text, "out": out}
    answer = push(document, url=url, key=key, timeout=timeout)
    body = answer["body"]
    snapshot_id = body.get("id", body.get("snapshot_id"))
    return {
        "dry_run": False,
        "document": document,
        "status": answer["status"],
        "snapshot_id": snapshot_id,
        "published_at": document["published_at"],
    }
