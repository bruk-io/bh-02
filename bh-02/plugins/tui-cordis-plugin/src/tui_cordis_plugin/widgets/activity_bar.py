"""The ActivityBar: the column of views on the far left (only the conversation, so far), and
the command palette's button."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

__all__ = ["ActivityBar"]


class ActivityBar(Vertical):
    """One glyph per view (the conversation is the only one so far), then the palette's."""

    DEFAULT_CSS = """
    ActivityBar {
        width: 4;
        background: $bh-surface-recessed;
        border-right: vkey $bh-border-muted;
        padding: 1 0;
    }
    ActivityBar > .activity {
        width: 100%;
        content-align: center middle;
        color: $bh-text-muted;
    }
    ActivityBar > .activity.-current {
        color: $bh-primary;
    }
    ActivityBar > #activity-palette {
        dock: bottom;
    }
    ActivityBar > #activity-palette:hover {
        color: $foreground;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("◆", classes="activity -current", id="activity-conversation")
        palette = Static("≡", classes="activity", id="activity-palette")
        palette.tooltip = "Commands (Ctrl-P)"
        yield palette

    def on_click(self, event: events.Click) -> None:
        """The palette's glyph opens the command palette."""
        if event.widget is not None and event.widget.id == "activity-palette":
            self.app.action_command_palette()
