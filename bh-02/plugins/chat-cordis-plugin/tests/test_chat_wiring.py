"""The chat row on a runtime: a port swap, a failure reaching the bootstrap."""

import asyncio

import pytest

from chat_cordis_plugin.testing import Echo, Noted, Queued, Screen, Typed
from chat_cordis_plugin.wiring import converse
from cordis import Effects, Inspection, Runtime, State, bind, component


def model_row(what: object) -> object:
    @component
    async def loop() -> Effects:
        yield bind("loop", what)

    return loop


def ui_row(input: object, output: object) -> object:
    @component
    async def ui() -> Effects:
        yield bind("input", input)
        yield bind("output", output)

    return ui


@component
async def commands_row() -> Effects:
    """The commands and jobs a session also needs, a row of its own as in a real composition."""
    yield bind("commands", Noted())
    yield bind("jobs", Queued())


async def test_the_session_ends_when_the_input_runs_out() -> None:
    echo, screen = Echo(), Screen()
    rt = Runtime()
    rt.mount(model_row(echo), id="loop")
    rt.mount(ui_row(Typed("hello", None), screen), id="ui")
    rt.mount(commands_row, id="commands")
    rt.mount(converse, id="chat")
    await asyncio.wait_for(rt.idle(), 2)  # returns when the loop has ended: nothing left running
    assert screen.shown == ["hello "]
    await rt.shutdown()


async def test_replacing_the_ui_restarts_the_loop_and_keeps_the_conversation() -> None:
    echo = Echo()
    first, second = Screen(), Screen()
    rt = Runtime()
    loop = rt.mount(model_row(echo), id="loop")
    ui = rt.mount(ui_row(Typed("to the first"), first), id="ui")
    rt.mount(commands_row, id="commands")
    chat = rt.mount(converse, id="chat")
    await rt.settle()
    await asyncio.sleep(0.01)
    assert first.shown == ["to the first "]

    await ui.retire()  # the chat row waits: its ports are gone
    await rt.settle()
    assert chat.state is State.INACTIVE
    assert Inspection(rt).waiting_on(chat) == ["input", "output"]

    rt.mount(ui_row(Typed("to the second", None), second), id="ui")
    await asyncio.wait_for(rt.idle(), 2)
    assert second.shown == ["to the second "]
    assert echo.seen == ["to the first", "to the second"]  # one conversation, two interfaces
    assert Inspection(rt).fiber("loop") is loop  # the model never restarted
    await rt.shutdown()


async def test_what_a_command_left_for_the_model_survives_the_chat_row_s_restart() -> None:
    """`/model` reloads the loop, and the chat row with it: `!`'s output, held by `commands`
    (a row that does not reload), still goes with the person's next message."""
    commands, typed, screen = Noted(), Typed("!git diff"), Screen()
    first, second = Echo(), Echo()

    @component
    async def held_commands() -> Effects:
        yield bind("commands", commands)
        yield bind("jobs", Queued())

    rt = Runtime()
    loop = rt.mount(model_row(first), id="loop")
    rt.mount(ui_row(typed, screen), id="ui")
    rt.mount(held_commands, id="commands")
    chat = rt.mount(converse, id="chat")
    await rt.settle()
    await asyncio.sleep(0.01)
    assert commands.ran == ["!git diff"]
    await loop.retire()  # a model switch: the chat row goes down with the loop
    await rt.settle()
    assert chat.state is State.INACTIVE
    rt.mount(model_row(second), id="loop")
    typed.type("review this")
    typed.type(None)
    await asyncio.wait_for(rt.idle(), 2)
    assert first.seen == []
    assert second.seen == ["(the person ran git diff)\n\nreview this"]
    await rt.shutdown()


async def test_an_unexpected_failure_in_the_loop_reaches_the_bootstrap() -> None:
    class Broken:
        async def read(self) -> str | None:
            raise RuntimeError("the terminal fell over")

        async def interrupted(self) -> None:
            await asyncio.Event().wait()

        async def closed(self) -> None:
            await asyncio.Event().wait()

    rt = Runtime()
    rt.mount(model_row(Echo()), id="loop")
    rt.mount(ui_row(Broken(), Screen()), id="ui")
    rt.mount(commands_row, id="commands")
    rt.mount(converse, id="chat")
    with pytest.raises(RuntimeError, match="the terminal fell over"):
        await asyncio.wait_for(rt.idle(), 2)
    await rt.shutdown()


async def test_a_row_bound_to_the_wrong_shape_fails_the_chat_at_load_with_a_message() -> None:
    rt = Runtime()
    rt.mount(model_row("not a model"), id="loop")
    rt.mount(ui_row(Typed(), Screen()), id="ui")
    rt.mount(commands_row, id="commands")
    chat = rt.mount(converse, id="chat")
    await rt.settle()
    assert chat.state is State.FAILED
    assert "chat: loop is bound to a str, which is missing reply" in str(chat.error)
    await rt.shutdown()


async def test_a_line_typed_during_a_restart_a_command_queued_reaches_the_new_loop() -> None:
    """`/clear` queues the loop's restart in `jobs` and answers; the chat row reads its next line
    only once that is done, so a line typed meanwhile is not read by the row the restart takes
    down (the old loop never sees it, and it is not dropped): the new row reads it, for the new
    loop."""
    pending = Queued()

    class Restarting(Noted):
        async def run(self, line: str) -> str | list[dict[str, object]]:
            pending.hold()  # the command queued a restart
            return await super().run(line)

    @component
    async def commands_and_jobs() -> Effects:
        yield bind("commands", Restarting())
        yield bind("jobs", pending)

    typed, screen, first, second = Typed("/clear", "again"), Screen(), Echo(), Echo()
    rt = Runtime()
    loop = rt.mount(model_row(first), id="loop")
    rt.mount(ui_row(typed, screen), id="ui")
    rt.mount(commands_and_jobs, id="commands")
    rt.mount(converse, id="chat")
    await rt.settle()
    await asyncio.sleep(0.01)
    assert first.seen == []  # waiting on the restart, not reading `again`
    await loop.retire()  # the restart: the chat row goes down with the loop, holding no line
    rt.mount(model_row(second), id="loop")
    await rt.settle()
    pending.done()
    typed.type(None)
    await asyncio.wait_for(rt.idle(), 2)
    assert first.seen == [] and second.seen == ["again"]
    await rt.shutdown()
