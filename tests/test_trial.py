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
                 "--role solo", "--arm B", "handoff", "remember",
                 # owner 2026-10-13: arm B lands its own PR, sha-guarded, then closes the bead
                 "gh pr merge", "--match-head-commit", f"bd close {b}", "BLOCKED"):
        assert must in text, must
    assert "--tag trial:A" not in text and "--role orchestrator" not in text
    assert "do NOT merge" not in text


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
    cloud_b = trial.brief(world[0], b, surface="cloud")
    assert "Session close" in cloud_b and "pulls/<n>/merge" in cloud_b and 'sha="$SHA"' in cloud_b
    assert "Do NOT merge" not in cloud_b and "beads-sync" in cloud_b


@pytest.mark.parametrize("surface", ["laptop", "cloud"])
def test_both_arms_land_by_the_same_words_and_the_same_squash_message(world, surface):
    a, b = enrolled_pair(world)
    text_a = trial.brief(world[0], a, surface=surface, registry=world[1])
    text_b = trial.brief(world[0], b, surface=surface, registry=world[1])
    assert trial._landing(a, surface) in text_a and trial._landing(b, surface) in text_b
    # the landing rule differs only by the bead id
    assert trial._landing(a, surface).replace(a, "X") == trial._landing(b, surface).replace(b, "X")
    # arm A's verbatim crew line carries the tag AND the squash message to every crew agent
    crew = text_a.split('after the bead id: "', 1)[1].split('" Do not edit', 1)[0]
    assert "--tag trial:A" in crew and trial.merge_message(a) in crew
    assert "trial:B" not in crew
    for bead, text in ((a, text_a), (b, text_b)):  # GitHub's default body would name the arm
        if surface == "laptop":
            assert f'--subject "<PR title> (#<n>)" --body "Bead {bead}."' in text
        else:
            assert f'-f commit_title="<PR title> (#<n>)" -f commit_message="Bead {bead}."' in text
    if surface == "laptop":
        assert f"bead/{trial._slug(a, 'alpha')}" in text_a
        assert f"bead/{trial._slug(b, 'alpha')}" in text_b


def test_arm_b_end_point_is_one_switch(world, monkeypatch):
    _, b = enrolled_pair(world)
    monkeypatch.setattr(trial, "ARM_B_SELF_MERGES", False)
    for surface in ("laptop", "cloud"):
        text = trial.brief(world[0], b, surface=surface, registry=world[1])
        assert "do NOT merge" in text or "Do NOT merge" in text
        assert "--match-head-commit" not in text and "pulls/<n>/merge" not in text


def test_arm_b_laptop_close_imports_between_pull_and_export(world):
    _, b = enrolled_pair(world)
    text = trial.brief(world[0], b, surface="laptop", registry=world[1])
    pull, imp, exp = (text.index(x) for x in ("--ff-only", "bd import .beads/issues.jsonl",
                                               "bd export -o .beads/issues.jsonl"))
    check = text.index("<(sort .beads/issues.jsonl)")
    assert pull < imp < exp < check < text.index("chore(beads): close")


def test_tailrace_close_imports_between_pull_and_export():
    line = next(ln for ln in (Path(__file__).parent.parent / ".claude/agents/tailrace.md")
                .read_text().splitlines() if ln.startswith("4. **Close the bead**"))
    assert (line.index("pull --ff-only") < line.index("bd import") < line.index("bd export")
            < line.index("<(sort $REPO/.beads/issues.jsonl)") < line.index("chore(beads)"))


def test_tailrace_cloud_export_checks_only_this_bead_changed():
    line = next(ln for ln in (Path(__file__).parent.parent / ".claude/agents/tailrace.md")
                .read_text().splitlines() if ln.lstrip().startswith("3. From `$REPO`"))
    assert line.index("bd export") < line.index('<(sort "$WT/.beads/issues.jsonl")')


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
    from watermill import stats  # the secondary is Mann-Whitney on exactly these values
    want = stats.mann_whitney([1.0 + i for i in range(30)], [4.0 + i for i in range(30)])[1]
    assert cost["p_value"] == round(want, 6)
    primary = s["metrics"]["primary"]  # and the primary is Fisher on the 2x2
    assert primary["p_value"] == round(stats.fisher_exact(3, 27, 12, 18), 6)
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


