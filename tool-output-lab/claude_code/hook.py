"""A Claude Code PostToolUse hook that folds large MCP tool results and Bash output.

    "PostToolUse": [{"matcher": "mcp__.*|Bash", "hooks": [{"type": "command", "timeout": 30,
        "command": "cd /ABSOLUTE/PATH/TO/tool-output-lab && uv run -q --no-project --python 3.15
                    --with ast-grep-py python -m claude_code.hook"}]}]   (the command on one line)

The `cd` is required: Claude Code runs hooks in the session's directory. The hook sees one of two
things in `tool_response`: the result itself, when it is under Claude Code's own limits, or Claude
Code's notice that it saved the result to a file. By default (`inline`) it folds only the first,
saving the raw beside Claude Code's own spills, and leaves spills to Claude Code, whose notice
already keeps the result out of the context. `spilled` folds only spills (it reads the file
Claude Code saved and gives Claude the folded view and that path); `all` folds both.

Bash is folded the same way, after the command has run: permission rules were checked on the real
command, and `cd` and exit codes are untouched (rewriting the command before it runs breaks both).
Its stdout is the inline result; above 30,000 characters Claude Code saves the output
and gives `persistedOutputPath`, which is the spill. Read is never folded: it is how Claude gets a
file exactly, and what Edit relies on.

A spill notice is trusted only when it is the plain-string notice Claude Code writes and its path
resolves inside this session's tool-results folder under Claude Code's naming; a tool's own output
that imitates the notice is treated as ordinary output. Files are read without following links,
only when regular and under a size cap, and written privately (0600) and atomically.

Environment: TOOL_OUTPUT_LAB_BUDGET (tokens, default 2000), TOOL_OUTPUT_LAB_MODE (`inline`, the
default, `spilled` or `all`), TOOL_OUTPUT_LAB_VIEW (`sample`, the default, or `schema`),
TOOL_OUTPUT_LAB_CONFIG (a TOML file of knobs, `compressors/config.py`), TOOL_OUTPUT_LAB_SET (knobs,
`schema.rare=0.15;tree_envelope.rare=0.25`, over the file's), TOOL_OUTPUT_LAB_LOG (a JSONL file to
append one line per decision to: the tool, the session, a digest of the raw text, the branch and the
sizes, so an eval can tell whether a session's large output was folded). A failure inside the hook
leaves the tool result untouched: it must never be why a tool call fails.
"""

import hashlib
import json
import os
import re
import shlex
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from compressors.common import estimate_tokens, query_terms
from compressors.config import DEFAULT, FoldConfig, load, with_sets
from compressors.route import Folded, fold

MAX_SPILL_BYTES = 32 * 1024 * 1024
_NOTICE = re.compile(
    r"\AError: result \([^)\n]*\) exceeds maximum allowed tokens\. "
    r"Output has been saved to (?P<path>[^\n]+?)\.\n"
)
# Claude Code's name for a saved MCP result. Its path is read from text the tool returned, which the
# tool could forge, so the name must match too. Bash's comes from a field Claude Code fills in.
_SPILL_NAME = re.compile(r"\Amcp-.+-\d+\.txt\Z")
# A command that reads a saved output is recovering a range the fold named: folding it would fold it again.
_RECOVERY = re.compile(r"/tool-results/|\bfolded-[\w.-]+\.txt")
_BASH_SPILL_FIELDS = ("persistedOutputPath", "persistedOutputSize")


@dataclass(frozen=True)
class Inline:
    raw: str  # the result as the tool returned it; the hook must save it


@dataclass(frozen=True)
class Spilled:
    path: str  # where Claude Code saved the result (checked before it is read)
    from_field: bool = False  # the path came from a field Claude Code fills in (Bash), not from a notice


type Action = Inline | Spilled | None


class Mode(StrEnum):
    """Which results the hook folds."""

    INLINE = "inline"  # results under Claude Code's limits; spills are left to Claude Code
    SPILLED = "spilled"  # only results Claude Code saved to a file
    ALL = "all"


def mode_of(value: str | None) -> Mode:
    """TOOL_OUTPUT_LAB_MODE as a Mode; unset is the default, inline.

    Raises:
        ValueError: the value names no mode.
    """
    try:
        return Mode(value or Mode.INLINE)
    except ValueError:
        raise ValueError(
            f"TOOL_OUTPUT_LAB_MODE={value!r}: use inline (the default), spilled or all"
        ) from None


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


