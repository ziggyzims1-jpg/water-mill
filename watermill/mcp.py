"""The context graph as a tool an agent can call, mid-task.

Everything else in this package runs *around* an agent: preflight before,
verification after. This is the one seam that runs *during*, and it exists
because the moment an agent needs to know whether something has burned this
project before is the moment it has the file open -- not twenty minutes
earlier, when the prompt was assembled.

A stdio JSON-RPC server, spoken to over the Model Context Protocol, started by
the engine as a child of the agent process. No dependencies, no network, no
port: it reads the same three append-only files everything else here reads.

Four properties are deliberate, and each of them is a thing that would
otherwise go wrong:

**It cannot hang a night.** Every call is a local file read. `land` and `ship`
were kept off the run loop because they talk to somebody else's service; this
one is *on* the run loop, which is only acceptable because there is nothing on
the other end of it to be slow.

**It is queried, never dumped.** `recall` returns a few one-line hits under a
character budget and says how many it left. An agent that wants more asks a
better question or opens one hit with `detail`. A tool that returns everything
it knows is a tool whose cost grows with the factory's memory, which is exactly
backwards.

**Provenance is stamped by the orchestrator, not claimed by the caller.** The
cell, the run and the task come from the command line the engine built. An
agent cannot file a finding against another project, or against a run that
never happened, because it is never asked which one it is in.

**A written finding is quarantined.** `propose` appends, and nothing it appends
is ever returned to another agent until a person promotes it in the monthly
sweep. That is the same boundary the task log draws between a machine's `hint`
and a person's annotation, and it is enforced in `recall.search`, where it can
be tested.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from . import knowledge, recall, usage

#: The protocol version spoken when a client does not name one.
DEFAULT_PROTOCOL = "2024-11-05"

SERVER_NAME = "watermill"

#: Tool descriptions are paid for in the agent's context on every single task,
#: so they are as short as they can be while still saying when to call them.
TOOLS = [
    {
        "name": "recall",
        "description": (
            "Search what this factory has learned across every project: past "
            "failures, root causes, and findings written by hand. Call it before "
            "changing an unfamiliar file, when a gate fails for a reason you do "
            "not recognise, or when a spec seems to assume something. Returns a "
            "few one-line hits, newest and most relevant first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Words, an error message, or a file path.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["this-project", "everywhere"],
                    "description": "Default this-project.",
                },
                "limit": {"type": "integer", "description": "1-20, default 5."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "detail",
        "description": (
            "Open one result from recall by its id, for the full text and what "
            "it is linked to. Use it on at most one or two hits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "propose",
        "description": (
            "Record something this task taught you that the next agent would "
            "want: a trap in this codebase, a wrong assumption in the spec, a "
            "thing that worked. It is held for human review and is not visible "
            "to anyone else until then. One sentence. Do not use it for what "
            "you did -- that is the handoff."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "One sentence."},
                "kind": {
                    "type": "string",
                    "enum": sorted(knowledge.KINDS),
                    "description": "Default lesson.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files this is about, if any.",
                },
                "detail": {"type": "string", "description": "Optional, a short paragraph."},
            },
            "required": ["text"],
        },
    },
]


@dataclass
class Server:
    """One MCP session. Holds the provenance the engine stamped on it."""

    root: Path
    cell: str = ""
    run_id: str = ""
    task_id: str = ""
    read_only: bool = False

    def tools(self) -> list[dict]:
        return [t for t in TOOLS if not (self.read_only and t["name"] == "propose")]

    # -- the three tools ---------------------------------------------------

    def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Dispatch one tool call. Returns the text and whether it is an error.

        A tool that raises kills the agent's turn, so every failure here comes
        back as text the agent can read and carry on from. The graph being
        unreadable is a reason to work without it, never a reason to stop.
        """
        try:
            if name == "recall":
                return self._recall(arguments), False
            if name == "detail":
                return self._detail(arguments), False
            if name == "propose":
                return self._propose(arguments)
        except Exception as exc:  # pragma: no cover - defensive, see docstring
            return f"The knowledge store could not be read ({exc}). Carry on without it.", True
        return f"No such tool: {name}", True

    def _log(self, tool: str, **fields) -> None:
        usage.record(
            self.root, tool=tool, cell=self.cell,
            run_id=self.run_id, task_id=self.task_id, **fields,
        )

    def _recall(self, arguments: dict) -> str:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return "recall needs a query."
        scope = str(arguments.get("scope", "this-project"))
        limit = arguments.get("limit", recall.DEFAULT_LIMIT)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = recall.DEFAULT_LIMIT
        graph = recall.build(self.root)
        answer = recall.search(
            graph,
            query,
            cell=self.cell if scope != "everywhere" else "",
            limit=limit,
        )
        # Recorded whatever the answer was, and an empty one above all: the
        # questions this graph could not answer are the list of findings worth
        # writing next, in the agent's own words.
        self._log(
            "recall", query=query, hits=len(answer.hits),
            matched=answer.matched, total=answer.total,
        )
        return answer.render()

    def _detail(self, arguments: dict) -> str:
        node_id = str(arguments.get("id", "")).strip()
        if not node_id:
            return "detail needs an id from a recall result."
        self._log("detail", query=node_id)
        return recall.detail(recall.build(self.root), node_id)

    def _propose(self, arguments: dict) -> tuple[str, bool]:
        if self.read_only:
            return "This session cannot record findings.", True
        text = str(arguments.get("text", "")).strip()
        if not text:
            return "propose needs one sentence of text.", True
        kind = str(arguments.get("kind") or "lesson")
        if kind not in knowledge.KINDS:
            kind = "lesson"
        paths = arguments.get("paths") or []
        try:
            line = knowledge.propose(
                self.root,
                cell=self.cell,
                kind=kind,
                text=text,
                detail=str(arguments.get("detail", "")),
                refs={"paths": paths, "tasks": [self.task_id] if self.task_id else [],
                      "runs": [self.run_id] if self.run_id else []},
                source_run=self.run_id,
                source_task=self.task_id,
            )
        except knowledge.KnowledgeError as exc:
            return f"Refused: {exc}", True
        self._log("propose", query=line["id"])
        return (
            f"Recorded as {line['id']}, held for human review. It is not visible "
            "to other agents until somebody promotes it.",
            False,
        )

    # -- protocol ----------------------------------------------------------

    def handle(self, message: dict) -> dict | None:
        """One JSON-RPC message in, one response out -- or None for a notification."""
        method = message.get("method", "")
        message_id = message.get("id")

        if method == "initialize":
            requested = (message.get("params") or {}).get("protocolVersion")
            return _result(message_id, {
                "protocolVersion": requested if isinstance(requested, str) else DEFAULT_PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "1"},
            })
        if method == "tools/list":
            return _result(message_id, {"tools": self.tools()})
        if method == "tools/call":
            params = message.get("params") or {}
            text, is_error = self.call(
                str(params.get("name", "")), params.get("arguments") or {}
            )
            return _result(message_id, {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            })
        if message_id is None:
            # A notification. `notifications/initialized` is the one that
            # matters; answering it at all is a protocol error.
            return None
        return _error(message_id, -32601, f"unknown method: {method}")


def serve(server: Server, stdin=None, stdout=None) -> int:
    """Read newline-delimited JSON-RPC until stdin closes.

    A line that does not parse is answered rather than fatal: a client that
    sends one malformed frame must not take the tool away for the rest of the
    task.
    """
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            _write(sink, _error(None, -32700, "parse error"))
            continue
        if not isinstance(message, dict):
            _write(sink, _error(None, -32600, "invalid request"))
            continue
        response = server.handle(message)
        if response is not None:
            _write(sink, response)
    return 0


def config_document(command: list[str]) -> dict:
    """The `--mcp-config` document handed to the agent.

    Written into the run's own log directory, never into the target repository:
    a file dropped in the project would show up in `git status`, and the engine
    discards a task that leaves the tree dirty. The fence would have caught it
    eventually; the tree check catches it immediately, and neither should ever
    have to.
    """
    return {"mcpServers": {SERVER_NAME: {"command": command[0], "args": list(command[1:])}}}


def _result(message_id, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "result": payload}


def _error(message_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _write(sink, payload: dict) -> None:
    sink.write(json.dumps(payload) + "\n")
    sink.flush()