# -- review (sluice, water-mill-d20): eligibility on real bead wording -------------


def _why(world, description, **labels):
    fence = world[1].get("alpha").load_contract().fence
    return trial.eligibility(task("a-1", description=description), fence, hand_only=set(),
                             fence_directed=labels.get("directed", set()), enrolled_beads=set(),
                             fence_clear=labels.get("clear", set()))


@pytest.mark.parametrize("text", [
    # wording taken from beads the first dry run excluded for a mention alone
    "Keep calendarErrorState.test.jsx green. See brain/handoffs/mill/6wo-5.md.",
    "Regression test per case (method in brain/handoffs/mill/79r.md).",
    "**Files.** `tests/test_db.py` (new test). `db.py` is fenced and not touched.",
    "Files: data-fixtures/job_runs.json, routes/jobs.py. No db.py change.",
])
def test_a_mention_that_is_not_an_edit_does_not_exclude(world, text):
    assert _why(world, text) == []


@pytest.mark.parametrize("text", [
    "Files: db.py (the migration), routes/x.py",
    "Edit db.py and leave the Makefile untouched.",  # a negation does not hide a directed edit
    "Update brain/schema.md with the new table",
    # a bold-marked Out of scope section ends at the next bold section
    "**Out of scope.** Changing the limits.\n**Verification.** run it\n**Files.** Makefile",
])
def test_a_fenced_edit_still_excludes(world, text):
    assert _why(world, text)


def test_the_owner_can_clear_a_false_fence_hit(world):
    text = "Files: x.py. Headless check with brain/samples/table.png."
    assert _why(world, text)
    assert _why(world, text, clear={"a-1"}) == []


def test_a_repeated_explicit_id_takes_one_block_position(world):
    tr = FakeTracker([task("a-1"), task("a-2")])
    got = enroll(world, "alpha", ["a-1", "a-1", "a-2"], tr)
    assert [r["bead"] for r in got["rows"]] == ["a-1", "a-2"]
    assert trial.ledger_problems(trial.read_ledger(world[0])) == []


def test_enroll_reports_a_partial_block(world):
    tr = FakeTracker([task(f"a-{i}") for i in range(6)])
    got = enroll(world, "alpha", [f"a-{i}" for i in range(6)], tr, dry_run=True)
    (p,) = got["partial_blocks"]
    assert p["block"] == 1 and p["filled"] == 2 and p["A"] + p["B"] == 6
    full = enroll(world, "alpha", [f"a-{i}" for i in range(4)], tr, dry_run=True)
    assert full["partial_blocks"] == []


# -- review: two machines enrol, git merges the ledger with merge=union ----------


def _git(cwd, *argv):
    import subprocess
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv], cwd=cwd,
                          capture_output=True, text=True, check=True)


def _two_machines(world, first, second, seeds=(7, 7)):
    """Enrol `first` on a branch and `second` on main from the same base; merge."""
    root = world[0]
    attrs = (Path(__file__).resolve().parents[1] / ".gitattributes").read_text()
    (root / ".gitattributes").write_text(attrs)
    _git(root, "init", "-q", "-b", "main")
    tr = FakeTracker([task(f"a-{i}") for i in range(8)])
    enroll(world, "alpha", ["a-7"], tr, seed=7)  # a shared base with a seed line
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    _git(root, "checkout", "-qb", "laptop2")
    # different machines enrol at different moments; byte-identical lines would collapse
    # in the union (and then carry the same arm, which is harmless)
    enroll(world, "alpha", first, tr, seed=seeds[0], now="2026-10-14T10:00:00+00:00")
    _git(root, "commit", "-qam", "machine 2")
    _git(root, "checkout", "-q", "main")
    enroll(world, "alpha", second, tr, seed=seeds[1], now="2026-10-14T10:00:05+00:00")
    _git(root, "commit", "-qam", "machine 1")
    _git(root, "merge", "-q", "--no-edit", "laptop2")  # union: no conflict, both kept
    return trial.read_ledger(root), tr


