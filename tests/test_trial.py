"""The trial harness (water-mill-d20): eligibility, randomisation, ledger, briefs, collect, blinding."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from watermill import cli, recorded, trial
from watermill.errors import WatermillError
from watermill.registry import Registry

CONTRACT = """\
version: 1
name: {name}
commands:
  gate: make verify
git:
  base_branch: main
fence:
  paths:
    - Makefile
    - brain/
    - db.py
"""


class FakeTracker:
    """A repo's beads: `tasks`, plus label sets; records the labels it was asked to add."""

    def __init__(self, tasks, labels=None):
        self.tasks = {t["id"]: t for t in tasks}
        self.labels = labels or {}
        self.added: list[tuple[str, str]] = []

    def ready(self):
        return [t for t in self.tasks.values() if t.get("status", "open") == "open"]

    def show(self, bead):
        return self.tasks.get(bead)

    def ids_with_label(self, label):
        return set(self.labels.get(label, ()))

    def add_label(self, bead, label):
        self.added.append((bead, label))
        return True


def task(bead, title="t", description="Goal: change frontend/src/App.jsx", **kw):
    return {"id": bead, "title": title, "description": description, "status": "open",
            "issue_type": "task", **kw}


@pytest.fixture
def world(tmp_path):
    """A factory root with two registered repos."""
    root = tmp_path / "wm"
    root.mkdir()
    entries = []
    for name in ("alpha", "beta"):
        repo = tmp_path / name
        repo.mkdir()
        (repo / "watermill.yaml").write_text(CONTRACT.format(name=name))
        entries.append(f"  - name: {name}\n    path: ../{name}\n")
    (root / "projects.yaml").write_text("version: 1\nprojects:\n" + "".join(entries))
    return root, Registry.load(root), tmp_path


def trackers(**by_repo):
    made = {}

    def make(path):
        return made.setdefault(Path(path).name, by_repo[Path(path).name])
    return make


def enroll(world, repo, ids, tracker, **kw):
    root, registry, _ = world
    return trial.enroll(root, registry, [repo], ids, dry_run=kw.pop("dry_run", False),
                        seed=kw.pop("seed", 7), tracker_for=lambda p: tracker, **kw)


# -- eligibility -------------------------------------------------------------


def test_eligibility_rules(world):
    _, registry, _ = world
    fence = registry.get("alpha").load_contract().fence
    ok = trial.eligibility(task("a-1"), fence, hand_only=set(), fence_directed=set(),
                           enrolled_beads=set())
    assert ok == []
    cases = {
        "epic": task("a-2", issue_type="epic"),
        "not open": task("a-3", status="in_progress"),
        "hand-only": task("a-4"),
        "fenced": task("a-5", description="Files: edit db.py and the tests"),
        "enrolled": task("a-6"),
    }
    why = {k: trial.eligibility(t, fence, hand_only={"a-4"}, fence_directed=set(),
                                enrolled_beads={"a-6"}) for k, t in cases.items()}
    assert all(why.values())
    assert "epic" in why["epic"] and "hand-only" in why["hand-only"][0]
    assert "db.py" in why["fenced"][0] and "never re-randomised" in why["enrolled"][0]


def test_a_fence_path_in_out_of_scope_does_not_exclude_but_a_directing_label_overrides(world):
    _, registry, _ = world
    fence = registry.get("alpha").load_contract().fence
    safe = task("a-1", description="Goal: x\nOut of scope: do not touch Makefile or db.py\n")
    assert trial.eligibility(safe, fence, hand_only=set(), fence_directed=set(),
                             enrolled_beads=set()) == []
    fenced = task("a-2", description="Files: Makefile (the bead directs this)")
    assert trial.eligibility(fenced, fence, hand_only=set(), fence_directed=set(),
                             enrolled_beads=set())
    assert trial.eligibility(fenced, fence, hand_only=set(), fence_directed={"a-2"},
                             enrolled_beads=set()) == []


def test_enroll_refuses_unregistered_repo(world):
    root, registry, _ = world
    with pytest.raises(WatermillError):
        trial.enroll(root, registry, ["nope"], ["x"], dry_run=True, seed=1,
                     tracker_for=lambda p: FakeTracker([]))


def test_explicit_ineligible_bead_refuses_everything(world):
    tr = FakeTracker([task("a-1"), task("a-2", issue_type="epic")])
    with pytest.raises(trial.TrialError):
        enroll(world, "alpha", ["a-1", "a-2"], tr)
    assert not trial.ledger_path(world[0]).exists()


