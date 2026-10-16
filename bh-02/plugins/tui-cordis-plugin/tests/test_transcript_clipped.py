"""Under Pilot: a clipped tool result, diff or piece of code opens to show every line and closes
again, by a click and by Enter or Space once its line has the focus (TASK-0089.07), as a finished
thinking block opens; closed is how every new block starts; and opening one moves nothing else:
a transcript that follows its end goes on following, one scrolled away stays where it is."""

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from textual.command import CommandPalette
from textual.pilot import Pilot
from textual.widget import Widget
from textual.widgets import Static

from tui_cordis_plugin import BhApp, History, replayable
from tui_cordis_plugin.messages import Asked, Shown
from tui_cordis_plugin.widgets import ApprovalScreen, Clipped, Composer, Transcript

_SIZE = (80, 24)


def _screen(app: BhApp) -> str:
    """What the terminal shows, as text."""
    return "\n".join(
        "".join(segment.text for segment in app.screen._compositor.render_update(full=True).strips[y])  # noqa: SLF001
        for y in range(app.size.height)
    )


def _result(lines: int, *, call: str = "c", error: bool = False, word: str = "out") -> Mapping[str, Any]:
    body = "\n".join(f"{word} {n}" for n in range(lines))
    return {"type": "tool_result", "call_id": call, "content": body, "is_error": error}


def _call(lines: int, call: str = "c") -> Mapping[str, Any]:
    code = "\n".join(f"x{n} = {n}" for n in range(lines))
    return {"type": "tool_call", "id": call, "name": "python", "input": {"code": code}}


def _text(n: int) -> Mapping[str, Any]:
    return {"type": "text", "text": f"filler {n}\n\n"}


def _clipped(app: BhApp) -> list[Clipped]:
    return list(app.query(Clipped))


def _toggle(block: Clipped) -> Widget:
    """The line that opens and closes a block."""
    return block.query_one(".more")


async def _draw(app: BhApp, pilot: Pilot[None], *events: Mapping[str, Any]) -> None:
    app.post_message(Shown(*events))
    await pilot.pause()


async def _click(pilot: Pilot[None], block: Clipped) -> None:
    await pilot.click(_toggle(block))
    await pilot.pause()


# What is clipped, and how it looks.


async def test_a_long_result_and_long_code_start_clipped_each_with_a_line_that_opens_it() -> None:
    app = BhApp()
    async with app.run_test(size=(80, 70)) as pilot:  # tall enough to see all of what shows
        await _draw(app, pilot, _call(50), _result(20), _result(5, call="d", word="short"))
        code, result = _clipped(app)
        assert (code.opened, result.opened) == (False, False)
        shown = _screen(app)
        assert "x39 = 39" in shown and "x40 = 40" not in shown  # forty lines of code
        assert "▶ 10 more lines" in shown
        assert "out 11" in shown and "out 12" not in shown  # twelve lines of a result
        assert "▶ 8 more lines" in shown
        assert "short 4" in shown and shown.count("more line") == 2  # five lines fit: no line to open
        assert len(_clipped(app)) == 2


async def test_a_diff_is_clipped_at_forty_lines_and_one_more_line_is_a_line_not_lines() -> None:
    diff = "@@ -1 +1 @@\n" + "\n".join(f"+added {n}" for n in range(40))  # 41 lines: one over
    app = BhApp()
    async with app.run_test(size=(80, 60)) as pilot:
        await _draw(app, pilot, {"type": "tool_result", "call_id": "c", "content": diff, "is_error": False})
        (block,) = _clipped(app)
        assert "▶ 1 more line" in _screen(app) and "more lines" not in _screen(app)
        assert "+added 38" in _screen(app) and "+added 39" not in _screen(app)
        await _click(pilot, block)
        assert "+added 39" in _screen(app) and "▼ 1 more line" in _screen(app)


# Opening and closing.


