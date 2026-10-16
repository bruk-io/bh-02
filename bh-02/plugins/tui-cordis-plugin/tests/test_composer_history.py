"""Under Pilot: Up and Down in the composer go back and forward through the lines sent this run
(TASK-0089.02), and which layer wins when another wants the key: the slash list's Up and Down
come first, and a question up keeps the keys from the composer altogether."""

import asyncio
from collections.abc import Mapping
from typing import Any

from textual.app import App
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp
from tui_cordis_plugin.frame import PaletteEntry
from tui_cordis_plugin.messages import Asked
from tui_cordis_plugin.widgets import ApprovalScreen, Completions, Composer

_SIZE = (100, 30)

_SPECS: list[Mapping[str, Any]] = [
    {
        "name": "model",
        "help": "show or switch the model",
        "usage": "[NAME]",
        "choices": lambda: [{"args": "haiku", "help": "h"}, {"args": "opus", "help": "o"}],
    },
]


def _composer(app: App[None]) -> Composer:
    return app.query_one(Composer)


async def _send(pilot: Pilot[None], *lines: str) -> None:
    """Type each line and press Enter; the lines pile up in the bridge, unread."""
    for line in lines:
        for part_number, part in enumerate(line.split("\n")):
            if part_number:
                await pilot.press("ctrl+j")
            await pilot.press(*part)
        await pilot.press("enter")
    await pilot.pause()


async def _shown(pilot: Pilot[None], key: str) -> str:
    await pilot.press(key)
    await pilot.pause()
    return _composer(pilot.app).text


async def test_up_walks_back_through_the_lines_sent_and_down_forward_to_the_draft() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "one", "two")
        await pilot.press(*"dra")
        assert await _shown(pilot, "up") == "two"
        assert await _shown(pilot, "up") == "one"
        assert await _shown(pilot, "up") == "one"  # nothing older: the text stays
        assert await _shown(pilot, "down") == "two"
        assert await _shown(pilot, "down") == "dra"  # past the newest: the draft being typed
        assert await _shown(pilot, "down") == "dra"  # not recalling: Down is the text area's
        assert _composer(app).cursor_location == (0, 3)


async def test_a_recalled_line_has_the_cursor_at_its_end_and_focus_stays() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "hello there")
        await pilot.press("up")
        await pilot.pause()
        assert _composer(app).cursor_location == (0, len("hello there"))
        assert app.focused is _composer(app)


async def test_with_nothing_sent_up_and_down_only_move_the_cursor_as_before() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"ab")
        assert await _shown(pilot, "up") == "ab"
        assert _composer(app).cursor_location == (0, 0)  # the text area's own Up on the first line
        assert await _shown(pilot, "down") == "ab"
        assert _composer(app).cursor_location == (0, 2)


async def test_a_message_a_command_and_a_shell_line_are_all_recalled() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "fix the bug", "/rows", "!git status")
        assert [await _shown(pilot, "up") for _ in range(3)] == ["!git status", "/rows", "fix the bug"]


async def test_a_command_run_from_the_list_or_the_palette_is_recalled_as_sent() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "earlier")
        await pilot.press(*"/he")
        await pilot.pause()
        await pilot.press("enter")  # takes the highlighted /help: it is what was sent
        await pilot.pause()
        assert await asyncio.wait_for(app.bridge.line(), 1) == "earlier"
        assert await asyncio.wait_for(app.bridge.line(), 1) == "/help"
        app.choose(PaletteEntry("/rows", "the composition"))  # the palette's choice
        await pilot.pause()
        assert [await _shown(pilot, "up") for _ in range(3)] == ["/rows", "/help", "earlier"]


async def test_an_edited_recalled_line_is_sent_as_edited_and_added_never_changed_in_place() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "hello world")
        assert await _shown(pilot, "up") == "hello world"
        await pilot.press(*["backspace"] * 5, *"there")
        assert _composer(app).text == "hello there"
        await pilot.press("enter")
        await pilot.pause()
        assert await asyncio.wait_for(app.bridge.line(), 1) == "hello world"
        assert await asyncio.wait_for(app.bridge.line(), 1) == "hello there"  # what was sent
        assert _composer(app).text == ""
        assert [await _shown(pilot, "up") for _ in range(3)] == ["hello there", "hello world", "hello world"]


async def test_sending_a_line_ends_the_walk_the_next_up_starts_from_the_newest() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "a", "b", "c")
        assert await _shown(pilot, "up") == "c"
        assert await _shown(pilot, "up") == "b"
        await pilot.press("enter")  # sends "b" again
        await pilot.pause()
        assert await _shown(pilot, "up") == "b"  # the newest line sent, not the one after "b"
        assert await _shown(pilot, "up") == "c"
        assert await _shown(pilot, "down") == "b"
        assert await _shown(pilot, "down") == ""  # the draft then was nothing