# -- randomisation -----------------------------------------------------------


def test_every_full_block_of_four_is_two_and_two_per_repo(world):
    ids = [f"a-{i:02d}" for i in range(12)]
    got = trial.assign(99, "alpha", 0, ids)
    for start in range(0, 12, 4):
        assert sorted(r["arm"] for r in got[start:start + 4]) == ["A", "A", "B", "B"]
    other = trial.assign(99, "beta", 0, ids)
    assert [r["arm"] for r in got] != [r["arm"] for r in other]  # blocks are per repo


def test_assignment_is_deterministic_and_independent_of_call_order(world):
    a = trial.assign(5, "alpha", 0, ["x3", "x1", "x2", "x4"])
    b = trial.assign(5, "alpha", 0, ["x4", "x2", "x1", "x3"])
    assert a == b and [r["bead"] for r in a] == ["x1", "x2", "x3", "x4"]
    assert trial.block_arms(5, "alpha", 0) == trial.block_arms(5, "alpha", 0)


def test_blocks_stay_balanced_across_separate_enrol_calls(world):
    tr = FakeTracker([task(f"a-{i}") for i in range(8)])
    enroll(world, "alpha", ["a-0", "a-1"], tr)
    enroll(world, "alpha", ["a-2", "a-3", "a-4", "a-5"], tr)
    enroll(world, "alpha", ["a-6", "a-7"], tr)
    arms = [r["arm"] for r in trial.read_ledger(world[0]) if r["type"] == "enroll"]
    assert len(arms) == 8 and arms[:4].count("A") == 2 and arms[4:].count("A") == 2


def test_dry_run_writes_nothing_and_matches_the_real_run(world):
    root = world[0]
    tr = FakeTracker([task(f"a-{i}") for i in range(4)])
    dry = enroll(world, "alpha", None, tr, dry_run=True)
    assert not (root / "knowledge").exists() and tr.added == []
    real = enroll(world, "alpha", None, tr)
    assert [(r["bead"], r["arm"]) for r in dry["rows"]] == [(r["bead"], r["arm"]) for r in real["rows"]]
    assert sorted(tr.added) == sorted((r["bead"], f"trial:{r['arm']}") for r in real["rows"])


def test_cannot_re_randomise(world):
    tr = FakeTracker([task("a-1"), task("a-2")])
    enroll(world, "alpha", ["a-1"], tr)
    again = enroll(world, "alpha", None, tr)  # --ready sweep sees a-1 in the ledger
    assert [r["bead"] for r in again["rows"]] == ["a-2"]
    assert again["refused"] and "never re-randomised" in again["refused"][0][2][0]
    with pytest.raises(trial.TrialError):  # explicit id
        enroll(world, "alpha", ["a-1"], tr)
    with pytest.raises(trial.TrialError, match="re-randomise"):  # different seed
        enroll(world, "alpha", ["a-2"], tr, seed=8)


def test_ledger_is_append_only(world):
    root = world[0]
    tr = FakeTracker([task(f"a-{i}") for i in range(3)])
    enroll(world, "alpha", ["a-0"], tr)
    before = trial.ledger_path(root).read_bytes()
    enroll(world, "alpha", ["a-1", "a-2"], tr)
    assert trial.ledger_path(root).read_bytes().startswith(before)
    kinds = [r["type"] for r in trial.read_ledger(root)]
    assert kinds.count("seed") == 1 and kinds.count("enroll") == 3
    row = trial.enrolled(trial.read_ledger(root))["a-0"]
    assert {"bead", "repo", "arm", "seed", "enrolled_at"} <= set(row)


def test_hand_only_label_excludes(world):
    tr = FakeTracker([task("a-1"), task("a-2")], labels={"hand-only": ["a-2"]})
    got = enroll(world, "alpha", None, tr, dry_run=True)
    assert [r["bead"] for r in got["rows"]] == ["a-1"]
    assert "hand-only" in got["refused"][0][2][0]


# -- start -------------------------------------------------------------------