async def test_a_click_opens_it_to_every_line_and_a_second_click_closes_it() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20))
        (block,) = _clipped(app)
        await _click(pilot, block)
        assert block.opened
        shown = _screen(app)
        assert "▼ 8 more lines" in shown and "out 19" in shown and "out 12" in shown
        assert block.text.splitlines()[-1] == "out 19"  # blocks() tells the person's view too
        await _click(pilot, block)
        assert not block.opened
        shown = _screen(app)
        assert "▶ 8 more lines" in shown and "out 11" in shown and "out 12" not in shown


async def test_opened_code_shows_every_line_in_its_gutter() -> None:
    app = BhApp()
    async with app.run_test(size=(80, 70)) as pilot:
        await _draw(app, pilot, _call(50))
        (block,) = _clipped(app)
        await _click(pilot, block)
        lines = _screen(app).splitlines()
        rows = lines[block.region.y : block.region.bottom]
        assert len(rows) == 40 + 1 + 10 and rows[-1].strip().endswith("x49 = 49")
        assert all(row[block.region.x] == "│" for row in rows)  # the gutter spans the whole block


async def test_the_rest_is_drawn_when_opened_not_before_and_once() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(2000))
        (block,) = _clipped(app)
        rest = block.query_one(".rest", Static)
        assert "out 1999" not in block.text and str(rest.content) == ""  # nothing drawn for the rest yet
        await _click(pilot, block)
        assert str(rest.content).count("\n") == 1987  # the 1,988 lines left out (2,000 less the first 12)
        assert block.text.splitlines()[-1] == "out 1999" and len(block.text.splitlines()) == 2001
        await pilot.press("enter", "enter")  # the line kept the focus; it is above the view now
        await pilot.pause()
        assert block.opened and block.text.splitlines()[-1] == "out 1999"  # reopening draws nothing again


async def test_blocks_open_one_by_one_and_new_output_starts_clipped() -> None:
    app = BhApp()
    async with app.run_test(size=(80, 50)) as pilot:
        await _draw(app, pilot, _result(20, call="a", word="first"), _result(20, call="b", word="second"))
        first, second = _clipped(app)
        await _click(pilot, first)
        assert (first.opened, second.opened) == (True, False)
        await _draw(app, pilot, _result(20, call="c", word="third"))
        third = _clipped(app)[2]
        assert not third.opened and "third 12" not in _screen(app)  # clipped is the default
        assert first.opened  # and what was opened stays open


async def test_a_block_drawn_again_from_the_history_is_clipped(tmp_path: Any) -> None:
    file = tmp_path / "events.jsonl"
    app = BhApp(history=History(str(file)))
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20))
        await _click(pilot, _clipped(app)[0])
        assert _clipped(app)[0].opened
    replay = replayable(History(str(file)).read(), 400)
    second = BhApp(replay=replay)
    async with second.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        (block,) = _clipped(second)
        assert not block.opened and "out 12" not in _screen(second)  # what was opened is not kept


async def test_the_error_colour_of_a_result_is_the_rest_s_too() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20, error=True))
        (block,) = _clipped(app)
        await _click(pilot, block)
        statics = block.query("Static").nodes
        head, rest = statics[0], statics[-1]
        assert rest.rich_style.color == head.rich_style.color
        assert head.rich_style.color != app.query_one(Composer).rich_style.color  # danger, not the text's


async def test_the_line_that_opens_a_block_is_not_part_of_what_a_selection_copies() -> None:
    """A mouse selection dragged across it takes the lines either side and leaves the label out,
    and clicking it copies nothing (copy on select says nothing for a click)."""
    app = BhApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _draw(app, pilot, _result(20), {"type": "text", "text": "below it\n\n"})
        (block,) = _clipped(app)
        body = block.query("Static").first()
        end = _toggle(block).region.bottom + 2
        await pilot.mouse_down(body, offset=(0, 0))
        await pilot.hover(None, offset=(30, end))
        await pilot.mouse_up(None, offset=(30, end))
        await pilot.pause()
        copied = app.screen.get_selected_text() or ""
        assert "out 11" in copied and "below it" in copied and "more line" not in copied
        assert app.clipboard == copied  # the selection was copied as the mouse let go
        app.screen.clear_selection()
        await _click(pilot, block)
        assert block.opened and app.clipboard == copied  # a click on the label copies nothing more


