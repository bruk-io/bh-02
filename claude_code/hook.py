"""A Claude Code PostToolUse hook that folds large MCP tool results.

    "PostToolUse": [{"matcher": "mcp__.*", "hooks": [{"type": "command", "timeout": 30,
        "command": "cd /ABSOLUTE/PATH/TO/tool-output-lab && uv run -q --no-project --python 3.15
                    --with ast-grep-py python -m claude_code.hook"}]}]   (the command on one line)

The `cd` is required: Claude Code runs hooks in the session's directory. The hook sees one of two
things in `tool_response`: the result itself, when it is under Claude Code's own limits, or Claude
Code's notice that it saved the result to a file. By default it acts only on the second (the A/Bs
found folding inline results costs more than it saves): it reads the file Claude Code saved and
gives Claude the folded view and that path. With TOOL_OUTPUT_LAB_MODE=all it also folds inline
results, saving the raw beside Claude Code's own spills first.

A spill notice is trusted only when it is the plain-string notice Claude Code writes and its path
resolves inside this session's tool-results folder under Claude Code's naming; a tool's own output
that imitates the notice is treated as ordinary output. Files are read without following links,
only when regular and under a size cap, and written privately (0600) and atomically.

Environment: TOOL_OUTPUT_LAB_BUDGET (tokens, default 2000), TOOL_OUTPUT_LAB_MODE (`spilled-only`,
the default, or `all`), TOOL_OUTPUT_LAB_LOG (a JSONL file to append one line per decision to). A
failure inside the hook leaves the tool result untouched: it must never be why a tool call fails.
"""

import json
import os
import re
import shlex
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compressors import markers
from compressors.common import estimate_tokens, query_terms
from compressors.route import Folded, fold

MAX_SPILL_BYTES = 32 * 1024 * 1024
_NOTICE = re.compile(
    r"\AError: result \([^)\n]*\) exceeds maximum allowed tokens\. "
    r"Output has been saved to (?P<path>[^\n]+?)\.\n"
)
_SPILL_NAME = re.compile(r"\Amcp-.+-\d+\.txt\Z")


@dataclass(frozen=True)
class Inline:
    raw: str  # the result as the tool returned it; the hook must save it


@dataclass(frozen=True)
class Spilled:
    path: str  # where the notice says Claude Code saved the result (checked before it is read)


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


def plan(event: dict[str, Any], fold_inline: bool = False) -> Action:
    """What to do with one PostToolUse event; None leaves the result alone.

    A spill is only Claude Code's own notice: a plain string that starts with it. A content-block
    result is the tool's own output, whatever it says. Inline results are folded only with
    `fold_inline`.
    """
    if not str(event.get("tool_name", "")).startswith("mcp__") or not event.get("transcript_path"):
        return None
    response = event.get("tool_response")
    if isinstance(response, str) and (m := _NOTICE.match(response)):
        return Spilled(m["path"])
    text = _text_of(response)
    if text is None or not fold_inline:
        return None
    return Inline(text)


def trusted_spill(resolved: str, session_resolved: str) -> bool:
    """Whether a spill path, with links resolved, is one of Claude Code's files for this session."""
    parent, name = os.path.split(resolved)
    return parent == session_resolved and _SPILL_NAME.match(name) is not None


def _jq_path(path: str) -> str:
    rest = path[1:]
    return rest if rest.startswith(".") else "." + rest


