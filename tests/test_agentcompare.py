"""agents compare: works vs runs, exclusions, too-few-to-say, CLI."""

from __future__ import annotations

import json

from watermill import agentcompare, agentlog, cli


def _handoff(i, *, outcome="landed", rounds=1, pushed=False, project="p"):
    inferred = ["detail.sluice_pushed_fixes"] if rounds else []
    return agentlog.make_record(
        key=f"crew:p-{i}", agent_kind="mill-crew", source="handoff", project=project,
        subject=f"p-{i}", outcome=outcome, ended_at=f"2026-10-{i % 28 + 1:02d}",
        fields_inferred=inferred,
        detail={"sluice_rounds": rounds, "sluice_pushed_fixes": pushed if rounds else None},
    )


def _run(key, kind, secs, tokens, *, calls=10, cost=None, role=None, day="2026-10-05"):
    return agentlog.make_record(
        key=key, agent_kind=kind, source="transcript", project="p", outcome=None,
        ended_at=day, duration_seconds=secs, cost_usd=cost,
        detail={"tokens_total": tokens, "tool_call_count": calls, "role": role},
    )


def _seed(root, records):
    agentlog.append_new(root, records)


def _find(result, pair_index, metric):
    return next(m for m in result["comparisons"][pair_index]["metrics"] if m["metric"] == metric)


def test_crew_runs_are_not_counted_per_handoff_and_beads_not_per_run(tmp_path):
    recs = [_handoff(i) for i in range(10)]
    # three transcript runs per bead, all agent_kind mill-crew
    recs += [_run(f"r{i}-{j}", "mill-crew", 100 + i, 1000 + i, role="sluice")
             for i in range(10) for j in range(3)]
    recs += [_run(f"s{i}", "subagent:x", 50 + i, 500 + i) for i in range(9)]
    _seed(tmp_path, recs)
    res = agentcompare.compare(tmp_path, [("crew", "subagent")])
    assert _find(res, 0, "duration_seconds")["groups"][0]["n"] == 30  # runs
    # beads: handoff records only, 10 -- but B has none so the bead scope is untested
    landed = _find(res, 0, "landed_rate")
    assert landed["groups"][0]["n"] == 10 and landed["groups"][1]["records"] == 0
    assert landed["tested"] is False


def test_too_few_prints_no_p_value_and_names_n(tmp_path):
    _seed(tmp_path, [_run(f"a{i}", "mill-crew", 100 + i, 1000) for i in range(20)]
          + [_run(f"b{i}", "subagent:x", 90 + i, 900) for i in range(7)])
    res = agentcompare.compare(tmp_path, [("crew", "subagent")])
    m = _find(res, 0, "duration_seconds")
    assert m["tested"] is False and m["p_value"] is None and m["difference"] is None
    text = agentcompare.render(res)
    assert "too few to say: n = 20 vs 7" in text
    assert "p =" not in text


def test_min_n_met_gives_difference_and_p_with_n_beside_it(tmp_path):
    _seed(tmp_path, [_run(f"a{i}", "mill-crew", 300 + i, 1000) for i in range(12)]
          + [_run(f"b{i}", "subagent:x", 100 + i, 900) for i in range(12)])
    res = agentcompare.compare(tmp_path, [("crew", "subagent")])
    m = _find(res, 0, "duration_seconds")
    assert m["tested"] and m["p_value"] < 0.001 and m["test"] == "Mann-Whitney U"
    assert m["difference"]["value"] > 0 and m["difference"]["ci95"][0] > 0
    assert "p = " in agentcompare.render(res) and "n = 12 vs 12" in agentcompare.render(res)


def test_nulls_and_inferred_are_excluded_and_counted(tmp_path):
    a = [_run(f"a{i}", "mill-crew", 100 + i, 1000) for i in range(10)]
    a.append(_run("a-null", "mill-crew", None, 1000))
    b = [_run(f"b{i}", "subagent:x", 100 + i, 1000) for i in range(9)]
    inferred = _run("b-inf", "subagent:x", 5, 1000)
    inferred["fields_inferred"] = ["duration_seconds"]
    _seed(tmp_path, a + b + [inferred])
    m = _find(agentcompare.compare(tmp_path, [("crew", "subagent")]), 0, "duration_seconds")
    ga, gb = m["groups"]
    assert (ga["n"], ga["excluded_null"], ga["records"]) == (10, 1, 11)
    assert (gb["n"], gb["excluded_inferred"], gb["records"]) == (9, 1, 10)
    kept = _find(agentcompare.compare(tmp_path, [("crew", "subagent")], include_inferred=True),
                 0, "duration_seconds")
    assert kept["groups"][1]["n"] == 10


