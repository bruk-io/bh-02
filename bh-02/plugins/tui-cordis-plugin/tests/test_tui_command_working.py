"""While a command runs the screen says so, and for how long, by the reply's line (TASK-0089.10).

A command (`!`, `/compact`) is shown only once it answers, so nothing on the stream says it is
running. The bridge knows: a line handed out and nobody has read since. It tells the app
(`Handling`), which times the same `Working` line while a reply streams or a line is being
handled. These tests drive the real bridge, input and output, with a reader standing for the
chat row (it reads a line, runs the command, shows its answer, reads again), and the clock and
the interval through the seams `BhApp(clock=, working_every=)`."""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from textual.message import Message
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp, Bridge, TuiOutput
from tui_cordis_plugin.app import running
from tui_cordis_plugin.messages import Handling
from tui_cordis_plugin.widgets import Transcript, Working

_SIZE = (80, 20)
_FAST = 0.05  # seconds between ticks


class _Clock:
    """A clock the test sets."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _screen(app: BhApp) -> str:
    return "\n".join(
        "".join(segment.text for segment in app.screen._compositor.render_update(full=True).strips[y])  # noqa: SLF001
        for y in range(app.size.height)
    )


def _line(app: BhApp) -> str | None:
    """The row of the screen that says something is working, if there is one."""
    return next((row.strip() for row in _screen(app).splitlines() if "Working" in row), None)


async def _until(pilot: Pilot[None], done: Callable[[], bool], *, within: float = 3.0) -> None:
    for _ in range(round(within / 0.02)):
        if done():
            return
        await pilot.pause(0.02)
    raise AssertionError("what the test waited for never happened")


def _app(clock: _Clock, every: float = _FAST) -> BhApp:
    return BhApp(clock=clock, working_every=every)


def _read(app: BhApp) -> asyncio.Future[str | None]:
    """The chat row reads its next line (it reads at once after an answer)."""
    return asyncio.ensure_future(app.bridge.line())


async def _handed(app: BhApp, pilot: Pilot[None], line: str) -> asyncio.Future[str | None]:
    """The person sends `line` to a chat row that was reading: it is handed out. Returns the
    chat row's next read, once it has the line."""
    reading = _read(app)
    await pilot.pause()
    app.send(line)
    assert await asyncio.wait_for(reading, 1) == line
    return reading


def _answer(app: BhApp, *events: Mapping[str, Any]) -> asyncio.Future[None]:
    return asyncio.ensure_future(TuiOutput(app.post_message, app.bridge).show(_each(events)))


async def _each(events: tuple[Mapping[str, Any], ...]) -> AsyncIterator[Mapping[str, Any]]:
    for event in events:
        yield event


def _note(text: str) -> Mapping[str, Any]:
    return {"type": "note", "text": text}


def _notes(app: BhApp) -> list[str]:
    return [text for kind, text in app.query_one(Transcript).blocks() if kind == "note"]


# The bridge's side: when it tells the app a line is being handled.


