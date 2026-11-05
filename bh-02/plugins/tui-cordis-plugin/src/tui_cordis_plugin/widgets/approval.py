"""The approval modal: a call put to the person, with any code it carries shown whole and
highlighted. A modal traps focus: keys reach only it until it is answered or withdrawn.

It answers nothing for its first `GRACE` seconds. A person typing a message when an input comes
up would otherwise answer it with whatever they typed next (the `n` of "Run now", declining the
input). Keys pressed in that moment are dropped: the modal holds focus, so they never reach the
composer beneath either, and once it is answered the composer has exactly what was typed before
it came up. Ctrl-C, the app's own priority binding, still stops the reply at once.

A key is judged by when it arrived (Textual stamps it where the driver reads it), against when
the modal was first painted, not by when the app gets round to it: a stalled app can read a key
typed ahead after the grace period is over by the clock, and it must still be dropped.
"""

from collections.abc import Mapping
from typing import Any

from textual._time import get_time  # the clock a Key's `time` is read from
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from tui_cordis_plugin import render

__all__ = ["GRACE", "ApprovalScreen"]

# How long a modal just shown ignores y, n and Escape: long enough to cover keys a person was
# already typing (a fast typist is at 10 keys a second), short enough not to be noticed.
GRACE = 0.4


def _answers(arrived: float, shown: float | None, grace: float) -> bool:
    """Whether a key that arrived at `arrived` may answer a modal first painted at `shown`
    (None: not painted yet, so no key may)."""
    return shown is not None and arrived >= shown + grace


class ApprovalScreen[T = bool](ModalScreen[T]):
    """Yes or no about one call (CONTRACTS.md: question). `y` allows; `n` or Escape declines,
    when the key arrived `grace` seconds or more after the modal was shown (`GRACE` unless the
    app says otherwise). Before then its keys line is dimmed and those keys are dropped.

    Ctrl-C (the app's priority binding) withdraws it, as a no, and interrupts the reply.

    The arming, the layout and the keys line are shared with `ChoiceScreen`, which answers a
    choice's value instead of a bool: `T` is what the modal dismisses with.
    """

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
    ApprovalScreen .approval-line {
        padding: 1 0 0 0;
    }
    ApprovalScreen #approval-warning {
        color: $bh-warning;
        text-style: bold;
        padding: 1 0 0 0;
    }
    ApprovalScreen #approval-keys {
        color: $bh-text 70%;  /* readable: 5.2:1 on the overlay, where text-muted is 2.2:1 */
        padding: 1 0;
    }
    ApprovalScreen #approval-keys.-arming {
        color: $bh-text 35%;  /* not answering yet: the keys typed ahead are being dropped */
    }
    """

    def __init__(self, question: Mapping[str, Any], *, grace: float = GRACE) -> None:
        super().__init__()
        self.question = question
        self._grace = grace
        self._shown: float | None = None
        self._answered = False

    def compose(self) -> ComposeResult:
        code = render.approval_lines(self.question)
        with Vertical(id="approval", classes="-code" if code else ""):
            yield Static(render.approval_heading(self.question), id="approval-title", markup=False)
            if code:
                with VerticalScroll(id="approval-code"):
                    # highlighted as the chat view highlights code: the theme's colours
                    yield Static(
                        render.code("\n".join(code), render.approval_language(self.question)),
                        id="approval-source",
                    )
            yield Static(
                "y  allow     n / Esc  decline     Ctrl-C  stop the reply",
                id="approval-keys",
                classes="-arming",
                markup=False,
            )

    def on_mount(self) -> None:
        # the code scrolls with the arrow keys; y and n still reach the screen
        for scroll in self.query("#approval-code"):
            scroll.focus()
        self.call_after_refresh(self._stamp)

    def _stamp(self) -> None:
        """The modal is on screen: the grace period runs from here."""
        self._shown = get_time()
        self.set_timer(self._grace, self._undim)

    def _undim(self) -> None:
        # display only: keys are judged by `_answers`, not by this timer
        self.query_one("#approval-keys").remove_class("-arming")

    @property
    def armed(self) -> bool:
        """Whether a key arriving now would answer (`grace` after the modal was shown)."""
        return _answers(get_time(), self._shown, self._grace)

    def _key_answer(self, key: str) -> T | None:
        """What `key` answers, or None when it is no answer's key."""
        match key:
            case "y":
                return True  # type: ignore[return-value]
            case "n" | "escape":
                return False  # type: ignore[return-value]
            case _:
                return None

    def on_key(self, event: Key) -> None:
        """An answer's key answers if it arrived after the grace period; either way it goes no
        further (a key dropped while arming must not reach the app's bindings, Escape's among
        them)."""
        answer = self._key_answer(event.key.lower())
        if answer is None:
            return
        event.stop()
        event.prevent_default()
        if not self._answered and _answers(event.time, self._shown, self._grace):
            self._answered = True
            self.dismiss(answer)