def plan(event: dict[str, Any], mode: Mode = Mode.INLINE) -> Action:
    """What to do with one PostToolUse event; None leaves the result alone.

    For an MCP tool, a spill is only Claude Code's own notice: a plain string that starts with it; a
    content-block result is the tool's own output, whatever it says. For Bash, see `_plan_bash`.
    `mode` says which of the two to fold.
    """
    tool = str(event.get("tool_name", ""))
    if not event.get("transcript_path"):
        return None
    response = event.get("tool_response")
    if tool == "Bash":
        return _plan_bash(event.get("tool_input") or {}, response, mode)
    if not tool.startswith("mcp__"):
        return None
    if isinstance(response, str) and (m := _NOTICE.match(response)):
        return Spilled(m["path"]) if mode in (Mode.SPILLED, Mode.ALL) else None
    if mode is Mode.SPILLED:
        return None
    text = _text_of(response)
    return None if text is None else Inline(text)


def _plan_bash(tool_input: dict[str, Any], response: Any, mode: Mode) -> Action:
    """Bash answers `{stdout, stderr, interrupted, isImage, ...}`: its stdout is folded inline, or, when
    Claude Code saved a large output (`persistedOutputPath`), that file is the spill. Never an image,
    and never a command that reads a saved output (`_RECOVERY`)."""
    if (
        not isinstance(response, dict)
        or response.get("isImage")
        or not isinstance(response.get("stdout"), str)
    ):
        return None
    if _RECOVERY.search(str(tool_input.get("command", ""))):
        return None
    persisted = response.get("persistedOutputPath")
    if isinstance(persisted, str):
        return Spilled(persisted, from_field=True) if mode in (Mode.SPILLED, Mode.ALL) else None
    return Inline(response["stdout"]) if mode in (Mode.INLINE, Mode.ALL) else None


def trusted_spill(resolved: str, session_resolved: str, from_field: bool = False) -> bool:
    """Whether a spill path, with links resolved, is one of Claude Code's files for this session: in
    its tool-results folder, under Claude Code's MCP naming unless the path came from a field Claude
    Code fills in, and never one of the hook's own copies."""
    parent, name = os.path.split(resolved)
    if parent != session_resolved or name.startswith("folded-"):
        return False
    return from_field or _SPILL_NAME.match(name) is not None


_EXACT = (
    " Every count and value in the envelope is exact, worked out over the whole output, not a sample:"
    " read the file only for what the envelope does not show"
)


def render(folded: Folded, path: str, raw_path: str = "", banner: str = "plain") -> str:
    """The folded view, under a banner that says where the full output is and how to read it.

    `path` is the file the envelope's line numbers or jq paths refer to; `raw_path`, when different,
    the raw. With `banner` "exact" the banner also says the envelope's counts are exact (it says
    nothing about checks: layer 1 checks the envelope's claims, and the hook does not)."""
    quoted = shlex.quote(path)
    raw_note = f" (the raw output: {raw_path})" if raw_path and raw_path != path else ""
    size = f"~{folded.raw_tokens} tokens -> ~{estimate_tokens(folded.body)}"
    head = f"[Folded: {size}. Full output: {path}{raw_note}"
    match folded.branch:
        case "json" | "jsonl":
            slurp = " -s" if folded.branch == "jsonl" else ""  # JSON Lines: jq reads the records as one array
            how = (
                "This is the data's envelope: its shape (fields, values and counts), the rows that break it, "
                f"samples, and how to get more, by jq path (jq{slurp}). FILE in a command is {quoted}"
            )
        case "lines":
            how = (
                "This is the output's envelope: its line templates and how many lines say each, the "
                "lines that break them, samples, and how to get more, by line number. FILE in a command "
                f"is {quoted}"
            )
        case _:  # a tree: XML, an outline, a page's text, plain text
            how = (
                "This is the output's envelope: its outline, each run of like items counted, the items "
                "that break a run, samples, and how to get more, by line number. FILE in a command is "
                f"{quoted}"
            )
    exact = f"{_EXACT}." if banner == "exact" else ""
    return f"{head}. {how}.{exact}]\n{folded.body}"


def session_dir(event: dict[str, Any]) -> Path:
    """Where Claude Code saves this session's large results (`<transcript without .jsonl>/tool-results`)."""
    return Path(str(event["transcript_path"])).with_suffix("") / "tool-results"


def _read_spill(path: str, session: Path, cap: int = MAX_SPILL_BYTES, from_field: bool = False) -> str | None:
    """The spilled file's text, or None when it is not a regular file of this session's, or too big."""
    try:
        resolved, session_resolved = os.path.realpath(path), os.path.realpath(session)
    except OSError:
        return None
    if not trusted_spill(resolved, session_resolved, from_field):
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
    """Write `text` to `target` at 0600, atomically, never through a link.

    Raises:
        OSError: the folder is a link, or the write fails.
    """
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


@dataclass(frozen=True)
class Outcome:
    """What the hook does once it has the raw text: the files to save, what to log, and the reply
    (None to leave the result alone)."""

    saves: tuple[tuple[Path, str], ...]
    log: dict[str, Any]
    reply: dict[str, Any] | None


