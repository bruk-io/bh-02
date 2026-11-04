"""A stdio MCP server that replays one MCP-Atlas task's recorded tool outputs (`evals.atlas`).

The task comes from the environment, TOOL_OUTPUT_LAB_TASK (an `atlas-<band>-<task>` id from
`evals.tasks`). It offers the tools the task's trajectory called, and answers each call with the
recorded output of the closest recorded call of that tool, so every session sees the data the
task was written against. Standard library and the lab only; newline-delimited JSON-RPC 2.0 on
stdin and stdout.
"""

import json
import os
import sys
from typing import Any

from evals import atlas
from evals.atlas import Record


def respond(request: dict[str, Any], record: Record) -> dict[str, Any] | None:
    """The reply to one JSON-RPC message, or None for a notification."""
    rid = request.get("id")
    if rid is None:
        return None
    params = request.get("params", {})
    match request.get("method"):
        case "initialize":
            result: dict[str, Any] = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "replay", "version": "1"},
            }
        case "tools/list":
            result = {"tools": atlas.tools(record)}
        case "tools/call":
            name = str(params.get("name", ""))
            call = atlas.reply(record, name, params.get("arguments") or {})
            if call is None:
                offered = ", ".join(t["name"] for t in atlas.tools(record))
                text, failed = f"no tool {name!r} here; the tools are: {offered}", True
            else:
                text, failed = call.output, False
            result = {"content": [{"type": "text", "text": text}], "isError": failed}
        case "ping":
            result = {}
        case _:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"no method {request.get('method')!r}"},
            }
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> int:
    task_id = os.environ["TOOL_OUTPUT_LAB_TASK"]
    record = atlas.record_for(task_id)
    for line in sys.stdin:
        if line.strip():
            reply = respond(json.loads(line), record)
            if reply is not None:
                sys.stdout.write(json.dumps(reply) + "\n")
                sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
