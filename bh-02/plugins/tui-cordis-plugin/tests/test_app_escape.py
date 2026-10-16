"""Under Pilot: Esc stops a running reply as Ctrl-C does (TASK-0089.03), and which layer wins
when another wants it: the composer's list of commands, a question and the palette each take
Esc first, and only that."""

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from textual.command import CommandPalette
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp
from tui_cordis_plugin.messages import Asked
from tui_cordis_plugin.widgets import ApprovalScreen, Completions, Composer, Transcript

_SIZE = (100, 30)

_SPECS: list[Mapping[str, Any]] = [{"name": "model", "help": "the model", "usage": "[NAME]"}]


def _blocks(app: BhApp) -> list[tuple[str, str]]:
    return app.query_one(Transcript).blocks()


async def _reply_running(app: BhApp, pilot: Pilot[None]) -> asyncio.Future[None]:
    """A turn waiting to hear Ctrl-C, as `chat:converse` waits during a reply."""
    turn = asyncio.ensure_future(app.bridge.interrupted())
    await pilot.pause()
    assert app.bridge.turn_running
    return turn


async def _armed(pilot: Pilot[None]) -> None:
    """Wait until the modal up answers keys (it drops them for a moment after it is shown)."""
    for _ in range(40):
        if isinstance(pilot.app.screen, ApprovalScreen) and pilot.app.screen.armed:
            return
        await pilot.pause(0.05)
    raise AssertionError("the approval modal never began answering keys")


def _ask(app: BhApp) -> asyncio.Future[bool]:
    answer = app.bridge.question()
    assert answer is not None
    app.post_message(Asked({"tool": "bash", "input": {"command": "ls"}}, answer))
    return answer


@pytest.mark.parametrize("key", ["ctrl+c", "escape"])
async def test_esc_stops_a_running_reply_exactly_as_ctrl_c_does(key: str) -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        turn = await _reply_running(app, pilot)
        await pilot.press(*"my draft")
        before = _blocks(app)
        await pilot.press(key)
        await asyncio.wait_for(turn, 1)  # the turn heard it
        await pilot.pause()
        assert _blocks(app) == before  # nothing said: the turn's own stop line is the reply's
        assert app.return_code is None
        composer = app.query_one(Composer)
        assert composer.text == "my draft" and app.focused is composer


async def test_esc_with_nothing_running_does_nothing_to_the_composer_or_anywhere() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        composer = app.query_one(Composer)
        await pilot.press(*"my draft", "left", "left")
        before, cursor = _blocks(app), composer.cursor_location
        await pilot.press("escape")
        await pilot.pause()
        assert composer.text == "my draft" and composer.cursor_location == cursor
        assert app.focused is composer
        assert _blocks(app) == before  # Ctrl-C would say "Nothing is running"; Esc says nothing
        assert not app.bridge.interrupt_held


async def test_esc_while_a_command_runs_does_not_hold_an_interrupt_for_the_next_turn() -> None:
    """A line handed out with no turn listening (a `!` command) is not a reply: Ctrl-C holds
    an interrupt for it and says it can't stop it, Esc is not a stop key for it."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"!sleep 600", "enter")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "!sleep 600"
        before = _blocks(app)
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert not app.bridge.interrupt_held and _blocks(app) == before


async def test_esc_stops_a_running_reply_with_the_focus_away_from_the_composer() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        turn = await _reply_running(app, pilot)
        await pilot.press("tab")  # the focus leaves the composer
        await pilot.pause()
        assert not isinstance(app.focused, Composer)
        await pilot.press("escape")
        await asyncio.wait_for(turn, 1)


async def test_esc_closes_the_list_of_commands_first_and_only_that_then_stops_the_reply() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(lambda: _SPECS)
        turn = await _reply_running(app, pilot)
        await pilot.press(*"/mo")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert listed.display
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not listed.display and app.query_one(Composer).text == "/mo"
        assert not turn.done()  # Esc closed the list, and nothing more
        await pilot.press("escape")  # the list is shut for this line: the reply is next
        await asyncio.wait_for(turn, 1)
        assert app.query_one(Composer).text == "/mo"


async def test_esc_declines_a_question_and_only_that_the_reply_runs_on() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE) as pilot:
        turn = await _reply_running(app, pilot)
        answer = _ask(app)
        await _armed(pilot)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert await answer is False and not app.asking
        assert not turn.done() and app.bridge.turn_running  # declined, not stopped
        await pilot.press("escape")  # nothing nearer wants it now
        await asyncio.wait_for(turn, 1)


async def test_esc_in_a_question_s_first_moments_is_dropped_and_does_not_stop_the_reply() -> None:
    app = BhApp(grace=5.0)  # still arming: its keys are dropped
    async with app.run_test(size=_SIZE) as pilot:
        turn = await _reply_running(app, pilot)
        answer = _ask(app)
        await pilot.pause(0.1)
        assert isinstance(app.screen, ApprovalScreen) and not app.screen.armed
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not answer.done() and app.asking and not turn.done()
        await pilot.press("ctrl+c")  # Ctrl-C is the one that still works at once
        await asyncio.wait_for(turn, 1)


async def test_esc_closes_the_palette_and_only_that_the_reply_runs_on() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        turn = await _reply_running(app, pilot)
        await pilot.press("ctrl+p")
        await pilot.pause(0.2)
        assert isinstance(app.screen, CommandPalette)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, CommandPalette)
        assert not turn.done()
        await pilot.press("escape")
        await asyncio.wait_for(turn, 1)
