"""Under Pilot: the command palette (Ctrl-P), the approval modal (code
highlighted, questions one at a time, withdrawn wherever it is, Ctrl-C answers no), and
`running` cancelled before the app is up."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from textual.command import CommandPalette
from textual.containers import VerticalScroll
from textual.content import Content
from textual.pilot import Pilot
from textual.screen import Screen
from textual.widgets import OptionList, Static

from tui_cordis_plugin import BhApp, render, running
from tui_cordis_plugin.messages import Asked
from tui_cordis_plugin.widgets import ApprovalScreen, Composer, Transcript

_SIZE = (120, 36)

_SPECS: list[Mapping[str, Any]] = [
    {"name": "rows", "help": "the running composition", "usage": ""},
    {"name": "model", "help": "show or switch the model", "usage": "[NAME]"},
]


def _said(app: BhApp) -> list[str]:
    return [str(block.content) for block in app.query_one(Transcript).query(Static)]


async def _settle(pilot: Pilot[None], times: int = 3) -> None:
    for _ in range(times):
        await pilot.pause(0.05)


async def _armed(pilot: Pilot[None]) -> None:
    """Wait until the modal up answers keys (it drops them for a moment after it is shown)."""
    app = pilot.app
    for _ in range(40):
        if isinstance(app.screen, ApprovalScreen) and app.screen.armed:
            return
        await pilot.pause(0.05)
    raise AssertionError("the approval modal never began answering keys")


def _ask(app: BhApp, request: Mapping[str, Any]) -> asyncio.Future[bool]:
    answer = app.bridge.question()
    assert answer is not None
    app.post_message(Asked(request, answer))
    return answer


async def test_ctrl_p_in_the_composer_lists_the_offered_commands_and_runs_one() -> None:
    app = BhApp()
    specs = list(_SPECS)
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(lambda: specs)
        specs.append({"name": "clear", "help": "start afresh", "usage": ""})  # offered after the push
        assert isinstance(app.focused, Composer)
        await pilot.press("ctrl+p")
        await _settle(pilot)
        assert isinstance(app.screen, CommandPalette)
        assert [e.call for e in app.palette_entries()] == ["/rows", "/model", "/clear", "/help", "/exit"]
        await pilot.press(*"clear", "enter")
        await _settle(pilot)
        assert not isinstance(app.screen, CommandPalette)
        assert await asyncio.wait_for(app.bridge.line(), 1) == "/clear"  # the normal input path
        assert "› /clear" in _said(app)


async def test_a_command_that_takes_arguments_is_put_in_the_composer_to_finish() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(lambda: _SPECS)
        await pilot.press("ctrl+p")
        await _settle(pilot)
        await pilot.press(*"model")
        await _settle(pilot)
        drawn = [str(o.prompt) for o in app.screen.query_one(OptionList).options]
        assert any("/model [NAME]" in text for text in drawn), drawn  # usage is text, not markup
        await pilot.press("enter")
        await _settle(pilot)
        composer = app.query_one(Composer)
        assert composer.text == "/model " and app.focused is composer
        await pilot.press(*"haiku", "enter")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "/model haiku"


async def test_exit_from_the_palette_leaves() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press("ctrl+p")
        await _settle(pilot)
        await pilot.press(*"exit", "enter")
        await _settle(pilot)
        assert app.return_code == 0


async def test_the_modal_shows_an_input_highlighted() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        code = "import os\n" + "\n".join(f"print({n})" for n in range(60))
        _ask(app, {"name": "python", "input": {"code": code}})
        await _settle(pilot)
        assert isinstance(app.screen, ApprovalScreen)
        source = app.screen.query_one("#approval-source", Static).content
        assert isinstance(source, Content) and source.plain == code  # whole, not cut to a glance
        assert source == render.code(code)  # highlighted as the transcript does, in theme tokens
        assert all(str(span.style).startswith(("$", "bold", "italic")) for span in source.spans)
        title = str(app.screen.query_one("#approval-title", Static).content)
        assert title.startswith("Run this python code (61 lines)?")
        await pilot.press("ctrl+p")  # no palette over a question
        await _settle(pilot)
        assert isinstance(app.screen, ApprovalScreen)


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
async def test_a_long_input_scrolls_inside_the_modal_and_the_keys_stay_on_screen(
    size: tuple[int, int],
) -> None:
    app = BhApp()
    async with app.run_test(size=size) as pilot:
        code = "\n".join(f"v{n} = {n}" for n in range(30))
        answer = _ask(app, {"name": "python", "input": {"code": code}})
        await _settle(pilot)
        dialog = app.screen.query_one("#approval")
        scroll = app.screen.query_one("#approval-code", VerticalScroll)
        keys = app.screen.query_one("#approval-keys")
        inside = dialog.content_region
        assert keys.region.height >= 1 and inside.contains_region(keys.region)  # the hints are shown
        assert inside.contains_region(scroll.region) and scroll.region.bottom <= keys.region.y
        assert "y  allow" in str(keys.render())
        await pilot.press("end")  # as far as the arrow keys can take it
        await _settle(pilot)
        shown = scroll.scroll_offset.y + scroll.scrollable_content_region.height
        assert scroll.scroll_offset.y > 0 and shown >= 30  # the last line, v29, can be read
        await _armed(pilot)
        await pilot.press("y")
        assert await asyncio.wait_for(answer, 1) is True


async def test_an_empty_input_shows_its_question_and_keys() -> None:
    """With no code to scroll, the title and the keys stay in the box and it grows around them
    (docked, an auto-height box would collapse to its border and hide the question)."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answer = _ask(app, {"name": "python", "input": {"code": ""}})
        await _settle(pilot)
        assert not app.screen.query("#approval-code")
        inside = app.screen.query_one("#approval").content_region
        title, keys = app.screen.query_one("#approval-title"), app.screen.query_one("#approval-keys")
        for part in (title, keys):
            assert part.region.height >= 1 and inside.contains_region(part.region)
        assert title.region.bottom <= keys.region.y  # the question, then the keys
        assert "Run this python code (0 lines)?" in str(title.render())
        await _armed(pilot)
        await pilot.press("y")
        assert await asyncio.wait_for(answer, 1) is True