def test_first_pass_approval_is_inferred_so_excluded_by_default(tmp_path):
    recs = [_handoff(i, rounds=1, pushed=(i % 4 == 0)) for i in range(12)]
    _seed(tmp_path, recs)
    default = _find(agentcompare.compare(tmp_path, [("crew", "session")]), 0,
                    "first_pass_approval_rate")["groups"][0]
    assert default["n"] == 0 and default["excluded_inferred"] == 12
    g = _find(agentcompare.compare(tmp_path, [("crew", "session")], include_inferred=True),
              0, "first_pass_approval_rate")["groups"][0]
    assert (g["n"], g["successes"]) == (12, 9)  # i = 0, 4, 8 pushed fixes


def test_first_pass_means_one_round_and_no_pushed_fixes():
    one = agentcompare._first_pass
    base = {"detail": {"sluice_rounds": 1, "sluice_pushed_fixes": False}}
    assert one(base) is True
    assert one({"detail": {"sluice_rounds": 2, "sluice_pushed_fixes": False}}) is False
    assert one({"detail": {"sluice_rounds": 1, "sluice_pushed_fixes": True}}) is False
    assert one({"detail": {"sluice_rounds": 0, "sluice_pushed_fixes": None}}) is False
    assert one({"detail": {}}) is None


def test_proportion_comparison_uses_fisher_and_wilson(tmp_path):
    a = [_handoff(i) for i in range(10)]
    b = []
    for i in range(10):
        r = _handoff(100 + i, outcome="landed" if i < 3 else "unlanded")
        r["agent_kind"] = "other"
        b.append(r)
    _seed(tmp_path, a + b)
    m = _find(agentcompare.compare(tmp_path, [("crew", "other")]), 0, "landed_rate")
    assert m["tested"] and m["test"] == "Fisher exact"
    assert m["p_value"] == 0.003096  # scipy.stats.fisher_exact([[10, 0], [3, 7]]).pvalue
    assert m["groups"][0]["ci95"][0] < 1.0


def test_since_filters_and_counts_undated(tmp_path):
    recs = [_run(f"o{i}", "mill-crew", 10, 1, day="2026-01-01") for i in range(9)]
    recs += [_run(f"n{i}", "mill-crew", 10, 1, day="2026-10-01") for i in range(9)]
    undated = _run("u", "mill-crew", 10, 1, day=None)
    _seed(tmp_path, recs + [undated])
    g = _find(agentcompare.compare(tmp_path, [("crew", "session")], since="2026-06-01"),
              0, "tokens_total")["groups"][0]
    assert (g["n"], g["excluded_undated"]) == (9, 1)


def test_crew_role_selector_and_multiple_comparison_warning(tmp_path):
    recs = [_run(f"s{i}", "mill-crew", 10 + i, 100 + i, role="sluice", cost=1.0 + i)
            for i in range(10)]
    recs += [_run(f"m{i}", "mill-crew", 50 + i, 300 + i, role="millstone", cost=2.0 + i)
             for i in range(10)]
    recs += [_handoff(i) for i in range(10)]
    _seed(tmp_path, recs)
    res = agentcompare.compare(tmp_path, [("crew:sluice", "crew:millstone")])
    assert _find(res, 0, "duration_seconds")["groups"][0]["n"] == 10
    assert "WARNING" not in agentcompare.render(res)  # 4 tested, below the threshold
    # six tested metrics trips the warning
    comp = res["comparisons"][0]
    comp["tested"] = 6
    assert "WARNING: 6 metrics" in agentcompare.render(res)


def test_cli_compare_json_and_pairing_rule(tmp_path, capsys):
    _seed(tmp_path, [_run(f"a{i}", "mill-crew", 10, 1) for i in range(3)])
    assert cli.main(["--root", str(tmp_path), "agents", "compare", "--kind", "crew"]) == 2
    capsys.readouterr()
    assert cli.main(["--root", str(tmp_path), "agents", "compare", "--json",
                     "--kind", "crew", "--vs", "session"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["min_n"] == 8 and data["comparisons"][0]["a"] == "crew"
    assert cli.main(["--root", str(tmp_path), "agents", "compare"]) == 0
    assert "too few to say" in capsys.readouterr().out
