"""The chat row driven with fakes and no runtime."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from chat_cordis_plugin import converse, is_command
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


async def test_a_command_goes_to_the_commands_and_never_to_the_model() -> None:
    echo, screen, commands = Echo(), Screen(), Noted()
    await converse(echo, Typed("/rows", "/tmp/app.py is broken", "/model haiku", None), screen, commands)  # type: ignore[arg-type]
    assert commands.ran == ["/rows", "/model haiku"]
    assert echo.seen == ["/tmp/app.py is broken"]  # a path is not a command
    assert {"type": "note", "text": "ran /model haiku"} in screen.events


async def test_a_command_that_answers_with_events_has_them_shown_as_they_are() -> None:
    """`/clear` answers `cleared` then a note: the ui is shown both, in order, and no model."""
    echo, screen = Echo(), Screen()
    await converse(echo, Typed("/clear", None), screen, Noted())  # type: ignore[arg-type]
    assert screen.events == [{"type": "cleared"}, {"type": "note", "text": "cleared"}]
    assert echo.seen == []


class Streaming:
    """A `commands` value whose every command answers as it goes (`/compact`): a note, then
    nothing more until `done` is set; `closed` says whether its answer was closed."""

    def __init__(self) -> None:
        self.done = asyncio.Event()
        self.closed = False

    async def run(self, line: str) -> AsyncIterator[dict[str, Any]]:
        return self._answer(line)

    async def _answer(self, line: str) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {"type": "note", "text": f"working on {line}"}
            await self.done.wait()
            yield {"type": "note", "text": "done"}
        finally:
            self.closed = True


async def test_a_command_that_answers_as_it_goes_is_shown_as_it_comes() -> None:
    commands, screen = Streaming(), Screen()
    commands.done.set()
    await converse(Echo(), Typed("/compact", None), screen, commands)  # type: ignore[arg-type]
    assert screen.events == [
        {"type": "note", "text": "working on /compact"},
        {"type": "note", "text": "done"},
    ]
    assert commands.closed


async def test_ctrl_c_stops_a_command_that_answers_as_it_goes_and_the_session_carries_on() -> None:
    """Stopped as a reply is: its answer closed, so the command stops what it runs."""
    commands, screen, typed = Streaming(), Screen(), Typed("/compact")
    session = asyncio.create_task(converse(Echo(), typed, screen, commands))  # type: ignore[arg-type]
    await asyncio.sleep(0.01)
    assert screen.events == [{"type": "note", "text": "working on /compact"}]
    typed.interrupt()
    await asyncio.sleep(0.01)
    assert commands.closed
    assert screen.events[-1] == {"type": "stop", "reason": "interrupted"}
    typed.type(None)  # and the session is still reading
    await asyncio.wait_for(session, 1)


async def test_the_input_ending_stops_a_command_that_answers_as_it_goes() -> None:
    """The ui gone (Ctrl-Q): `interrupted()` returns at once, the answer is closed and the chat
    ends, rather than wait for the command (a summary that takes minutes)."""

    class Ending(Typed):
        """An input that, once `ended`, reads None and hears an interrupt at once, as the
        app's does once it has ended."""

        def __init__(self) -> None:
            super().__init__()
            self.ended = asyncio.Event()

        async def read(self) -> str | None:
            return "/compact" if not self.ended.is_set() else None

        async def interrupted(self) -> None:
            await self.ended.wait()

    typed, commands = Ending(), Streaming()
    session = asyncio.create_task(converse(Echo(), typed, Screen(), commands))  # type: ignore[arg-type]
    await asyncio.sleep(0.01)
    typed.ended.set()
    await asyncio.wait_for(session, 1)
    assert commands.closed and not commands.done.is_set()


def test_what_counts_as_a_command() -> None:
    assert is_command("/help") and is_command("  /model haiku ") and is_command("/new-thing x")
    assert not is_command("/tmp/x.py") and not is_command("/") and not is_command("hi /help")
    assert not is_command("/2fast") and not is_command("")
