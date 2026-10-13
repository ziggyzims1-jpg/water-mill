"""pricing.py: estimated cost from model + tokens (water-mill-cdi)."""

from pathlib import Path

from watermill import agentcompare, agentlog, pricing, recorded, sessionlog

FIXTURES = Path(__file__).parent / "fixtures" / "sessions"


def _rec(model="claude-sonnet-5-5", models=None, **tokens):
    detail = {"input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0,
              "cache_read_tokens": 0, "model": model, "models": models or [model], **tokens}
    return agentlog.make_record(key="k", agent_kind="mill-crew", source="transcript",
                                project="p", outcome=None, detail=detail)


def test_known_model_prices_every_token_class():
    r = pricing.annotate(_rec(input_tokens=1_000_000, output_tokens=1_000_000,
                              cache_creation_tokens=1_000_000, cache_read_tokens=1_000_000))
    # sonnet 5.5: 2 + 10 + 2.5 (write, 1.25x) + 0.2 (read)
    assert r["detail"]["cost_usd_est"] == 14.7
    assert r["detail"]["tokens_total_incl_cache"] == 4_000_000
    assert r["fields_inferred"] == ["detail.cost_usd_est"] and r["cost_usd"] is None


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
    assert "detail.cost_usd_est" not in r["fields_inferred"]
    assert r["detail"]["tokens_total_incl_cache"] == 500  # still reported


def test_mixed_price_models_are_null_and_suffixes_are_normalised():
    mixed = pricing.annotate(_rec(models=["claude-opus-5-5", "claude-sonnet-5-5"],
                                  input_tokens=10))
    assert mixed["detail"]["cost_usd_est"] is None
    assert pricing.canonical("claude-opus-5-5[1m]") == "claude-opus-5-5"
    assert pricing.canonical("claude-sonnet-5-5-20261001") == "claude-sonnet-5-5"


def test_transcript_records_gain_the_estimate():
    for r in sessionlog.collect(FIXTURES, [], {}):
        d = r["detail"]
        assert d["tokens_total_incl_cache"] == (d["input_tokens"] + d["output_tokens"]
                                                + d["cache_creation_tokens"] + d["cache_read_tokens"])
        assert "cost_usd_est" in d
        assert (d["cost_usd_est"] is not None) == ("detail.cost_usd_est" in r["fields_inferred"])


def test_recorded_records_gain_the_estimate():
    base = _rec("claude-sonnet-5-5", output_tokens=1_000_000)
    out = recorded.build(base, role="millstone", project="p", bead="p-abc")
    assert out["source"] == "recorded"
    assert out["detail"]["cost_usd_est"] == 10.0
    assert out["fields_inferred"] == ["detail.cost_usd_est"]
    flags_only = recorded.build(None, role="millstone", project="p", bead="p-abc")
    assert "cost_usd_est" not in flags_only["detail"]


def test_compare_excludes_the_estimate_unless_asked_and_says_so(tmp_path):
    def run(i, cost, kind):
        r = _rec(output_tokens=10)
        r.update(key=f"{kind}{i}", agent_kind=kind, ended_at="2026-10-01T00:00:00Z")
        r["detail"]["cost_usd_est"] = cost
        r["fields_inferred"] = ["detail.cost_usd_est"]
        return r
    agentlog.append_new(tmp_path, [run(i, 1.0 + i, "mill-crew") for i in range(6)]
                        + [run(i, 3.0 + i, "session") for i in range(6)])
    pair = [("crew", "session")]
    default = agentcompare.compare(tmp_path, pair)
    m = next(x for x in default["comparisons"][0]["metrics"] if x["metric"] == "cost_usd_est")
    assert m["groups"][0]["n"] == 0 and m["groups"][0]["excluded_inferred"] == 6
    assert "ESTIMATE" in agentcompare.render(default)
    asked = agentcompare.compare(tmp_path, pair, include_inferred=True)
    m = next(x for x in asked["comparisons"][0]["metrics"] if x["metric"] == "cost_usd_est")
    assert m["groups"][0]["n"] == 6
    assert "ESTIMATE" not in agentcompare.render(asked)
