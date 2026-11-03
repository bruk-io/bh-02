"""A stdio MCP server that serves one synthetic needle case, for headless Claude Code runs.

The case comes from the environment so the model never sees the experiment's parameters:
NEEDLE_FORMAT (json | log), NEEDLE_KIND, NEEDLE_SIZE, NEEDLE_POSITION and NEEDLE_SEED. Tools:
`list_pods(namespace)` answers with the JSON case, `get_logs(service)` with the log case,
`browser_snapshot()` with the accessibility case and `get_figma_metadata(nodeId)` with the Figma case.
Standard library only; speaks newline-delimited JSON-RPC 2.0 on stdin and stdout.
"""

import json
import os
import random
import sys
from typing import Any

from harness.needle import a11y_case, figma_case, json_case, log_case

_TOOLS = [
    {
        "name": "list_pods",
        "description": "List the pods in a Kubernetes namespace, with their status.",
        "inputSchema": {
            "type": "object",
            "properties": {"namespace": {"type": "string"}},
            "required": ["namespace"],
        },
    },
    {
        "name": "browser_snapshot",
        "description": "Capture an accessibility snapshot of the current browser page.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_figma_metadata",
        "description": "Get the layer tree of a Figma node as XML: ids, names, types, positions and sizes.",
        "inputSchema": {
            "type": "object",
            "properties": {"nodeId": {"type": "string", "description": "e.g. 0:1"}},
            "required": ["nodeId"],
        },
    },
    {
        "name": "get_logs",
        "description": "Fetch the recent log lines of a service.",
        "inputSchema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
]


def _case_text(tool: str, env: dict[str, str]) -> str:
    rng = random.Random(env.get("NEEDLE_SEED", "0"))
    kind = env.get("NEEDLE_KIND", "rare_value")
    size = int(env.get("NEEDLE_SIZE", "500"))
    position = float(env.get("NEEDLE_POSITION", "0.5"))
    make = {
        "list_pods": json_case,
        "get_logs": log_case,
        "browser_snapshot": a11y_case,
        "get_figma_metadata": figma_case,
    }[tool]
    return make(kind, size, position, rng).raw


def respond(request: dict[str, Any], env: dict[str, str]) -> dict[str, Any] | None:
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
                "serverInfo": {"name": "fixture", "version": "0"},
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
            result = {"content": [{"type": "text", "text": _case_text(name, env)}], "isError": False}
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
    env = dict(os.environ)
    for line in sys.stdin:
        if not line.strip():
            continue
        reply = respond(json.loads(line), env)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