class _Told:
    """Stands in for `app.post_message`: keeps what the bridge told."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def __call__(self, message: Message) -> bool:
        self.messages.append(message)
        return True

    @property
    def said(self) -> list[bool]:
        return [m.busy for m in self.messages if isinstance(m, Handling)]


async def test_the_bridge_tells_the_app_when_a_line_is_handed_out_and_when_it_is_read_again() -> None:
    told = _Told()
    bridge = Bridge(told)
    reading = asyncio.ensure_future(bridge.line())
    await asyncio.sleep(0)
    assert told.said == [] and not bridge.handling  # nobody has typed
    bridge.submit("!sleep 600")
    assert await reading == "!sleep 600"
    assert told.said == [True] and bridge.handling
    bridge.submit("typed meanwhile")  # kept: the command is still the line being handled
    assert told.said == [True]
    asyncio.ensure_future(bridge.line())  # the command answered: the chat row reads again
    await asyncio.sleep(0)
    assert told.said == [True, False, True] and bridge.handling  # the kept line is a new one, handed out
    bridge.submit("later")
    await asyncio.sleep(0)
    assert told.said == [True, False, True]


async def test_a_line_kept_while_nobody_reads_is_handled_once_it_is_read() -> None:
    told = _Told()
    bridge = Bridge(told)
    bridge.submit("early")
    assert told.said == []
    assert await bridge.line() == "early"
    assert told.said == [True]


async def test_an_answer_that_restarts_rows_ends_it_before_the_read_that_waits_for_them() -> None:
    """The chat row reads again only once the restart a command queued is done, so the answer
    is where the command ended."""
    told = _Told()
    bridge = Bridge(told)
    bridge.submit("/model opus")
    assert await bridge.line() == "/model opus"
    assert bridge.handling
    bridge.announce(["loop"])
    assert told.said == [True, False] and not bridge.handling
    bridge.announce(["transcript"])
    assert told.said == [True, False]  # said once
    asyncio.ensure_future(bridge.line())  # the new chat row reads
    await asyncio.sleep(0)
    assert told.said == [True, False] and not bridge.handling


async def test_the_app_ending_ends_it() -> None:
    told = _Told()
    bridge = Bridge(told)
    bridge.submit("!sleep 600")
    assert await bridge.line() == "!sleep 600"
    bridge.end()
    assert told.said == [True, False] and not bridge.handling
    bridge.end()
    assert told.said == [True, False]


# On screen, under Pilot.


async def test_while_a_command_runs_the_screen_says_so_and_for_how_long_and_it_goes_at_its_answer() -> None:
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _handed(app, pilot, "!sleep 600")
        await _until(pilot, lambda: app.query_one(Working).ticking)
        await _until(pilot, lambda: _line(app) == "Working · 0s")
        clock.now += 7
        await _until(pilot, lambda: _line(app) == "Working · 7s")
        clock.now += 58
        await _until(pilot, lambda: _line(app) == "Working · 1m 05s")
        await _answer(app, _note("exit 0"))  # the answer, through output.show
        _read(app)  # and the chat row reads again
        await _until(pilot, lambda: _line(app) is None)
        assert not app.query_one(Working).ticking
        assert "exit 0" in _notes(app)


async def test_a_command_that_shows_its_own_note_and_runs_on_keeps_the_line_through_it() -> None:
    """`/compact` says it is asking the model (through output.show: a stream that starts and
    ends), then runs for as long as the summary takes, then answers."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _handed(app, pilot, "/compact")
        clock.now += 3
        await _until(pilot, lambda: _line(app) == "Working · 3s")
        await _answer(app, _note("asking the model for a summary"))
        await pilot.pause(0.2)
        assert _line(app) is not None and app.query_one(Working).ticking  # the note did not end it
        clock.now += 40
        await _until(pilot, lambda: _line(app) == "Working · 43s")
        await _answer(app, _note("compacted"))
        await pilot.pause(0.2)
        assert _line(app) is not None  # until the chat row has read again
        _read(app)
        await _until(pilot, lambda: _line(app) is None)
        assert _notes(app)[-2:] == ["asking the model for a summary", "compacted"]


async def test_a_command_that_answers_before_the_first_tick_never_shows_the_line() -> None:
    """Most commands answer at once (`/help`): through output.show, as a reply is. No flash, so
    no layout moving."""
    clock = _Clock()
    app = _app(clock, every=0.5)
    async with app.run_test(size=_SIZE) as pilot:
        working = app.query_one(Working)
        await _handed(app, pilot, "/help")
        await _answer(app, _note("the commands"))
        _read(app)
        await pilot.pause(0.7)  # past the first tick it would have had
        assert not working.display and not working.ticking
        assert str(working.content) == ""  # never drawn, not hidden again
        assert "the commands" in _notes(app)


async def test_an_answer_that_restarts_rows_takes_the_line_down_while_they_come_up() -> None:
    """`/model NAME`, `/clear`, `/compact`: the chat row reads again only once the restart is
    done, but the command has answered and its answer says it restarts rows."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _handed(app, pilot, "/model opus")
        clock.now += 5
        await _until(pilot, lambda: _line(app) == "Working · 5s")
        await _answer(app, _note("model: opus"), {"type": "restarting", "rows": ["model", "loop"]})
        await _until(pilot, lambda: _line(app) is None)  # no read has come: the rows are restarting
        assert not app.query_one(Working).ticking
        app.send("typed meanwhile")  # kept for the new chat row
        clock.now += 30  # the restart takes a while
        await pilot.pause(0.2)
        assert _line(app) is None
        assert await asyncio.wait_for(app.bridge.line(), 1) == "typed meanwhile"  # the new chat row
        await _until(pilot, lambda: _line(app) == "Working · 0s")  # a line of its own, from its own start


async def test_a_line_read_right_after_a_reply_counts_from_its_own_start() -> None:
    """A line typed during a reply is kept, and read the moment the reply ends: the line goes
    with the reply and comes back for it, from zero, as for any next reply."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _handed(app, pilot, "!sleep 600")
        clock.now += 20
        await _until(pilot, lambda: _line(app) == "Working · 20s")
        app.send("a second line")  # kept: the command still runs
        await _answer(app, _note("done"))
        assert await asyncio.wait_for(app.bridge.line(), 1) == "a second line"
        await _until(pilot, lambda: _line(app) is None or _line(app) == "Working · 0s")
        clock.now += 4
        await _until(pilot, lambda: _line(app) == "Working · 4s")  # not 24s: its own start


