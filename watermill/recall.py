"""The context graph, and the one way to ask it a question.

Everything this factory knows is already written down: `ledger.py` has the
runs, `tasklog.py` the tasks and their root causes, `knowledge.py` the findings
a person wrote by hand. What none of them had was a way for the thing actually
doing the work -- an agent, mid-task, in a cell it has never seen -- to ask
whether this has bitten anyone before.

This module builds those three sources into one graph of nodes and edges and
answers queries against it.

**It is queried, never loaded.** That is the whole design constraint and it is
about cost: this graph reaches an agent's context, and a context surface that
returns everything it has costs tokens on every task forever, gets worse as the
factory learns more, and is the reason a knowledge base ends up switched off.
So `search()` returns a handful of one-line hits under a hard character budget,
`detail()` opens exactly one of them, and the prompt itself carries no findings
at all -- only four lines saying the tool exists. Knowledge growing must make
the answers *better*, never bigger.

**The graph is derived, and rebuilt on every call.** The three sources are the
truth; nothing here is a cache to invalidate, because there is no cache. At the
scale this operates at -- hundreds of tasks, tens of findings -- building it in
memory is milliseconds, and an index would be a staleness bug bought with
nothing. The moment that stops being true, measure it before believing it.

**Provenance is carried, never flattened.** A finding a person judged, an
outcome the machine observed and a proposal an agent guessed are three
different things, and an answer that presents them identically is worse than no
answer. Proposals are quarantined outright: `search()` will not return one, so
an agent can never read its own guess back as though somebody had agreed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import knowledge, ledger, tasklog

#: Node kinds. `finding` is a human judgement, `task` a mechanical outcome,
#: `run` a night. Paths and cells are nodes so a query can be a filename.
FINDING = "finding"
TASK = "task"
RUN = "run"

#: Provenance tiers, in descending order of what an answer may claim.
#:
#: `REJECTED` is its own tier rather than a flavour of `PROPOSED` because the
#: two are read differently -- a proposal is waiting for a person, a rejection
#: has had one -- but they are searched identically: neither is ever returned.
#: Deriving the tier from anything other than the record's status is how the
#: quarantine leaked once already; see `build`.
JUDGED = "judged"
OBSERVED = "observed"
PROPOSED = "proposed"
REJECTED = "rejected"

#: The result budget. Small on purpose -- see the module docstring. A caller
#: may lower these, and `MAX_LIMIT` is the ceiling nobody can raise.
DEFAULT_LIMIT = 5
MAX_LIMIT = 20
LINE_CHARS = 200
BUDGET_CHARS = 1200

_WORD = re.compile(r"[a-z0-9_.\-/]+")
_SEPARATOR = re.compile(r"[./_\-]")
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
    "have", "how", "if", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "this", "to", "was", "were", "what", "when", "where", "which", "who", "why",
    "with", "you", "your",
})


@dataclass(frozen=True)
class Node:
    """One thing the factory knows about."""

    id: str
    kind: str
    cell: str
    text: str
    date: str
    provenance: str
    label: str = ""
    stale: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def tokens(self) -> frozenset[str]:
        return _tokenize(f"{self.text} {self.label} {self.cell} {_refs_text(self.meta)}")


@dataclass(frozen=True)
class Edge:
    src: str
    kind: str
    dst: str


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def by_id(self, node_id: str) -> Node | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def neighbours(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.src == node_id or e.dst == node_id]

    @property
    def cells(self) -> list[str]:
        return sorted({n.cell for n in self.nodes if n.cell})


@dataclass(frozen=True)
class Hit:
    node: Node
    score: float

    def line(self, width: int = LINE_CHARS) -> str:
        """One hit, on one line, under `width` characters."""
        head = f"{self.node.id}  [{self.node.label or self.node.kind}]"
        if self.node.cell:
            head += f" {self.node.cell}"
        head += f" {self.node.date}"
        flags = " (stale -- unconfirmed)" if self.node.stale else ""
        room = max(40, width - len(head) - len(flags) - 2)
        return f"{head}  {_clip(self.node.text, room)}{flags}"


@dataclass
class Answer:
    """What a query returns: a few lines, and an honest count of the rest."""

    query: str
    hits: list[Hit] = field(default_factory=list)
    matched: int = 0
    searched: int = 0
    total: int = 0
    note: str = ""

    @property
    def truncated(self) -> bool:
        return self.matched > len(self.hits)

    def render(self) -> str:
        if not self.hits:
            # Three different empty answers, because they mean three different
            # things and only one of them is "nobody knows". Collapsing them
            # told an agent the factory was new when in fact it was looking in
            # the wrong cell.
            if not self.total:
                return "Nothing has been recorded yet. This is a new factory, not a quiet one."
            if not self.searched:
                return (
                    f"Nothing recorded for this scope, though {self.total} items exist "
                    "elsewhere. Try scope 'everywhere'."
                )
            return f"No match in {self.searched} recorded items. Nothing is known about this."
        lines = [h.line() for h in self.hits]
        if self.truncated:
            lines.append(
                f"... {self.matched - len(self.hits)} more match. Narrow the query, "
                "or open one with detail(id)."
            )
        if self.note:
            lines.append(self.note)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "hits": [
                {
                    "id": h.node.id,
                    "kind": h.node.kind,
                    "label": h.node.label,
                    "cell": h.node.cell,
                    "date": h.node.date,
                    "provenance": h.node.provenance,
                    "stale": h.node.stale,
                    "text": _clip(h.node.text, LINE_CHARS),
                }
                for h in self.hits
            ],
            "matched": self.matched,
            "searched": self.searched,
            "total": self.total,
            "truncated": self.truncated,
        }


# -- building --------------------------------------------------------------


def build(root: Path, as_of: date | None = None) -> Graph:
    """Assemble the graph from the three append-only sources.

    Superseded findings are carried as nodes so that looking one up by id says
    what replaced it, and excluded from search by `_searchable`. A finding that
    vanishes when it stops being true takes the reason with it.
    """
    graph = Graph()
    seen_cells: set[str] = set()

    for record in knowledge.read(root, include_superseded=True):
        status = record.status
        # Every status that is not a person's standing judgement gets its own
        # tier. Written as a mapping rather than as `PROPOSED if ... else
        # JUDGED`, which is what this was: that spelling made *rejected* the
        # one status it did not name, so rejecting a proposal promoted it --
        # out of quarantine and into `search` labelled as a human judgement,
        # which is the exact opposite of what the person deciding asked for.
        provenance = {
            knowledge.PROPOSED: PROPOSED,
            knowledge.REJECTED: REJECTED,
        }.get(status, JUDGED)
        graph.nodes.append(
            Node(
                id=record.id,
                kind=FINDING,
                cell=record.cell,
                text=record.text,
                date=record.observed_at,
                provenance=provenance,
                label=record.kind,
                stale=record.is_stale(as_of),
                meta={
                    "status": status,
                    "detail": record.detail,
                    "destination": record.destination,
                    "root_cause": record.root_cause,
                    "tags": record.tags,
                    "refs": record.refs,
                    "confirmed_at": record.confirmed_at,
                    "superseded_by": record.superseded_by,
                    "author": record.author,
                    "age_days": record.age_days(as_of),
                },
            )
        )
        if record.cell:
            seen_cells.add(record.cell)
        if record.superseded_by:
            graph.edges.append(Edge(record.id, "superseded_by", record.superseded_by))
        for task_id in record.refs.get("tasks", []):
            graph.edges.append(Edge(record.id, "about", _task_node_id(record.cell, task_id)))
        for run_id in record.refs.get("runs", []):
            graph.edges.append(Edge(record.id, "from_run", run_id))
        for path in record.refs.get("paths", []):
            graph.edges.append(Edge(record.id, "touches", path))
        for cell in record.refs.get("cells", []):
            graph.edges.append(Edge(record.id, "also_in", cell))

    for record in tasklog.read(root):
        row = record.outcome
        cell = str(row.get("project", ""))
        task_id = str(row.get("task_id", ""))
        node_id = _task_node_id(cell, task_id)
        outcome = str(row.get("outcome", ""))
        text = " -- ".join(
            part for part in (
                str(row.get("title", "")),
                str(row.get("reason", "")),
                f"root cause: {record.root_cause}" if record.root_cause else "",
                record.note,
            ) if part
        )
        graph.nodes.append(
            Node(
                id=node_id,
                kind=TASK,
                cell=cell,
                text=text or task_id,
                date=str(row.get("recorded_at", ""))[:10],
                provenance=OBSERVED,
                label=outcome,
                meta={
                    "task_id": task_id,
                    "run_id": row.get("run_id", ""),
                    "commit": row.get("commit", ""),
                    "root_cause": record.root_cause,
                    "hint": row.get("hint", ""),
                    "cost_cents": row.get("cost_cents"),
                },
            )
        )
        if cell:
            seen_cells.add(cell)
        if row.get("run_id"):
            graph.edges.append(Edge(node_id, "in_run", str(row["run_id"])))

    for row in ledger.read(root):
        run_id = str(row.get("run_id", ""))
        if not run_id:
            continue
        cell = str(row.get("project", ""))
        graph.nodes.append(
            Node(
                id=run_id,
                kind=RUN,
                cell=cell,
                text=(
                    f"kept {row.get('completed', 0)}, discarded {row.get('failed', 0)}, "
                    f"escalated {row.get('escalated', 0)}"
                    + (f" -- halted: {row.get('halt_reason')}" if row.get("halt_reason") else "")
                ),
                date=str(row.get("started_at", ""))[:10],
                provenance=OBSERVED,
                label="run",
                meta={"refused": row.get("refused"), "spend_cents": row.get("spend_cents")},
            )
        )
        if cell:
            seen_cells.add(cell)

    return graph


# -- querying --------------------------------------------------------------


def search(
    graph: Graph,
    query: str,
    *,
    cell: str = "",
    kinds: tuple[str, ...] = (),
    since: str = "",
    cause: str = "",
    limit: int = DEFAULT_LIMIT,
    budget_chars: int = BUDGET_CHARS,
    include_proposed: bool = False,
) -> Answer:
    """The one read an agent makes. Ranked, filtered, and budgeted.

    Three things are enforced here rather than left to callers, because a
    caller that forgets any of them is a caller that quietly costs tokens or
    leaks a guess:

    * a **proposal is never returned** unless a person's tool asked for it;
    * `limit` is capped at `MAX_LIMIT` whatever was passed;
    * the rendered result stops at `budget_chars`, and says how many it left.

    `since` and `cause` are structured filters, and they are here rather than
    in the agent's tool schema on purpose. Free text is the right query surface
    for somebody with a problem in front of them; a date window and a
    root-cause bucket are what somebody *auditing* the graph wants, and every
    parameter added to the tool is paid for in the prompt on every task. What
    agents actually reach for is a measurement (`usage.py`), not a guess --
    a filter earns its place in the tool schema once the log shows the
    questions being asked in words instead.
    """
    pool = [n for n in graph.nodes if _searchable(n, include_proposed)]
    total = len(pool)
    if cell:
        pool = [n for n in pool if n.cell == cell or not n.cell]
    if kinds:
        pool = [n for n in pool if n.kind in kinds]
    if since:
        pool = [n for n in pool if n.date >= since]
    if cause:
        pool = [n for n in pool if n.meta.get("root_cause") == cause]

    terms = _tokenize(query)
    idf = _idf(pool)
    scored: list[Hit] = []
    for node in pool:
        score = _score(node, terms, idf, cell)
        if score > 0:
            scored.append(Hit(node=node, score=score))

    # Deterministic: score, then the more recent, then the id. Two answers to
    # the same question on the same data must be the same answer. Two stable
    # sorts rather than one clever key -- the second is the tie-break, and a
    # string cannot be negated the way a score can.
    scored.sort(key=lambda h: (h.node.date, h.node.id), reverse=True)
    scored.sort(key=lambda h: -h.score)

    kept: list[Hit] = []
    spent = 0
    for hit in scored[: max(1, min(limit, MAX_LIMIT))]:
        line = hit.line()
        if kept and spent + len(line) > budget_chars:
            break
        kept.append(hit)
        spent += len(line)

    return Answer(
        query=query, hits=kept, matched=len(scored), searched=len(pool), total=total
    )


def detail(graph: Graph, node_id: str, budget_chars: int = 2000) -> str:
    """Open exactly one node. The only place long text is ever returned.

    A superseded finding answers with what replaced it rather than with
    nothing: somebody arriving with an old id has to be told the belief moved,
    or they will conclude the factory never knew it.
    """
    node = graph.by_id(node_id)
    if node is None:
        return f"No such id: {node_id}"

    lines = [f"{node.id}  [{node.label or node.kind}] {node.cell} {node.date}".rstrip()]
    lines.append(f"provenance: {node.provenance}")
    if node.provenance == REJECTED:
        # Reachable with an id from a sweep or a commit message. Saying nothing
        # would render a rejected guess as ordinary text under an id, which is
        # the shape somebody trusts.
        lines.append("REJECTED: a person looked at this and did not agree with it.")
    elif node.provenance == PROPOSED:
        lines.append("PROPOSED: an agent's guess, not yet reviewed by anybody.")
    if node.stale:
        age = node.meta.get("age_days")
        lines.append(
            f"STALE: nobody has confirmed this in {age} days. Weigh it accordingly."
        )
    superseded_by = node.meta.get("superseded_by")
    if superseded_by:
        replacement = graph.by_id(str(superseded_by))
        lines.append(f"SUPERSEDED by {superseded_by}. This is no longer current.")
        if replacement is not None:
            lines.append(f"  now: {_clip(replacement.text, 300)}")
    lines.append("")
    lines.append(_clip(node.text, 600))
    body = str(node.meta.get("detail", ""))
    if body:
        lines.append("")
        lines.append(_clip(body, 900))
    if node.meta.get("destination"):
        lines.append("")
        lines.append(f"mechanised as: {node.meta['destination']}")
    refs = node.meta.get("refs") or {}
    if refs:
        lines.append("refs: " + "; ".join(f"{k}: {', '.join(v[:6])}" for k, v in refs.items()))
    related = [e for e in graph.neighbours(node.id) if e.kind != "superseded_by"]
    if related:
        lines.append(
            "related: " + ", ".join(sorted({_other(e, node.id) for e in related})[:8])
        )
    return _clip("\n".join(lines), budget_chars)


def promotable(graph: Graph) -> list[tuple[str, list[Node]]]:
    """Lessons that have now appeared in two cells.

    Water Mill's filing rule -- a lesson is promoted when it has been seen
    twice, in two repositories -- has until now been enforced by memory. It is
    a graph query: findings whose text overlaps strongly and whose cells
    differ. Reported, never promoted automatically; the promotion is an edit to
    this repository's own doctrine and that is a person's to make.
    """
    findings = [
        n for n in graph.nodes
        if n.kind == FINDING and n.provenance == JUDGED and not n.meta.get("superseded_by")
    ]
    groups: list[tuple[str, list[Node]]] = []
    used: set[str] = set()
    for index, node in enumerate(findings):
        if node.id in used:
            continue
        cluster = [node]
        for other in findings[index + 1:]:
            if other.id in used or other.cell == node.cell:
                continue
            if _overlap(node.tokens, other.tokens) >= 0.5:
                cluster.append(other)
        if len({n.cell for n in cluster if n.cell}) >= 2:
            for member in cluster:
                used.add(member.id)
            groups.append((node.text, cluster))
    return groups


def unmechanised(graph: Graph) -> list[Node]:
    """Active lessons that never became a gate check or a fence path.

    A lesson in prose is a suggestion; the same lesson in the gate cannot be
    ignored. Advice that has survived a sweep and is still only advice is the
    most common way knowledge here decays, so the sweep names it every month
    until somebody either mechanises it or says why it cannot be.
    """
    return [
        n for n in graph.nodes
        if n.kind == FINDING
        and n.label == "lesson"
        and n.provenance == JUDGED
        and not n.meta.get("destination")
        and not n.meta.get("superseded_by")
    ]


def missing_structure(graph: Graph) -> list[Node]:
    """Active findings still lacking a root cause or a tag after annotations merge."""
    return [
        n for n in graph.nodes
        if n.kind == FINDING
        and n.provenance == JUDGED
        and not n.meta.get("superseded_by")
        and not (
            n.meta.get("root_cause") not in ("", None, knowledge.PENDING_CAUSE)
            and n.meta.get("tags")
        )
    ]


def proposals(graph: Graph) -> list[Node]:
    """Agent proposals still waiting on a person. Never returned by search."""
    return [n for n in graph.nodes if n.provenance == PROPOSED]


def stale(graph: Graph) -> list[Node]:
    """Active findings nobody has vouched for inside the review window."""
    return [
        n for n in graph.nodes
        if n.kind == FINDING and n.provenance == JUDGED
        and n.stale and not n.meta.get("superseded_by")
    ]


# -- internals -------------------------------------------------------------


def _searchable(node: Node, include_proposed: bool) -> bool:
    if node.meta.get("superseded_by"):
        return False
    if node.provenance == REJECTED:
        # Not even for `--include-proposed`, which is a person asking to see
        # what is *waiting* on them. A rejection is a decision already taken,
        # and re-surfacing it is asking the same question twice.
        return False
    return include_proposed or node.provenance != PROPOSED


def _score(node: Node, terms: frozenset[str], idf: dict[str, float], cell: str) -> float:
    hits = terms & node.tokens
    if not hits:
        return 0.0
    score = sum(idf.get(term, 1.0) for term in hits)
    # A human judgement outranks a mechanical outcome at equal relevance: the
    # outcome says a gate failed, the finding says why it keeps failing.
    if node.kind == FINDING:
        score *= 1.4
    if cell and node.cell == cell:
        score *= 1.5
    # A path named in a finding's refs is a strong signal -- an agent about to
    # edit `db.py` asking "db.py" wants exactly those.
    if terms & _tokenize(_refs_text(node.meta)):
        score *= 1.6
    if node.stale:
        # Weighed down, never hidden. A stale finding may be the only thing
        # anybody knows about this, and it is labelled when it is returned.
        score *= 0.7
    return score


def _idf(nodes: list[Node]) -> dict[str, float]:
    """Rarer words count for more. Without this every query matches every gate."""
    total = len(nodes) or 1
    counts: dict[str, int] = {}
    for node in nodes:
        for token in node.tokens:
            counts[token] = counts.get(token, 0) + 1
    return {token: 1.0 + (total / (1 + count)) ** 0.5 for token, count in counts.items()}


@lru_cache(maxsize=8192)
def _tokenize(text: str) -> frozenset[str]:
    """Words, with their punctuation stripped and their paths broken up.

    Two details earn their place. Trailing punctuation is stripped, because
    `migrations.` at the end of a sentence and `migrations` in a query are the
    same word and the first version of this matched neither against the other.
    And a path contributes its parts as well as itself, so an agent asking
    about `db` finds a finding about `db.py` -- while the whole token survives,
    so an exact path match still scores as the stronger signal.
    """
    words: set[str] = set()
    for raw in _WORD.findall((text or "").lower()):
        word = raw.strip("._-/")
        if len(word) < 2 or word in _STOP:
            continue
        words.add(word)
        for part in _SEPARATOR.split(word):
            if len(part) > 2 and part not in _STOP:
                words.add(part)
    return frozenset(words)


def _refs_text(meta: dict) -> str:
    refs = meta.get("refs") or {}
    return " ".join(" ".join(values) for values in refs.values() if isinstance(values, list))


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _task_node_id(cell: str, task_id: str) -> str:
    return f"{cell}:{task_id}" if cell else task_id


def _other(edge: Edge, node_id: str) -> str:
    return edge.dst if edge.src == node_id else edge.src


def _clip(text: str, width: int) -> str:
    text = " ".join((text or "").split()) if "\n" not in (text or "") else (text or "")
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."