def test_start_binds_one_session_to_one_bead(world):
    root = world[0]
    enroll(world, "alpha", ["a-1", "a-2"], FakeTracker([task("a-1"), task("a-2")]))
    line = trial.start(root, "a-1", session_id="sess-1", remote=False)
    assert line["surface"] == "laptop" and line["arm"] in "AB"
    with pytest.raises(trial.TrialError, match="one trial bead per session"):
        trial.start(root, "a-2", session_id="sess-1", remote=False)
    with pytest.raises(trial.TrialError, match="already has a session"):
        trial.start(root, "a-1", session_id="sess-2", remote=False)
    with pytest.raises(trial.TrialError, match="not enrolled"):
        trial.start(root, "zz", session_id="s", remote=False)
    with pytest.raises(trial.TrialError, match="SESSION_ID"):
        trial.start(root, "a-2", session_id=None, remote=False)


# -- briefs ------------------------------------------------------------------


def enrolled_pair(world):
    tr = FakeTracker([task(f"alpha-{i}") for i in range(4)])
    enroll(world, "alpha", None, tr)
    rows = trial.enrolled(trial.read_ledger(world[0]))
    a = next(b for b, r in rows.items() if r["arm"] == "A")
    b = next(b for b, r in rows.items() if r["arm"] == "B")
    return a, b


def test_arm_a_laptop_brief_names_the_crew_and_passes_the_tag_down(world):
    a, _ = enrolled_pair(world)
    text = trial.brief(world[0], a, registry=world[1])
    for must in ("millstone", "sluice", "tailrace", "trial start", "recall",
                 "--tag trial:A", "--role orchestrator", "--arm A", "VERBATIM", "EACH crew agent",
                 "Do not edit the crew definition files", f"--task {a}"):
        assert must in text
    assert "--tag trial:B" not in text and "gh api" not in text
    assert str(world[0].resolve()) in text and str(world[2] / "alpha") in text


def test_arm_b_laptop_brief_is_solo_with_the_same_knowledge_steps(world):
    _, b = enrolled_pair(world)
    text = trial.brief(world[0], b, registry=world[1])
    for must in ("single general-purpose Claude", "trial start", "recall", "--tag trial:B",
                 "make verify", "Do NOT use the millstone, sluice or tailrace",
                 "--role solo", "--arm B", "handoff", "do NOT merge", "remember"):
        assert must in text
    assert "--tag trial:A" not in text and "--role orchestrator" not in text


def test_cloud_briefs_follow_the_rest_runbook_and_say_what_cost_is_missing(world):
    a, b = enrolled_pair(world)
    for bead, arm in ((a, "A"), (b, "B")):
        text = trial.brief(world[0], bead, surface="cloud")
        for must in ("gh api", "claude/", "HEAD:refs/heads/$SB", "BD_DOLT_AUTO_PUSH=false",
                     "never `gh pr ...`", "$WM", "SNAPSHOT", "--cost-usd", f"--tag trial:{arm}"):
            assert must in text, (arm, must)
        assert "gh pr create" not in text
    assert "Session close" in trial.brief(world[0], a, surface="cloud")
    assert "floor" in trial.brief(world[0], a, surface="cloud")
    assert "Do NOT merge" in trial.brief(world[0], b, surface="cloud")


def test_brief_refuses_an_unenrolled_bead(world):
    with pytest.raises(trial.TrialError):
        trial.brief(world[0], "nope", registry=world[1])


# -- collect -----------------------------------------------------------------

SID = "11111111-2222-3333-4444-555555555555"


def write_session(base: Path, sid=SID, *, cost=2.5, with_cost=True, age=3600):
    d = base / "-proj"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "user", "timestamp": "2026-10-20T10:00:00.000Z", "cwd": "/x/alpha",
         "message": {"content": "SECRET-PROMPT"}},
        {"type": "assistant", "timestamp": "2026-10-20T10:30:00.000Z", "cwd": "/x/alpha",
         "message": {"id": "m1", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                     "usage": {"input_tokens": 10, "output_tokens": 20}, "content": []}},
        {"type": "cost-state", "totalCostUSD": 0.5, "modelUsage": {
            "m": {"inputTokens": 1, "outputTokens": 1, "cacheReadInputTokens": 1,
                  "cacheCreationInputTokens": 1}}},
    ]
    if with_cost:  # a later cumulative snapshot: the LAST one must win
        lines.append({"type": "cost-state", "totalCostUSD": cost, "modelUsage": {
            "fable": {"inputTokens": 100, "outputTokens": 200, "cacheReadInputTokens": 1000,
                      "cacheCreationInputTokens": 50},
            "haiku": {"inputTokens": 5, "outputTokens": 5, "cacheReadInputTokens": 0,
                      "cacheCreationInputTokens": 0}}})
    else:
        lines.pop(2)
    path = d / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    old = time.time() - age
    import os
    os.utime(path, (old, old))
    return path