def test_a_union_merge_that_double_assigns_a_bead_is_detected_and_refused(world):
    ledger, tr = _two_machines(world, ["a-1"], ["a-1"])
    assert sum(1 for r in ledger if r.get("bead") == "a-1") == 2
    problems = trial.ledger_problems(ledger)
    assert any("a-1 is enrolled 2 times" in p for p in problems)
    with pytest.raises(trial.TrialError, match="inconsistent"):
        enroll(world, "alpha", ["a-5"], tr)
    with pytest.raises(trial.TrialError, match="inconsistent"):
        trial.start(world[0], "a-1", session_id="s", remote=False)
    with pytest.raises(trial.TrialError, match="inconsistent"):
        trial.brief(world[0], "a-1", registry=world[1])
    s = trial.status(world[0])
    assert s["ledger_problems"] and "LEDGER INCONSISTENT" in trial.render_status(s)


def test_a_union_merge_of_different_beads_on_one_block_position_is_detected(world):
    ledger, _ = _two_machines(world, ["a-1", "a-2"], ["a-3", "a-4"])
    problems = trial.ledger_problems(ledger)
    assert any("no longer balanced" in p for p in problems), problems


def test_a_sound_ledger_has_no_problems(world):
    tr = FakeTracker([task(f"a-{i}") for i in range(8)])
    enroll(world, "alpha", ["a-0", "a-1", "a-2"], tr)
    enroll(world, "alpha", ["a-3", "a-4"], tr)
    trial.start(world[0], "a-0", session_id="s0", remote=False)
    assert trial.ledger_problems(trial.read_ledger(world[0])) == []


def test_a_second_master_seed_is_a_problem():
    ledger = [{"type": "seed", "seed": 1}, {"type": "seed", "seed": 2}]
    assert "2 master seeds" in trial.ledger_problems(ledger)[0]


def test_the_first_enrol_line_is_the_bead_s_arm():
    ledger = [{"type": "enroll", "bead": "x", "arm": "A"}, {"type": "enroll", "bead": "x",
                                                           "arm": "B"}]
    assert trial.enrolled(ledger)["x"]["arm"] == "A"


# -- review: the blind scorer sees the same thing for either arm -----------------


def test_scorepack_blocks_are_identical_in_form_for_both_arms(world):
    root, registry, _ = world
    same = dict(title="Same title", description="Goal: same text\nFiles: x.py")
    tr = FakeTracker([task(f"alpha-{i}", labels=["trial:A", "trial:B"],
                           comments=[{"text": "## Sluice said hi"}], **same) for i in range(4)])
    enroll(world, "alpha", None, tr)
    enr = trial.enrolled(trial.read_ledger(root))
    rows = [{"type": "collect", "bead": b, "repo": "alpha", "arm": r["arm"], "landed": True,
             "landed_at": "2026-09-01T00:00:00Z", "landed_sha": f"sha-{b}", "pr_number": 77,
             "first_push_ci_green": True, "owner_corrections": 0} for b, r in enr.items()]
    trial._append(trial.results_path(root), rows)
    text = trial.scorepack(root, tracker_for=lambda p: tr, registry=registry,
                           today=datetime(2026, 10, 20, tzinfo=UTC))
    blocks = {}
    for chunk in text.split("### ")[1:]:
        bead = chunk.split("\n", 1)[0]
        blocks[enr[bead]["arm"]] = chunk.replace(bead, "<id>").strip()
    assert set(blocks) == {"A", "B"} and blocks["A"] == blocks["B"]
    lowered = text.lower()
    for forbidden in ("trial", "sluice", "#77", "pull request:", "bead/", "claude/"):
        assert forbidden not in lowered, forbidden
    assert trial.BLIND_PATHSPEC in text and "sha-" in text