def render(folded: Folded, path: str, raw_path: str = "") -> str:
    """The folded view, under a banner that says where the full output is and how to read it.

    `path` is the file the markers' line numbers refer to; `raw_path`, when different, the raw."""
    quoted = shlex.quote(path)
    raw_note = f" (the raw output: {raw_path})" if raw_path and raw_path != path else ""
    size = f"~{folded.raw_tokens} tokens -> ~{estimate_tokens(folded.body)}"
    head = f"[Folded: {size}. Full output: {path}{raw_note}"
    match folded.branch:
        case "json":
            m = markers.JSON_SLICE_IN_TEXT.search(folded.body)
            example = f"{_jq_path(m[1])}[{m[2]}:{min(int(m[3]), int(m[2]) + 5)}]" if m else "."
            how = (
                "Fold markers give the JSON path of what they hide, and say why any item shown out of order "
                f"is shown. Read hidden parts from the file, e.g. jq '{example}' {quoted}"
            )
        case "lines" | "html" | "xml" | "outline":
            m = markers.ANY_RANGE.search(folded.body)
            first, last = (int(m[1]), min(int(m[2]), int(m[1]) + 20)) if m else (1, 20)
            how = (
                "Markers name the line numbers they hide. "
                f"Read them with sed -n '{first},{last}p' {quoted} or grep -n"
            )
        case _:
            how = f"Markers give the character offsets they hide; read them with python or grep on {quoted}"
    return f"{head}. {how}.]\n{folded.body}"


def session_dir(event: dict[str, Any]) -> Path:
    """Where Claude Code saves this session's large results (`<transcript without .jsonl>/tool-results`)."""
    return Path(str(event["transcript_path"])).with_suffix("") / "tool-results"


def _read_spill(path: str, session: Path, cap: int = MAX_SPILL_BYTES) -> str | None:
    """The spilled file's text, or None when it is not a regular file of this session's, or too big."""
    try:
        resolved, session_resolved = os.path.realpath(path), os.path.realpath(session)
    except OSError:
        return None
    if not trusted_spill(resolved, session_resolved):
        return None
    try:
        fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)  # a FIFO must not block the open
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > cap:
            return None
        return f.read(cap + 1).decode("utf-8", errors="replace")


def _write_private(target: Path, text: str) -> None:
    """Write `text` to `target` at 0600, atomically, never through a link."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise OSError(f"refusing to write into a linked folder: {target.parent}")
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(temp, target)


def _log(entry: dict[str, Any]) -> None:
    """Append to TOOL_OUTPUT_LAB_LOG; a failing log never changes what the hook does."""
    target = os.environ.get("TOOL_OUTPUT_LAB_LOG")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"tool-output-lab hook could not log to {target}: {e}", file=sys.stderr)


def handle(event: dict[str, Any], budget: int, fold_inline: bool = False) -> dict[str, Any] | None:
    """The hook's JSON reply for one event, or None to leave the result alone."""
    action = plan(event, fold_inline)
    if action is None:
        return None
    session = session_dir(event)
    match action:
        case Spilled(path=path):
            raw = _read_spill(path, session)
            if raw is None:
                _log({"tool": event.get("tool_name"), "event": "untrusted-spill", "path": path})
                return None
        case Inline(raw=raw):
            path = ""
    folded = fold(raw, budget_tokens=budget, terms=query_terms(event.get("tool_input") or {}))
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
    call = re.sub(r"[^A-Za-z0-9_-]", "_", str(event.get("tool_use_id", "call")))
    if isinstance(action, Inline):  # keep the raw, always
        raw_path = session / f"folded-{call}.txt"
        _write_private(raw_path, raw)
        path = str(raw_path)
    raw_path = path
    if folded.source is not None:  # the line numbers refer to a copy (pretty XML, page text): save it too
        view = session / f"folded-{call}.view.txt"
        _write_private(view, folded.source)
        path = str(view)
    text = render(folded, path, raw_path)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": text}}


def main() -> int:
    try:
        event = json.load(sys.stdin)
        budget = int(os.environ.get("TOOL_OUTPUT_LAB_BUDGET", "2000"))
        reply = handle(event, budget, fold_inline=os.environ.get("TOOL_OUTPUT_LAB_MODE") == "all")
    except Exception as e:  # the hook must never break the tool call; say why on stderr  # noqa: BLE001
        print(f"tool-output-lab hook left the result untouched: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if reply is not None:
        print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
