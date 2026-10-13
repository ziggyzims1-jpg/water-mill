"""Estimated run cost from model + token counts. An estimate, never a bill.

`cost_usd` on a record stays "stated cost only" (a session's own cost line).
This module derives `detail.cost_usd_est` beside it, listed in `fields_inferred`,
so `agents compare` excludes it unless asked (`--include-inferred`).

Rates are USD per million tokens. Source: the Claude API reference (claude-api
skill, models table and prompt-caching economics) as cached 2026-10-06, taken
2026-10-13. Prices change: update RATES and AS_OF together, and the estimate
field is named "est" for that reason. Not every model is listed: a model absent
from the table gets NO estimate (null), never a guess. Haiku 5.5 is left out on
purpose (its price steps up above 100K-token prompts, and crew runs exceed that).

Assumptions that make this an estimate:
* cache writes are billed at the 5-minute-TTL rate (1.25x input); a 1-hour write
  (2x) cannot be told apart in the transcript counters;
* cache reads use each model's own rate (0.1x input generally; 0.05x on Opus 5.5;
  0.025x on Fable 5.1; Fable 5 is 0.1x), which dominate crew runs;
* all of a record's tokens are priced at one rate card, so a record whose
  `models` differ in price gets null rather than a blend.
"""

from __future__ import annotations

import re

AS_OF = "2026-10-13"
SOURCE = "Claude API reference (claude-api skill: models table, prompt-caching economics)"

# model -> (input, output, cache_write_5m, cache_read) USD per million tokens
RATES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 12.5, 0.25),
    "claude-fable-5": (10.0, 50.0, 12.5, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 6.25, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 2.5, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 3.75, 0.30),
}

_SUFFIX = re.compile(r"(\[[^\]]*\]|-\d{8})$")


def canonical(model: str | None) -> str | None:
    """`claude-opus-5-5[1m]` / `claude-opus-5-5-20261001` -> `claude-opus-5-5`."""
    if not isinstance(model, str):
        return None
    name = model.strip().lower()
    while _SUFFIX.search(name):
        name = _SUFFIX.sub("", name)
    return name or None


def _n(detail: dict, key: str) -> int | None:
    v = detail.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def tokens_total_incl_cache(detail: dict) -> int | None:
    parts = [_n(detail, k) for k in ("input_tokens", "output_tokens",
                                     "cache_creation_tokens", "cache_read_tokens")]
    return None if parts[0] is None or parts[1] is None else sum(p or 0 for p in parts)


def estimate_usd(detail: dict) -> float | None:
    """The estimate for a record's `detail`, or None when it cannot be priced."""
    names = detail.get("models") or [detail.get("model")]
    cards = {RATES.get(canonical(m) or "") for m in names}
    if len(cards) != 1 or None in cards:
        return None
    inp, out = _n(detail, "input_tokens"), _n(detail, "output_tokens")
    if inp is None or out is None:
        return None
    rate = next(iter(cards))
    cw, cr = _n(detail, "cache_creation_tokens") or 0, _n(detail, "cache_read_tokens") or 0
    return round((inp * rate[0] + out * rate[1] + cw * rate[2] + cr * rate[3]) / 1e6, 4)


def annotate(record: dict) -> dict:
    """Add tokens_total_incl_cache and cost_usd_est to `record` in place."""
    detail = record.setdefault("detail", {})
    detail.pop("cost_usd_est", None)
    total = tokens_total_incl_cache(detail)
    if total is None:
        return record
    detail["tokens_total_incl_cache"] = total
    est = estimate_usd(detail)
    detail["cost_usd_est"] = est
    inferred = set(record.get("fields_inferred") or [])
    if est is not None:
        inferred.add("detail.cost_usd_est")
    record["fields_inferred"] = sorted(inferred)
    return record
