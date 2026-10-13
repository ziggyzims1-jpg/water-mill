"""API-equivalent cost estimate from model + token counts. An estimate, never a bill.

On a Claude subscription nothing is billed per token: `cost_usd_est` is what the
same tokens would cost at Anthropic's first-party API list prices. It is useful
for comparing runs with each other, not for reconciling a bill.

`cost_usd` on a record stays "stated cost only" (a session's own cost line).
This module derives `detail.cost_usd_est` beside it, listed in `fields_inferred`,
so `agents compare` excludes it unless asked (`--include-inferred`).

DERIVED AT READ TIME, NOT STORED. `agentlog.read()` calls `annotate()` on every
record it returns, so the estimate always reflects THIS table: an older line
(recorded before the table existed, or under older prices) is priced the same
way as a new one, and a price change is one edit here, not a re-sweep. Writers
(`sessionlog`, `recorded`) store only the raw counters. A stored
`cost_usd_est` on an old line is ignored and recomputed.

Rates are USD per million tokens. Source: the Claude API reference (claude-api
skill: models table, shared/models.md and shared/prompt-caching.md "Economics"),
cached 2026-10-06, taken 2026-10-13; the pricing page itself is
https://platform.claude.com/docs/en/about-claude/pricing. Prices change: update
RATES and AS_OF together. A model absent from the table gets NO estimate (null),
never a guess. Haiku 5.5 is left out on purpose: its price steps up above
100K-token prompts and only per-request prompt sizes (not kept) could tell.

Cache writes are priced by TTL: 1.25x input for a 5-minute write, 2x for a
1-hour write (the published multipliers, the same on every model). Claude Code
transcripts carry the split per message (`usage.cache_creation.
ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`), which sessionlog
keeps as `cache_creation_5m_tokens` / `cache_creation_1h_tokens`. Write tokens
the split does not cover (an older record, a transcript without the split) are
priced at the TTL Claude Code uses for that kind of run: 1 hour for a top-level
session (agent_kind "session"), 5 minutes for a subagent. That is not a guess:
over every transcript on the owner's machine on 2026-10-13, top-level sessions
wrote 9.3 M cache tokens, all 1h, and subagents 33.3 M, all 5m (settings
`promptCacheTtl` / `subagentPromptCacheTtl`).

Other assumptions:
* cache reads use each model's own rate (0.1x input generally; 0.05x on Opus 5.5;
  0.025x on Fable 5.1), and Fable 5 is 0.1x ($1.00);
* standard speed and tier: no fast-mode or batch pricing (no crew transcript on
  2026-10-13 carried `usage.speed` other than "standard");
* all of a record's tokens are priced at one rate card, so a record whose
  `models` differ in price gets null rather than a blend (1 of 16 top-level
  sessions and 0 of 198 subagent runs on 2026-10-13).
"""

from __future__ import annotations

import re

AS_OF = "2026-10-13"
SOURCE = "Claude API reference (claude-api skill: models table, prompt-caching economics)"
BASIS = "API-equivalent estimate at list prices, not a bill"

WRITE_5M = 1.25  # x input, cache write with the 5-minute TTL
WRITE_1H = 2.0   # x input, cache write with the 1-hour TTL

# model -> (input, output, cache_read) USD per million tokens
RATES: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
}

DERIVED = ("cost_usd_est", "cost_usd_est_as_of", "tokens_total_incl_cache")

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


def write_split(detail: dict, agent_kind: str | None) -> tuple[int, int]:
    """(5-minute, 1-hour) cache-write tokens; the unsplit rest by the kind's TTL."""
    total = _n(detail, "cache_creation_tokens") or 0
    w5 = _n(detail, "cache_creation_5m_tokens") or 0
    w1 = _n(detail, "cache_creation_1h_tokens") or 0
    rest = max(0, total - w5 - w1)
    if agent_kind == "session":
        w1 += rest
    else:
        w5 += rest
    return w5, w1


def estimate_usd(detail: dict, agent_kind: str | None = None) -> float | None:
    """The estimate for a record's `detail`, or None when it cannot be priced."""
    names = detail.get("models") or [detail.get("model")]
    cards = {RATES.get(canonical(m) or "") for m in names}
    if len(cards) != 1 or None in cards:
        return None
    inp, out = _n(detail, "input_tokens"), _n(detail, "output_tokens")
    if inp is None or out is None:
        return None
    rin, rout, rread = next(iter(cards))
    w5, w1 = write_split(detail, agent_kind)
    cr = _n(detail, "cache_read_tokens") or 0
    usd = inp * rin + out * rout + w5 * rin * WRITE_5M + w1 * rin * WRITE_1H + cr * rread
    return round(usd / 1e6, 4)


def annotate(record: dict) -> dict:
    """(Re)derive tokens_total_incl_cache and cost_usd_est on `record`, in place."""
    detail = record.setdefault("detail", {})
    for key in DERIVED:
        detail.pop(key, None)
    inferred = set(record.get("fields_inferred") or [])
    inferred.discard("detail.cost_usd_est")
    total = tokens_total_incl_cache(detail)
    if total is not None:
        detail["tokens_total_incl_cache"] = total
        est = estimate_usd(detail, record.get("agent_kind"))
        detail["cost_usd_est"] = est
        if est is not None:
            detail["cost_usd_est_as_of"] = AS_OF
            inferred.add("detail.cost_usd_est")
    record["fields_inferred"] = sorted(inferred)
    return record