class FakeGH:
    def __init__(self, merged_at="2026-10-21T09:00:00Z", runs=None, commits=None):
        self.merged_at = merged_at
        self.runs = runs if runs is not None else {"c1": [{"status": "completed", "conclusion": "success"}]}
        self.commits = commits or [
            {"sha": "c1", "parents": [1], "commit": {"message": "feat\n\nCo-Authored-By: Claude X"}},
            {"sha": "c2", "parents": [1], "commit": {"message": "fix by the owner"}},
            {"sha": "c3", "parents": [1, 2], "commit": {"message": "Merge branch main"}},
        ]

    def pr(self, n):
        return {"merged_at": self.merged_at}

    def check_runs(self, sha):
        return self.runs.get(sha, [])

    def commits_(self):
        return self.commits


def gh_factory(fake):
    fake.commits_ = fake.commits
    cls = type("G", (), {"pr": lambda s, n: fake.pr(n), "commits": lambda s, n: fake.commits,
                         "check_runs": lambda s, sha: fake.check_runs(sha)})
    return lambda path: cls()


def started_world(world, repo="alpha"):
    root = world[0]
    tr = FakeTracker([task(f"{repo}-1")])
    enroll(world, repo, None, tr)
    bead = f"{repo}-1"
    trial.start(root, bead, session_id=SID, remote=False, now="2026-10-20T09:59:00+00:00")
    return bead


def test_collect_reads_the_last_cost_state_ci_owner_commits_and_landing(world):
    root, registry, tmp = world
    bead = started_world(world)
    sessions = tmp / "sessions"
    write_session(sessions)
    got = trial.collect(root, registry, sessions_dir=sessions, prs={bead: 12},
                        gh_for=gh_factory(FakeGH()), stamp="2026-10-22T00:00:00+00:00")
    (row,) = got["collected"]
    assert row["cost_basis"] == "cost-state" and row["cost_usd_est"] == 2.5  # last line wins
    assert row["tokens_total_incl_cache"] == 100 + 200 + 1000 + 50 + 10
    assert row["landed"] is True and row["pr_number"] == 12
    assert row["first_push_ci_green"] is True
    assert row["owner_corrections"] == 1  # the merge commit and the Claude commit do not count
    assert row["duration_seconds"] == 1800.0 and row["session_id"] == SID
    assert "SECRET-PROMPT" not in trial.results_path(root).read_text()
    # Re-running changes nothing; a landing that arrives later is a NEW line, not an edit.
    assert trial.collect(root, registry, sessions_dir=sessions, prs={bead: 12},
                         gh_for=gh_factory(FakeGH()))["collected"] == []
    again = trial.collect(root, registry, sessions_dir=sessions, prs={bead: 12},
                          gh_for=gh_factory(FakeGH(merged_at=None)))
    assert again["collected"][0]["landed"] is False
    assert len(trial.read_results(root)) == 2


def test_collect_waits_for_a_session_that_has_not_ended(world):
    root, registry, tmp = world
    started_world(world)
    sessions = tmp / "sessions"
    write_session(sessions, with_cost=False)
    got = trial.collect(root, registry, sessions_dir=sessions, gh_for=gh_factory(FakeGH()))
    assert got["collected"] == [] and "cost-state" in got["waiting"][0][1]
    write_session(sessions, age=5)  # still being written
    got = trial.collect(root, registry, sessions_dir=sessions, gh_for=gh_factory(FakeGH()))
    assert "still being written" in got["waiting"][0][1]


def test_collect_a_red_first_push(world):
    root, registry, tmp = world
    bead = started_world(world)
    sessions = tmp / "sessions"
    write_session(sessions)
    red = FakeGH(runs={"c1": [{"status": "completed", "conclusion": "failure"}]})
    (row,) = trial.collect(root, registry, sessions_dir=sessions, prs={bead: 3},
                           gh_for=gh_factory(red))["collected"]
    assert row["first_push_ci_green"] is False


