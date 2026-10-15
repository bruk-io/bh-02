"""While a reply runs the screen says so, and for how long (TASK-0089.06): a line above the
composer, redrawn about once a second by a Textual timer that starts and stops with the reply.

The tests drive the clock through the seams `BhApp(clock=, working_every=)`: a clock the test
sets, and an interval short enough to wait for. One test runs at the real clock and the real
interval. Waiting is `pilot.pause` in a short poll (`_until`), never a sleep for as long as a
tick."""

import asyncio
import re
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

import pytest
from textual.command import CommandPalette
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp, TuiOutput, render
from tui_cordis_plugin.messages import Asked, Shown, TurnEnded, TurnStarted
from tui_cordis_plugin.widgets import ApprovalScreen, Completions, Composer, Transcript, Working

_SIZE = (80, 20)
_FAST = 0.05  # seconds between ticks in the tests that set the clock themselves


class _Clock:
    """A clock the test sets: it reads whatever the test last made it."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class _ProviderFailed(Exception):
    pass


def _screen(app: BhApp) -> str:
    """What the terminal shows, as text."""
    return "\n".join(
        "".join(segment.text for segment in app.screen._compositor.render_update(full=True).strips[y])  # noqa: SLF001
        for y in range(app.size.height)
    )


def _line(app: BhApp) -> str | None:
    """The row of the screen that says the reply is working, if there is one."""
    return next((row.strip() for row in _screen(app).splitlines() if "Working" in row), None)


async def _until(pilot: Pilot[None], done: Callable[[], bool], *, within: float = 3.0) -> None:
    """Let the app run until `done()`, polling in short pauses."""
    for _ in range(round(within / 0.02)):
        if done():
            return
        await pilot.pause(0.02)
    raise AssertionError("what the test waited for never happened")


def _app(clock: _Clock, every: float = _FAST) -> BhApp:
    return BhApp(clock=clock, working_every=every)


async def _started(app: BhApp, pilot: Pilot[None]) -> None:
    """A reply began, and the app has taken its start from the clock."""
    app.post_message(TurnStarted())
    await _until(pilot, lambda: app.query_one(Working).ticking)


# The words: pure.


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0, "Working · 0s"),
        (0.9, "Working · 0s"),
        (7, "Working · 7s"),
        (59.9, "Working · 59s"),
        (60, "Working · 1m 00s"),
        (65, "Working · 1m 05s"),
        (3599, "Working · 59m 59s"),
        (3600, "Working · 1h 00m"),
        (3725, "Working · 1h 02m"),
        (-3, "Working · 0s"),  # a clock that went back says nothing odd
    ],
)
def test_the_time_is_seconds_then_minutes_then_hours(seconds: float, said: str) -> None:
    assert render.working_line(seconds) == said


# On screen, under Pilot.


async def test_while_a_reply_runs_the_screen_says_so_and_for_how_long() -> None:
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        assert _line(app) is None  # nothing is running
        await _started(app, pilot)
        await _until(pilot, lambda: _line(app) == "Working · 0s")
        clock.now += 7
        await _until(pilot, lambda: _line(app) == "Working · 7s")  # redrawn by the timer
        clock.now += 58
        await _until(pilot, lambda: _line(app) == "Working · 1m 05s")  # then minutes


async def test_the_line_sits_between_the_transcript_and_the_composer_and_is_one_row() -> None:
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        app.post_message(TurnStarted())
        await _until(pilot, lambda: _line(app) is not None)
        transcript, working, composer = (app.query_one(each) for each in (Transcript, Working, Composer))
        assert working.region.height == 1
        assert transcript.region.bottom <= working.region.y < composer.region.y
        assert working.region.width == _SIZE[0]


async def test_a_timer_draws_it_and_nothing_else_does() -> None:
    """The time on screen changes only when the timer fires: with a long interval a clock that
    moved is not read until the tick, and it is timing (`ticking`) from the reply's start."""
    clock = _Clock()
    app = _app(clock, every=0.4)
    async with app.run_test(size=_SIZE) as pilot:
        working = app.query_one(Working)
        assert not working.ticking
        await _started(app, pilot)
        clock.now += 100  # nothing reads the clock but the tick
        await pilot.pause(0.1)
        assert _line(app) is None
        await _until(pilot, lambda: _line(app) == "Working · 1m 40s")  # the first tick, 0.4 s in
        assert working.ticking


