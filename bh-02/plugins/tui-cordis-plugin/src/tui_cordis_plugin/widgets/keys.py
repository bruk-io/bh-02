"""The Keys line: one line under the composer that names the everyday keys (`render.keys_line`),
in the longest form that fits the width, again whenever the width changes."""

from textual import events
from textual.widgets import Static

from tui_cordis_plugin import render

__all__ = ["Keys"]


class Keys(Static):
    """The keys to send, start a new line, stop, scroll, recall, copy, open the palette and quit."""

    DEFAULT_CSS = """
    Keys {
        height: 1;
        width: 100%;
        padding: 0 0 0 1;
        color: $bh-text 70%;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)

    def on_resize(self, event: events.Resize) -> None:
        self.update(render.keys_line(self.content_size.width))
