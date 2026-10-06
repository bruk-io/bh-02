"""The Transcript: the conversation as a scrolling column of blocks.

A block is one widget per thing said: a message the person sent, a run of streamed text or
thinking, a tool call, its result, usage, a stop, a note. What each says is `render`'s (pure);
this module only puts it in widgets and gives each a CSS class, which is how it looks.

Streaming never re-draws the log: a chunk grows the open `Stream` only, and a stream settles
its text into pieces of a few lines each, so a chunk re-draws at most one piece however long
the reply grows. Wrapped lines keep their gutter: a result is a marker column beside a body
that wraps inside its own column, and an input's code has a left border the height of the block.

A model step's usage is one line however many usage events it sends (Anthropic sends what was
read as the turn starts, and the rest as it ends): the events are summed and the line drawn
once the step's usage is complete, which is when anything but its own text, thinking
or calls comes next (a result, a stop, a note, the reply's end; a line the person types
meanwhile is drawn after the reply, see `BhApp.send`).
A reply stopped mid-stream so still shows what it read, under what it said.
"""

from collections.abc import Mapping
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from tui_cordis_plugin import render
from tui_cordis_plugin.history import Replay

__all__ = ["Stream", "Transcript"]

# How many lines a streaming piece grows to before it is settled and a new one opened, and
# how many characters, for text that comes without newlines (a long paragraph).
_PIECE_LINES = 24
_PIECE_CHARS = 2_000


class Stream(Vertical):
    """A run of streamed text, drawn as markdown in pieces: settled pieces are drawn once; only
    the last, open piece is re-drawn as text arrives."""

    DEFAULT_CSS = """
    Stream {
        height: auto;
    }
    Stream > Static {
        width: 100%;
    }
    """

    def __init__(self, *, classes: str | None = None) -> None:
        super().__init__(classes=classes)
        self._settled: list[str] = []
        self._tail = ""
        self._fence: render.Fence = None  # the code fence open where the tail starts
        self._piece: Static | None = None
        self._unattached: list[Static] = []  # pieces drawn before the stream was in the DOM

    @property
    def text(self) -> str:
        """Everything streamed into this block so far."""
        return "".join(self._settled) + self._tail

    @property
    def pieces(self) -> int:
        """How many widgets the text is drawn in."""
        return len(self._settled) + (self._piece is not None)

    def append(self, text: str) -> None:
        """Add streamed text: settle the open piece once it is long enough, then draw the rest."""
        self._tail += text
        while cut := render.settle_point(self._tail, _PIECE_LINES, _PIECE_CHARS):
            piece, self._tail = self._tail[:cut], self._tail[cut:]
            self._draw(piece.removesuffix("\n"))
            self._settled.append(piece)
            self._fence = render.fence_after(piece.removesuffix("\n"), self._fence)
            self._piece = None
        if self._tail:
            self._draw(self._tail.rstrip("\n"))

    def compose(self) -> ComposeResult:
        yield from self._unattached
        self._unattached = []

    def _draw(self, text: str) -> None:
        shown = render.markdown(text, self._fence)
        if self._piece is not None:
            self._piece.update(shown)
            return
        self._piece = Static(shown)
        if self.is_attached:
            self.mount(self._piece)
        else:  # inside a container not composed yet (a Collapsible): mounted with the stream
            self._unattached.append(self._piece)