# The keys.


async def test_shift_tab_reaches_the_newest_clipped_block_and_enter_and_space_open_and_close_it() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20, call="a", word="old"), _result(20, call="b", word="new"))
        old, new = _clipped(app)
        await pilot.press(*"draft")
        await pilot.press("shift+tab")
        assert app.focused is _toggle(new)  # the newest, first
        await pilot.press("enter")
        await pilot.pause()
        assert (old.opened, new.opened) == (False, True) and "new 19" in _screen(app)
        await pilot.press("enter")
        assert not new.opened
        await pilot.press("space")
        await pilot.pause()
        assert new.opened
        await pilot.press("space")
        assert not new.opened
        await pilot.press("shift+tab")
        assert app.focused is _toggle(old)
        await pilot.press("enter")
        assert old.opened and not new.opened
        assert app.query_one(Composer).text == "draft" and not app.bridge.kept  # nothing was sent or typed


async def test_tab_leaves_the_line_for_the_composer_and_typing_goes_on() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20))
        await pilot.press("shift+tab", "enter", "tab")
        assert isinstance(app.focused, Composer)
        await pilot.press(*"ok")
        assert app.query_one(Composer).text == "ok"


# Opening moves nothing else.


async def _fill(app: BhApp, pilot: Pilot[None], *, before: int = 0, after: int = 60) -> Transcript:
    """A transcript longer than its page, ending in a long result, at its end (following)."""
    events = [_text(n) for n in range(before)] + [_call(3), _result(20)] + [_text(n) for n in range(after)]
    await _draw(app, pilot, *events)
    transcript = app.query_one(Transcript)
    assert transcript.max_scroll_y > 0 and transcript.scroll_y == transcript.max_scroll_y
    return transcript


@pytest.mark.parametrize("how", ["click", "key"])
async def test_opening_the_block_at_the_end_keeps_the_transcript_following_its_end(how: str) -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _call(3), _result(20))
        transcript = app.query_one(Transcript)
        await _draw(app, pilot, *[_text(n) for n in range(3)])  # a few lines after it, in view
        (block,) = _clipped(app)
        assert transcript.max_scroll_y > 0 and transcript.scroll_y == transcript.max_scroll_y
        if how == "click":
            await _click(pilot, block)
        else:
            await pilot.press("shift+tab", "enter")
            await pilot.pause()
        assert block.opened
        assert transcript.scroll_y == transcript.max_scroll_y  # still at the end
        await _draw(app, pilot, {"type": "text", "text": "newest, after opening\n\n"})
        assert transcript.scroll_y == transcript.max_scroll_y and "newest, after opening" in _screen(app)
        if how == "click":
            await _click(pilot, block)
        else:
            await pilot.press("enter")
            await pilot.pause()
        assert not block.opened and transcript.scroll_y == transcript.max_scroll_y
        await _draw(app, pilot, {"type": "text", "text": "newest, after closing\n\n"})
        assert transcript.scroll_y == transcript.max_scroll_y and "newest, after closing" in _screen(app)


