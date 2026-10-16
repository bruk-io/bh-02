"""Under Pilot: PageUp and PageDown in the composer scroll the transcript a page (TASK-0089.04),
the focus staying in the composer; scrolled up the transcript stops following new output and
scrolled back to its end it follows again, as the mouse wheel does; and which layer wins when
another wants the key."""

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from textual import events
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp
from tui_cordis_plugin.messages import Asked, Shown
from tui_cordis_plugin.widgets import ApprovalScreen, Completions, Composer, Transcript

_SIZE = (80, 15)

_SPECS: list[Mapping[str, Any]] = [{"name": "model", "help": "the model", "usage": "[NAME]"}]


async def _fill(app: BhApp, pilot: Pilot[None], lines: int = 60) -> Transcript:
    """Draw `lines` lines, so the transcript is longer than its page and at its end."""
    for n in range(lines):
        app.post_message(Shown({"type": "text", "text": f"line {n}\n\n"}))
    await pilot.pause()
    transcript = app.query_one(Transcript)
    assert transcript.max_scroll_y > 3 * transcript.scrollable_content_region.height
    assert transcript.scroll_y == transcript.max_scroll_y  # following the end
    return transcript


def _wheel(transcript: Transcript, *, up: bool) -> None:
    """One notch of the mouse wheel over the transcript."""
    event = events.MouseScrollUp if up else events.MouseScrollDown
    transcript.post_message(event(transcript, 5, 5, 0, -1 if up else 1, 0, False, False, False))


async def _scroll(pilot: Pilot[None], transcript: Transcript, how: str, *, up: bool) -> None:
    """Scroll up or down by the key, or by the wheel enough notches to go the same way."""
    if how == "key":
        await pilot.press("pageup" if up else "pagedown")
    else:
        for _ in range(transcript.scrollable_content_region.height):
            _wheel(transcript, up=up)
    await pilot.pause()


async def test_page_up_and_page_down_scroll_the_transcript_a_page_and_the_composer_is_left_alone() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = await _fill(app, pilot)
        composer = app.query_one(Composer)
        await pilot.press(*"ab", "left")
        cursor = composer.cursor_location
        page = transcript.scrollable_content_region.height
        end = transcript.scroll_y
        await pilot.press("pageup")
        await pilot.pause()
        assert transcript.scroll_y == end - page
        await pilot.press("pageup")
        await pilot.pause()
        assert transcript.scroll_y == end - 2 * page
        await pilot.press("pagedown")
        await pilot.pause()
        assert transcript.scroll_y == end - page
        assert app.focused is composer  # the focus stays
        assert composer.text == "ab" and composer.cursor_location == cursor  # the cursor did not page


@pytest.mark.parametrize("how", ["key", "wheel"])
async def test_scrolled_up_it_stops_following_and_back_at_the_end_it_follows_again(how: str) -> None:
    """The same with the keys and with the mouse wheel: both go through `scroll_to`."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = await _fill(app, pilot)
        await _scroll(pilot, transcript, how, up=True)
        scrolled = transcript.scroll_y
        assert scrolled < transcript.max_scroll_y
        app.post_message(Shown({"type": "text", "text": "new output\n\n"}))
        await pilot.pause()
        assert transcript.scroll_y == scrolled  # not pulled to the end
        assert transcript.max_scroll_y > scrolled
        for _ in range(3):  # back down, past the end
            await _scroll(pilot, transcript, how, up=False)
        assert transcript.scroll_y == transcript.max_scroll_y
        end = transcript.max_scroll_y
        app.post_message(Shown({"type": "text", "text": "newer output\n\n"}))
        await pilot.pause()
        assert transcript.max_scroll_y > end
        assert transcript.scroll_y == transcript.max_scroll_y  # following the end again


async def test_with_nothing_to_scroll_the_keys_leave_the_cursor_and_the_transcript_still_follows() -> None:
    """A PageUp on a transcript that fits its page must not release its anchor: the output that
    makes it longer would then not be followed."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = app.query_one(Transcript)
        composer = app.query_one(Composer)
        await pilot.press(*"ab", "left")
        cursor, at = composer.cursor_location, transcript.scroll_y
        await pilot.press("pageup", "pagedown")
        await pilot.pause()
        assert transcript.scroll_y == at and transcript.max_scroll_y == 0
        assert composer.cursor_location == cursor and app.focused is composer
        await _fill(app, pilot)  # grows past its page: still following the end


async def test_with_the_slash_list_open_the_page_keys_scroll_the_transcript_and_leave_the_list() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(lambda: _SPECS)
        transcript = await _fill(app, pilot)
        await pilot.press(*"/m")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert listed.display
        end = transcript.scroll_y
        highlighted = listed.highlighted
        await pilot.press("pageup")
        await pilot.pause()
        assert transcript.scroll_y < end  # the page key is not the list's: the conversation scrolls
        assert listed.display and listed.highlighted == highlighted
        assert app.query_one(Composer).text == "/m" and app.focused is app.query_one(Composer)


async def test_with_a_question_up_the_page_keys_are_the_modal_s_and_the_transcript_stays() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE) as pilot:
        transcript = await _fill(app, pilot)
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"tool": "bash", "input": {"command": "ls"}}, answer))
        await pilot.pause(0.2)
        assert isinstance(app.screen, ApprovalScreen)
        end = transcript.scroll_y
        await pilot.press("pageup", "pagedown", "pageup")
        await pilot.pause()
        assert transcript.scroll_y == end and not answer.done()
        await pilot.press("n")
        await pilot.pause(0.1)
        assert await asyncio.wait_for(answer, 1) is False
        await pilot.press("pageup")  # the composer has the key again
        await pilot.pause()
        assert transcript.scroll_y < end
