"""Where the focus is after the mouse has been in the chat view (TASK-0089.09). A click or a drag
in the chat view focuses the ChatView (Textual focuses what is clicked), so the keys typed next
would go nowhere. The mouse lets go and the focus goes back to the composer; the selection a drag
made stays shown, Tab still moves the focus to the chat view and back, and PageUp and PageDown
still scroll it from the composer."""

import asyncio
from collections.abc import Mapping
from typing import Any

from textual.pilot import Pilot
from textual.widgets import Static

from tui_cordis_plugin import BhApp
from tui_cordis_plugin.messages import Asked, Shown
from tui_cordis_plugin.widgets import ApprovalScreen, ChatView, Completions, Composer
from tui_cordis_plugin.widgets.chat_view import Clipped

_SIZE = (100, 30)
_SAID = "Hello brave new world, here is the answer."
_SPECS: list[Mapping[str, Any]] = [{"name": "model", "help": "the model", "usage": "[NAME]"}]


def _plain(block: Static) -> str:
    content = block.content
    return content if isinstance(content, str) else content.plain


async def _say(app: BhApp, pilot: Pilot[None], text: str = _SAID) -> Static:
    """The model says `text`; the block that shows it."""
    app.post_message(Shown({"type": "text", "text": text}))
    await pilot.pause()
    return next(s for s in app.query_one(ChatView).query(Static) if text.split("\n")[0] in _plain(s))


async def _drag(pilot: Pilot[None], block: Static, first: int, last: int) -> None:
    """Select cells `first` to `last` of the block's first row with the mouse, as a person does."""
    await pilot.mouse_down(block, offset=(first, 0))
    await pilot.hover(block, offset=(last, 0))
    await pilot.mouse_up(block, offset=(last, 0))
    await pilot.pause()


async def test_after_a_click_in_the_chat_view_typing_reaches_the_composer() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        block = await _say(app, pilot)
        await pilot.click(block, offset=(4, 0))
        await pilot.pause()
        assert isinstance(app.focused, Composer)
        await pilot.press(*"abc")
        assert app.query_one(Composer).text == "abc"


async def test_after_a_selection_typing_reaches_the_composer_and_the_selection_stays_shown() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        block = await _say(app, pilot)
        await _drag(pilot, block, 0, 10)
        assert app.screen.get_selected_text() == "Hello brave"  # the focus going back left it shown
        assert app.clipboard == "Hello brave"  # and copy on select is as it was
        assert isinstance(app.focused, Composer)
        await pilot.press(*"abc")
        assert app.query_one(Composer).text == "abc"
        assert app.screen.get_selected_text() is None  # Textual clears it once the composer's cursor moves


async def test_a_drag_let_go_over_the_composer_gives_the_focus_back_too() -> None:
    """The mouse is up wherever the pointer is: the chat view never sees this one's release."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        block = await _say(app, pilot)
        composer = app.query_one(Composer)
        await pilot.mouse_down(block, offset=(0, 0))
        await pilot.hover(composer, offset=(3, 1))
        await pilot.mouse_up(composer, offset=(3, 1))
        await pilot.pause()
        assert app.focused is composer
        await pilot.press(*"abc")
        assert composer.text == "abc"


async def test_a_click_in_the_chat_view_after_tab_took_the_focus_there_gives_it_back_too() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        block = await _say(app, pilot)
        await pilot.press("tab")
        assert app.focused is app.query_one(ChatView)
        await pilot.click(block, offset=(4, 0))
        await pilot.pause()
        assert isinstance(app.focused, Composer)
        await pilot.press(*"abc")
        assert app.query_one(Composer).text == "abc"


async def test_tab_still_moves_the_focus_to_the_chat_view_and_back() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _say(app, pilot)
        await pilot.press(*"draft")
        await pilot.press("tab")
        assert app.focused is app.query_one(ChatView)
        await pilot.press("tab")
        assert isinstance(app.focused, Composer)
        await pilot.press("!")
        assert app.query_one(Composer).text == "draft!"


async def test_page_up_and_page_down_scroll_the_chat_view_from_the_composer_after_a_click_in_it() -> None:
    app = BhApp()
    async with app.run_test(size=(80, 15)) as pilot:
        for n in range(60):
            app.post_message(Shown({"type": "text", "text": f"line {n}\n\n"}))
        await pilot.pause()
        chat_view = app.query_one(ChatView)
        assert chat_view.scroll_y > 0 and chat_view.scroll_y == chat_view.max_scroll_y
        await pilot.click(chat_view, offset=(3, 2))  # on some line of it
        await pilot.pause()
        assert isinstance(app.focused, Composer)
        scrolled = chat_view.scroll_y  # the click scrolled nothing
        await pilot.press("pageup")
        await pilot.pause()
        assert chat_view.scroll_y < scrolled
        await pilot.press("pagedown")
        await pilot.pause()
        assert chat_view.scroll_y == scrolled
        assert isinstance(app.focused, Composer)  # the focus stays


async def test_a_click_on_the_line_that_opens_a_block_still_leaves_the_focus_on_it() -> None:
    """A control the person chose is not the chat view taking the focus (TASK-0089.07): Enter
    and Space on it go on opening and closing the block."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        lines = "\n".join(f"out {n}" for n in range(20))
        app.post_message(Shown({"type": "tool_result", "call_id": "c", "content": lines, "is_error": False}))
        await pilot.pause()
        (block,) = app.query_one(ChatView).query(Clipped)
        label = next(w for w in block.query(Static) if w.has_class("more"))
        await pilot.click(label)
        await pilot.pause()
        assert block.opened and app.focused is label
        await pilot.press("enter")
        assert not block.opened and app.focused is label


async def test_a_click_closes_the_list_of_commands_as_before_and_typing_opens_it_again() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(lambda: _SPECS)
        block = await _say(app, pilot)
        await pilot.press(*"/mo")
        listed = app.query_one(Completions)
        assert listed.is_open
        await pilot.click(block, offset=(4, 0))
        await pilot.pause()
        assert not listed.is_open  # the composer lost the focus for a moment, as it always did
        assert isinstance(app.focused, Composer) and app.query_one(Composer).text == "/mo"
        await pilot.press("d")
        assert listed.is_open and app.query_one(Composer).text == "/mod"


async def test_with_a_question_up_a_click_in_it_moves_the_focus_under_it_nowhere() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE) as pilot:
        await _say(app, pilot)
        await pilot.press("tab")  # the chat view has the focus beneath the question
        chat_view = app.query_one(ChatView)
        assert app.focused is chat_view
        answer = asyncio.ensure_future(_question(app))
        await pilot.pause(0.2)
        modal = app.screen
        assert isinstance(modal, ApprovalScreen)
        await pilot.click("#approval-title")
        await pilot.pause()
        assert app.screen is modal and not answer.done()
        assert app.screen_stack[0].focused is chat_view  # nothing under the question was refocused
        await pilot.press("n")
        assert await asyncio.wait_for(answer, 1) is False


async def _question(app: BhApp) -> bool:
    answer: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    app.post_message(Asked({"name": "python", "input": {"code": "1"}}, answer))
    return await answer
