"""Under Pilot: a modal judges a key by when it arrived, not when it was processed. A key typed
while the modal was not answering yet stays dropped even when the app stalls past the grace
period before the key is read (Textual stamps a key where the driver reads it, so a key made
before a stall and posted after it is what a person's queued key is)."""

import asyncio
import time
from collections.abc import Mapping
from typing import Any

from textual.events import Key
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp
from tui_cordis_plugin.messages import Asked
from tui_cordis_plugin.widgets import ApprovalScreen, ChoiceScreen

_SIZE = (120, 36)
_GRACE = 0.3
_CHOICE: Mapping[str, Any] = {
    "title": "Allow net example.com:443?",
    "lines": [],
    "warning": "",
    "choices": [
        {"key": "o", "value": "once", "label": "once"},
        {"key": "n", "value": "no", "label": "no"},
    ],
    "escape": "no",
}


async def _shown(pilot: Pilot[None], kind: type[ApprovalScreen[Any]]) -> ApprovalScreen[Any]:
    for _ in range(40):
        if isinstance(pilot.app.screen, kind):
            return pilot.app.screen
        await pilot.pause(0.02)
    raise AssertionError("the modal never came up")


async def _stall_then_read(app: BhApp, keys: list[Key]) -> None:
    """Hold the event loop past the grace period with `keys` already made, let the grace timer
    expire, then hand the keys to the app: they are processed late, but they arrived early."""
    time.sleep(_GRACE + 0.2)
    await asyncio.sleep(0.1)
    for key in keys:
        app.post_message(key)
    await asyncio.sleep(0.1)


async def test_keys_queued_before_the_grace_ended_do_not_answer_the_approval_when_read_late() -> None:
    app = BhApp(grace=_GRACE)
    async with app.run_test(size=_SIZE) as pilot:
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"name": "python", "input": {"code": "print(1)"}}, answer))
        screen = await _shown(pilot, ApprovalScreen)
        keys = [Key("y", "y"), Key("n", "n"), Key("escape", None)]
        await _stall_then_read(app, keys)
        assert screen.armed  # the grace period is over by the clock
        assert not answer.done() and app.screen is screen
        await pilot.press("y")  # a key that arrives after the grace period answers at once
        assert await asyncio.wait_for(answer, 1) is True


async def test_keys_queued_before_the_grace_ended_do_not_answer_the_choice_when_read_late() -> None:
    app = BhApp(grace=_GRACE)
    async with app.run_test(size=_SIZE) as pilot:
        answer = app.bridge.choice()
        assert answer is not None
        app.post_message(Asked(_CHOICE, answer))
        screen = await _shown(pilot, ChoiceScreen)
        keys = [Key("o", "o"), Key("n", "n"), Key("escape", None)]
        await _stall_then_read(app, keys)
        assert screen.armed
        assert not answer.done() and app.screen is screen
        await pilot.press("o")
        assert await asyncio.wait_for(answer, 1) == "once"