def test_the_blind_pathspec_hides_handoffs_records_findings_and_labels(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "app.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the work")
    for path in ("brain/handoffs/mill/x.md", "knowledge/agent-runs/sluice-x.jsonl",
                 ".beads/issues.jsonl", "HANDOFF-mill/x.md"):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("## Sluice\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"notes {path}")
    import shlex
    argv = shlex.split(f"log --format=%s {trial.BLIND_PATHSPEC}")
    assert _git(repo, *argv).stdout.split("\n")[:-1] == ["the work"]


# -- review: cost --------------------------------------------------------------


def test_cost_state_read_keeps_numbers_only(world):
    root, registry, tmp = world
    bead = started_world(world)
    sessions = tmp / "sessions"
    path = write_session(sessions)
    with path.open("a") as handle:  # a cost-state line with text in it: none of it may leak
        handle.write(json.dumps({"type": "cost-state", "totalCostUSD": 3.0, "lastPrompt":
                                 "CANARY-PROMPT", "modelUsage": {"CANARY-MODEL": {
                                     "inputTokens": 1, "outputTokens": 1}}}) + "\n")
    old = time.time() - 3600
    import os
    os.utime(path, (old, old))
    (row,) = trial.collect(root, registry, sessions_dir=sessions, prs={bead: 1},
                           gh_for=gh_factory(FakeGH()))["collected"]
    assert row["cost_usd_est"] == 3.0
    assert "CANARY" not in trial.results_path(root).read_text()


def test_an_owner_supplied_cost_is_marked_and_survives_a_later_collect(world):
    root, registry, tmp = world
    bead = started_world(world)
    sessions = tmp / "sessions"
    write_session(sessions)
    gh = gh_factory(FakeGH())
    (row,) = trial.collect(root, registry, sessions_dir=sessions, manual_cost={bead: 9.5},
                           prs={bead: 1}, gh_for=gh)["collected"]
    assert row["cost_basis"] == "manual" and row["cost_supplied_by"] == "owner"
    assert any("supplied by the owner" in n for n in row["notes"])
    assert trial.collect(root, registry, sessions_dir=sessions, prs={bead: 1},
                         gh_for=gh)["collected"] == []  # not reverted to the cost-state figure
    assert trial.latest(trial.read_results(root), "collect")[bead]["cost_usd_est"] == 9.5
    with pytest.raises(trial.TrialError, match="not in the trial"):
        trial.collect(root, registry, sessions_dir=sessions, manual_cost={"zz-9": 1.0},
                      gh_for=gh)


def test_collect_records_the_landing_commit(world):
    root, registry, tmp = world
    bead = started_world(world)
    sessions = tmp / "sessions"
    write_session(sessions)
    fake = FakeGH()
    fake.pr = lambda n: {"merged_at": "2026-10-21T09:00:00Z", "merge_commit_sha": "abc123"}
    (row,) = trial.collect(root, registry, sessions_dir=sessions, prs={bead: 1},
                           gh_for=gh_factory(fake))["collected"]
    assert row["landed_sha"] == "abc123"


def test_cost_is_compared_on_laptop_beads_only(tmp_path):
    seed_trial(tmp_path, 9)
    rows = trial.read_results(tmp_path)
    for r in rows:
        if r["type"] == "collect" and r["arm"] == "B" and r["bead"].endswith(("0", "1")):
            trial._append(trial.results_path(tmp_path), [{**r, "cost_basis": "manual"}])
    s = trial.status(tmp_path)
    assert s["metrics"]["secondary"][0]["n"] == {"A": 9, "B": 7}
    assert s["cost_excluded_by_basis"] == {"manual": 2}
    assert "laptop beads only" in trial.render_status(s)


# -- review: the sensitivity analysis -------------------------------------------


def test_sensitivity_counts_an_unlanded_bead_after_30_days_as_a_failure(tmp_path):
    ledger = [{"type": "seed", "seed": 1}]
    for arm in "AB":
        ledger.append({"type": "enroll", "bead": f"x-{arm}", "repo": "alpha", "arm": arm,
                       "seed": 1, "block": 0, "pos": "AB".index(arm),
                       "enrolled_at": "2026-09-01T00:00:00+00:00"})
    trial._append(trial.ledger_path(tmp_path), ledger)
    trial._append(trial.results_path(tmp_path), [
        {"type": "collect", "bead": "x-A", "arm": "A", "landed": True,
         "landed_at": "2026-09-05T00:00:00Z"},
        {"type": "score", "bead": "x-A", "early": False, "escapes": []}])
    early = trial.status(tmp_path, today=datetime(2026, 9, 20, tzinfo=UTC))
    assert early["metrics"]["sensitivity"]["n"] == {"A": 1, "B": 0}
    late = trial.status(tmp_path, today=datetime(2026, 10, 5, tzinfo=UTC))
    m = late["metrics"]["sensitivity"]
    assert m["n"] == {"A": 1, "B": 1} and m["k"] == {"A": 0, "B": 1}


def test_only_blocker_and_bug_are_primary_escapes(tmp_path):
    seed_trial(tmp_path, 3)
    trial._append(trial.results_path(tmp_path), [
        {"type": "score", "bead": "alpha-A0", "early": False, "escapes": [{"severity": "test-gap"}]},
        {"type": "score", "bead": "alpha-A1", "early": False, "escapes": [{"severity": "blocker"}]}])
    assert trial.status(tmp_path)["metrics"]["primary"]["k"] == {"A": 1, "B": 0}


# -- harm stop (water-mill-kt6) ---------------------------------------------


def test_pause_blocks_start_status_shows_it_and_resume_clears_it(world, capsys):
    root, _, _ = world
    enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))
    assert trial.pause_state(trial.read_ledger(root)) is None
    trial.pause(root, "blocker landed in a-9", now="2026-10-20T00:00:00+00:00")
    with pytest.raises(trial.TrialError, match="PAUSED.*blocker landed in a-9"):
        trial.start(root, "a-1", session_id="s1", remote=False)
    with pytest.raises(trial.TrialError, match="already paused"):
        trial.pause(root, "again")
    s = trial.status(root)
    assert s["paused"]["reason"] == "blocker landed in a-9"
    assert "PAUSED" in trial.render_status(s) and "blocker landed in a-9" in trial.render_status(s)
    assert trial.ledger_problems(trial.read_ledger(root)) == []
    trial.resume(root, "reverted; owner decision")
    assert "PAUSED" not in trial.render_status(trial.status(root))
    assert trial.start(root, "a-1", session_id="s1", remote=False)["bead"] == "a-1"
    with pytest.raises(trial.TrialError, match="not paused"):
        trial.resume(root, "x")
    with pytest.raises(trial.TrialError, match="reason"):
        trial.pause(root, "  ")
    # append-only: pause, resume, both kept
    kinds = [r["type"] for r in trial.read_ledger(root)]
    assert kinds.count("pause") == 1 and kinds.count("resume") == 1