async def test_keys_typed_as_the_modal_comes_up_answer_nothing_and_reach_nothing() -> None:
    """A person typing "Run now" as an input is put to them: the `n` must not decline it. For a
    moment after it is shown the modal drops y, n and Escape (and every other key: it holds
    focus, so the composer beneath gets none of them); then y answers as always. A longer
    grace than the shipped one, so a loaded machine's slow key presses still land inside it."""
    app = BhApp(grace=2.0)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"Run")  # typed before the question: the composer's
        answer = _ask(app, {"name": "python", "input": {"code": "print(1)"}})
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen) and not app.screen.armed
        await pilot.press(*" now", "escape", "y")  # still typing, as the modal comes up
        await pilot.pause()
        assert not answer.done() and isinstance(app.screen, ApprovalScreen)
        assert app.screen.query_one("#approval-keys").has_class("-arming")  # dimmed meanwhile
        await _armed(pilot)
        assert not answer.done()  # dropped, not queued up for when it arms
        assert not app.screen.query_one("#approval-keys").has_class("-arming")
        await pilot.press("n")
        assert await asyncio.wait_for(answer, 1) is False
        await _settle(pilot)
        assert app.query_one(Composer).text == "Run"  # what was typed before it, and nothing after


async def test_ctrl_c_stops_the_turn_while_the_modal_is_not_answering_yet() -> None:
    app = BhApp(grace=2.0)
    async with app.run_test(size=_SIZE) as pilot:
        shown = _ask(app, {"name": "python", "input": {"code": "1"}})
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen) and not app.screen.armed
        await pilot.press("ctrl+c")
        assert shown.done() and shown.result() is False


async def test_the_modal_traps_focus() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        _ask(app, {"name": "python", "input": {"code": "print(1)"}})
        await _settle(pilot)
        for _ in range(4):
            await pilot.press("tab")
            focused = app.focused
            assert focused is None or focused.screen is app.screen  # never the composer beneath
        await pilot.press(*"hello")
        assert app.query_one(Composer).text == ""


async def test_questions_are_asked_one_at_a_time_in_order() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        first = _ask(app, {"name": "python", "input": {"code": "1"}})
        second = _ask(app, {"name": "python", "input": {"code": "2"}})
        await _settle(pilot)
        assert sum(isinstance(s, ApprovalScreen) for s in app.screen_stack) == 1
        await _armed(pilot)
        await pilot.press("y")
        assert await asyncio.wait_for(first, 1) is True
        await _settle(pilot)
        assert isinstance(app.screen, ApprovalScreen) and app.screen.request["input"] == {"code": "2"}
        await _armed(pilot)
        await pilot.press("n")
        assert await asyncio.wait_for(second, 1) is False
        await _settle(pilot)
        assert not app.asking and not isinstance(app.screen, ApprovalScreen)