class Transcript(VerticalScroll):
    """Blocks appended as a turn streams in; it follows the end unless scrolled away."""

    DEFAULT_CSS = """
    Transcript {
        height: 1fr;
        padding: 0 1;
    }
    Transcript > .block {
        width: 100%;
        height: auto;
        margin: 1 0 0 0;
    }
    Transcript > .text {
        color: $bh-text;
    }
    Transcript > .user {
        color: $bh-text-bright;
        background: $bh-surface-raised;
        padding: 0 1;
        text-style: bold;
    }
    Transcript > .thinking {
        border: none;
        padding: 0;
        background: transparent;
        color: $bh-text-muted;
        text-style: italic;
    }
    Transcript > .thinking Contents {
        padding: 0 0 0 2;
    }
    Transcript .row {
        height: auto;
    }
    Transcript .marker {
        width: 2;
        color: $bh-accent-secondary;
    }
    Transcript .body {
        width: 1fr;
    }
    Transcript > .tool_call {
        margin: 1 0 0 0;
    }
    Transcript > .tool_call .head {
        color: $bh-accent-secondary;
        text-style: bold;
    }
    Transcript > .tool_call .code {
        margin: 0 0 0 2;
        padding: 0 0 0 1;
        border-left: solid $bh-accent-secondary;
    }
    Transcript > .tool_result {
        margin: 0;
        color: $bh-text-muted;
    }
    Transcript > .tool_result .marker {
        width: 4;
        padding: 0 0 0 2;
        color: $bh-text-muted;
    }
    Transcript > .tool_result.-error .body {
        color: $bh-danger;
    }
    Transcript > .usage {
        width: auto;
        margin: 0 0 0 2;
        padding: 0 1;
        background: $panel;
        color: $bh-text 70%;  /* readable: 5.2:1 on the panel, where text-tertiary is 2.2:1 */
    }
    Transcript > .stop {
        width: auto;
        margin: 0 0 0 2;
        padding: 0 1;
        background: $bh-danger 20%;
        color: $bh-danger;
    }
    Transcript > .note {
        border-left: wide $bh-link-subtle;
        padding: 0 0 0 1;
        color: $bh-link-subtle;
    }
    Transcript > .failure {
        border-left: wide $bh-danger;
        padding: 0 0 0 1;
        color: $bh-danger;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._stream: Stream | None = None
        self._thinking: Collapsible | None = None
        self._usage: Mapping[str, Any] | None = None  # this model step's usage, not drawn yet

    def on_mount(self) -> None:
        self.anchor()  # follow the end until the person scrolls away

    def user(self, text: str) -> None:
        """Add a message the person sent."""
        self._settle_usage()
        self._add(Static(f"› {text}", markup=False), "user")

    def note(self, text: str, kind: str = "note") -> None:
        """Add something bh-02 itself says (`kind` is `note` or `failure`)."""
        self._settle_usage()
        self._add(Static(text, markup=False), kind)

    def event(self, event: Mapping[str, Any]) -> None:
        """Add one event of a turn (CONTRACTS.md: event); a type it doesn't know is skipped."""
        kind = str(event.get("type", ""))
        if kind == "usage":
            self._usage = event if self._usage is None else render.usage_sum(self._usage, event)
            return
        if kind not in ("text", "thinking", "tool_call"):
            self._settle_usage()  # the model step's usage is complete
        match kind:
            case "text" | "thinking" as kind:
                self._streaming(kind).append(str(event.get("text", "")))
            case "tool_call":
                self._add(_tool_call(event), "tool_call")
            case "tool_result":
                self._add(
                    _tool_result(event), "tool_result -error" if event.get("is_error") else "tool_result"
                )
            case "note":
                self._add(Static(str(event.get("text", "")), markup=False), "note")
            case "cleared":
                self.clear()
            case "stop" if not render.is_quiet_stop(event):
                self._add(Static(render.stop_line(event), markup=False), "stop")
            case _:
                pass

    def clear(self) -> None:
        """The conversation starts afresh (CONTRACTS.md: `cleared`): drop every block so far."""
        self._usage = None
        self._close_stream()
        self.remove_children()

    def end_turn(self) -> None:
        """The reply ended: what streams next starts a new block."""
        self._settle_usage()
        self._close_stream()

    def replay(self, replay: Replay) -> None:
        """Draw a session's history again (see `history`), then say where it ends."""
        if replay.skipped:
            self.note(f"… {replay.skipped} earlier entries of this session are not shown")
        for entry in replay.entries:
            match entry.get("type"):
                case "user":
                    self.user(str(entry.get("text", "")))
                case "turn_end":
                    self.end_turn()
                case "noted":
                    self.note(str(entry.get("text", "")), str(entry.get("kind", "note")))
                case _:
                    self.event(entry)
        self.end_turn()
        if replay.entries:
            self.note("↑ the session so far (a resumed session's kernel starts empty)")

    def blocks(self) -> list[tuple[str, str]]:
        """What the transcript shows, as (kind, plain text) per block, top to bottom."""
        return [(_kind(block), _plain(block)) for block in self.children]

    def _settle_usage(self) -> None:
        """Draw the model step's usage line, if it has usage not drawn yet."""
        if self._usage is not None:
            used, self._usage = self._usage, None
            self._add(Static(render.usage_line(used), markup=False), "usage")

    def _streaming(self, kind: str) -> Stream:
        """The open stream of `kind`, or a new one (closing a stream of the other kind)."""
        if self._stream is not None and self._stream.has_class(kind):
            return self._stream
        self._close_stream()
        stream = Stream(classes=kind)
        if kind == "thinking":
            self._thinking = Collapsible(stream, title="thinking", collapsed=False)
            self._mount_block(self._thinking, kind)
        else:
            self._mount_block(stream, kind)
        self._stream = stream
        return stream

    def _close_stream(self) -> None:
        """Close the open stream; thinking folds away to one line once it is done."""
        if self._thinking is not None and self._stream is not None:
            lines = self._stream.text.strip("\n").count("\n") + 1
            self._thinking.title = f"thinking · {lines} line{'s' if lines != 1 else ''}"
            self._thinking.collapsed = True
        self._stream, self._thinking = None, None

    def _add(self, block: Widget, kind: str) -> None:
        """Append a block that is not streamed; it closes any open stream."""
        self._close_stream()
        self._mount_block(block, kind)

    def _mount_block(self, block: Widget, kind: str) -> None:
        block.add_class("block", *kind.split())
        self.mount(block)


def _tool_call(event: Mapping[str, Any]) -> Widget:
    """A call: a marker and its name and arguments; the code it carries below, in a gutter."""
    head = Horizontal(
        Static("⏺", classes="marker"),
        Static(render.tool_call_head(event), markup=False, classes="body head"),
        classes="row",
    )
    code = render.tool_call_code(event)
    return Vertical(head, *([Static(code, classes="code")] if code is not None else []))


def _tool_result(event: Mapping[str, Any]) -> Widget:
    """A result: a marker column beside the body, so wrapped lines hang under the body."""
    return Horizontal(Static("⎿", classes="marker"), Static(render.tool_result_body(event), classes="body"))


_KINDS = ("user", "text", "thinking", "tool_call", "tool_result", "usage", "stop", "note", "failure")


def _kind(block: Widget) -> str:
    return next((kind for kind in _KINDS if block.has_class(kind)), "?")


def _plain(widget: Widget) -> str:
    """A block's text as the person reads it: a row's columns joined by a space, lines by a newline."""
    if isinstance(widget, Collapsible):  # its title is decoration; the text is its stream's
        return "\n".join(_plain(stream) for stream in widget.query(Stream))
    if isinstance(widget, Static):
        content = widget.content
        return content.plain if isinstance(content, Content) else str(content)
    parts = [text for child in widget.children if (text := _plain(child))]
    return (" " if isinstance(widget, Horizontal) else "\n").join(parts)
