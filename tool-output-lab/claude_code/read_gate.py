"""A Claude Code PreToolUse hook: the first whole-file Read of a large source file gets its outline.

    "PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command":
        "uv run -q --no-project --python 3.15 --with ast-grep-py python -m claude_code.read_gate"}]}]

Run it with the lab as the working directory. When Claude asks Read for a whole source file (no
offset or limit) that is larger than TOOL_OUTPUT_LAB_READ_MIN tokens (default 4000), the hook turns
that one call away and gives Claude the file's outline instead, folded by ast-grep with the real
line numbers: every class and function header, opened as far as a budget of a quarter of the file
allows (2,000 to 8,000 tokens). Claude then reads the ranges it needs with offset and limit, and
Read's own numbering stays right. Asking for the whole file again goes through: the gate turns a
path away once per session. Why PreToolUse: in PostToolUse, Read's result is numbered by Claude
Code from `startLine`, so a folded body there would carry wrong line numbers.

TOOL_OUTPUT_LAB_LOG, when set, gets one JSON line per decision. A failure inside the hook lets the
Read through unchanged.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_code.hook import session_dir
from compressors.code import fold_code, language_for
from compressors.common import estimate_tokens

_MAX_BYTES = 256 * 1024  # Claude Code refuses a whole Read beyond this itself


@dataclass(frozen=True)
class Gate:
    path: str
    language: str
    budget: int


def outline_budget(file_tokens: int) -> int:
    return max(2000, min(8000, file_tokens // 4))


def plan(event: dict[str, Any], file_text: str | None, seen: frozenset[str], min_tokens: int) -> Gate | None:
    """Whether to turn this Read away with an outline; None lets it through."""
    if event.get("tool_name") != "Read":
        return None
    args = event.get("tool_input") or {}
    path = str(args.get("file_path", ""))
    if args.get("offset") is not None or args.get("limit") is not None or args.get("pages"):
        return None
    language = language_for(path)
    if language is None or file_text is None or path in seen:
        return None
    tokens = estimate_tokens(file_text)
    if tokens <= min_tokens:
        return None
    return Gate(path, language, outline_budget(tokens))


def reason(gate: Gate, file_text: str, outline: str) -> str:
    n = len(file_text.splitlines())
    return (
        f"Not read whole: {gate.path} has {n} lines (~{estimate_tokens(file_text)} tokens). Below is its "
        "outline with the file's real line numbers: every class and function header, opened as far as "
        "it fits. Each [... lines A-B folded] marker names lines left out; read the ranges you need with "
        "Read offset=A limit=B-A+1, or Grep. To read the whole file anyway, call Read on it again.\n\n"
        + outline
    )


def _seen_file(event: dict[str, Any]) -> Path:
    return session_dir(event) / "read-gate-seen.txt"


def _log(entry: dict[str, Any]) -> None:
    target = os.environ.get("TOOL_OUTPUT_LAB_LOG")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def handle(event: dict[str, Any], min_tokens: int) -> dict[str, Any] | None:
    path = str((event.get("tool_input") or {}).get("file_path", ""))
    file_text = None
    p = Path(path)
    if path and language_for(path) and p.is_file() and p.stat().st_size <= _MAX_BYTES:
        file_text = p.read_text(encoding="utf-8", errors="replace")
    seen_path = _seen_file(event)
    seen = frozenset(seen_path.read_text().splitlines()) if seen_path.is_file() else frozenset()
    gate = plan(event, file_text, seen, min_tokens)
    if gate is None or file_text is None:
        if path in seen:
            _log({"event": "read-whole-after-outline", "path": path})
        return None
    fold = fold_code(file_text, gate.language, gate.budget)
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    with seen_path.open("a", encoding="utf-8") as f:
        f.write(path + "\n")
    _log(
        {
            "event": "outlined",
            "path": path,
            "file_tokens": estimate_tokens(file_text),
            "outline_tokens": estimate_tokens(fold.text),
            "open": fold.expanded,
            "folded": fold.folded,
        }
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason(gate, file_text, fold.text),
        }
    }


def main() -> int:
    try:
        event = json.load(sys.stdin)
        reply = handle(event, int(os.environ.get("TOOL_OUTPUT_LAB_READ_MIN", "4000")))
    except Exception as e:  # the hook must never break the Read; say why on stderr
        print(f"tool-output-lab read gate let the Read through: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if reply is not None:
        print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
