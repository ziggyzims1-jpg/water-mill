"""`watermill agents compare`: the honest comparison Grafana cannot draw.

Reads `runs/agents.jsonl` through `agentlog.read()` (latest line per key) and
compares two groups of agent work, metric by metric, with `stats` doing the
arithmetic. Three rules decide what is counted, and the output prints the
grouping so nobody has to guess:

* **Works vs runs.** `agent_kind == "mill-crew"` alone counts a bead several
  times (its handoff record plus a transcript record per millstone / sluice /
  tailrace dispatch). Per-bead outcome metrics (landed, sluice rounds,
  first-pass approval) use `source == "handoff"` records only; per-run metrics
  (duration, tokens, tool calls, cost, cost_usd_est) use `source == "transcript"` records
  only. Two groups are always compared inside one section, never a handoff
  record against a transcript record.
* **Nulls and inferred values are excluded, per metric, and counted.** A value
  is inferred when the record names its field in `fields_inferred`.
  `--include-inferred` puts them back. One exception, for first-pass approval
  only: `detail.sluice_pushed_fixes` is admitted when `detail.sluice_verdict`
  is exactly `approve` or `approve_after_fixes`, because crewlog then derives
  the flag from the verdict word, not from prose (`crewlog._pushed_fixes`).
  How many were admitted that way is counted and printed.
* **Too few to say is an answer.** Below `min_n` usable values in either group
  no difference, interval or p-value is printed -- only n, and the medians if
  they exist. Do not lower the default to get a p-value.

"First-pass approval rate" = landed with exactly one Sluice round and no pushed
fixes; a landed bead with no Sluice round has no value (null), not a failure.

Crew runs and sessions are not like-for-like (a session is a whole
conversation, a crew run is one agent's task); any comparison with a `session`
side carries a caveat line, and the numbers are still printed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from watermill import agentlog, stats

DEFAULT_MIN_N = 8
MULTIPLE_WARNING_AFTER = 5
DEFAULT_PAIRS = [("crew", "subagent"), ("crew", "session")]
CREW_ROLES = ("millstone", "sluice", "tailrace")


# -- groups ----------------------------------------------------------------


def group_label(name: str) -> str:
    return {
        "crew": "crew (mill-crew)",
        "subagent": "non-crew subagents (subagent:*)",
        "session": "sessions",
    }.get(name, name)


def _matches(name: str, record: dict) -> bool:
    kind = record.get("agent_kind") or ""
    if name in ("crew", "mill-crew"):
        return kind == "mill-crew"
    if name.startswith("crew:"):  # crew:sluice -- one role's runs
        return kind == "mill-crew" and (record.get("detail") or {}).get("role") == name[5:]
    if name == "subagent":
        return kind.startswith("subagent:")
    return kind == name


def _date(record: dict) -> str | None:
    for value in (record.get("ended_at"), record.get("started_at"),
                  (record.get("detail") or {}).get("landed_at")):
        if value:
            return str(value)[:10]
    return None


# -- metrics ---------------------------------------------------------------


@dataclass(frozen=True)
class Metric:
    name: str
    scope: str            # "run" (transcript records) or "bead" (handoff records)
    kind: str             # "continuous" | "proportion"
    value: Callable[[dict], Any]   # None means null
    fields: tuple[str, ...]        # fields_inferred names that make it inferred
    unit: str = ""
    only: Callable[[dict], bool] = lambda r: True  # population filter
    # Inferred fields admitted anyway when `admit(record)` holds (counted apart).
    admit_fields: tuple[str, ...] = ()
    admit: Callable[[dict], bool] = lambda r: False


def _detail(name: str) -> Callable[[dict], Any]:
    return lambda r: (r.get("detail") or {}).get(name)


VERDICT_DERIVED = ("approve", "approve_after_fixes")


def _verdict_derived(r: dict) -> bool:
    """crewlog._pushed_fixes followed the verdict word, not prose."""
    return (r.get("detail") or {}).get("sluice_verdict") in VERDICT_DERIVED


def _first_pass(r: dict) -> Any:
    d = r.get("detail") or {}
    if not d.get("sluice_rounds"):  # None, or landed without any Sluice review
        return None
    return d["sluice_rounds"] == 1 and d.get("sluice_pushed_fixes") is False


METRICS = [
    Metric("duration_seconds", "run", "continuous", lambda r: r.get("duration_seconds"),
           ("duration_seconds",), "s"),
    Metric("tokens_total", "run", "continuous", _detail("tokens_total"),
           ("detail.tokens_total",), "tok"),
    Metric("tool_call_count", "run", "continuous", _detail("tool_call_count"),
           ("detail.tool_call_count",)),
    Metric("cost_usd", "run", "continuous", lambda r: r.get("cost_usd"),
           ("cost_usd",), "$"),
    # An estimate from model + tokens (pricing.py): inferred, so excluded unless
    # --include-inferred. cost_usd above stays the stated cost only.
    Metric("cost_usd_est", "run", "continuous", _detail("cost_usd_est"),
           ("detail.cost_usd_est",), "$"),
    Metric("landed_rate", "bead", "proportion",
           lambda r: {"landed": True, "unlanded": False}.get(r.get("outcome")), ("outcome",)),
    Metric("sluice_rounds", "bead", "continuous", _detail("sluice_rounds"),
           ("detail.sluice_rounds",), only=lambda r: r.get("outcome") == "landed"),
    Metric("first_pass_approval_rate", "bead", "proportion", _first_pass,
           ("detail.sluice_rounds", "detail.sluice_pushed_fixes"),
           only=lambda r: r.get("outcome") == "landed",
           admit_fields=("detail.sluice_pushed_fixes",), admit=_verdict_derived),
]


def _collect(records: list[dict], group: str, metric: Metric, since: str | None,
             include_inferred: bool) -> dict:
    source = "transcript" if metric.scope == "run" else "handoff"
    # a recorded line is a transcript record the agent filed itself (it wins the
    # fold for its key, so a run is still counted once)
    accepted = (source, "recorded") if source == "transcript" else (source,)
    pool = [r for r in records
            if r.get("source") in accepted and _matches(group, r) and metric.only(r)]
    undated = 0
    if since:
        kept = []
        for r in pool:
            day = _date(r)
            if day is None:
                undated += 1
            elif day >= since:
                kept.append(r)
        pool = kept
    values: list = []
    nulls = inferred = admitted = 0
    for r in pool:
        v = metric.value(r)
        hit = set(metric.fields) & set(r.get("fields_inferred") or [])
        if v is None:
            nulls += 1
        elif hit and not include_inferred:
            if hit <= set(metric.admit_fields) and metric.admit(r):
                admitted += 1
                values.append(v)
            else:
                inferred += 1
        else:
            values.append(v)
    return {"group": group, "source": source, "records": len(pool), "values": values,
            "n": len(values), "excluded_null": nulls, "excluded_inferred": inferred,
            "excluded_undated": undated, "admitted_verdict_derived": admitted}


# -- one metric, two groups ------------------------------------------------


def _round(x: float | None, places: int = 4) -> float | None:
    return None if x is None else round(float(x), places)


def compare_metric(records, metric, a, b, *, since, min_n, include_inferred, seed) -> dict:
    ga = _collect(records, a, metric, since, include_inferred)
    gb = _collect(records, b, metric, since, include_inferred)
    out: dict = {
        "metric": metric.name, "scope": metric.scope, "source": ga["source"],
        "kind": metric.kind, "unit": metric.unit, "min_n": min_n, "groups": [],
        "enough": ga["n"] >= min_n and gb["n"] >= min_n, "tested": False,
        "difference": None, "p_value": None, "test": None,
    }
    for g in (ga, gb):
        row = {k: g[k] for k in ("group", "records", "n", "excluded_null",
                                  "excluded_inferred", "excluded_undated",
                                  "admitted_verdict_derived")}
        vals = g["values"]
        if metric.kind == "proportion":
            k = sum(1 for v in vals if v)
            row["successes"] = k
            row["rate"] = _round(k / len(vals)) if vals else None
            ci = stats.wilson(k, len(vals)) if vals else None
            row["ci95"] = [_round(ci[0]), _round(ci[1])] if ci else None
        else:
            row["median"] = _round(stats.median(vals)) if vals else None
            ci = stats.median_ci(vals) if vals else None
            row["ci95"] = [_round(ci[0]), _round(ci[1])] if ci else None
        out["groups"].append(row)
    if not out["enough"]:
        return out
    out["tested"] = True
    if metric.kind == "proportion":
        ka, kb = out["groups"][0]["successes"], out["groups"][1]["successes"]
        d, lo, hi = stats.newcombe_diff(ka, ga["n"], kb, gb["n"])
        out["difference"] = {"value": _round(d), "ci95": [_round(lo), _round(hi)],
                             "what": "rate A - rate B (Newcombe)"}
        out["p_value"] = _round(stats.fisher_exact(ka, ga["n"] - ka, kb, gb["n"] - kb), 6)
        out["test"] = "Fisher exact"
    else:
        d, lo, hi = stats.bootstrap_median_diff(ga["values"], gb["values"], seed=seed)
        out["difference"] = {"value": _round(d), "ci95": [_round(lo), _round(hi)],
                             "what": "median A - median B (seeded percentile bootstrap)"}
        out["p_value"] = _round(stats.mann_whitney(ga["values"], gb["values"])[1], 6)
        out["test"] = "Mann-Whitney U"
    return out


SESSION_CAVEAT = ("  caveat: sessions are not like-for-like with agent runs -- a session is a "
                  "whole conversation, a crew run is one agent's task.")


def _session_side(a: str, b: str) -> bool:
    return "session" in (a, b)


def compare(root, pairs=None, *, since: str | None = None, min_n: int = DEFAULT_MIN_N,
            include_inferred: bool = False, seed: int = 0) -> dict:
    records = agentlog.read(root)
    comparisons = []
    for a, b in pairs or DEFAULT_PAIRS:
        results = [compare_metric(records, m, a, b, since=since, min_n=min_n,
                                  include_inferred=include_inferred, seed=seed)
                   for m in METRICS]
        comparisons.append({"a": a, "b": b, "metrics": results,
                            "caveat": SESSION_CAVEAT.strip() if _session_side(a, b) else None,
                            "tested": sum(1 for r in results if r["tested"])})
    return {"since": since, "min_n": min_n, "include_inferred": include_inferred,
            "seed": seed, "records_read": len(records), "comparisons": comparisons}


# -- text ------------------------------------------------------------------


def _num(x, unit="", proportion=False) -> str:
    if x is None:
        return "-"
    if proportion:
        return f"{x * 100:.0f}%"
    text = f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}".rstrip("0").rstrip(".")
    return f"${text}" if unit == "$" else text


def _ci(row, unit, proportion=False) -> str:
    if not row["ci95"]:
        return "95% CI: n/a (n too small)"
    lo, hi = (_num(v, unit, proportion) for v in row["ci95"])
    return f"95% CI {lo}..{hi}"


def render(result: dict) -> str:
    lines = [
        "watermill agents compare",
        f"  records read: {result['records_read']} (latest line per key); "
        f"min n per group: {result['min_n']}"
        + (f"; since {result['since']}" if result["since"] else "")
        + ("; inferred values INCLUDED" if result["include_inferred"] else
           "; inferred and null values excluded per metric"),
        "  per-run metrics use source=transcript records, per-bead metrics use "
        "source=handoff records; the two are never mixed.",
    ]
    for comp in result["comparisons"]:
        lines.append("")
        if comp.get("caveat"):
            lines.append(SESSION_CAVEAT)
        lines += [f"=== A: {group_label(comp['a'])}   vs   B: {group_label(comp['b'])} ==="]
        scope = None
        for m in comp["metrics"]:
            if m["scope"] == "bead" and not all(g["records"] for g in m["groups"]):
                if scope != "bead":
                    scope = "bead"
                    empty = [tag for tag, g in zip("AB", m["groups"], strict=True)
                             if not g["records"]]
                    lines.append(
                        "  -- per bead (source=handoff): skipped -- no handoff records for "
                        f"group {' and '.join(empty)} (only mill-crew work has them) --")
                if (m["metric"] == "first_pass_approval_rate" and not result["include_inferred"]):
                    for tag, g in zip("AB", m["groups"], strict=True):
                        if g["records"]:
                            lines.append(
                                f"     ({tag}: first_pass_approval_rate would use n={g['n']}: "
                                f"admitted {g['admitted_verdict_derived']} with pushed-fixes "
                                f"from the verdict, excluded {g['excluded_inferred']} inferred, "
                                f"{g['excluded_null']} null)")
                continue
            if m["scope"] != scope:
                scope = m["scope"]
                lines.append(
                    "  -- per run (source=transcript) --" if scope == "run"
                    else "  -- per bead (source=handoff; first-pass approval = landed, "
                         "one Sluice round, no pushed fixes) --")
            prop = m["kind"] == "proportion"
            lines.append(f"  {m['metric']}")
            for tag, g in zip("AB", m["groups"], strict=True):
                stat = (f"{g['successes']}/{g['n']} = {_num(g['rate'], proportion=True)}"
                        if prop and g["n"] else f"median {_num(g.get('median'), m['unit'])}")
                if g["n"] == 0:
                    stat = "no usable values"
                excl = (f"excluded: {g['excluded_null']} null, "
                        f"{g['excluded_inferred']} inferred"
                        + (f", {g['excluded_undated']} undated" if g["excluded_undated"] else "")
                        + (f"; admitted {g['admitted_verdict_derived']} with pushed-fixes from "
                           "the verdict" if m["metric"] == "first_pass_approval_rate"
                           and not result["include_inferred"] else ""))
                lines.append(f"      {tag}  n={g['n']:<4} {stat}"
                             + (f"  {_ci(g, m['unit'], prop)}" if g["n"] else "")
                             + f"   [{g['records']} records; {excl}]")
            if m["metric"] == "cost_usd_est" and not result["include_inferred"]:
                lines.append("      (cost_usd_est is an ESTIMATE from model + tokens, so it is "
                             "inferred and excluded here; pass --include-inferred to compare it)")
            if m["tested"]:
                d = m["difference"]
                lo, hi = (_num(v, m["unit"], prop) for v in d["ci95"])
                lines.append(f"      A-B {_num(d['value'], m['unit'], prop)}  95% CI {lo}..{hi}  "
                             f"({d['what']})")
                na, nb = m["groups"][0]["n"], m["groups"][1]["n"]
                lines.append(f"      p = {m['p_value']:.4g}  ({m['test']}, n = {na} vs {nb})")
            else:
                na, nb = m["groups"][0]["n"], m["groups"][1]["n"]
                lines.append(f"      too few to say: n = {na} vs {nb}, "
                             f"need at least {m['min_n']} in each group")
        if comp["tested"] > MULTIPLE_WARNING_AFTER:
            lines.append(f"  WARNING: {comp['tested']} metrics were tested in this comparison; "
                         "no multiple-comparison correction is applied, so expect about one "
                         "p < 0.05 in twenty by chance alone.")
    return "\n".join(lines) + "\n"