async def test_a_reply_is_one_line_from_the_line_handed_out_and_goes_when_it_ends_and_is_read_past() -> None:
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        release = asyncio.Event()

        async def reply() -> AsyncIterator[Mapping[str, Any]]:
            yield {"type": "tool_call", "id": "c", "name": "python", "input": {"code": "sleep(600)"}}
            await release.wait()
            yield {"type": "tool_result", "call_id": "c", "content": "done", "is_error": False}

        await _handed(app, pilot, "hello")
        reply_task = asyncio.ensure_future(TuiOutput(app.post_message, app.bridge).show(reply()))
        await _until(pilot, lambda: app.query_one(Working).ticking)
        clock.now += 9
        await _until(pilot, lambda: _line(app) == "Working · 9s")
        release.set()
        await reply_task
        _read(app)
        await _until(pilot, lambda: _line(app) is None)
        assert not app.query_one(Working).ticking


async def test_esc_and_ctrl_c_are_as_before_while_a_command_runs_with_the_line_up() -> None:
    """Esc does nothing and says nothing; Ctrl-C is held and, unheard, says a command is
    running and how to leave: neither stops the command, and the line stays until it answers."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _handed(app, pilot, "!sleep 600")
        clock.now += 3
        await _until(pilot, lambda: _line(app) == "Working · 3s")
        before = app.query_one(Transcript).blocks()
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert not app.bridge.interrupt_held and app.query_one(Transcript).blocks() == before
        assert _line(app) is not None
        await pilot.press("ctrl+c")
        await _until(pilot, lambda: any("A command is running" in text for text in _notes(app)))
        assert app.bridge.interrupt_held and _line(app) is not None  # held; the command goes on
        await _answer(app, _note("exit 0"))
        _read(app)  # the read drops the held interrupt
        await _until(pilot, lambda: _line(app) is None)
        assert not app.bridge.interrupt_held


async def test_esc_and_ctrl_c_still_stop_a_reply_and_take_the_line_down_with_it() -> None:
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _handed(app, pilot, "hello")
        output = TuiOutput(app.post_message, app.bridge)

        async def endless() -> AsyncIterator[Mapping[str, Any]]:
            yield {"type": "text", "text": "thinking about it"}
            await asyncio.Event().wait()
            yield {"type": "text", "text": "never"}

        reply_task = asyncio.ensure_future(output.show(endless()))

        async def stopped_by_the_person() -> None:
            """What `chat:converse` does: cancel the reply once the input is interrupted."""
            await app.bridge.interrupted()
            reply_task.cancel()

        stopper = asyncio.ensure_future(stopped_by_the_person())
        clock.now += 2
        await _until(pilot, lambda: _line(app) == "Working · 2s")
        await pilot.press("escape")
        await asyncio.gather(reply_task, stopper, return_exceptions=True)
        _read(app)
        await _until(pilot, lambda: _line(app) is None)


async def test_leaving_while_a_command_runs_with_the_line_up_ends_cleanly() -> None:
    """The app leaves with the command still running (the chat row cancels it on `closed()`): the
    bridge ends, nothing is handled, and nothing the line was timing outlives the app."""
    clock = _Clock()
    app = _app(clock)
    async with running(app, headless=True):
        pilot = Pilot(app)
        await _handed(app, pilot, "!sleep 600")
        clock.now += 2
        await _until(pilot, lambda: _line(app) == "Working · 2s")
        closed = asyncio.ensure_future(app.bridge.closed())
        await pilot.press("ctrl+q")
        await asyncio.wait_for(closed, 3)
        assert app.bridge.ended and not app.bridge.handling
    assert app.return_code in (None, 0)  # it left, it did not crash