def test_cloud_falls_back_to_a_recorded_snapshot_and_marks_it(world):
    root, registry, tmp = world
    bead = started_world(world)
    repo = tmp / "alpha"
    record = {
        "key": f"session:{SID}", "source": "recorded", "agent_kind": "session",
        "project": "alpha", "subject": bead, "started_at": "2026-10-20T10:00:00Z",
        "ended_at": "2026-10-20T11:00:00Z", "fields_inferred": [],
        "detail": {"role": "orchestrator", "transcript_located": True, "session_id": SID,
                   "pr_number": 9, "model": "claude-fable-5-1", "models": ["claude-fable-5-1"],
                   "input_tokens": 1000, "output_tokens": 500, "cache_read_tokens": 0,
                   "cache_creation_tokens": 0}}
    recorded.write(repo / recorded.RECORDED_DIR, record)
    empty = tmp / "no-transcripts-in-the-cloud"
    empty.mkdir()
    (row,) = trial.collect(root, registry, sessions_dir=empty,
                           gh_for=gh_factory(FakeGH()))["collected"]
    assert row["cost_basis"] == "recorded-snapshot" and row["pr_number"] == 9
    assert row["duration_seconds"] == 3600.0
    # the owner can supply the real figure
    (fixed,) = trial.collect(root, registry, sessions_dir=empty, manual_cost={bead: 4.2},
                             gh_for=gh_factory(FakeGH()))["collected"]
    assert fixed["cost_basis"] == "manual" and fixed["cost_usd_est"] == 4.2


# -- scoring: blind ----------------------------------------------------------


def landed_rows(root, specs, landed="2026-09-01T00:00:00Z"):
    rows = [{"type": "collect", "bead": b, "repo": "alpha", "arm": arm, "landed": True,
             "landed_at": landed, "pr_number": 5, "cost_usd_est": cost, "cost_basis": "cost-state",
             "duration_seconds": dur, "first_push_ci_green": ci, "owner_corrections": 0}
            for b, arm, cost, dur, ci in specs]
    trial._append(trial.results_path(root), rows)


def test_scorepack_never_shows_the_arm_the_ledger_or_trial_tags(world):
    root, registry, _ = world
    tr = FakeTracker([task(f"alpha-{i}", title=f"title {i}") for i in range(4)])
    enroll(world, "alpha", None, tr)
    enr = trial.enrolled(trial.read_ledger(root))
    landed_rows(root, [(b, r["arm"], 1, 1, True) for b, r in enr.items()])
    text = trial.scorepack(root, tracker_for=lambda p: tr, registry=registry,
                           today=datetime(2026, 10, 20, tzinfo=UTC))
    assert all(b in text for b in enr) and "blocker" in text
    lowered = text.lower()
    for forbidden in ("trial", "ledger", "knowledge/", "results.jsonl", "arm a", "arm b",
                      "orchestrator", "millstone", "sluice", "tailrace"):
        assert forbidden not in lowered, forbidden
    import re
    assert not re.search(r"\barm\b|\bcrew\b|\bsolo\b|\bcondition\b", lowered)
    # order is a hash order, not the enrolment or arm order
    order = [line[4:] for line in text.splitlines() if line.startswith("### ")]
    assert sorted(order) == sorted(enr) and order != list(enr)


def test_scoring_waits_for_the_window_and_only_counts_a_closed_one(world):
    root, _, _ = world
    landed_rows(root, [("alpha-1", "A", 1, 1, True)], landed="2026-10-10T00:00:00Z")
    soon = datetime(2026, 10, 15, tzinfo=UTC)
    assert trial.due_for_scoring(root, today=soon) == []
    with pytest.raises(trial.TrialError, match="14-day"):
        trial.score(root, "alpha-1", [], today=soon)
    trial.score(root, "alpha-1", [], early=True, today=soon)
    with pytest.raises(trial.TrialError, match="severity"):
        trial.score(root, "alpha-1", [{"severity": "huge"}], today=datetime(2026, 12, 1, tzinfo=UTC))
    later = datetime(2026, 12, 1, tzinfo=UTC)
    assert [r["bead"] for r in trial.due_for_scoring(root, today=later)] == ["alpha-1"]  # early score
    trial.score(root, "alpha-1", [{"severity": "bug", "ref": "x"}], today=later)
    assert trial.due_for_scoring(root, today=later) == []


# -- status ------------------------------------------------------------------


