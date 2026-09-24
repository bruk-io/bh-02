"""What the input, output and frame post to the app: the only way anything outside it reaches the screen.

They run in cordis's coroutines, outside the app's own task, where Textual's context
(the active app) is not set; a posted message is handled inside the app, where it is. So the
screen is only ever touched by the app, and a failure while drawing is the app's to report.
"""

import asyncio
from collections.abc import Mapping
from typing import Any

from textual.message import Message

__all__ = ["Asked", "FrameChanged", "Noted", "RowsUp", "Shown", "TurnEnded", "TurnStarted", "Withdrawn"]


class Shown(Message):
    """Events of a turn (CONTRACTS.md: event), in order, to draw as they stream in. `drawn`,
    when given, is settled once the app has drawn them, so the output posts no faster than
    the app draws (and a Ctrl-C never waits behind a queue of them)."""

    def __init__(self, *events: Mapping[str, Any], drawn: asyncio.Future[None] | None = None) -> None:
        super().__init__()
        self.events = events
        self.drawn = drawn


class TurnStarted(Message):
    """A reply began streaming: a line the person types from now until it ends is drawn after it."""


class TurnEnded(Message):
    """A reply's stream ended: whatever streams next starts a block of its own."""


class Noted(Message):
    """Something bh-02 itself says: a note, a failure the person can recover from, a reload."""

    def __init__(self, text: str, kind: str = "note") -> None:
        super().__init__()
        self.text = text
        self.kind = kind


class Asked(Message):
    """A yes-or-no question about a call; the answer goes in `answer`."""

    def __init__(self, request: Mapping[str, Any], answer: asyncio.Future[bool]) -> None:
        super().__init__()
        self.request = request
        self.answer = answer


class FrameChanged(Message):
    """Something a row pushed into the frame changed; `what` is its kind (`status`,
    `commands`, `sessions`), so the app redraws only what that kind shows."""

    def __init__(self, what: str) -> None:
        super().__init__()
        self.what = what


class RowsUp(Message):
    """Every row that was coming (back) up is up, or down for good: a status field kept on
    screen meanwhile can go, unless rows start coming up again first."""


class Withdrawn(Message):
    """A question nobody waits for any more (its turn was interrupted): take its modal down,
    or drop it from the queue if it was not shown yet."""

    def __init__(self, answer: asyncio.Future[bool]) -> None:
        super().__init__()
        self.answer = answer