async def test_the_screen_answers_keys_between_ticks() -> None:
    """Nothing waits for the clock: keys typed while it counts reach the composer at once."""
    clock = _Clock()
    app = _app(clock, every=0.4)
    async with app.run_test(size=_SIZE) as pilot:
        app.post_message(TurnStarted())
        await pilot.pause()
        await pilot.press(*"typing on")
        assert app.query_one(Composer).text == "typing on"
        assert app.focused is app.query_one(Composer)


async def test_it_goes_when_the_reply_ends_and_comes_back_for_the_next_counting_from_zero() -> None:
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _started(app, pilot)
        clock.now += 12
        await _until(pilot, lambda: _line(app) == "Working · 12s")
        app.post_message(TurnEnded())
        await _until(pilot, lambda: _line(app) is None)
        assert not app.query_one(Working).ticking
        clock.now += 500  # time passes while nothing runs
        await pilot.pause(0.2)
        assert _line(app) is None  # and nothing draws it
        await _started(app, pilot)
        await _until(pilot, lambda: _line(app) == "Working · 0s")  # the next reply, from its own start
        clock.now += 3
        await _until(pilot, lambda: _line(app) == "Working · 3s")


async def test_replies_overlapping_are_one_line_until_the_last_ends() -> None:
    """The app counts the replies streaming (a sub-agent's note can arrive during one): the
    time is the first one's, and the line stays until none is left."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        await _started(app, pilot)
        clock.now += 5
        await _until(pilot, lambda: _line(app) == "Working · 5s")
        app.post_message(TurnStarted())
        clock.now += 1
        await _until(pilot, lambda: _line(app) == "Working · 6s")
        app.post_message(TurnEnded())
        await pilot.pause(0.2)
        assert _line(app) is not None and app.query_one(Working).ticking
        app.post_message(TurnEnded())
        await _until(pilot, lambda: _line(app) is None)


async def test_a_reply_that_ends_before_the_first_tick_never_shows_it() -> None:
    """A command's answer goes through the same stream as a reply and ends at once: no flash of
    the line, and so no layout moving, for it."""
    clock = _Clock()
    app = _app(clock, every=0.5)
    async with app.run_test(size=_SIZE) as pilot:
        working = app.query_one(Working)
        output = TuiOutput(app.post_message, app.bridge)
        await output.show(render.noted("a command's answer"))
        await pilot.pause(0.7)  # past the first tick the reply would have had
        assert not working.display and not working.ticking
        assert str(working.content) == ""  # never drawn, not just hidden again
        assert ("note", "a command's answer") in app.query_one(Transcript).blocks()


@pytest.mark.parametrize("ending", ["finishes", "is stopped with Esc", "is stopped with Ctrl-C", "fails"])
async def test_it_goes_when_the_reply_finishes_is_stopped_or_fails(ending: str) -> None:
    """Through the real output: a reply waiting on a long tool call (no event arrives) shows the
    line, whichever way it ends takes it down, and the next reply shows it again."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        output = TuiOutput(app.post_message, app.bridge)
        release = asyncio.Event()

        async def reply() -> AsyncIterator[Mapping[str, Any]]:
            yield {"type": "tool_call", "id": "c", "name": "python", "input": {"code": "sleep(600)"}}
            await release.wait()  # the tool runs for minutes: nothing arrives
            if ending == "fails":
                raise _ProviderFailed
            yield {"type": "tool_result", "call_id": "c", "content": "done", "is_error": False}

        turn = asyncio.ensure_future(output.show(reply()))

        async def stopped_by_the_person() -> None:
            """What `chat:converse` does with a reply: stop it once the input is interrupted."""
            await app.bridge.interrupted()
            turn.cancel()

        stopper = asyncio.ensure_future(stopped_by_the_person())
        await _until(pilot, lambda: app.query_one(Working).ticking)
        clock.now += 30
        await _until(pilot, lambda: _line(app) == "Working · 30s")
        if ending.startswith("is stopped"):
            await pilot.press("escape" if "Esc" in ending else "ctrl+c")
        else:
            release.set()
            stopper.cancel()  # nobody interrupts this one
        await asyncio.gather(turn, stopper, return_exceptions=True)
        await _until(pilot, lambda: _line(app) is None)
        assert not app.query_one(Working).ticking
        # and it comes back for the next reply
        app.post_message(TurnStarted())
        await _until(pilot, lambda: _line(app) == "Working · 0s")
        app.post_message(TurnEnded())
        await _until(pilot, lambda: _line(app) is None)


