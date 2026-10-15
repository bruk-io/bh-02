"""The Working line: one line above the composer that says a reply is running and for how long.

It is drawn by a Textual timer (`set_interval`), started with the reply and stopped with it:
nothing waits or loops, and between ticks nothing runs. Its first tick comes a whole interval
after the reply began, and until then it is hidden: a reply that ends within a second, such as
a command's answer (it goes through the same stream), never shows it, so the layout does not
flash. The time and the interval are what the app gives it (`BhApp(clock=, working_every=)`), so
a test drives them.
"""

import time
from collections.abc import Callable

from textual.timer import Timer
from textual.widgets import Static

from tui_cordis_plugin import render

__all__ = ["WORKING_EVERY", "Working"]

WORKING_EVERY = 1.0  # seconds between the redraws of the time


class Working(Static):
    """Says a reply is running, and for how long, from `begin` until `end`."""

    DEFAULT_CSS = """
    Working {
        display: none;
        height: 1;
        padding: 0 2;
        color: $bh-text 70%;
    }
    """

    def __init__(
        self,
        *,
        id: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        every: float = WORKING_EVERY,
    ) -> None:
        super().__init__(id=id, markup=False)
        self._clock = clock
        self._every = every
        self._began = 0.0
        self._timer: Timer | None = None

    @property
    def ticking(self) -> bool:
        """Whether a reply is being timed (between `begin` and `end`)."""
        return self._timer is not None

    def begin(self) -> None:
        """A reply started: time it from now. Already timing one, it keeps its start."""
        if self._timer is None:
            self._began = self._clock()
            self._timer = self.set_interval(self._every, self._tick)

    def end(self) -> None:
        """The reply ended, whichever way (finished, stopped, failed): stop timing, hide the line."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.display = False

    def _tick(self) -> None:
        self.update(render.working_line(self._clock() - self._began))
        self.display = True
