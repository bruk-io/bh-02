"""The Composer: where the person writes. Enter sends; Ctrl-J (or Shift+Enter, where the
terminal tells them apart) starts a new line."""

from textual import events
from textual.message import Message
from textual.widgets import TextArea

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

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id, soft_wrap=True, show_line_numbers=False, compact=False)

    async def on_key(self, event: events.Key) -> None:
        """Send on Enter; a new line on the newline keys. Runs before TextArea's own handling."""
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text
            if text.strip():
                self.clear()
                self.post_message(self.Submitted(text))
        elif event.key in _NEWLINE_KEYS:
            event.prevent_default()
            event.stop()
            self.insert("\n")