def digest(text: str) -> str:
    """A short digest of a result's text, for the log: enough to tell one output from another."""
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def decide(
    event: dict[str, Any],
    action: Inline | Spilled,
    raw: str,
    budget: int,
    session: Path,
    view: str = "sample",
    config: FoldConfig = DEFAULT,
) -> Outcome:
    """The fold, and where its banner points: Claude Code's own file for a spill, a saved copy of
    the raw for an inline result, and a saved view when the line numbers refer to one."""
    terms = query_terms(event.get("tool_input") or {})
    folded = fold(raw, budget_tokens=budget, terms=terms, view=view, config=config)
    log = {
        "tool": event.get("tool_name"),
        "tool_use_id": event.get("tool_use_id"),
        "session_id": event.get("session_id"),
        "digest": digest(raw),  # which output this was: an eval matches it to its task's
        "spilled": isinstance(action, Spilled),
        "raw_tokens": estimate_tokens(raw),
        "branch": folded.branch if folded else "passthrough",
        "out_tokens": estimate_tokens(folded.body) if folded else None,
    }
    if folded is None:
        return Outcome((), log, None)
    call = re.sub(r"[^A-Za-z0-9_-]", "_", str(event.get("tool_use_id", "call")))
    saves: list[tuple[Path, str]] = []
    match action:
        case Spilled(path=path):
            raw_path = path
        case Inline():  # keep the raw, always
            saved = session / f"folded-{call}.txt"
            saves.append((saved, raw))
            raw_path = str(saved)
    path = raw_path
    if folded.source is not None:  # the line numbers refer to a copy (pretty XML, page text): save it too
        copy = session / f"folded-{call}.view.txt"
        saves.append((copy, folded.source))
        path = str(copy)
    text = render(folded, path, raw_path, config.banner)
    reply = {
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": _in_shape(event, text)}
    }
    return Outcome(tuple(saves), log, reply)


def _in_shape(event: dict[str, Any], text: str) -> str | dict[str, Any]:
    """The folded view as the tool's own result: a string for an MCP tool; for Bash, its response with
    stdout replaced (stderr and the exit fields kept) and the saved-output fields dropped, so Claude
    Code shows the fold and not its own notice."""
    if event.get("tool_name") != "Bash":
        return text
    response = {k: v for k, v in event["tool_response"].items() if k not in _BASH_SPILL_FIELDS}
    return response | {"stdout": text}


def handle(
    event: dict[str, Any],
    budget: int,
    mode: Mode = Mode.INLINE,
    view: str = "sample",
    config: FoldConfig = DEFAULT,
) -> dict[str, Any] | None:
    """The hook's JSON reply for one event, or None to leave the result alone: `plan` and `decide`
    choose, this reads the spill and writes what they say. A copy that cannot be saved raises
    OSError from `_write_private`; main reports it and leaves the result alone."""
    action = plan(event, mode)
    if action is None:
        return None
    session = session_dir(event)
    match action:
        case Spilled(path=path, from_field=from_field):
            raw = _read_spill(path, session, from_field=from_field)
            if raw is None:
                _log({"tool": event.get("tool_name"), "event": "untrusted-spill", "path": path})
                return None
        case Inline(raw=raw):
            pass
    outcome = decide(event, action, raw, budget, session, view, config)
    _log(outcome.log)
    for target, text in outcome.saves:
        _write_private(target, text)
    return outcome.reply


def config_from(env: Mapping[str, str]) -> tuple[FoldConfig, str]:
    """The knobs and view an environment sets: TOOL_OUTPUT_LAB_CONFIG (a TOML file), then
    TOOL_OUTPUT_LAB_SET (`;`-separated NAME=VALUE) over it, and TOOL_OUTPUT_LAB_VIEW. A file that
    cannot be read raises OSError, and a bad knob ValueError, from `compressors.config`."""
    base = load(path) if (path := env.get("TOOL_OUTPUT_LAB_CONFIG")) else DEFAULT
    knobs = [s for s in env.get("TOOL_OUTPUT_LAB_SET", "").split(";") if s.strip()]
    return with_sets(base, knobs), env.get("TOOL_OUTPUT_LAB_VIEW", "sample")


def main() -> int:
    try:
        event = json.load(sys.stdin)
        budget = int(os.environ.get("TOOL_OUTPUT_LAB_BUDGET", "2000"))
        config, view = config_from(os.environ)
        reply = handle(event, budget, mode_of(os.environ.get("TOOL_OUTPUT_LAB_MODE")), view, config)
    except Exception as e:  # the hook must never break the tool call; say why on stderr  # noqa: BLE001
        print(f"tool-output-lab hook left the result untouched: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if reply is not None:
        print(json.dumps(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
