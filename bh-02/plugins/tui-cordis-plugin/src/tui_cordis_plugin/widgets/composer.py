"""The Composer: where the person writes. Enter sends; Ctrl-J (or Shift+Enter, where the
terminal tells them apart) starts a new line. While the list of commands (`Completions`) is
open it also takes Up, Down, Tab and Escape, and Enter when it should (decision-0003); with it
closed, Up on the first line and Down on the last go back and forward through the lines sent
this run (`recall`). The list's keys come first: a key it takes never reaches the history."""

from textual import events
from textual.message import Message
from textual.widgets import TextArea

from tui_cordis_plugin import recall
from tui_cordis_plugin.frame import PaletteEntry
from tui_cordis_plugin.widgets.completions import Completions

__all__ = ["Composer"]

_NEWLINE_KEYS = frozenset({"shift+enter", "ctrl+j"})


class Composer(TextArea):
    """A text area that sends its text on Enter and clears itself."""

    DEFAULT_CSS = """
    Composer {
        height: auto;
        max-height: 10;
        min-height: 3;
        background: $bh-surface;
        border: round $bh-border;
    }
    Composer:focus {
        border: round $bh-ring;
    }
    """

    class Submitted(Message):
        """The person sent a message."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class Chose(Message):
        """Enter took an entry of the list rather than sending the text as typed."""

        def __init__(self, entry: PaletteEntry) -> None:
            super().__init__()
            self.entry = entry

    def __init__(self, *, id: str | None = None, completions: Completions | None = None) -> None:
        super().__init__("", id=id, soft_wrap=True, show_line_numbers=False, compact=False)
        self._completions = completions
        self._recall = recall.Recall()

    def remember(self, line: str) -> None:
        """`line` was sent: it is the newest line of the history, and the person is writing
        their own text again. Enter does this itself; a line run from the list or the palette
        is told by the app."""
        self._recall = recall.remember(self._recall, line)

    @property
    def recalled(self) -> bool:
        """Whether the text is a line recalled from the history, as it was sent. The list of
        commands stays shut for it (its Up and Down would block going further back), and opens
        once the person edits it."""
        return recall.recalled(self._recall, self.text)

    @property
    def _completing(self) -> Completions | None:
        """The list, while it is open: the only time its keys are not the text area's."""
        listed = self._completions
        return listed if listed is not None and listed.is_open else None

    def _complete(self, entry: PaletteEntry) -> None:
        """Put `entry` in the text, ready for arguments when it takes them; run nothing."""
        self.text = f"{entry.call} " if entry.takes_arguments else entry.call
        self.move_cursor(self.document.end)

    async def on_key(self, event: events.Key) -> None:
        """Send on Enter; a new line on the newline keys; Up and Down through the history. Runs
        before TextArea's own handling."""
        listed = self._completing
        if listed is not None and self._list_key(listed, event):
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text
            if text.strip():
                self.remember(text)
                self.clear()
                self.post_message(self.Submitted(text))
        elif event.key in _NEWLINE_KEYS:
            event.prevent_default()
            event.stop()
            if self._completions is not None:
                self._completions.close()  # a command is one line
            self.insert("\n")
        elif self._history_key(event.key):
            event.prevent_default()
            event.stop()

    def _history_key(self, key: str) -> bool:
        """Handle `key` as a step through the history: Up on the first line shown, Down on the
        last (a wrapped line counts as the lines it is drawn in). Whether it was one: with no
        step to take (nothing sent, the oldest shown, not recalling) the key is the text area's."""
        match key:
            case "up" if self.navigator.is_first_wrapped_line(self.cursor_location):
                step = recall.older(self._recall, self.text)
            case "down" if self.navigator.is_last_wrapped_line(self.cursor_location):
                step = recall.newer(self._recall)
            case _:
                return False
        if step is None:
            return False
        self._recall = step.recall
        self.text = step.text
        self.move_cursor(self.document.end)
        return True

    def _list_key(self, listed: Completions, event: events.Key) -> bool:
        """Handle `event` as the open list's key; whether it was one (Enter is, only when it
        takes an entry: otherwise the text is sent as typed)."""
        match event.key:
            case "up" | "down":
                listed.move(-1 if event.key == "up" else 1)
            case "tab" if listed.highlight is not None:
                self._complete(listed.highlight)
            case "escape":
                listed.shut()
            case "enter" if (entry := listed.taken_by_enter(self.text)) is not None:
                self.post_message(self.Chose(entry))
            case _:
                return False
        return True
