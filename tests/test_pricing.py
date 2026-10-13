"""pricing.py: API-equivalent cost estimate from model + tokens (water-mill-cdi)."""

import json
from pathlib import Path

from watermill import agentcompare, agentlog, pricing, recorded, sessionlog

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"


def _rec(model="claude-sonnet-5-5", models=None, kind="mill-crew", **tokens):
    detail = {"input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0,
              "cache_read_tokens": 0, "model": model, "models": models or [model], **tokens}
    return agentlog.make_record(key="k", agent_kind=kind, source="transcript",
                                project="p", outcome=None, detail=detail)


def test_known_model_prices_every_token_class():
    r = pricing.annotate(_rec(input_tokens=1_000_000, output_tokens=1_000_000,
                              cache_creation_tokens=1_000_000, cache_read_tokens=1_000_000))
    # sonnet 5.5, a subagent with no split -> 5-minute writes: 2 + 10 + 2.5 + 0.2
    assert r["detail"]["cost_usd_est"] == 14.7
    assert r["detail"]["cost_usd_est_as_of"] == pricing.AS_OF
    assert r["detail"]["tokens_total_incl_cache"] == 4_000_000
    assert r["fields_inferred"] == ["detail.cost_usd_est"] and r["cost_usd"] is None


def test_cache_writes_are_priced_by_ttl():
    m = 1_000_000
    split = pricing.annotate(_rec("claude-opus-5-5", cache_creation_tokens=2 * m,
                                  cache_creation_5m_tokens=m, cache_creation_1h_tokens=m))
    assert split["detail"]["cost_usd_est"] == 5.0 + 8.0  # 1.25x and 2x of $4
    # no split: a top-level session writes with the 1-hour TTL, a subagent 5-minute
    session = pricing.annotate(_rec("claude-opus-5-5", kind="session", cache_creation_tokens=m))
    sub = pricing.annotate(_rec("claude-opus-5-5", kind="mill-crew", cache_creation_tokens=m))
    assert (session["detail"]["cost_usd_est"], sub["detail"]["cost_usd_est"]) == (8.0, 5.0)
    # a partial split: the uncovered rest goes by the kind's TTL
    part = pricing.annotate(_rec("claude-opus-5-5", kind="session", cache_creation_tokens=2 * m,
                                 cache_creation_5m_tokens=m, cache_creation_1h_tokens=0))
    assert part["detail"]["cost_usd_est"] == 5.0 + 8.0


def test_cache_reads_are_cheap_and_writes_are_dear():
    reads = pricing.annotate(_rec("claude-opus-5-5", cache_read_tokens=1_750_000,
                                  input_tokens=894))["detail"]["cost_usd_est"]
    writes = pricing.annotate(_rec("claude-opus-5-5", cache_creation_tokens=1_750_000)
                              )["detail"]["cost_usd_est"]
    assert reads == round((1_750_000 * 0.20 + 894 * 4.0) / 1e6, 4) == 0.3536
    assert writes == 8.75 and writes > 20 * reads
    fable = pricing.annotate(_rec("claude-fable-5-1", cache_read_tokens=1_000_000))
    assert fable["detail"]["cost_usd_est"] == 0.25


def test_unknown_model_is_null_not_a_guess():
    r = pricing.annotate(_rec("claude-mystery-9", input_tokens=500))
    assert r["detail"]["cost_usd_est"] is None
    assert "cost_usd_est_as_of" not in r["detail"]
    assert "detail.cost_usd_est" not in r["fields_inferred"]
    assert r["detail"]["tokens_total_incl_cache"] == 500  # still reported
    assert pricing.annotate(_rec("claude-haiku-5-5", input_tokens=5))["detail"]["cost_usd_est"] \
        is None  # tiered pricing: left out on purpose


def test_mixed_price_models_are_null_and_suffixes_are_normalised():
    mixed = pricing.annotate(_rec(models=["claude-opus-5-5", "claude-sonnet-5-5"],
                                  input_tokens=10))
    assert mixed["detail"]["cost_usd_est"] is None
    assert pricing.canonical("claude-opus-5-5[1m]") == "claude-opus-5-5"
    assert pricing.canonical("claude-sonnet-5-5-20261001") == "claude-sonnet-5-5"


def test_annotate_recomputes_and_never_trusts_a_stored_estimate():
    r = _rec(output_tokens=1_000_000)
    r["detail"].update(cost_usd_est=999.0, cost_usd_est_as_of="1999-01-01")
    r["fields_inferred"] = ["detail.cost_usd_est", "subject"]
    pricing.annotate(r)
    assert r["detail"]["cost_usd_est"] == 10.0 and r["detail"]["cost_usd_est_as_of"] == pricing.AS_OF
    unknown = _rec("claude-mystery-9", output_tokens=1)
    unknown["detail"]["cost_usd_est"] = 5.0
    unknown["fields_inferred"] = ["detail.cost_usd_est"]
    pricing.annotate(unknown)
    assert unknown["detail"]["cost_usd_est"] is None and unknown["fields_inferred"] == []


