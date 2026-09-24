"""The SidebarPanel: the sessions a row lists through the frame (CONTRACTS.md: frame).

bh-01's sidebar-panel holding a list, the running session wearing a badge. Choosing a session
(Enter or a click) says how to continue it, as a note in the transcript.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from tui_cordis_plugin.messages import Noted
from tui_cordis_plugin.sessions import resume_note, session_label

__all__ = ["SidebarPanel"]

_NONE = "(none listed)"


def _prompt(item: Mapping[str, Any]) -> Content:
    """One session's entry: its id, its detail dimmed, and a badge on the running one."""
    sid, *details = session_label(item)
    lines = [Content.styled(sid, "bold"), *(Content.styled(detail, "$text-muted") for detail in details)]
    if item.get("current"):
        lines.append(Content.styled(" current ", "bold $background on $accent"))
    return Content("\n").join(lines)


class SidebarPanel(Vertical):
    """A heading and a list of sessions; says there are none until a row pushes some."""

    DEFAULT_CSS = """
    SidebarPanel {
        width: 28;
        background: $bh-surface;
        border-right: vkey $bh-border-muted;
        padding: 0 1;
    }
    SidebarPanel > .heading {
        color: $bh-text 70%;  /* readable: 5.7:1 on the surface, where text-muted is 2.6:1 */
        text-style: bold;
        padding: 1 0 1 0;
    }
    SidebarPanel > #sessions {
        height: 1fr;
        background: $bh-surface;
        border: none;
        padding: 0;
        color: $bh-text;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._items: tuple[Mapping[str, Any], ...] | None = None

    def compose(self) -> ComposeResult:
        yield Static("SESSIONS", classes="heading")
        yield OptionList(id="sessions")

    @property
    def items(self) -> tuple[Mapping[str, Any], ...]:
        """The sessions listed, in order."""
        return self._items or ()

    def show_sessions(self, items: Sequence[Mapping[str, Any]]) -> None:
        """List `items` (each with an `id`; `current` marks the running one), or say there are
        none. The same list again changes nothing, so the highlight stays where it was."""
        listed = tuple(items)
        if listed == self._items:
            return
        self._items = listed
        options = [Option(_prompt(item), id=str(item.get("id"))) for item in listed]
        self.query_one("#sessions", OptionList).set_options(options or [Option(_NONE, disabled=True)])

    def focus_list(self) -> None:
        """Focus the list of sessions, so Up, Down and Enter choose one."""
        self.query_one("#sessions", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Say how to continue the chosen session (a note, drawn by the app)."""
        event.stop()
        chosen = next((item for item in self.items if str(item.get("id")) == event.option_id), None)
        if chosen is not None:
            self.post_message(Noted(resume_note(chosen)))
