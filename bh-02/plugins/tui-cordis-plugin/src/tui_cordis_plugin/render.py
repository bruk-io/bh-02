"""What a turn's events, a lifecycle change and a jail's grades say: pure.

Text for what is one line (a stop, usage, a note), `Content` for what has styled parts (a
reply's markdown, an input's highlighted code, a coloured diff). Every style is a theme token
(`$text-success`, ...), never a colour, so the theme decides how it looks; the widgets add a
CSS class per kind. Everything here is a function of its arguments (CONTRACTS.md: event), so
it is tested without an app.
"""

import re
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any

from textual.content import Content
from textual.highlight import highlight

__all__ = [
    "approval_language",
    "approval_lines",
    "approval_title",
    "code",
    "fence_after",
    "is_quiet_stop",
    "jail_forms",
    "lifecycle_line",
    "session_forms",
    "markdown",
    "noted",
    "settle_point",
    "stop_line",
    "tool_call_code",
    "tool_call_head",
    "tool_result_body",
    "usage_line",
    "usage_sum",
    "waiting_line",
]

type Event = Mapping[str, Any]
# The language of the code fence a piece of streamed text ends inside, or None.
type Fence = str | None

_MAX_ARG = 60
# Arguments that are code, shown as a block rather than cut to a glance: an input's.
_BLOCKS = ("code",)
_MAX_CODE_LINES = 40
_MAX_RESULT_LINES = 12
_MAX_DIFF_LINES = 40
# Every provider's word for "the model finished on its own"; anything else is worth showing.
_QUIET_STOPS = frozenset({"answered", "end_turn", "stop", "success", "stop_sequence", "tool_use"})
_FAILURES = frozenset({"failed", "work-failed", "observe-failed", "teardown-error"})
# brig's grades, strongest first, as one glyph each (CONTRACTS.md: jail).
_GRADES = {"enforced": "✓", "best_effort": "~", "cooperative": "?", "unenforced": "✗"}
# The axes worth a glance in a status bar; the rest are in `report()` for whoever asks.
_AXES = ("fs_write", "network", "fs_read", "env")
# Each axis as the one letter a shorter form of the jail's field keeps.
_INITIALS = {"fs_write": "w", "network": "n", "fs_read": "r", "env": "e"}

# Theme tokens, by what they mark.
_MUTED = "$text-muted"
_HEADING = "bold $text-primary"
_INLINE_CODE = "$text-accent"
_DIFF = {"+++": "bold", "---": "bold", "@@": "$text-accent", "+": "$text-success", "-": "$text-error"}

_OPEN_FENCE = re.compile(r"^\s*```\s*([\w+#.-]*)\s*$")
_CLOSE_FENCE = re.compile(r"^\s*```\s*$")
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_INLINE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*|(?<![\w*])\*([^*\s][^*\n]*)\*(?![\w*])")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


def markdown(text: str, fence: Fence = None) -> Content:
    """Streamed reply text as Content: headings, bullets, quotes, `code`, **bold**, *italic*,
    and fenced code blocks highlighted. Line breaks are kept as they came (no reflow), so a
    reply can be split at any line and drawn in pieces; `fence` is the fence the piece starts
    inside (see `fence_after`)."""
    parts: list[Content] = []
    block: list[str] = []
    for line in text.split("\n"):
        if fence is not None:
            if _CLOSE_FENCE.match(line):
                parts.extend([code("\n".join(block), fence)] if block else [])
                block, fence = [], None
            else:
                block.append(line)
        elif match := _OPEN_FENCE.match(line):
            fence = match.group(1) or "text"
        else:
            parts.append(_markdown_line(line))
    if fence is not None and block:
        parts.append(code("\n".join(block), fence))
    return Content("\n").join(parts)


def fence_after(text: str, fence: Fence = None) -> Fence:
    """The fence still open after `text`'s lines, given the one open before them."""
    for line in text.split("\n"):
        if fence is not None:
            fence = None if _CLOSE_FENCE.match(line) else fence
        elif match := _OPEN_FENCE.match(line):
            fence = match.group(1) or "text"
    return fence


def settle_point(text: str, limit: int, most: int) -> int:
    """Where a streaming piece of text can be closed, or 0 (keep growing it): past its
    `limit`-th full line once it holds that many; else, once it is longer than `most`
    characters with too few newlines (a long paragraph), at the last line end or space
    before `most` (a hard cut if there is neither). What is settled is drawn once and never
    again, and no piece is longer than `limit` lines or much longer than `most` characters, so
    a chunk re-draws a bounded piece however long the reply grows, however much comes at once,
    and whether or not it has newlines. A cut at a space ends a line there on screen."""
    end = -1
    for _ in range(limit):
        end = text.find("\n", end + 1)
        if end < 0:
            break
    else:
        return end + 1
    if len(text) <= most:
        return 0
    newline = text.rfind("\n", 0, most)
    if newline >= 0:
        return newline + 1
    space = text.rfind(" ", 0, most)
    return space + 1 if space > 0 else most