def test_cli_start_on_a_paused_ledger_exits_nonzero_with_the_reason(world, capsys):
    root, _, _ = world
    enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))
    assert cli.main(["--root", str(root), "trial", "pause", "--reason", "harm x"]) == 0
    assert cli.main(["--root", str(root), "trial", "pause"]) != 0  # reason required
    capsys.readouterr()
    rc = cli.main(["--root", str(root), "trial", "start", "a-1", "--session-id", "s1"])
    out = capsys.readouterr()
    assert rc != 0 and "harm x" in (out.err + out.out)
    assert cli.main(["--root", str(root), "trial", "resume", "--reason", "ok"]) == 0
    assert cli.main(["--root", str(root), "trial", "start", "a-1", "--session-id", "s1"]) == 0


def test_enroll_refuses_while_paused_but_a_dry_run_still_works(world):
    root, _, _ = world
    trial.pause(root, "harm y")
    with pytest.raises(trial.TrialError, match="PAUSED.*harm y"):
        enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))
    assert trial.enrolled(trial.read_ledger(root)) == {}
    assert enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]), dry_run=True)["rows"]
    trial.resume(root, "owner: resume")
    assert enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))["rows"]


def test_a_stale_resume_cannot_clear_a_pause_it_never_saw_whatever_the_merge_order(tmp_path):
    p1 = {"type": "pause", "reason": "first", "at": "2026-10-20T00:00:00+00:00"}
    r1 = {"type": "resume", "reason": "laptop", "at": "2026-10-21T00:00:00+00:00",
          "resumes": [p1["at"]]}
    p2 = {"type": "pause", "reason": "second harm", "at": "2026-10-22T00:00:00+00:00"}
    # a second checkout, still on the P1 base, also resumed P1 only
    r2 = {"type": "resume", "reason": "cloud", "at": "2026-10-23T00:00:00+00:00",
          "resumes": [p1["at"]]}
    for order in ([p1, r1, p2, r2], [p1, r2, r1, p2], [p1, p2, r1, r2]):
        assert trial.pause_state(order)["reason"] == "second harm"
        assert trial.ledger_problems(order) == []
    # a resume written now clears every open pause, and the ledger line says which
    trial._append(trial.ledger_path(tmp_path), [p1, p2])
    line = trial.resume(tmp_path, "owner: both handled")
    assert line["resumes"] == [p1["at"], p2["at"]]
    assert trial.pause_state(trial.read_ledger(tmp_path)) is None
    with pytest.raises(trial.TrialError, match="already in the ledger"):
        trial.pause(tmp_path, "same second", now=p2["at"])


