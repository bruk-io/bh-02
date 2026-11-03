"""A stdio MCP server with one tool, `fold`: a large file's outline in a token budget.

For sessions with no shell, where `lab-fold` cannot be run: the tool returns what `./lab fold`
prints for a file (`compressors.cli.fold_text`), header included. Code folds by its extension
through ast-grep; JSON, XML, outlines, logs and text by what they are. Every marker names the line
range or JSON path it hides, so Read with offset and limit, or Grep, fetches exactly that.

It reads any path it is given, as Read does, but Claude Code's permission rules do not govern an MCP
server's own file access: give it only to sessions allowed to read those files. Standard library
and the lab only; speaks newline-delimited JSON-RPC 2.0 on stdin and stdout.
"""

import json
import os
import sys
from collections.abc import Callable
from typing import Any

from claude_code.hook import config_from
from compressors.cli import fold_text
from compressors.common import read_text

type Fold = Callable[[str, int, str], str]  # (path, budget, query) -> the folded view

_TOOL = {
    "name": "fold",
    "description": (
        "Show a large file's outline within a token budget: every class, function and block of code "
        "with its real line number, XML by element, JSON with long arrays cut to head, tail and the items "
        "that stand out. Each marker names the lines or JSON path it hides; fetch them with Read (offset "
        "and limit) or Grep. A file that fits the budget comes back whole."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "the file, as an absolute path"},
            "budget": {"type": "integer", "description": "tokens to fold into (default 2000)"},
            "query": {"type": "string", "description": "words whose items or definitions to keep in view"},
        },
        "required": ["path"],
    },
}


def _error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def respond(request: dict[str, Any], fold: Fold) -> dict[str, Any] | None:
    """The reply to one JSON-RPC message, or None for a notification. `fold` does the reading, so
    this decides and the caller does the I/O."""
    rid = request.get("id")
    if rid is None:
        return None
    params = request.get("params", {})
    match request.get("method"):
        case "initialize":
            result: dict[str, Any] = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fold", "version": "1"},
            }
        case "tools/list":
            result = {"tools": [_TOOL]}
        case "tools/call":
            if params.get("name") != "fold":
                return _error(rid, -32602, f"no tool {params.get('name')!r}; this server has fold")
            args = params.get("arguments", {})
            if not isinstance(args.get("path"), str):
                return _error(rid, -32602, "fold needs a path: the file to fold, as an absolute path")
            try:
                text, failed = (
                    fold(args["path"], int(args.get("budget", 2000)), str(args.get("query", ""))),
                    False,
                )
            except (OSError, ValueError) as e:  # a missing file, an unknown language: the model can act on it
                text, failed = f"fold: {e}", True
            result = {"content": [{"type": "text", "text": text}], "isError": failed}
        case "ping":
            result = {}
        case _:
            return _error(rid, -32601, f"no method {request.get('method')!r}")
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _fold_file(path: str, budget: int, query: str) -> str:  # the view and knobs come from the environment
    """The file's folded view. A file that cannot be read raises OSError, and a language with no
    ast-grep grammar ValueError, from the reader and the fold."""
    config, view = config_from(os.environ)
    return fold_text(read_text(path), budget=budget, path=path, query=query, view=view, config=config).text


def main() -> int:
    for line in sys.stdin:
        if line.strip():
            reply = respond(json.loads(line), _fold_file)
            if reply is not None:
                sys.stdout.write(json.dumps(reply) + "\n")
                sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
