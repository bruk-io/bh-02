"""The chat row driven with fakes and no runtime."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from chat_cordis_plugin import converse
from chat_cordis_plugin.testing import Angry, Echo, Noted, Screen, Typed


async def test_converse_replies_until_the_input_runs_out() -> None:
    echo, screen = Echo(), Screen()
    await converse(echo, Typed("hello there", "  ", "again", None), screen)  # type: ignore[arg-type]
    assert echo.seen == ["hello there", "again"]  # the blank line was skipped
    assert screen.shown == ["hello there ", "again "]


async def test_converse_shows_a_recoverable_failure_and_carries_on() -> None:
    screen = Screen()
    await converse(Angry(), Typed("one", "two", None), screen)  # type: ignore[arg-type]
    assert screen.notices == ["slow down", "slow down"]


async def test_a_failure_without_the_recoverable_shape_is_a_bug_and_propagates() -> None:
    class Broken:
        async def reply(self, message: str) -> AsyncIterator[str]:
            raise RuntimeError("no kind, no message")
            yield  # pragma: no cover

    with pytest.raises(RuntimeError):
        await converse(Broken(), Typed("hi", None), Screen())  # type: ignore[arg-type]


async def test_a_reply_abandoned_mid_stream_is_closed() -> None:
    """The provider's cleanup runs on close; an output that stops reading must trigger it."""
    closed: list[bool] = []

    class Model:
        async def reply(self, message: str) -> AsyncIterator[str]:
            try:
                yield "a"
                yield "b"
            finally:
                closed.append(True)

    class Impatient:
        async def show(self, chunks: AsyncIterator[str]) -> None:
            async for _ in chunks:
                raise RuntimeError("client went away")

        async def notice(self, message: str) -> None: ...

    with pytest.raises(RuntimeError, match="went away"):
        await converse(Model(), Typed("hi", None), Impatient())  # type: ignore[arg-type]
    assert closed == [True]


async def test_an_interrupt_stops_the_turn_says_so_and_the_session_carries_on() -> None:
    class Endless:
        def __init__(self) -> None:
            self.closed = False

        async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
            try:
                yield {"type": "text", "text": "thinking about " + message}
                await asyncio.Event().wait()  # a reply that never ends on its own
                yield {"type": "text", "text": "never"}  # pragma: no cover
            finally:
                self.closed = True  # a provider's chance to stop its own work

    model, screen, typed = Endless(), Screen(), Typed("first")
    session = asyncio.create_task(converse(model, typed, screen))
    await asyncio.sleep(0.01)
    typed.interrupt()
    await asyncio.sleep(0.01)
    assert model.closed
    assert screen.shown[0] == "thinking about first"
    assert {"type": "stop", "reason": "interrupted"} in screen.events
    typed.type(None)  # and the session is still reading
    await asyncio.wait_for(session, 1)


async def test_a_line_the_commands_claim_goes_to_them_and_never_to_the_model() -> None:
    """Which lines are commands is the `commands` value's to say (`claims`), not the chat's."""
    echo, screen, commands = Echo(), Screen(), Noted("/rows", "!ls", "/model haiku")
    lines = ("/rows", "/tmp/app.py is broken", "!ls", "/model haiku", None)
    await converse(echo, Typed(*lines), screen, commands)  # type: ignore[arg-type]
    assert commands.ran == ["/rows", "!ls", "/model haiku"]
    assert echo.seen == ["/tmp/app.py is broken"]  # not claimed: the model's
    assert {"type": "note", "text": "ran /model haiku"} in screen.events


async def test_what_a_command_holds_for_the_model_goes_with_the_next_message_and_is_not_shown() -> None:
    """`!`'s output (`for_model`) waits for the person's next message, in front of it: commands
    in between keep it, and the message after that has nothing in front of it."""
    echo, screen = Echo(), Screen()
    lines = ("!git status", "/rows", "!ls", "what changed?", "and now?", None)
    await converse(echo, Typed(*lines), screen, Noted())  # type: ignore[arg-type]
    assert echo.seen == [
        "(the person ran git status)\n\n(the person ran ls)\n\nwhat changed?",
        "and now?",
    ]
    assert {"type": "note", "text": "git status printed this"} in screen.events  # shown
    assert not [event for event in screen.events if event.get("type") == "for_model"]  # held


async def test_what_a_command_holds_never_reaches_a_turn_already_running() -> None:
    """A `!` line typed during a turn is read, and run, once the turn has ended, so its output
    goes with the message after it, never into the turn."""

    class Gated:
        def __init__(self) -> None:
            self.seen: list[str] = []
            self.go = asyncio.Event()

        async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
            self.seen.append(message)
            await self.go.wait()
            yield {"type": "text", "text": "done"}

    model, screen, commands, typed = Gated(), Screen(), Noted(), Typed("first")
    session = asyncio.create_task(converse(model, typed, screen, commands))
    await asyncio.sleep(0.01)
    typed.type("!pytest")
    await asyncio.sleep(0.01)
    assert commands.ran == [] and model.seen == ["first"]  # the turn is running: nothing else is
    model.go.set()
    await asyncio.sleep(0.01)
    assert commands.ran == ["!pytest"]
    typed.type("why did it fail?")
    typed.type(None)
    await asyncio.wait_for(session, 1)
    assert model.seen == ["first", "(the person ran pytest)\n\nwhy did it fail?"]


async def test_a_new_conversation_drops_what_was_held_for_the_old_one() -> None:
    echo = Echo()
    await converse(echo, Typed("!ls", "/clear", "hi", None), Screen(), Noted())  # type: ignore[arg-type]
    assert echo.seen == ["hi"]


async def test_a_command_that_answers_with_events_has_them_shown_as_they_are() -> None:
    """`/clear` answers `cleared` then a note: the ui is shown both, in order, and no model."""
    echo, screen = Echo(), Screen()
    await converse(echo, Typed("/clear", None), screen, Noted())  # type: ignore[arg-type]
    assert screen.events == [{"type": "cleared"}, {"type": "note", "text": "cleared"}]
    assert echo.seen == []
