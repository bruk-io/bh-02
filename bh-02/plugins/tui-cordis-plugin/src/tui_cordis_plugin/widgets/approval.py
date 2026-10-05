"""The approval modal: a call put to the person, with any code it carries shown whole and
highlighted. A modal traps focus: keys reach only it until it is answered or withdrawn.

It answers nothing for its first `GRACE` seconds. A person typing a message when an input comes
up would otherwise answer it with whatever they typed next (the `n` of "Run now", declining the
input). Keys pressed in that moment are dropped: the modal holds focus, so they never reach the
composer beneath either, and once it is answered the composer has exactly what was typed before
it came up. Ctrl-C, the app's own priority binding, still stops the turn at once.
"""

from collections.abc import Mapping
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from tui_cordis_plugin import render

__all__ = ["GRACE", "ApprovalScreen"]

# How long a modal just shown ignores y, n and Escape: long enough to cover keys a person was
# already typing (a fast typist is at 10 keys a second), short enough not to be noticed.
GRACE = 0.4


class ApprovalScreen(ModalScreen[bool]):
    """Yes or no about one call (CONTRACTS.md: request). `y` allows; `n` or Escape declines,
    once it is `armed`: `grace` seconds after it is shown (`GRACE` unless the app says
    otherwise). Until then its keys line is dimmed and those keys are dropped.

    Ctrl-C (the app's priority binding) withdraws it, as a no, and interrupts the turn.
    """

    BINDINGS = [
        Binding("y", "answer(True)", "Allow"),
        Binding("n", "answer(False)", "Decline"),
        Binding("escape", "answer(False)", "Decline", show=False),
    ]

    DEFAULT_CSS = """
    ApprovalScreen {
        align: center middle;
        background: $bh-bg 45%;
    }
    ApprovalScreen > #approval {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 70%;
        border: round $bh-primary;
        background: $bh-surface-overlay;
        color: $bh-text;
        padding: 0 1;
    }
    ApprovalScreen #approval-title {
        color: $bh-text-bright;
        text-style: bold;
        padding: 1 0 0 0;
    }
    /* with code, the title and the keys are docked, so they always show; the code takes what
       is left and scrolls within it, however long the input and however small the terminal.
       Without code they stay in the flow: an auto-height box counts only undocked children, so
       docking both would collapse it to its border and hide the question. */
    ApprovalScreen > #approval.-code #approval-title {
        dock: top;
    }
    ApprovalScreen > #approval.-code #approval-keys {
        dock: bottom;
    }
    ApprovalScreen #approval-code {
        height: auto;
        max-height: 100%;
        background: $bh-surface-recessed;
        margin: 1 0 0 0;
        padding: 0 1;
    }
    ApprovalScreen #approval-keys {
        color: $bh-text 70%;  /* readable: 5.2:1 on the overlay, where text-muted is 2.2:1 */
        padding: 1 0;
    }
    ApprovalScreen #approval-keys.-arming {
        color: $bh-text 35%;  /* not answering yet: the keys typed ahead are being dropped */
    }
    """

    def __init__(self, request: Mapping[str, Any], *, grace: float = GRACE) -> None:
        super().__init__()
        self.request = request
        self._grace = grace
        self._armed = False

    def compose(self) -> ComposeResult:
        code = render.approval_lines(self.request)
        with Vertical(id="approval", classes="-code" if code else ""):
            yield Static(render.approval_title(self.request), id="approval-title", markup=False)
            if code:
                with VerticalScroll(id="approval-code"):
                    # highlighted as the transcript highlights code: the theme's colours
                    yield Static(render.code("\n".join(code)), id="approval-source")
            yield Static(
                "y  allow     n / Esc  decline     Ctrl-C  stop the turn",
                id="approval-keys",
                classes="-arming",
                markup=False,
            )

    def on_mount(self) -> None:
        # the code scrolls with the arrow keys; y and n still reach the screen
        for scroll in self.query("#approval-code"):
            scroll.focus()
        self.set_timer(self._grace, self._arm)

    @property
    def armed(self) -> bool:
        """Whether y, n and Escape answer yet (`grace` after the modal was shown)."""
        return self._armed

    def _arm(self) -> None:
        self._armed = True
        self.query_one("#approval-keys").remove_class("-arming")

    def action_answer(self, allowed: bool) -> None:
        """Answer, unless the modal was shown too recently for the key to be meant for it."""
        if self._armed:
            self.dismiss(allowed)