def code(source: str, language: str = "python") -> Content:
    """Source code, syntax-highlighted with the theme's colours (Textual's highlight tokens,
    which the theme resolves), as the transcript and the approval modal both draw it."""
    return highlight(source, language=language).rstrip("\n")


def tool_call_head(event: Event) -> str:
    """A tool call's name and its arguments cut to a glance, the code it carries left out."""
    name = str(event.get("name", "?"))
    input: Mapping[str, Any] = event.get("input") or {}
    block = _block_key(input)
    args = ", ".join(f"{k}={_short(v)}" for k, v in input.items() if k != block)
    return name if block is not None and not args else f"{name}({args})"


def tool_call_code(event: Event) -> Content | None:
    """The code a tool call carries (an input's), highlighted; else None.
    A long one is cut, and says how much was left out."""
    input: Mapping[str, Any] = event.get("input") or {}
    block = _block_key(input)
    if block is None:
        return None
    body = str(input[block]).strip("\n").splitlines() or [""]
    shown = code("\n".join(body[:_MAX_CODE_LINES]))
    return _with_more(shown, len(body) - _MAX_CODE_LINES)


def tool_result_body(event: Event) -> Content:
    """A tool's result, cut to a glance; a unified diff coloured line by line (and allowed
    more lines, since a diff is worth reading). An error's colour is the widget's to give."""
    body = str(event.get("content", "")).rstrip("\n").splitlines() or ["(no output)"]
    if not event.get("is_error") and any(_HUNK.match(line) for line in body):
        shown = Content("\n").join(_diff_line(line) for line in body[:_MAX_DIFF_LINES])
        return _with_more(shown, len(body) - _MAX_DIFF_LINES)
    return _with_more(Content("\n".join(body[:_MAX_RESULT_LINES])), len(body) - _MAX_RESULT_LINES)


def _markdown_line(line: str) -> Content:
    """One line of prose outside a fence."""
    if match := _HEADING_LINE.match(line):
        return Content.styled(match.group(1), _HEADING)
    if match := _BULLET.match(line):
        return Content.assemble(match.group(1), ("• ", _MUTED), _inline(match.group(2)))
    if match := _QUOTE.match(line):
        return Content.assemble(("▎ ", _MUTED), _inline(match.group(1)).stylize("italic"))
    return _inline(line)


def _inline(text: str) -> Content:
    """`code`, **bold** and *italic* spans in a line; everything else as it is."""
    parts: list[str | tuple[str, str]] = []
    at = 0
    for match in _INLINE.finditer(text):
        parts.append(text[at : match.start()])
        quoted, bold, italic = match.groups()
        if quoted is not None:
            parts.append((quoted, _INLINE_CODE))
        elif bold is not None:
            parts.append((bold, "bold"))
        else:
            parts.append((italic, "italic"))
        at = match.end()
    parts.append(text[at:])
    return Content.assemble(*parts)


def _diff_line(line: str) -> Content:
    style = next((style for prefix, style in _DIFF.items() if line.startswith(prefix)), "")
    return Content.styled(line, style) if style else Content(line)


def _with_more(shown: Content, hidden: int) -> Content:
    """`shown`, and a muted line saying how many more lines were left out, if any were."""
    return Content.assemble(shown, (f"\n… {hidden} more lines", _MUTED)) if hidden > 0 else shown


def _block_key(input: Mapping[str, Any]) -> str | None:
    return next((key for key in _BLOCKS if isinstance(input.get(key), str)), None)


def usage_line(event: Event) -> str:
    """Tokens in and out, how many of those in were read from the prompt cache (when any were),
    and the cost when the provider reports one. Usage still `partial` (a reply stopped before
    the provider counted its output) says the output is not counted, and its cost is the input's."""
    partial = bool(event.get("partial"))
    out = "output not counted" if partial else f"{int(event.get('output_tokens', 0)):,} out"
    parts = [f"{int(event.get('input_tokens', 0)):,} in", out]
    if cached := int(event.get("cache_read_input_tokens") or 0):
        parts.insert(1, f"{cached:,} cached")
    if (cost := event.get("cost_usd")) is not None:
        parts.append(f"${float(cost):.4f}" + (" for input" if partial else ""))
    return " · ".join(parts)


