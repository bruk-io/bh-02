"""A stdio MCP server that serves one eval task's payload, for headless Claude Code runs.

The task comes from the environment, TOOL_OUTPUT_LAB_TASK (an id from `evals.tasks`), so the
model never sees which case it is. Every synthetic format has its tool: `list_pods` (JSON),
`get_logs` (logs), `browser_snapshot` (an accessibility snapshot) and `get_figma_metadata` (Figma
XML); whichever is called answers with the task's payload, as one text block. Standard library and
the lab only; speaks newline-delimited JSON-RPC 2.0 on stdin and stdout.
"""

import json
import os
import sys
from typing import Any

from evals.tasks import TOOLS, task

_TOOLS = [
    {
        "name": TOOLS["json"],
        "description": "List the pods in a Kubernetes namespace, with their status.",
        "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}},
    },
    {
        "name": TOOLS["log"],
        "description": "Fetch the recent log lines of a service.",
        "inputSchema": {"type": "object", "properties": {"service": {"type": "string"}}},
    },
    {
        "name": TOOLS["a11y"],
        "description": "Capture an accessibility snapshot of the current browser page.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": TOOLS["figma"],
        "description": "Get the layer tree of a Figma node as XML: ids, names, types, positions and sizes.",
        "inputSchema": {
            "type": "object",
            "properties": {"nodeId": {"type": "string", "description": "e.g. 0:1"}},
        },
    },
]


def respond(request: dict[str, Any], payload: str) -> dict[str, Any] | None:
    """The reply to one JSON-RPC message, or None for a notification."""
    method = request.get("method")
    rid = request.get("id")
    if rid is None:
        return None
    match method:
        case "initialize":
            version = request.get("params", {}).get("protocolVersion", "2025-06-18")
            result: dict[str, Any] = {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1"},
            }
        case "tools/list":
            result = {"tools": _TOOLS}
        case "tools/call":
            name = request.get("params", {}).get("name")
            if name not in {t["name"] for t in _TOOLS}:
                return {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32602, "message": f"no tool {name!r}"},
                }
            result = {"content": [{"type": "text", "text": payload}], "isError": False}
        case "ping":
            result = {}
        case _:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": f"no method {method!r}"},
            }
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> int:
    payload = task(os.environ["TOOL_OUTPUT_LAB_TASK"]).payload()
    for line in sys.stdin:
        if line.strip():
            reply = respond(json.loads(line), payload)
            if reply is not None:
                sys.stdout.write(json.dumps(reply) + "\n")
                sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
