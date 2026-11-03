"""A Claude Code PostToolUse hook that folds large MCP tool results.

    "PostToolUse": [{"matcher": "mcp__.*", "hooks": [{"type": "command",
        "command": "uv run -q --no-project --python 3.15 python -m claude_code.hook"}]}]

Run it with the lab as the working directory. The hook sees one of two things in `tool_response`:
the result itself, when it is under Claude Code's own limits, or Claude Code's notice that the
result was saved to a file. In the first case it saves the raw result beside Claude Code's own
spilled results; in the second it reads the file Claude Code saved. Either way Claude gets the
folded view and the file's path, and reads the rest from the file with jq, grep or python, the way
it already does with Claude Code's spilled results.

Environment: TOOL_OUTPUT_LAB_BUDGET (tokens, default 2000), TOOL_OUTPUT_LAB_MODE (`spilled-only`
folds only what Claude Code itself saved to a file), TOOL_OUTPUT_LAB_LOG (a JSONL file to append
one line per decision to, for experiments). A failure inside the hook leaves the tool
result untouched: the hook must never be the reason a tool call fails.
"""

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compressors.common import estimate_tokens
from compressors.route import Folded, fold

_SPILL_NOTICE = re.compile(r"Output has been saved to (/\S+?)\.?\s*$", re.MULTILINE)
_JSON_SLICE = re.compile(r'"_folded": "(\$[^"\s]*)\[(\d+):(\d+)\] omitted')
_LINE_GAP = re.compile(r"\[\.\.\. lines (\d+)-(\d+) omitted")


@dataclass(frozen=True)
class Inline:
    raw: str  # the result as the tool returned it; the hook must save it


@dataclass(frozen=True)
class Spilled:
    path: str  # Claude Code already saved the result here


type Action = Inline | Spilled | None


def _text_of(response: Any) -> str | None:
    """The text of an MCP result: a string, or text-only content blocks. None for anything else."""
    if isinstance(response, str):
        return response
    if (
        isinstance(response, list)
        and response
        and all(isinstance(b, dict) and b.get("type") == "text" for b in response)
    ):
        return "\n".join(b.get("text", "") for b in response)
    return None


def plan(event: dict[str, Any], spilled_only: bool = False) -> Action:
    """What to do with one PostToolUse event; None leaves the result alone.

    With `spilled_only`, a result Claude Code passed inline is left alone too: only results it
    saved to a file (and showed a head-only preview of) are folded.
    """
    if not str(event.get("tool_name", "")).startswith("mcp__"):
        return None
    text = _text_of(event.get("tool_response"))
    if text is None:
        return None
    m = _SPILL_NOTICE.search(text)
    if m and len(text) < 4000 and "exceeds maximum allowed tokens" in text:
        return Spilled(m[1])
    return None if spilled_only else Inline(text)


def _jq_path(path: str) -> str:
    rest = path[1:]
    return rest if rest.startswith(".") else "." + rest


def render(folded: Folded, path: str) -> str:
    """The folded view, under a banner that says where the full output is and how to read it."""
    head = f"[Folded: ~{folded.raw_tokens} tokens -> ~{estimate_tokens(folded.body)}. Full output: {path}"
    match folded.branch:
        case "json":
            m = _JSON_SLICE.search(folded.body)
            example = f"{_jq_path(m[1])}[{m[2]}:{min(int(m[3]), int(m[2]) + 5)}]" if m else "."
            how = (
                "Fold markers give the JSON path of what they hide, and say why any item shown out of order "
                f"is shown. Read hidden parts from the file, e.g. jq '{example}' {path}"
            )
        case "lines" | "html" | "xml" | "outline":
            m = _LINE_GAP.search(folded.body)
            first, last = (int(m[1]), min(int(m[2]), int(m[1]) + 20)) if m else (1, 20)
            how = (
                "Markers name the line numbers they hide. "
                f"Read them with sed -n '{first},{last}p' {path} or grep -n"
            )
        case _:
            how = f"Markers give the character offsets they hide; read them with python or grep on {path}"
    return f"{head}. {how}.]\n{folded.body}"


def session_dir(event: dict[str, Any]) -> Path:
    transcript = event.get("transcript_path")
    if transcript:
        return Path(transcript).with_suffix("") / "tool-results"
    return Path(tempfile.gettempdir()) / "tool-output-lab"


def _log(entry: dict[str, Any]) -> None:
    target = os.environ.get("TOOL_OUTPUT_LAB_LOG")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def handle(event: dict[str, Any], budget: int, spilled_only: bool = False) -> dict[str, Any] | None:
    """The hook's JSON reply for one event, or None to leave the result alone."""
    action = plan(event, spilled_only)
    if action is None:
        return None
    match action:
        case Spilled(path=path):
            raw = Path(path).read_text(encoding="utf-8")
        case Inline(raw=raw):
            path = ""
    folded = fold(event.get("tool_input") or {}, raw, budget_tokens=budget)
    _log(
        {
            "tool": event.get("tool_name"),
            "tool_use_id": event.get("tool_use_id"),
            "spilled": isinstance(action, Spilled),
            "raw_tokens": estimate_tokens(raw),
            "branch": folded.branch if folded else "passthrough",
            "out_tokens": estimate_tokens(folded.body) if folded else None,
        }
    )
    if folded is None:
        return None
    if isinstance(action, Inline) or folded.source is not None:
        target = session_dir(event) / f"folded-{event.get('tool_use_id', 'call')}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(folded.source if folded.source is not None else raw, encoding="utf-8")
        path = str(target)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": render(folded, path)}}


def main() -> int:
    try:
        event = json.load(sys.stdin)
        budget = int(os.environ.get("TOOL_OUTPUT_LAB_BUDGET", "2000"))
        reply = handle(event, budget, os.environ.get("TOOL_OUTPUT_LAB_MODE") == "spilled-only")
    except Exception as e:  # the hook must never break the tool call; say why on stderr
        print(f"tool-output-lab hook left the result untouched: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if reply is not None:
        print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