def seed_trial(root, n_per_arm, *, escapes_a=0, escapes_b=0):
    """Enrol/collect/score `n_per_arm` landed beads per arm directly in the files."""
    ledger, specs, scores = [{"type": "seed", "seed": 1}], [], []
    for arm, esc in (("A", escapes_a), ("B", escapes_b)):
        for i in range(n_per_arm):
            bead = f"alpha-{arm}{i}"
            ledger.append({"type": "enroll", "bead": bead, "repo": "alpha", "arm": arm, "seed": 1,
                           "block": 0, "pos": 0, "enrolled_at": "x"})
            specs.append((bead, arm, 1.0 + i + (3 if arm == "B" else 0), 100 + i, i % 2 == 0))
            scores.append({"type": "score", "bead": bead, "early": False, "scored_at": "x",
                           "escapes": [{"severity": "bug"}] if i < esc else
                           [{"severity": "quality"}]})
    trial._append(trial.ledger_path(root), ledger)
    landed_rows(root, specs)
    trial._append(trial.results_path(root), scores)


def test_status_says_too_few_to_say_and_withholds_p_before_the_interim(tmp_path):
    seed_trial(tmp_path, 3, escapes_a=1, escapes_b=2)
    s = trial.status(tmp_path)
    assert s["stage"] == "pre-interim" and s["per_arm"]["A"]["scored"] == 3
    p = s["metrics"]["primary"]
    assert p["p_value"] is None and "too few to say" in p["note"]
    assert p["k"] == {"A": 1, "B": 2} and p["n"] == {"A": 3, "B": 3}  # quality is not primary
    assert "too few to say" in trial.render_status(s)


def test_status_withholds_the_p_value_between_8_and_30_then_shows_it_at_the_interim(tmp_path):
    seed_trial(tmp_path, 12, escapes_a=1, escapes_b=6)
    p = trial.status(tmp_path)["metrics"]["primary"]
    assert p["p_value"] is None and "withheld" in p["note"]


def test_status_interim_at_30_per_arm_prints_fisher_and_mann_whitney(tmp_path):
    seed_trial(tmp_path, 30, escapes_a=3, escapes_b=12)
    s = trial.status(tmp_path)
    assert s["stage"] == "interim"
    assert s["metrics"]["primary"]["p_value"] is not None
    assert s["metrics"]["primary"]["p_value"] < 0.05
    cost = s["metrics"]["secondary"][0]
    assert cost["p_value"] is not None and cost["median"]["B"] > cost["median"]["A"]
    seed_trial_final = tmp_path / "f"
    seed_trial_final.mkdir()
    seed_trial(seed_trial_final, 60)
    assert trial.status(seed_trial_final)["stage"] == "final"


def test_status_excludes_cloud_snapshots_from_the_cost_comparison(tmp_path):
    seed_trial(tmp_path, 9)
    rows = trial.read_results(tmp_path)
    for r in rows:
        if r["type"] == "collect" and r["arm"] == "A":
            trial._append(trial.results_path(tmp_path), [{**r, "cost_basis": "recorded-snapshot"}])
    s = trial.status(tmp_path)
    assert s["metrics"]["secondary"][0]["n"] == {"A": 0, "B": 9}
    assert s["cost_snapshots_excluded"] == 9


# -- cli ---------------------------------------------------------------------


def test_cli_dry_run_and_refusals_have_the_right_exit_codes(world, capsys, monkeypatch):
    root = world[0]
    monkeypatch.setattr(trial, "Tracker", lambda path: FakeTracker([task(f"{Path(path).name}-1")]))
    monkeypatch.setattr(trial, "enroll", trial.enroll)
    rc = cli.main(["--root", str(root), "trial", "enroll", "alpha", "--ready", "--dry-run",
                   "--seed", "3"])
    out = capsys.readouterr().out
    assert rc == 0 and "alpha-1" in out and "dry run" in out
    assert not (root / "knowledge").exists()
    assert cli.main(["--root", str(root), "trial", "enroll", "alpha"]) == 3  # no ids, no --ready
    assert cli.main(["--root", str(root), "trial", "brief", "alpha-1"]) == 3  # not enrolled
    assert cli.main(["--root", str(root), "trial", "status"]) == 0


def test_recorded_accepts_the_orchestrator_role_as_a_session():
    assert "orchestrator" in recorded.ROLES
    rec = recorded.build(None, role="orchestrator", project="p", bead="p-1", arm="A")
    assert rec["agent_kind"] == "session" and "crew_key" not in rec["detail"]
    crew = recorded.build(None, role="sluice", project="p", bead="p-1")
    assert crew["agent_kind"] == "mill-crew" and crew["detail"]["crew_key"] == "crew:p-1"