def test_a_trial_bound_session_cannot_pause_or_resume_but_the_owner_can(world):
    root, _, _ = world
    enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))
    trial.start(root, "a-1", session_id="trial-sess", remote=False)
    with pytest.raises(trial.TrialError, match="bound to a trial bead"):
        trial.pause(root, "I think it is harmful", session_id="trial-sess")
    assert trial.pause_state(trial.read_ledger(root)) is None
    trial.pause(root, "owner: real harm", session_id="owner-terminal")
    with pytest.raises(trial.TrialError, match="bound to a trial bead"):
        trial.resume(root, "agent resumes itself", session_id="trial-sess")
    assert trial.pause_state(trial.read_ledger(root)) is not None
    trial.resume(root, "owner: handled")  # no session id at all: a plain terminal
    assert trial.pause_state(trial.read_ledger(root)) is None


def test_cli_pause_reads_the_session_id_from_the_environment(world, monkeypatch, capsys):
    root, _, _ = world
    enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))
    trial.start(root, "a-1", session_id="trial-sess", remote=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "trial-sess")
    assert cli.main(["--root", str(root), "trial", "pause", "--reason", "x"]) != 0
    assert "bound to a trial bead" in capsys.readouterr().err
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "someone-else")
    assert cli.main(["--root", str(root), "trial", "pause", "--reason", "x"]) == 0


@pytest.mark.parametrize("arm", ["A", "B"])
def test_both_briefs_forbid_the_owner_only_trial_commands(world, arm):
    root, reg, _ = world
    enroll(world, "alpha", ["a-1", "a-2"], FakeTracker([task("a-1"), task("a-2")]))
    bead = next(b for b, r in trial.enrolled(trial.read_ledger(root)).items() if r["arm"] == arm)
    text = trial.brief(root, bead, registry=reg)
    assert "never run `watermill trial pause`, `trial resume`" in text
    assert "human judgement" in text


# -- water-mill-2ez: enroll (not dry run), score and scorepack are owner-only too ----------


