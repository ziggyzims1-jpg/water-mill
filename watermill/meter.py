"""Reading a cost and a verdict out of whatever the agent printed.

There is no API that answers "what has this run spent tonight", so the only
number available is the one each agent invocation reports about itself. The
agent runs with `--output-format json` and this module splits that into a
readable transcript and a cost in cents.

Two properties follow from the number's provenance, and both are load-bearing:

**It counts what the agent reports.** If that number is wrong, so is this one.
Nothing here can detect an under-report; a provider-side budget is the only
thing that can, and setting one as a second backstop costs nothing.

**An unparseable transcript reports no cost, and that is signal.** A crashed
agent writes no JSON. Returning zero would be a lie in the direction that lets
a run continue; returning None lets `caps.check` halt after a few of them,
because a run with no meter looks cheap right up until the invoice.

Field names are read through a tolerant accessor rather than by index. This is
someone else's output format and it will be renamed; a rename should make the
meter read *less* -- a countable, haltable None -- rather than raise.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: Candidate keys for the total cost, most specific first.
_COST_KEYS = ("total_cost_usd", "cost_usd", "total_cost", "usd_cost")
#: Candidate keys for the agent's final text.
_TEXT_KEYS = ("result", "text", "output", "content", "message")
#: Candidate keys for a self-reported failure.
_ERROR_KEYS = ("is_error", "error")

ESCALATION_MARKER = "ESCALATE"


@dataclass(frozen=True)
class Reading:
    """One agent invocation, as the meter understands it."""

    #: None means the agent reported nothing parseable -- see `caps.max_unmetered_tasks`.
    cost_cents: int | None
    text: str
    reported_error: bool
    parsed: bool

    @property
    def escalated(self) -> bool:
        """True when the agent stopped and asked for a judgement call.

        Matched at a line start so that an agent *describing* escalation in
        prose -- "I considered whether to ESCALATE here" -- does not read as
        one. The prompt asks for the word on its own line for this reason.
        """
        return bool(re.search(rf"^\s*{ESCALATION_MARKER}\b", self.text, re.MULTILINE))


def _first(obj: dict, keys) -> object | None:
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _to_cents(value: object) -> int | None:
    try:
        dollars = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if dollars < 0:
        return None
    # Rounded up: a run should never be told it spent less than it did.
    return int(dollars * 100 + 0.5)


def _candidate_objects(raw: str):
    """Yield every JSON object in the output, whole-document form first.

    `--output-format json` emits one object; `stream-json` emits one per line
    and the totals arrive on the last. Supporting both means the meter does not
    break the day someone changes the flag for a better transcript.
    """
    text = raw.strip()
    if not text:
        return
    try:
        whole = json.loads(text)
    except (ValueError, TypeError):
        pass
    else:
        if isinstance(whole, dict):
            yield whole
            return
        if isinstance(whole, list):
            for item in reversed(whole):
                if isinstance(item, dict):
                    yield item
            return
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            yield obj


def read(raw: str) -> Reading:
    """Parse an agent transcript into a cost, its text, and whether it failed."""
    cost: int | None = None
    text = ""
    reported_error = False
    parsed = False

    for obj in _candidate_objects(raw):
        parsed = True
        if cost is None:
            cost = _to_cents(_first(obj, _COST_KEYS))
        if not text:
            value = _first(obj, _TEXT_KEYS)
            if isinstance(value, str):
                text = value
            elif isinstance(value, list):
                # stream-json content blocks: [{"type": "text", "text": "..."}]
                parts = [
                    part.get("text", "")
                    for part in value
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ]
                text = "\n".join(p for p in parts if p)
        if not reported_error:
            reported_error = bool(_first(obj, _ERROR_KEYS))
        if cost is not None and text:
            break

    if not parsed:
        # Not JSON at all. Keep the raw output as the text so an escalation
        # written by a plain-text agent is still seen, but report no cost.
        text = raw

    return Reading(cost_cents=cost, text=text, reported_error=reported_error, parsed=parsed)