async def test_the_transcript_keeps_its_end_in_view_as_the_line_comes_and_goes() -> None:
    """The line takes a row from the transcript; the transcript, anchored to its end, must
    still show its newest line and follow what comes next."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        for n in range(60):
            app.post_message(Shown({"type": "text", "text": f"line {n}\n\n"}))
        await pilot.pause()
        transcript = app.query_one(Transcript)
        assert transcript.max_scroll_y > 0 and transcript.scroll_y == transcript.max_scroll_y
        app.post_message(TurnStarted())
        await _until(pilot, lambda: _line(app) is not None)
        await pilot.pause()
        assert transcript.scroll_y == transcript.max_scroll_y and "line 59" in _screen(app)
        app.post_message(Shown({"type": "text", "text": "newest while working\n\n"}))
        await pilot.pause()
        assert "newest while working" in _screen(app)
        app.post_message(TurnEnded())
        await _until(pilot, lambda: _line(app) is None)
        await pilot.pause()
        assert transcript.scroll_y == transcript.max_scroll_y and "newest while working" in _screen(app)


_SPECS: list[Mapping[str, Any]] = [{"name": "model", "help": "the model", "usage": "[NAME]"}]


async def test_the_list_of_commands_opens_under_it_and_the_palette_and_a_question_come_over_it() -> None:
    """Nothing it sits beside changes: the list opens between it and the composer, Ctrl-P opens
    the palette and Esc closes it (stopping nothing), a question is a modal and is answered; and
    the line goes on counting through all three."""
    clock = _Clock()
    app = _app(clock)
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(lambda: _SPECS)
        app.post_message(TurnStarted())
        await _until(pilot, lambda: _line(app) is not None)
        composer, working, listed = (
            app.query_one(Composer),
            app.query_one(Working),
            app.query_one(Completions),
        )
        await pilot.press("/")
        await pilot.pause()
        assert listed.is_open and working.region.bottom <= listed.region.y < composer.region.y
        await pilot.press("escape")  # closes the list only: the reply was not asked to stop
        await pilot.pause()
        assert not listed.is_open and app.query_one(Working).ticking
        await pilot.press("ctrl+u")
        await pilot.press("ctrl+p")
        await _until(pilot, lambda: isinstance(app.screen, CommandPalette))
        await pilot.press("escape")
        await _until(pilot, lambda: not isinstance(app.screen, CommandPalette))
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"tool": "bash", "input": {"command": "ls"}}, answer))
        await _until(pilot, lambda: isinstance(app.screen, ApprovalScreen) and app.screen.armed)
        await pilot.press("n")
        assert await asyncio.wait_for(answer, 1) is False
        await _until(pilot, lambda: not isinstance(app.screen, ApprovalScreen))
        clock.now += 20
        await _until(pilot, lambda: _line(app) == "Working · 20s")


async def test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts() -> None:
    """The defaults, undriven: about once a second, so nothing for the first moments, then
    the seconds."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.post_message(TurnStarted())
        await pilot.pause(0.4)
        assert _line(app) is None
        await _until(pilot, lambda: _line(app) is not None, within=3.0)
        assert re.fullmatch(r"Working · [12]s", _line(app) or "")
        await _until(pilot, lambda: _line(app) == "Working · 2s", within=3.0)
        app.post_message(TurnEnded())
        await _until(pilot, lambda: _line(app) is None)