async def test_a_withdrawn_question_comes_down_even_when_it_is_not_on_top() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        shown = _ask(app, {"name": "python", "input": {"code": "1"}})
        queued = _ask(app, {"name": "python", "input": {"code": "2"}})
        await _settle(pilot)
        app.push_screen(Screen())  # something over the modal
        await _settle(pilot)
        assert not isinstance(app.screen, ApprovalScreen)
        queued.cancel()  # its turn was interrupted: dropped before it is shown
        shown.cancel()
        await _settle(pilot)
        assert not any(isinstance(s, ApprovalScreen) for s in app.screen_stack)
        assert not app.asking and len(app.screen_stack) == 1


async def test_ctrl_c_with_a_question_up_stops_the_turn_which_withdraws_it() -> None:
    """As `chat:converse` races a turn against `interrupted()`: the turn is cancelled while it
    waits on the answer, so it never carries on with one, and the modal comes down."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answered: list[bool] = []

        async def work() -> None:
            answer = _ask(app, {"name": "python", "input": {"code": "1"}})
            answered.append(await answer)

        async def turn() -> None:
            doing = asyncio.ensure_future(work())
            stop = asyncio.ensure_future(app.bridge.interrupted())
            await asyncio.wait({doing, stop}, return_when=asyncio.FIRST_COMPLETED)
            doing.cancel()

        running_turn = asyncio.ensure_future(turn())
        await _settle(pilot)
        assert isinstance(app.screen, ApprovalScreen)
        await pilot.press("ctrl+c")
        await asyncio.wait_for(running_turn, 1)
        await _settle(pilot)
        assert answered == []  # cancelled, not answered: the turn did not carry on
        assert not app.asking and not isinstance(app.screen, ApprovalScreen)
        assert not any(text.startswith("Nothing is running") for text in _said(app))


async def test_ctrl_c_answers_no_to_questions_no_turn_withdraws() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        turn = asyncio.ensure_future(app.bridge.interrupted())  # a turn that asks nothing itself
        shown = _ask(app, {"name": "python", "input": {"code": "1"}})
        queued = _ask(app, {"name": "python", "input": {"code": "2"}})
        await _settle(pilot)
        assert isinstance(app.screen, ApprovalScreen)
        await pilot.press("ctrl+c")
        await asyncio.wait_for(turn, 1)
        assert await asyncio.wait_for(shown, 2) is False and await asyncio.wait_for(queued, 2) is False
        await _settle(pilot)
        assert not app.asking and not isinstance(app.screen, ApprovalScreen)
        assert not any(text.startswith("Nothing is running") for text in _said(app))


async def test_ctrl_c_with_only_questions_open_answers_them_no_at_once() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        shown = _ask(app, {"name": "python", "input": {"code": "1"}})
        await _settle(pilot)
        await pilot.press("ctrl+c")
        assert shown.done() and shown.result() is False
        await _settle(pilot)
        assert not isinstance(app.screen, ApprovalScreen)


async def test_ctrl_c_after_a_line_is_sent_is_held_for_its_turn() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        reading = asyncio.ensure_future(app.bridge.line())
        await pilot.press(*"hello", "enter")
        assert await asyncio.wait_for(reading, 1) == "hello"
        await pilot.press("ctrl+c")  # before the turn listens
        assert not any(text.startswith("Nothing is running") for text in _said(app))
        await asyncio.wait_for(app.bridge.interrupted(), 1)


async def test_an_enter_caninputed_before_the_app_is_up_takes_the_app_down() -> None:
    before = set(asyncio.all_tasks())
    app = BhApp()

    async def enter() -> None:
        async with running(app, headless=True):
            raise AssertionError("never entered")

    entering = asyncio.ensure_future(enter())
    await asyncio.sleep(0)
    entering.cancel()
    await asyncio.gather(entering, return_exceptions=True)
    assert entering.cancelled()
    left: Sequence[asyncio.Task[Any]] = [
        t for t in asyncio.all_tasks() - before if t is not asyncio.current_task() and not t.done()
    ]
    assert left == [], left
    assert app.bridge.ended  # and whoever waits on its ports is settled
    crash = app.bridge.crash
    assert crash is not None and crash.message == "the app was cancelled"
