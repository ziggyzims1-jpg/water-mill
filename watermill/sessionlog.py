"""Claude Code transcripts as agents.jsonl records: metadata only.

`~/.claude/projects/<project>/<session>.jsonl` is a top-level session and
`<project>/<session>/subagents/agent-*.jsonl` (+ a sibling `.meta.json`) is one
subagent run. Both hold private conversations, and `runs/` is committed and
shipped, so the one hard rule here is:

    NOTHING that a person or a tool wrote ever reaches a record or a log line.

No message text, no tool input, no tool output. Records are built from an
explicit whitelist of numbers, timestamps, enums and ids (`_extract` is the only
function that reads a transcript line, and it returns counters, not content),
and every string that does get through passes `_clip`. The one free-text field
is `title`, and only a mill-crew run has one: its `.meta.json` `description`,
a label the orchestrator writes by convention ("Sluice: review PR #32 (a7z)"),
capped at TITLE_CAP. Sessions get no title (their `ai-title` summarises the
conversation) and neither do other subagents: their description is a model's
summary of a task in whatever project the owner was in, which is conversation
content by another name.

Two facts about real transcripts that synthetic fixtures got wrong:

* An assistant message is written once per content block, all sharing one
  `message.id`, with a *partial* `usage` that grows as the stream goes (output
  tokens 1 -> 237 in one real message). Summing lines multiplies the total by
  the block count; the right figure is the largest value per field per id.
  Likewise a `tool_use` block id is counted once.
* `agentType` is not only `millstone`: dispatch names it `millstone-ng1`,
  `sluice-69y-2`, ... so the crew test is on the part before the first hyphen.

Record shape (envelope in `agentlog`): `source` "transcript", `outcome` null
(a transcript does not say whether the work was good; the last message is not
evidence), `cost_usd` only from a session's own `cost-state` line, and a
subagent's `duration_seconds` as last minus first timestamp. `agent_kind` is
`session`, `mill-crew` (agentType millstone/bolter/sluice/tailrace) or
`subagent:<agentType>`.

`detail` (all kinds): `transcript` (path relative to the sessions dir),
`session_id`, `role` (millstone|bolter|sluice|tailrace|null), `model`, `models`,
`input_tokens`, `output_tokens`, `tokens_total` (input + output; cache reads
and writes are excluded, they are reported on their own),
`cache_creation_tokens`, `cache_read_tokens`, `cache_creation_5m_tokens` /
`cache_creation_1h_tokens` (the writes split by cache TTL, from
`usage.cache_creation`; null when no message carried the split),
`message_count` (distinct assistant messages), `tool_call_count`, `error_count`
(API error lines), `interrupted` (bool), `cwd_repo`, `agent_id`, `subagent_count`
(sessions), `crew_key` / `bead_hint` (mill-crew, see below). The estimate
`cost_usd_est` and `tokens_total_incl_cache` are NOT stored here: `agentlog.read`
derives them from these counters (see pricing).

* **`output_tokens` is only trustworthy for a message that has a line with a
  `stop_reason`** (water-mill-658, measured on 16 sessions / 201 subagent runs,
  counts only). A top-level session writes the final `usage` on every line of a
  message, so max-per-id is the true total (within 0-6% of the session's
  `cost-state` outputTokens, which also counts side calls). A subagent
  transcript is written live: the lines of a message grow 1 -> N, and 63% of
  its messages never get a line with `stop_reason` or the final `usage` at all
  (no later line, result, summary or sidecar carries the total: a subagent
  transcript holds only user/attachment/assistant lines). Those messages carry
  the first chunk (tens of tokens for thousands of characters of content), so a
  subagent's `output_tokens` is a FLOOR. `detail.output_messages_final` /
  `output_messages_partial` count the two kinds, `detail.output_tokens_floor` is
  true when more than PARTIAL_SHARE of the messages are partial, and then
  `detail.output_tokens` and `detail.tokens_total` are listed in
  `fields_inferred` (so `agents compare` excludes them by default; the cost
  estimate's output term is a floor too). Only the presence of `stop_reason` is
  read, never its value.

Crew subagents *link, they do not double-count*: the handoff-derived record
`crew:<bead>` stays the one record of the bead's outcome; the transcript record
for a role's run carries `detail.crew_key` pointing at it. Both have
`agent_kind == "mill-crew"`, so every reader filters on `source`: per-bead work
is `source == "handoff"`, per-run cost/tokens is `source == "transcript"` (one
per role run -- a bead has up to three plus re-reviews).

Linking prefers a missing link to a wrong one. A short id (`a7z`) is matched
within the run's own repo; it may match another project's bead only when the
run's cwd is not inside one repo (the workshop root, an ancestor of a known
checkout), and then only if exactly one bead has that suffix.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import agentlog, landed

SOURCE = "transcript"
TITLE_CAP = 60
SHORT_CAP = 80
DEFAULT_DIR = Path("~/.claude/projects")
CREW_ROLES = agentlog.CREW_ROLES
# A message whose every streamed line lacks `stop_reason` never had its final
# usage written, so its output_tokens is the first chunk (see the docstring). A
# run is a FLOOR when more than this share of its messages are like that; a
# session's last message may be cut off mid-stream, which is not a bias.
PARTIAL_SHARE = 0.05
# What a floor run lists in fields_inferred (recorded.build keeps these too).
FLOOR_FIELDS = ("detail.output_tokens", "detail.tokens_total")
_BEAD_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9.]+)+$")
_USAGE_FIELDS = (
    ("input_tokens", "input_tokens"),
    ("output_tokens", "output_tokens"),
    ("cache_creation_input_tokens", "cache_creation_tokens"),
    ("cache_read_input_tokens", "cache_read_tokens"),
)
# usage.cache_creation splits the writes by TTL (priced 1.25x vs 2x input).
_WRITE_SPLIT = (
    ("ephemeral_5m_input_tokens", "cache_creation_5m_tokens"),
    ("ephemeral_1h_input_tokens", "cache_creation_1h_tokens"),
)


def _clip(value, cap: int = SHORT_CAP) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = " ".join(value.split())
    return value if len(value) <= cap else value[: cap - 1] + "…"


def _seconds(start: str | None, end: str | None) -> float | None:
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return max(0.0, (b - a).total_seconds())


def _extract(path: Path) -> dict | None:
    """Counters and timestamps from one transcript; never any content."""
    messages: dict[str, dict[str, int]] = {}
    finished: set[str] = set()  # message ids with a line that carries a stop_reason
    models: Counter = Counter()
    tools: set[str] = set()
    times: list[str] = []
    cwd = None
    errors = 0
    interrupted = False
    cost = None
    lines = 0
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for raw in handle:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            lines += 1
            stamp = row.get("timestamp")
            if isinstance(stamp, str):
                times.append(stamp)
            if cwd is None and isinstance(row.get("cwd"), str):
                cwd = row["cwd"]
            kind = row.get("type")
            if kind == "cost-state":
                total = row.get("totalCostUSD")
                if isinstance(total, (int, float)) and not isinstance(total, bool):
                    cost = float(total)
            elif kind == "user":
                body = (row.get("message") or {}).get("content")
                if isinstance(body, list):
                    body = next(
                        (b.get("text") for b in body
                         if isinstance(b, dict) and b.get("type") == "text"), "")
                if isinstance(body, str) and body.startswith("[Request interrupted by user"):
                    interrupted = True
            elif kind == "assistant":
                if row.get("isApiErrorMessage"):
                    errors += 1
                msg = row.get("message") or {}
                model = msg.get("model")
                if not isinstance(model, str) or model.startswith("<"):
                    continue  # "<synthetic>" error stand-ins are not model output
                models[_clip(model) or "unknown"] += 1
                key = msg.get("id") or f"line-{lines}"
                usage = msg.get("usage") or {}
                best = messages.setdefault(key, {})
                if msg.get("stop_reason"):  # presence only; the value is never kept
                    finished.add(key)
                for src, dst in _USAGE_FIELDS:
                    n = usage.get(src)
                    if isinstance(n, int) and not isinstance(n, bool):
                        best[dst] = max(best.get(dst, 0), n)
                split = usage.get("cache_creation")
                if isinstance(split, dict):
                    for src, dst in _WRITE_SPLIT:
                        n = split.get(src)
                        if isinstance(n, int) and not isinstance(n, bool):
                            best[dst] = max(best.get(dst, 0), n)
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tools.add(str(block.get("id") or f"{key}-{len(tools)}"))
    if not lines:
        return None
    totals = {dst: sum(m.get(dst, 0) for m in messages.values()) for _, dst in _USAGE_FIELDS}
    for _, dst in _WRITE_SPLIT:  # null, not 0, when no message carried the split
        seen = [m[dst] for m in messages.values() if dst in m]
        totals[dst] = sum(seen) if seen else None
    partial = len(messages) - len(finished)
    return {
        **totals,
        "output_messages_final": len(finished),
        "output_messages_partial": partial,
        "output_tokens_floor": bool(messages) and partial / len(messages) > PARTIAL_SHARE,
        "tokens_total": totals["input_tokens"] + totals["output_tokens"],
        "message_count": len(messages),
        "tool_call_count": len(tools),
        "error_count": errors,
        "interrupted": interrupted,
        "models": sorted(models),
        "model": models.most_common(1)[0][0] if models else None,
        "cwd": cwd,
        "first": min(times) if times else None,
        "last": max(times) if times else None,
        "cost": cost,
    }


def repo_name(cwd: str | None, known: dict[str, Path] | None = None) -> str | None:
    """The repo a working directory belongs to; worktrees map to their repo."""
    if not cwd:
        return None
    path = Path(cwd)
    for name, checkout in (known or {}).items():
        try:
            path.relative_to(checkout)
            return name
        except ValueError:
            continue
    parts = path.parts
    if ".claude" in parts and "worktrees" in parts:
        parts = parts[: parts.index(".claude")]
    if "code" in parts and parts.index("code") + 1 < len(parts):
        return landed.normalise(parts[parts.index("code") + 1]) or None
    return landed.normalise(parts[-1]) if parts else None


def _role(agent_type: str | None) -> str | None:
    head = (agent_type or "").lower().split("-", 1)[0]
    return head if head in CREW_ROLES else None


_PR = re.compile(r"\bpr\s*#(\d+)", re.IGNORECASE)
_STRIP = "()[],.:;\"'`"


def _bead_hint(agent_type: str | None, description: str | None) -> str | None:
    """A bead id (or its short suffix) from the label, else from the agentType.

    Labels are free-ish ("Millstone: build water-mill-qam", "Sluice: review PR
    #32 (a7z)", "Millstone: bead 0fk"), so: a hyphenated token, else the word
    after "bead", else a parenthesised 3-5 character id. The hint is a short
    token, never the label.
    """
    words = [w.strip(_STRIP) for w in (description or "").lower().split()]
    for word in reversed(words):
        if _BEAD_TOKEN.match(word) and len(word) <= SHORT_CAP and word not in CREW_ROLES:
            return word
    for i, word in enumerate(words[:-1]):
        if word == "bead" and re.fullmatch(r"[a-z0-9.]{2,12}", words[i + 1]):
            return words[i + 1]
    for word in reversed((description or "").lower().split()):
        if word.startswith("(") and re.fullmatch(r"[a-z0-9.]{3,5}", word.strip(_STRIP)):
            return word.strip(_STRIP)
    label = (description or "").lower().split(":", 1)
    if len(label) == 2 and re.fullmatch(r"[a-z0-9]{3}(?:\.\d+)?", label[1].strip()):
        return label[1].strip()  # "Millstone: 6wo.7"
    parts = (agent_type or "").lower().split("-", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def _link(hint: str | None, repo: str | None, crew: list[dict],
          description: str | None = None, anchored: bool = True) -> dict | None:
    """The one handoff-derived crew record this label names, else None.

    By bead id (exact, then suffix within the repo's project), then by the
    "PR #n" the label names against the note's pr_number in the same project.
    Ambiguity links nothing, and a run `anchored` in one repo never links to
    another project's bead by suffix (bead `cheme-abc` must not land on
    `zimmy-life-tracker-abc` because cheme-solver is not registered).
    """
    if hint:
        exact = [r for r in crew if r.get("subject") == hint]
        if len(exact) == 1:
            return exact[0]
        tail = [r for r in crew if (r.get("subject") or "").endswith("-" + hint)]
        mine = [r for r in tail if r.get("project") == repo]
        if len(mine) == 1 or (not mine and not anchored and len(tail) == 1):
            return (mine or tail)[0]
    pr = _PR.search(description or "")
    if pr and repo:
        same = [
            r for r in crew
            if r.get("project") == repo
            and (r.get("detail") or {}).get("pr_number") == int(pr.group(1))
        ]
        if len(same) == 1:
            return same[0]
    return None


def _meta(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _record(
    path: Path, base: Path, *, key: str, agent_kind: str, project: str,
    stats: dict, title: str | None, subject: str | None,
    duration: float | None, cost: float | None, inferred: list[str], detail: dict,
) -> dict:
    if stats["output_tokens_floor"]:  # compare excludes these unless --include-inferred
        inferred = [*inferred, *FLOOR_FIELDS]
    return agentlog.make_record(
        key=key, agent_kind=agent_kind, source=SOURCE, project=project,
        subject=subject, title=title, outcome=None,
        started_at=stats["first"], ended_at=stats["last"],
        cost_usd=cost, duration_seconds=duration, fields_inferred=inferred,
        detail={
            "transcript": str(path.relative_to(base)),
            "model": stats["model"],
            "models": stats["models"],
            "input_tokens": stats["input_tokens"],
            "output_tokens": stats["output_tokens"],
            "tokens_total": stats["tokens_total"],
            "cache_creation_tokens": stats["cache_creation_tokens"],
            "cache_read_tokens": stats["cache_read_tokens"],
            "cache_creation_5m_tokens": stats["cache_creation_5m_tokens"],
            "cache_creation_1h_tokens": stats["cache_creation_1h_tokens"],
            "message_count": stats["message_count"],
            "output_messages_final": stats["output_messages_final"],
            "output_messages_partial": stats["output_messages_partial"],
            "output_tokens_floor": stats["output_tokens_floor"],
            "tool_call_count": stats["tool_call_count"],
            "error_count": stats["error_count"],
            "interrupted": stats["interrupted"],
            **detail,
        },
    )


def _session_record(transcript: Path, base: Path, stats: dict,
                    known: dict[str, Path] | None) -> dict:
    sid = transcript.stem
    repo = repo_name(stats["cwd"], known)
    subs = sorted((transcript.parent / sid / "subagents").glob("agent-*.jsonl"))
    return _record(
        transcript, base, key=f"session:{sid}", agent_kind="session",
        project=repo or transcript.parent.name, stats=stats, title=None,
        subject=None, duration=None, cost=stats["cost"], inferred=[],
        detail={"session_id": sid, "role": None, "cwd_repo": repo,
                "subagent_count": len(subs)},
    )


def _subagent_record(agent: Path, base: Path, stats: dict, crew: list[dict],
                     known: dict[str, Path] | None) -> dict:
    sid = agent.parent.parent.name
    meta = _meta(agent.with_suffix(".meta.json"))
    agent_type = _clip(meta.get("agentType")) or "unknown"
    role = _role(agent_type)
    repo = repo_name(stats["cwd"], known)
    inferred: list[str] = []
    subject = None
    detail = {"session_id": sid, "role": role, "cwd_repo": repo,
              "agent_id": agent.stem.removeprefix("agent-"),
              "agent_type": agent_type, "stopped_by_user": bool(meta.get("stoppedByUser"))}
    kind = f"subagent:{agent_type.lower()}"
    if role:
        kind = "mill-crew"
        hint = _bead_hint(agent_type, meta.get("description"))
        linked = _link(hint, repo, crew, meta.get("description"),
                       anchored=_anchored(stats["cwd"], known))
        detail["bead_hint"] = hint
        detail["crew_key"] = linked["key"] if linked else None
        if linked:
            subject = linked["subject"]
            repo = linked.get("project") or repo  # cwd is often just ~/code
            inferred += ["subject", "detail.crew_key"]
        elif hint:
            inferred.append("detail.bead_hint")
    stats["interrupted"] = stats["interrupted"] or detail["stopped_by_user"]
    return _record(
        agent, base, key=f"session:{sid}:{agent.stem}", agent_kind=kind,
        project=repo or agent.parents[2].name, stats=stats,
        title=_clip(meta.get("description"), TITLE_CAP) if role else None,
        subject=subject,
        duration=_seconds(stats["first"], stats["last"]), cost=None,
        inferred=inferred, detail=detail,
    )


def record_for(path: Path, base: Path, crew: list[dict] | None = None,
               known: dict[str, Path] | None = None) -> dict | None:
    """The transcript record of ONE transcript (a session or a subagent run).

    The same whitelist as `collect`; `agents record` calls it on the running
    agent's own transcript.
    """
    path = Path(path)
    stats = _extract(path)
    if stats is None:
        return None
    if path.parent.name == "subagents":
        return _subagent_record(path, base, stats, crew or [], known)
    return _session_record(path, base, stats, known)


def collect(
    sessions_dir: Path, crew: list[dict] | None = None,
    known: dict[str, Path] | None = None, settle_seconds: float = 0,
    now: float | None = None,
) -> list[dict]:
    """Records for every session and subagent under `sessions_dir`. Reads only."""
    import time
    base = Path(sessions_dir).expanduser()
    if not base.is_dir():
        return []
    crew = crew or []
    now = time.time() if now is None else now
    out: list[dict] = []
    for transcript in sorted(base.glob("*/*.jsonl")):
        stats = _extract(transcript)
        if stats is None or _unsettled(transcript, settle_seconds, now):
            continue
        out.append(_session_record(transcript, base, stats, known))
    for agent in sorted(base.glob("*/*/subagents/agent-*.jsonl")):
        stats = _extract(agent)
        if stats is None or _unsettled(agent, settle_seconds, now):
            continue
        out.append(_subagent_record(agent, base, stats, crew, known))
    return out


# -- finding the running agent's own transcript -----------------------------
#
# Proven empirically (2026-10-13, from inside a millstone subagent):
#   * CLAUDE_CODE_SESSION_ID holds the TOP-LEVEL session's id even inside a
#     subagent, so it locates the session, never the subagent.
#   * A subagent writes to <projects>/<dir>/<session>/subagents/agent-<id>.jsonl;
#     no environment variable names that <id>.
#   * A tool call is flushed to the transcript only AFTER it returns, so a
#     command cannot find itself by its own arguments -- but an EARLIER call can
#     be found. Hence `agents whoami` prints a random tag (it lands in this
#     agent's transcript as that call's output), and `agents record --run-tag`
#     finds the one transcript containing it. The search returns a path and
#     keeps nothing it read.
# Without a tag only a solo run is located: it is the top-level file the
# session id names, which nothing else shares. A crew role is NEVER located
# without a tag: two crew agents of one type routinely run side by side in one
# session, and "the one recently written file of that agentType" picks the
# wrong one whenever its owner sits in a long tool call. A record in the wrong
# file silently corrupts the numbers, so anything ambiguous is refused (exit 2,
# nothing written), never guessed.

TAG_PREFIX = "wm-run-"


class LocateError(Exception):
    """The running agent's transcript could not be pinned down.

    `refuse` is False only when there is no transcript to find here at all (no
    directory, or no file for this session -- a cloud container): the caller
    may then record its flags alone. Otherwise a transcript exists and the
    caller could not say which, and must write nothing.
    """

    def __init__(self, message: str, *, refuse: bool = True):
        super().__init__(message)
        self.refuse = refuse


def new_tag() -> str:
    import secrets
    return TAG_PREFIX + secrets.token_hex(6)


def _session_files(base: Path, session_id: str) -> list[Path]:
    files = sorted(base.glob(f"*/{session_id}.jsonl"))
    files += sorted(base.glob(f"*/{session_id}/subagents/agent-*.jsonl"))
    return files


def _contains(path: Path, needle: str) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return any(needle in line for line in handle)
    except OSError:
        return False


def locate_own(
    sessions_dir: Path, *, session_id: str | None, role: str | None = None,
    tag: str | None = None,
) -> Path:
    """The transcript file of the agent calling this, or LocateError."""
    base = Path(sessions_dir).expanduser()
    if not base.is_dir():
        raise LocateError(f"no transcript directory at {base}", refuse=False)
    if session_id:
        pool = _session_files(base, session_id)
        if not pool:
            raise LocateError(f"session {session_id} has no transcript under {base}",
                              refuse=False)
    else:
        pool = sorted(base.glob("*/*.jsonl")) + sorted(base.glob("*/*/subagents/agent-*.jsonl"))
    if tag:
        hits = [p for p in pool if _contains(p, tag)]
        if len(hits) == 1:
            return hits[0]
        raise LocateError(
            f"tag {tag} found in {len(hits)} transcripts (run `agents whoami` as an "
            "earlier, separate tool call in this same agent, then pass its output)")
    if role in ("solo", "orchestrator"):
        top = [p for p in pool if p.parent.name != "subagents"]
        if len(top) == 1:
            return top[0]
        raise LocateError("cannot tell which top-level session is this one; "
                          "pass --run-tag from `agents whoami`")
    raise LocateError(f"role {role or 'unset'} needs --run-tag from `agents whoami` "
                      "(only --role solo|orchestrator is located without one)")


def _anchored(cwd: str | None, known: dict[str, Path] | None) -> bool:
    """True when `cwd` sits inside one repo, not above the known checkouts."""
    if not cwd:
        return False
    here = Path(cwd)
    return not any(here in Path(checkout).parents for checkout in (known or {}).values())


def _unsettled(path: Path, settle_seconds: float, now: float) -> bool:
    """A transcript still being written would append a new line every sweep."""
    if settle_seconds <= 0:
        return False
    try:
        return now - path.stat().st_mtime < settle_seconds
    except OSError:
        return True