def _transcript(tmp_path, usages, subagent=True):
    if subagent:
        path = tmp_path / "-p" / "s1" / "subagents" / "agent-a1.jsonl"
    else:
        path = tmp_path / "-p" / "s1.jsonl"
    path.parent.mkdir(parents=True)
    lines = [{"type": "assistant", "timestamp": f"2026-10-01T10:00:0{i}.000Z",
              "message": {"id": f"m{i}", "model": "claude-opus-5-5", "usage": u}}
             for i, u in enumerate(usages)]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return path


def test_transcripts_keep_the_ttl_split_and_store_no_estimate(tmp_path):
    split = {"ephemeral_5m_input_tokens": 300, "ephemeral_1h_input_tokens": 700}
    _transcript(tmp_path, [
        {"input_tokens": 1, "output_tokens": 2, "cache_creation_input_tokens": 1000,
         "cache_read_input_tokens": 0, "cache_creation": split},
        {"input_tokens": 1, "output_tokens": 2, "cache_creation_input_tokens": 1000,
         "cache_read_input_tokens": 0, "cache_creation": split},
    ])
    (r,) = sessionlog.collect(tmp_path)
    d = r["detail"]
    assert (d["cache_creation_5m_tokens"], d["cache_creation_1h_tokens"]) == (600, 1400)
    assert "cost_usd_est" not in d and "tokens_total_incl_cache" not in d
    assert "detail.cost_usd_est" not in r["fields_inferred"]
    priced = pricing.annotate(r)["detail"]["cost_usd_est"]
    assert priced == round((2 * 4 + 4 * 20 + 600 * 5 + 1400 * 8) / 1e6, 4)


def test_a_transcript_without_the_split_says_null_not_zero():
    for r in sessionlog.collect(FIXTURES, [], {}):
        d = r["detail"]
        assert d["cache_creation_5m_tokens"] is None and d["cache_creation_1h_tokens"] is None
        assert "cost_usd_est" not in d


def test_recorded_records_store_counters_only():
    base = _rec("claude-sonnet-5-5", output_tokens=1_000_000)
    out = recorded.build(base, role="millstone", project="p", bead="p-abc")
    assert out["source"] == "recorded"
    assert "cost_usd_est" not in out["detail"] and out["fields_inferred"] == []
    assert pricing.annotate(out)["detail"]["cost_usd_est"] == 10.0


def test_read_derives_the_estimate_for_old_lines_and_unseen_ignores_it(tmp_path):
    old = _rec("claude-sonnet-5-5", output_tokens=1_000_000)
    old["detail"]["cost_usd_est"] = 1.23  # a frozen figure from an older table
    path = tmp_path / agentlog.AGENTLOG_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(old) + "\n")
    (r,) = agentlog.read(tmp_path)
    assert r["detail"]["cost_usd_est"] == 10.0
    assert r["detail"]["tokens_total_incl_cache"] == 1_000_000
    assert "detail.cost_usd_est" in r["fields_inferred"]
    # a fresh sweep of the same counters (no derived fields) is not "new"
    fresh = _rec("claude-sonnet-5-5", output_tokens=1_000_000)
    fresh["detail"]["cost_usd_est"] = 1.23
    assert agentlog.unseen(tmp_path, [fresh]) == []
    assert agentlog.append_new(tmp_path, [fresh]) == []
    assert len(path.read_text().splitlines()) == 1


def test_compare_excludes_the_estimate_unless_asked_and_says_so(tmp_path):
    def run(i, tokens, kind):
        r = _rec(output_tokens=tokens)
        r.update(key=f"{kind}{i}", agent_kind=kind, ended_at="2026-10-01T00:00:00Z")
        return r  # no stored estimate: compare sees the one read() derives
    agentlog.append_new(tmp_path, [run(i, 100_000 * (i + 1), "mill-crew") for i in range(6)]
                        + [run(i, 300_000 * (i + 1), "session") for i in range(6)])
    pair = [("crew", "session")]
    default = agentcompare.compare(tmp_path, pair)
    assert default["pricing_as_of"] == pricing.AS_OF
    m = next(x for x in default["comparisons"][0]["metrics"] if x["metric"] == "cost_usd_est")
    assert m["groups"][0]["n"] == 0 and m["groups"][0]["excluded_inferred"] == 6
    text = agentcompare.render(default)
    assert "API-equivalent ESTIMATE" in text and pricing.AS_OF in text
    assert "--include-inferred" in text
    asked = agentcompare.compare(tmp_path, pair, include_inferred=True)
    m = next(x for x in asked["comparisons"][0]["metrics"] if x["metric"] == "cost_usd_est")
    assert m["groups"][0]["n"] == 6 and m["groups"][0]["median"] == 3.5
    text = agentcompare.render(asked)
    assert "API-equivalent ESTIMATE" in text and "excluded here" not in text
