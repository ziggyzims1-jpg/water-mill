"""Publishing a status snapshot to Zimmy.

The assembler is exercised against a fake ledger, a fake task log and a faked
command runner -- no real `bd`, `gh` or `git` -- because what is under test is
the document, not those tools. The transport is exercised against a real local
HTTP server rather than a stubbed `urlopen`, because the request that reaches a
socket (method, path, header, body) is the thing Zimmy will actually see.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from watermill import cli, ledger, publish, tasklog
from watermill.registry import Project

PROJECT = "demo"


# -- fixtures ---------------------------------------------------------------


def _run(root: Path, run_id="r-1", **over):
    summary = {
        "run_id": run_id, "project": PROJECT,
        "started_at": "2026-08-26T03:00:00+00:00",
        "ended_at": "2026-08-26T04:00:00+00:00",
        "refused": False, "supervised": False, "halt_reason": "queue exhausted",
        "counts": {"attempted": 2, "completed": 1, "failed": 1, "escalated": 0},
        "spend_cents": 120, "under_counted": False,
        "tasks": [
            {"id": "demo-aaa", "title": "one", "outcome": "completed", "cost_cents": 70},
            {"id": "demo-bbb", "title": "two", "outcome": "failed", "reason": "gate failed"},
        ],
    }
    summary.update(over)
    ledger.append(root, ledger.Entry.from_summary(summary, root / "logs"))
    tasklog.append_run(root, summary, root / "logs")


class FakeRunner:
    """Answers each argv from a table keyed on its first words; records calls."""

    def __init__(self, answers: dict | None = None):
        self.answers = dict(answers or {})
        self.calls: list[list[str]] = []

    def __call__(self, argv, cwd):
        self.calls.append(list(argv))
        for key, value in self.answers.items():
            if tuple(argv[: len(key)]) == key:
                return value if isinstance(value, publish.Output) else publish.Output(0, value)
        return publish.Output(127, "", f"could not run {argv[0]!r}: not faked")


def _issues(*rows):
    return json.dumps(list(rows))


GOOD_ANSWERS = {
    ("git", "rev-parse"): "abc1234\n",
    ("git", "remote", "get-url"): "git@github.com:owner/demo.git\n",
    ("bd", "ready"): _issues({"id": "demo-aaa", "title": "one", "issue_type": "task"}),
    ("bd", "list", "--status", "in_progress"): _issues(),
    tuple(publish.BD_LIST): _issues(
        {"id": "demo-epc", "title": "An epic", "issue_type": "epic", "status": "open"},
        {"id": "demo-epc.1", "title": "child", "issue_type": "task", "status": "closed",
         "parent": "demo-epc"},
        {"id": "demo-aaa", "title": "one", "issue_type": "task", "status": "open",
         "parent": "demo-epc"},
        {"id": "demo-ccc", "title": "blocked", "issue_type": "task", "status": "blocked"},
    ),
    ("gh", "pr", "list"): json.dumps([]),
}


@pytest.fixture
def factory(tmp_path):
    """A registry with one git project whose contract has a beads queue."""
    root = tmp_path / "factory"
    root.mkdir()
    target = tmp_path / "demo"
    (target / ".git").mkdir(parents=True)
    (target / "VERSION").write_text("1.2.3\n")
    (root / "projects").mkdir()
    (root / "projects" / "demo.yaml").write_text(
        "version: 1\nname: demo\ncommands:\n  gate: true\n"
        "git:\n  base_branch: main\n  target: branch\n"
        "queue:\n  kind: beads\n  ready: bd ready --json\n"
        "  stale: bd list --status in_progress --json\n"
        "  show: bd show {id}\n  claim: bd update {id} --claim\n"
        "  release: bd update {id} --status open\n  close: bd close {id}\n"
        "caps:\n  max_tasks: 5\n  max_hours: 3\n  task_timeout_minutes: 30\n"
    )
    (root / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: demo\n    path: ../demo\n"
        "    contract: projects/demo.yaml\n"
    )
    return root


def _project(root) -> Project:
    from watermill.registry import Registry
    return Registry.load(root).get(PROJECT)


# -- the document -----------------------------------------------------------


def test_the_document_has_the_schema_and_every_source(factory):
    _run(factory)
    runner = FakeRunner(GOOD_ANSWERS)
    doc = publish.assemble(factory, runner=runner)

    assert doc["schema"] == 1
    assert doc["publisher"] == "watermill publish"
    assert doc["published_at"].endswith("+00:00")
    [project] = doc["projects"]
    assert project["name"] == "demo"
    assert project["repo"] == "owner/demo"
    assert project["url"] == "https://github.com/owner/demo"
    assert project["version"] == "1.2.3"
    assert project["main_sha"] == "abc1234"
    assert project["target"] == "branch"
    assert project["caps"] == {"max_tasks": 5, "max_hours": 3.0, "task_timeout_minutes": 30.0}
    assert project["queue"] == {
        "ready": 1, "in_progress": 0, "open": 2, "blocked": 1, "deferred": 0, "closed": 1,
        "epics": [{"id": "demo-epc", "title": "An epic", "open": 1, "closed": 1}],
    }
    assert project["runs"] == {
        "total": 1, "refused": 0, "kept": 1, "discarded": 1, "escalated": 0,
        "spend_cents": 120, "last_started_at": "2026-08-26T03:00:00+00:00",
        "last_outcome": "queue exhausted", "unannotated": 1,
    }
    assert [r["run_id"] for r in project["recent_runs"]] == ["r-1"]
    assert [(t["task_id"], t["annotated"]) for t in project["recent_tasks"]] == [
        ("demo-aaa", False), ("demo-bbb", False),
    ]
    assert project["prs"] == []
    assert doc["overall"]["kept_tasks"] == 1
    assert doc["overall"]["discarded_tasks"] == 1
    assert doc["overall"]["unannotated_tasks"] == 1
    assert doc["overall"]["keep_rate"] == 0.5


def test_nothing_the_publisher_runs_can_write(factory):
    """Every command is a query. `bd list` carries the flags that make it one."""
    runner = FakeRunner(GOOD_ANSWERS)
    publish.assemble(factory, runner=runner)
    heads = {tuple(c[:2]) for c in runner.calls}
    assert heads <= {("git", "rev-parse"), ("git", "remote"), ("bd", "ready"),
                     ("bd", "list"), ("gh", "pr")}
    listing = next(c for c in runner.calls if c[:2] == ["bd", "list"] and "--all" in c)
    assert "--readonly" in listing
    assert not any(c[0] == "git" and c[1] in ("fetch", "pull", "checkout") for c in runner.calls)


def test_an_epic_counts_children_by_id_prefix_without_a_parent_field(factory):
    answers = dict(GOOD_ANSWERS)
    answers[tuple(publish.BD_LIST)] = _issues(
        {"id": "demo-epc", "title": "E", "issue_type": "epic", "status": "open"},
        {"id": "demo-epc.1", "title": "c", "issue_type": "task", "status": "open"},
        {"id": "demo-epc.2", "title": "c", "issue_type": "task", "status": "closed"},
    )
    [project] = publish.assemble(factory, runner=FakeRunner(answers))["projects"]
    assert project["queue"]["epics"] == [{"id": "demo-epc", "title": "E", "open": 1, "closed": 1}]


def test_a_refused_run_is_counted_and_named(factory):
    _run(factory, run_id="r-0", refused=True, halt_reason="preflight refused: dirty tree",
         counts={}, spend_cents=0, tasks=[])
    [project] = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))["projects"]
    assert project["runs"]["refused"] == 1
    assert project["runs"]["last_outcome"] == "refused"
    assert project["recent_runs"][-1]["refused"] is True


def test_recent_lists_are_capped(factory):
    for n in range(14):
        _run(factory, run_id=f"r-{n:02d}")
    [project] = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))["projects"]
    assert len(project["recent_runs"]) == publish.RECENT_RUNS
    assert project["recent_runs"][-1]["run_id"] == "r-13"
    assert len(project["recent_tasks"]) == publish.RECENT_TASKS
    assert project["runs"]["total"] == 14


def test_an_annotated_task_no_longer_counts_as_unannotated(factory):
    _run(factory)
    tasklog.annotate(factory, PROJECT, "demo-aaa", "none")
    [project] = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))["projects"]
    assert project["runs"]["unannotated"] == 0
    assert project["recent_tasks"][0]["annotated"] is True
    assert not [a for a in project["attention"] if a["kind"] == "unannotated"]


def test_a_project_that_never_ran_has_no_runs_key(factory):
    [project] = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))["projects"]
    assert "runs" not in project
    assert "recent_runs" not in project
    assert "recent_tasks" not in project


def test_only_the_named_project_is_assembled(factory):
    (factory / "projects.yaml").write_text(
        "version: 1\nprojects:\n"
        "  - name: demo\n    path: ../demo\n    contract: projects/demo.yaml\n"
        "  - name: other\n    path: ../other\n"
    )
    doc = publish.assemble(factory, project="demo", runner=FakeRunner(GOOD_ANSWERS))
    assert [p["name"] for p in doc["projects"]] == ["demo"]


# -- unknown is omitted, never zeroed --------------------------------------


def test_a_broken_bd_omits_the_totals_and_says_so(factory):
    answers = dict(GOOD_ANSWERS)
    answers[tuple(publish.BD_LIST)] = publish.Output(
        1, "", "Error: no beads database found\nrun bd init\n"
    )
    [project] = publish.assemble(factory, runner=FakeRunner(answers))["projects"]
    for key in ("open", "closed", "blocked", "deferred", "epics"):
        assert key not in project["queue"]
    assert project["queue"]["ready"] == 1  # the contract's own command still worked
    drift = [a for a in project["attention"] if a["kind"] == "drift"]
    assert drift == [{"kind": "drift", "text": "bd list: Error: no beads database found"}]


def test_a_missing_tool_is_unknown_not_zero(factory):
    """`bd` not installed and an empty queue both look like 'no rows' from
    the outside; the page must be able to tell them apart."""
    runner = FakeRunner({k: v for k, v in GOOD_ANSWERS.items() if k[0] != "bd"})
    [project] = publish.assemble(factory, runner=runner)["projects"]
    assert "queue" not in project
    kinds = [a["kind"] for a in project["attention"]]
    assert kinds.count("drift") == 3  # ready, stale, list
    assert all("could not run 'bd'" in a["text"] for a in project["attention"])


def test_bd_export_warning_on_stderr_is_drift_not_failure(factory):
    answers = dict(GOOD_ANSWERS)
    answers[tuple(publish.BD_LIST)] = publish.Output(
        0, GOOD_ANSWERS[tuple(publish.BD_LIST)],
        "Warning: auto-export skipped 2 orphaned issues in issues.jsonl\n",
    )
    [project] = publish.assemble(factory, runner=FakeRunner(answers))["projects"]
    assert project["queue"]["open"] == 2
    drift = [a for a in project["attention"] if a["kind"] == "drift"]
    assert len(drift) == 1
    assert drift[0]["text"].startswith("bd: Warning: auto-export")


def test_a_failing_gh_omits_prs_and_says_so(factory):
    answers = dict(GOOD_ANSWERS)
    answers[("gh", "pr", "list")] = publish.Output(4, "", "gh: To get started with GitHub CLI, please run: gh auth login\n")
    [project] = publish.assemble(factory, runner=FakeRunner(answers))["projects"]
    assert "prs" not in project
    assert {"kind": "drift", "text": "gh pr list: gh: To get started with GitHub CLI, please run: gh auth login"} in project["attention"]


def test_no_version_file_means_no_version_key(factory, tmp_path):
    (tmp_path / "demo" / "VERSION").unlink()
    [project] = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))["projects"]
    assert "version" not in project


def test_a_project_with_a_broken_contract_is_still_listed(factory):
    (factory / "projects" / "demo.yaml").write_text("version: 1\nname: demo\nbogus: 1\n")
    [project] = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))["projects"]
    assert project["name"] == "demo"
    assert project["attention"][0]["kind"] == "drift"
    assert "contract" in project["attention"][0]["text"]


def test_overall_omits_rates_that_cannot_be_computed(factory):
    doc = publish.assemble(factory, runner=FakeRunner(GOOD_ANSWERS))
    assert "keep_rate" not in doc["overall"]
    assert "cents_per_kept_task" not in doc["overall"]
    assert doc["overall"]["runs"] == 0


# -- attention rules --------------------------------------------------------


def test_every_attention_rule_fires_from_its_cause(factory):
    _run(factory)  # one kept task, unannotated
    answers = dict(GOOD_ANSWERS)
    answers[("bd", "list", "--status", "in_progress")] = _issues(
        {"id": "demo-zzz", "title": "stuck", "issue_type": "task"}
    )
    answers[("gh", "pr", "list")] = json.dumps([
        {"number": 7, "title": "feat: green (demo-aaa)", "headRefName": "watermill/x",
         "url": "u7", "updatedAt": "t", "statusCheckRollup": [{"conclusion": "SUCCESS", "status": "COMPLETED"}]},
        {"number": 8, "title": "feat: red", "headRefName": "watermill/demo-bbb",
         "url": "u8", "updatedAt": "t", "statusCheckRollup": [{"conclusion": "FAILURE", "status": "COMPLETED"}]},
        {"number": 9, "title": "feat: running", "headRefName": "x",
         "url": "u9", "updatedAt": "t", "statusCheckRollup": [{"status": "IN_PROGRESS"}]},
    ])
    [project] = publish.assemble(factory, runner=FakeRunner(answers))["projects"]
    by_kind = {}
    for item in project["attention"]:
        by_kind.setdefault(item["kind"], []).append(item["text"])
    assert by_kind["stale_claim"] == ["demo-zzz is claimed: stuck"]
    assert by_kind["unannotated"] == ["1 kept task(s) have no root cause recorded"]
    assert by_kind["pr_waiting"] == ["#7 feat: green (demo-aaa) is green and waiting"]
    assert by_kind["verify_failed"] == ["#8 feat: red has a failing check"]
    assert by_kind["queue_low"] == ["1 ready task(s), fewer than the 5 a night may take"]
    assert "drift" not in by_kind
    # The pending one raised nothing: there is nothing for a person to do yet.
    assert [p["task_id"] for p in project["prs"]] == ["demo-aaa", "demo-bbb", None]


def test_queue_low_needs_a_known_ready_count(factory):
    runner = FakeRunner({k: v for k, v in GOOD_ANSWERS.items() if k != ("bd", "ready")})
    [project] = publish.assemble(factory, runner=runner)["projects"]
    assert not [a for a in project["attention"] if a["kind"] == "queue_low"]


def test_queue_low_is_quiet_when_the_queue_is_deep(factory):
    answers = dict(GOOD_ANSWERS)
    answers[("bd", "ready")] = _issues(*[{"id": f"demo-{n:03d}", "title": "t"} for n in range(6)])
    [project] = publish.assemble(factory, runner=FakeRunner(answers))["projects"]
    assert project["queue"]["ready"] == 6
    assert not [a for a in project["attention"] if a["kind"] == "queue_low"]


# -- the small pure pieces ---------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("feat: do it (zimmy-life-tracker-bzq)", "zimmy-life-tracker-bzq"),
    ("watermill/zimmy-life-tracker-jam.1", "zimmy-life-tracker-jam.1"),
    ("Zimmy Life Tracker-9i7.2: store snapshots", "Zimmy Life Tracker-9i7.2"),
    ("zimmy life tracker-9i7", "zimmy life tracker-9i7"),
    ("fix: unrelated", None),
    ("zimmy-life-tracker-toolong", None),
    ("", None),
])
def test_task_id_extraction(text, expected):
    assert publish.task_id_in(text, "zimmy-life-tracker") == expected


def test_task_id_extraction_does_not_match_another_project():
    assert publish.task_id_in("other-project-abc", "zimmy-life-tracker") is None


@pytest.mark.parametrize("rollup, expected", [
    (None, "none"),
    ([], "none"),
    ([{"conclusion": "SUCCESS", "status": "COMPLETED"}], "passing"),
    ([{"conclusion": "SUCCESS", "status": "COMPLETED"}, {"conclusion": "SKIPPED", "status": "COMPLETED"}], "passing"),
    ([{"state": "SUCCESS"}], "passing"),
    ([{"conclusion": "FAILURE", "status": "COMPLETED"}], "failing"),
    ([{"conclusion": "SUCCESS", "status": "COMPLETED"}, {"conclusion": "CANCELLED", "status": "COMPLETED"}], "failing"),
    ([{"state": "ERROR"}], "failing"),
    ([{"status": "IN_PROGRESS"}], "pending"),
    ([{"status": "QUEUED", "conclusion": None}], "pending"),
    ([{"state": "PENDING"}], "pending"),
    ([{"conclusion": "SUCCESS", "status": "COMPLETED"}, {"status": "IN_PROGRESS"}], "pending"),
    ([{"conclusion": "FAILURE", "status": "COMPLETED"}, {"status": "IN_PROGRESS"}], "failing"),
])
def test_checks_mapping(rollup, expected):
    assert publish.checks_state(rollup) == expected


@pytest.mark.parametrize("remote, expected", [
    ("git@github.com:owner/name.git", "owner/name"),
    ("https://github.com/owner/name", "owner/name"),
    ("https://github.com/owner/name.git\n", "owner/name"),
    ("ssh://git@github.com/owner/name.git", "owner/name"),
    ("", None),
    ("nonsense", None),
])
def test_repo_from_remote(remote, expected):
    assert publish.repo_from_remote(remote) == expected


def test_endpoint_is_appended_once():
    assert publish.endpoint("https://zimmy.local") == "https://zimmy.local/api/watermill"
    assert publish.endpoint("https://zimmy.local/") == "https://zimmy.local/api/watermill"
    assert publish.endpoint("https://zimmy.local/api/watermill") == "https://zimmy.local/api/watermill"


# -- the command ------------------------------------------------------------


@pytest.fixture
def quiet_runner(monkeypatch):
    """The CLI runs the real runner by default; point it at the fake."""
    runner = FakeRunner(GOOD_ANSWERS)
    monkeypatch.setattr(publish, "run_command", runner)
    # `publish()` bound the default at definition time, so patch the call too.
    original = publish.publish

    def patched(root, **kw):
        kw.setdefault("runner", runner)
        return original(root, **kw)

    monkeypatch.setattr(cli.publish, "publish", patched)
    return runner


def test_dry_run_prints_valid_json_and_sends_nothing(factory, quiet_runner, capsys, monkeypatch):
    monkeypatch.delenv(publish.URL_ENV, raising=False)
    monkeypatch.delenv(publish.KEY_ENV, raising=False)
    code = cli.main(["--root", str(factory), "publish", "--dry-run"])
    assert code == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == 1
    assert doc["projects"][0]["name"] == "demo"
    assert not any(c[0] == "curl" for c in quiet_runner.calls)


def test_dry_run_can_write_to_a_file(factory, quiet_runner, tmp_path):
    out = tmp_path / "snapshot.json"
    assert cli.main(["--root", str(factory), "publish", "--dry-run", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["schema"] == 1


def test_no_url_is_a_refusal_naming_the_variable(factory, quiet_runner, monkeypatch, capsys):
    monkeypatch.delenv(publish.URL_ENV, raising=False)
    monkeypatch.setenv(publish.KEY_ENV, "zk_secret")
    assert cli.main(["--root", str(factory), "publish"]) == 3
    err = capsys.readouterr().err
    assert "ZIMMY_URL" in err
    assert "zk_secret" not in err
    assert quiet_runner.calls == []  # refused before anything was assembled


def test_no_key_is_a_refusal_naming_the_variable(factory, quiet_runner, monkeypatch, capsys):
    monkeypatch.setenv(publish.URL_ENV, "http://127.0.0.1:1")
    monkeypatch.delenv("OTHER_KEY", raising=False)
    assert cli.main(["--root", str(factory), "publish", "--key-env", "OTHER_KEY"]) == 3
    assert "OTHER_KEY" in capsys.readouterr().err
    assert quiet_runner.calls == []


# -- the push, against a real socket ---------------------------------------


class _Zimmy(BaseHTTPRequestHandler):
    """Records what arrived and answers with whatever the test configured."""

    status = 201
    body = b'{"id": 42}'
    received: list[dict] = []

    def do_PUT(self):  # noqa: N802 - http.server's naming
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        type(self).received.append({
            "method": "PUT", "path": self.path,
            # Looked up here rather than copied, because HTTP header names are
            # case-insensitive and urllib sends this one as `X-api-key`. Flask
            # reads it the same way Zimmy's presented_key does.
            "headers": {
                "Content-Type": self.headers.get("Content-Type"),
                "X-API-Key": self.headers.get("X-API-Key"),
                "Authorization": self.headers.get("Authorization"),
            },
            "body": raw,
        })
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def zimmy():
    """A local server; yields its base URL and the handler class."""
    _Zimmy.received = []
    _Zimmy.status = 201
    _Zimmy.body = b'{"id": 42}'
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Zimmy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", _Zimmy
    finally:
        server.shutdown()
        server.server_close()


def test_push_is_a_put_with_the_key_as_zimmy_expects(factory, quiet_runner, zimmy, monkeypatch, capsys):
    url, handler = zimmy
    monkeypatch.setenv(publish.URL_ENV, url)
    monkeypatch.setenv(publish.KEY_ENV, "zk_test_secret")
    code = cli.main(["--root", str(factory), "publish"])
    assert code == 0
    [request] = handler.received
    assert request["method"] == "PUT"
    assert request["path"] == "/api/watermill"
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["headers"]["X-API-Key"] == "zk_test_secret"
    doc = json.loads(request["body"])
    assert doc["schema"] == 1
    assert doc["projects"][0]["name"] == "demo"
    out = capsys.readouterr().out
    assert "snapshot 42" in out
    assert doc["published_at"] in out
    assert "zk_test_secret" not in out


def test_a_500_is_a_failure_with_the_first_line_of_the_body(factory, quiet_runner, zimmy, monkeypatch, capsys):
    url, handler = zimmy
    handler.status = 500
    handler.body = b"snapshot store is read-only\nsecond line\n"
    monkeypatch.setenv(publish.URL_ENV, url)
    monkeypatch.setenv(publish.KEY_ENV, "zk_test_secret")
    assert cli.main(["--root", str(factory), "publish"]) == 1
    err = capsys.readouterr().err
    assert "500" in err
    assert "snapshot store is read-only" in err
    assert "second line" not in err
    assert "zk_test_secret" not in err


def test_an_unreachable_host_is_a_failure(factory, quiet_runner, monkeypatch, capsys):
    monkeypatch.setenv(publish.URL_ENV, "http://127.0.0.1:9")  # discard port; nothing listens
    monkeypatch.setenv(publish.KEY_ENV, "zk_test_secret")
    assert cli.main(["--root", str(factory), "publish"]) == 1
    assert "could not reach Zimmy" in capsys.readouterr().err