async def test_opening_a_block_in_a_transcript_scrolled_away_leaves_it_where_it_is() -> None:
    """Scrolled away from the end it is not following, and opening a block does not take it to
    the end (nor does closing it); scrolled back to its end it follows again."""
    app = BhApp()
    async with app.run_test(size=(80, 40)) as pilot:  # tall enough for the block's line to be in view
        transcript = await _fill(app, pilot)
        transcript.scroll_to(y=0, animate=False, immediate=True)  # as the person does by scrolling up
        await pilot.pause()
        (block,) = _clipped(app)
        assert transcript.scroll_y == 0 and transcript.max_scroll_y > 0
        await _click(pilot, block)
        assert block.opened and transcript.scroll_y == 0
        before = transcript.max_scroll_y
        await _draw(app, pilot, {"type": "text", "text": "while scrolled away\n\n"})
        assert transcript.scroll_y == 0 and transcript.max_scroll_y > before  # not followed
        await _click(pilot, block)
        assert not block.opened and transcript.scroll_y == 0
        transcript.scroll_end(animate=False)
        await pilot.pause()
        assert transcript.scroll_y == transcript.max_scroll_y
        await _draw(app, pilot, {"type": "text", "text": "back at the end\n\n"})
        assert transcript.scroll_y == transcript.max_scroll_y and "back at the end" in _screen(app)


@pytest.mark.parametrize("focus", ["on the line", "back on the composer"])
async def test_reaching_a_line_off_screen_by_the_keyboard_scrolls_to_it_and_stops_following_until_the_end(
    focus: str,
) -> None:
    """Focusing a line shows it (Textual scrolls to what takes the focus), and a transcript scrolled
    up stops following new output, as TASK-0089.04 has it: until it is back at its end. Opening
    the block then scrolls nothing."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = await _fill(app, pilot)  # following the end, the block far above it
        (block,) = _clipped(app)
        line = _toggle(block)
        assert line.region.bottom <= transcript.region.y  # off screen, above the transcript's view
        end = transcript.max_scroll_y
        await pilot.press("shift+tab")
        await pilot.pause()
        assert app.focused is line
        assert transcript.region.y <= line.region.y < transcript.region.bottom  # scrolled into view
        assert transcript.scroll_y < end  # which is not the end any more
        shown = transcript.scroll_y
        await pilot.press("enter")
        await pilot.pause()
        assert block.opened and transcript.scroll_y == shown  # opening scrolls nothing
        await _draw(app, pilot, {"type": "text", "text": "while scrolled up\n\n"})
        assert transcript.scroll_y == shown and "while scrolled up" not in _screen(app)  # not following
        if focus == "back on the composer":
            await pilot.press("tab")
            assert isinstance(app.focused, Composer)
        for _ in range(40):  # PageDown, the transcript's own with the focus on the line, the composer's else
            if transcript.scroll_y >= transcript.max_scroll_y:
                break
            await pilot.press("pagedown")
            await pilot.pause()
        assert transcript.scroll_y == transcript.max_scroll_y  # back at its end
        await _draw(app, pilot, {"type": "text", "text": "back at the end again\n\n"})
        assert transcript.scroll_y == transcript.max_scroll_y and "back at the end again" in _screen(app)


# What it sits beside.


async def test_with_the_line_focused_esc_stops_a_running_reply_and_ctrl_p_opens_the_palette() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20))
        turn = asyncio.ensure_future(app.bridge.interrupted())  # a reply waiting to be stopped
        await pilot.pause()
        await pilot.press("shift+tab")
        assert app.focused is _toggle(_clipped(app)[0])
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette) and not turn.done()
        await pilot.press("escape")  # closes the palette only
        await pilot.pause()
        assert not isinstance(app.screen, CommandPalette) and not turn.done()
        await pilot.press("escape")
        await asyncio.wait_for(turn, 1)  # the reply heard it
        assert not _clipped(app)[0].opened  # and the line did not take the key


async def test_a_question_over_the_line_takes_enter_and_space_and_is_answered() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE) as pilot:
        await _draw(app, pilot, _result(20))
        await pilot.press("shift+tab")
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"tool": "bash", "input": {"command": "ls"}}, answer))
        for _ in range(100):
            if isinstance(app.screen, ApprovalScreen):
                break
            await pilot.pause(0.02)
        await pilot.press("enter", "space")  # the modal's, not the block's
        await pilot.pause()
        assert not answer.done() and not _clipped(app)[0].opened
        await pilot.press("n")
        assert await asyncio.wait_for(answer, 1) is False