async def test_up_recalls_only_on_the_first_line_and_down_only_on_the_last() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "old", "x\ny")
        await pilot.press(*"a", "ctrl+j", *"b")  # a two-line draft, the cursor on its last line
        composer = _composer(app)
        assert await _shown(pilot, "down") == "a\nb"  # the last line, nothing recalled: the cursor only
        assert await _shown(pilot, "up") == "a\nb"  # not the first line: the cursor moves up
        assert composer.cursor_location[0] == 0
        assert await _shown(pilot, "down") == "a\nb"  # not the last line: the cursor moves down
        assert composer.cursor_location[0] == 1
        await pilot.press("up")
        assert await _shown(pilot, "up") == "x\ny"  # the first line: back, the draft kept
        assert composer.cursor_location == (1, 1)  # the end of what was recalled
        assert await _shown(pilot, "up") == "x\ny"  # now on its second line: the cursor moves up
        assert composer.cursor_location[0] == 0
        assert await _shown(pilot, "up") == "old"
        assert await _shown(pilot, "down") == "x\ny"
        await pilot.press("up")  # the cursor to the first line of the two
        assert composer.cursor_location[0] == 0
        await pilot.press("down")  # not the last line: the cursor moves down, not forward
        assert composer.text == "x\ny" and composer.cursor_location[0] == 1
        assert await _shown(pilot, "down") == "a\nb"  # the last line: forward, to the draft


async def test_a_long_line_that_wraps_counts_as_the_lines_it_is_drawn_in() -> None:
    app = BhApp()
    async with app.run_test(size=(40, 20)) as pilot:
        await _send(pilot, "old")
        await pilot.press(*"x" * 50)  # drawn on two rows at 40 columns
        long = "x" * 50
        composer = _composer(app)
        assert await _shown(pilot, "up") == long  # drawn row 2 to row 1: the cursor moves
        assert composer.cursor_location[1] < 50
        assert await _shown(pilot, "up") == "old"  # the first drawn row: back
        assert await _shown(pilot, "down") == long  # draft back, the cursor at its end
        assert composer.cursor_location == (0, 50)


async def _commands(app: BhApp, pilot: Pilot[None]) -> None:
    app.frame.commands(lambda: _SPECS)
    await pilot.pause()


def _listed(app: BhApp) -> list[str]:
    return [e.call for e in app.query_one(Completions).shown]


async def test_with_the_slash_list_open_up_moves_its_highlight_and_recalls_nothing() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _commands(app, pilot)
        await _send(pilot, "earlier")
        await pilot.press(*"/m")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert listed.display and listed.highlighted == 0
        assert await _shown(pilot, "up") == "/m"  # the list's key: the highlight wraps to the last
        assert listed.highlighted == len(listed.shown) - 1
        assert await _shown(pilot, "down") == "/m" and listed.highlighted == 0
        await pilot.press("escape")  # the list shut for this line: the keys are the history's again
        await pilot.pause()
        assert not listed.display
        assert await _shown(pilot, "up") == "earlier"
        assert await _shown(pilot, "down") == "/m"


async def test_a_recalled_command_does_not_open_the_list_so_up_goes_on_until_it_is_edited() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _commands(app, pilot)
        await _send(pilot, "first", "/model")
        listed = app.query_one(Completions)
        assert await _shown(pilot, "up") == "/model"
        assert not listed.display  # a list here would take the next Up for its highlight
        assert await _shown(pilot, "up") == "first"
        assert await _shown(pilot, "down") == "/model" and not listed.display
        assert await _shown(pilot, "down") == ""
        await pilot.press("up")
        await pilot.press(*" h")  # edited, it is the person's own text again: the list opens
        await pilot.pause()
        assert _composer(app).text == "/model h"
        assert _listed(app) == ["/model haiku"]
        assert await _shown(pilot, "up") == "/model h"  # and its keys are the list's


async def test_with_a_question_up_the_keys_go_to_the_modal_and_the_composer_is_left_alone() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE) as pilot:
        await _send(pilot, "earlier")
        await pilot.press(*"draft")
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"tool": "bash", "input": {"command": "ls"}}, answer))
        await pilot.pause(0.2)
        assert isinstance(app.screen, ApprovalScreen)
        await pilot.press("up", "down", "up")
        await pilot.pause()
        assert _composer(app).text == "draft"
        await pilot.press("n")
        await pilot.pause(0.1)
        assert await answer is False
        assert await _shown(pilot, "up") == "earlier"  # the composer has its history again