def _bound_session(world, monkeypatch):
    root, _, _ = world
    monkeypatch.setattr(trial, "Tracker", lambda path: FakeTracker([task(f"{Path(path).name}-1")]))
    enroll(world, "alpha", ["a-1"], FakeTracker([task("a-1")]))
    trial.start(root, "a-1", session_id="trial-sess", remote=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "trial-sess")
    return root


def test_a_trial_bound_session_cannot_enroll_score_or_scorepack(world, monkeypatch, capsys):
    root = _bound_session(world, monkeypatch)
    before = trial.read_ledger(root)
    for argv in (["enroll", "alpha", "--ready"], ["scorepack"], ["score", "a-1", "--none"]):
        assert cli.main(["--root", str(root), "trial", *argv]) != 0
        assert "bound to a trial bead" in capsys.readouterr().err, argv
    assert trial.read_ledger(root) == before


def test_a_trial_bound_session_can_still_dry_run_enroll_collect_and_status(world, monkeypatch,
                                                                         capsys):
    root = _bound_session(world, monkeypatch)
    assert cli.main(["--root", str(root), "trial", "enroll", "alpha", "--ready", "--dry-run"]) == 0
    assert cli.main(["--root", str(root), "trial", "status"]) == 0
    cli.main(["--root", str(root), "trial", "collect", "--dry-run"])
    assert "bound to a trial bead" not in capsys.readouterr().err


def test_the_owner_terminal_is_never_blocked_from_score_or_scorepack(world, monkeypatch, capsys):
    root = _bound_session(world, monkeypatch)
    for env in (None, "someone-else"):
        if env is None:
            monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
        else:
            monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", env)
        assert cli.main(["--root", str(root), "trial", "scorepack"]) == 0
        cli.main(["--root", str(root), "trial", "score", "a-1", "--none"])
        assert "bound to a trial bead" not in capsys.readouterr().err


@pytest.mark.parametrize("arm", ["A", "B"])
def test_both_briefs_name_every_command_the_harness_refuses(world, arm):
    """The brief's parenthetical tracks the CLI guard (water-mill-2ez)."""
    root, reg, _ = world
    enroll(world, "alpha", ["a-1", "a-2"], FakeTracker([task("a-1"), task("a-2")]))
    bead = next(b for b, r in trial.enrolled(trial.read_ledger(root)).items() if r["arm"] == arm)
    text = trial.brief(root, bead, registry=reg)
    assert "`trial pause`, `resume`, `enroll`, `score` and `scorepack` also refuse" in text


# -- a cancelled batch is archived and the next one starts fresh --------------


def test_the_cancelled_first_batch_is_archived_not_live():
    repo = Path(__file__).resolve().parent.parent
    assert not trial.ledger_path(repo).exists()
    archive = repo / trial.TRIAL_DIR / "archive" / "2026-10-14-cancelled.jsonl"
    rows = [json.loads(line) for line in archive.read_text().splitlines()]
    assert [r["type"] for r in rows].count("enroll") == 8
    assert rows[-1]["type"] == "cancelled" and "crew" in rows[-1]["reason"]


def test_a_trial_with_an_archived_ledger_starts_fresh(world):
    root = world[0]
    archive = root / trial.TRIAL_DIR / "archive" / "old.jsonl"
    archive.parent.mkdir(parents=True)
    old = [{"type": "seed", "seed": 111}, {"type": "enroll", "bead": "a-1", "repo": "alpha",
           "arm": "A", "block": 0, "pos": 0, "seed": 111}]
    trial._append(archive, old)
    before = archive.read_bytes()
    assert trial.read_ledger(root) == [] and trial.master_seed([]) is None
    tr = FakeTracker([task("a-1"), task("a-2")])
    out = enroll(world, "alpha", ["a-1", "a-2"], tr, seed=222)  # a-1 is not "enrolled" any more
    assert out["seed"] == 222 and out["seed_is_new"]
    ledger = trial.read_ledger(root)
    assert trial.master_seed(ledger) == 222 and set(trial.enrolled(ledger)) == {"a-1", "a-2"}
    assert archive.read_bytes() == before