def usage_sum(shown: Event, more: Event) -> dict[str, Any]:
    """One model step's usage, when its provider sends it in parts (Anthropic: what was read as
    the turn starts, then the rest as it ends): the counts added, and the cost when either has one."""
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    total: dict[str, Any] = {"type": "usage"} | {
        key: int(shown.get(key) or 0) + int(more.get(key) or 0) for key in keys
    }
    costs = [float(e["cost_usd"]) for e in (shown, more) if e.get("cost_usd") is not None]
    if costs:
        total["cost_usd"] = sum(costs)
    if shown.get("partial") and more.get("partial"):
        total["partial"] = True  # no part has brought the output count yet
    return total


def is_quiet_stop(event: Event) -> bool:
    """Whether a stop is the ordinary end of a turn, which needs no line of its own."""
    return str(event.get("reason", "")) in _QUIET_STOPS


def stop_line(event: Event) -> str:
    """Why a turn ended, when that was not the model simply finishing."""
    return f"stopped: {event.get('reason', '?')}"


def lifecycle_line(kind: str, row: str, error: str | None, seen: bool) -> str | None:
    """A change to the running composition worth a note, or None.

    `seen` is whether this row was already up once: the first time a row goes active is the
    program starting and says nothing; every time after is a reload. A failure always says
    what went wrong.
    """
    if kind in _FAILURES:
        return f"✗ {row} {kind}: {error or '?'}"
    if kind == "active" and seen:
        return f"↻ {row} reloaded"
    return None


def waiting_line(rows: Iterable[str]) -> str:
    """What a message typed while rows come back up says: that it waits, and for what."""
    named = sorted(rows)
    them = "it is" if len(named) == 1 else "they are"
    return f"⧗ waiting for {', '.join(named)} to start; this message is sent once {them} up"


def approval_title(request: Event) -> str:
    """The question an approval asks, in one line, with how long what it shows is: the request's
    own `title` (a tool's call as its registration shows it, an extension to load), else run this
    code."""
    lines = approval_lines(request)
    size = f"{len(lines)} line{'s' if len(lines) != 1 else ''}"
    if title := str(request.get("title") or ""):
        question = title.removesuffix("?")
        return f"{question} ({size}){title[len(question) :]}" if lines else title
    return f"Run this {request.get('name', '?')} code ({size})?"


def approval_lines(request: Event) -> list[str]:
    """What an approval shows, whole (nobody approves code unseen): the request's own `lines` (a
    tool's call as its registration shows it), else the code its input carries."""
    if isinstance(lines := request.get("lines"), list | tuple):
        return [str(line) for line in lines]
    input: Mapping[str, Any] = request.get("input") or {}
    return str(input.get("code") or "").strip("\n").splitlines()


def approval_language(request: Event) -> str:
    """The language an approval's lines are highlighted as: the request's `language`, else Python."""
    return str(request.get("language") or "python")


def jail_forms(confined: bool, report: Mapping[str, str]) -> tuple[str, ...]:
    """A kernel's confinement for a status bar, fullest form first: confined or not and a glyph
    per main axis, each axis named (`jailed fs_write ✓ network ✓`), then by its initial
    (`jailed w✓ n✓`), the initials run together (`jailed w✓n✓`), and the glyphs alone, in the
    axes' fixed order (`jailed ✓✓`). The status bar takes the first that fits."""
    head = "jailed" if confined else "unjailed"
    graded = [(axis, _GRADES.get(report[axis], "?")) for axis in _AXES if axis in report]
    if not graded:
        return (head,)
    initials = [f"{_INITIALS[axis]}{glyph}" for axis, glyph in graded]
    return (
        " ".join([head, *(f"{axis} {glyph}" for axis, glyph in graded)]),
        " ".join([head, *initials]),
        f"{head} {''.join(initials)}",
        f"{head} {''.join(glyph for _, glyph in graded)}",
    )


async def noted(text: str) -> AsyncIterator[Event]:
    """`text` as the one `note` event a reply would carry (CONTRACTS.md: event)."""
    yield {"type": "note", "text": text}


def session_forms(sid: str, *, resumed: bool = False) -> tuple[str, ...]:
    """A session's id for a status bar, fullest form first: the id (`(resumed)` after it on a
    resume), then its last part for a narrow bar (`58d9`, or `58d9 ↻`), which `--resume`
    takes too."""
    tail = sid.rsplit("-", 1)[-1]
    if resumed:
        return f"{sid} (resumed)", f"{tail} ↻"
    return sid, tail


def _short(value: object) -> str:
    text = repr(value)
    return text if len(text) <= _MAX_ARG else text[: _MAX_ARG - 1] + "…"
