"""Under Pilot: the choice modal (`output.choose`): its keys come from the question's `choices`,
answer only once armed, Escape gives the question's `escape`, and a withdrawal (Ctrl-C, the reply
cancelled, the app ending) answers ''."""

import asyncio
from collections.abc import Mapping
from typing import Any

from textual.pilot import Pilot
from textual.widgets import Static

from tui_cordis_plugin import BhApp, render
from tui_cordis_plugin.messages import Asked
from tui_cordis_plugin.ports import TuiOutput
from tui_cordis_plugin.widgets import ApprovalScreen, ChoiceScreen

_SIZE = (120, 36)

_QUESTION: Mapping[str, Any] = {
    "title": "Allow net example.com:443?",
    "lines": ["What: net example.com:443", "Asked by: row python, because: it fetches"],
    "warning": "",
    "choices": [
        {"key": "o", "value": "once", "label": "once (for this session)"},
        {"key": "a", "value": "always", "label": "always (for this project)"},
        {"key": "n", "value": "no", "label": "no"},
    ],
    "escape": "no",
}


def _choose(app: BhApp, question: Mapping[str, Any] = _QUESTION) -> asyncio.Future[str]:
    answer = app.bridge.choice()
    assert answer is not None
    app.post_message(Asked(question, answer))
    return answer


async def _shown(pilot: Pilot[None]) -> ChoiceScreen:
    for _ in range(40):
        if isinstance(pilot.app.screen, ChoiceScreen):
            return pilot.app.screen
        await pilot.pause(0.05)
    raise AssertionError("the choice modal never came up")


async def _armed(pilot: Pilot[None]) -> ChoiceScreen:
    screen = await _shown(pilot)
    for _ in range(40):
        if screen.armed:
            return screen
        await pilot.pause(0.05)
    raise AssertionError("the choice modal never began answering keys")


def test_a_choice_is_told_from_a_yes_or_no_by_its_choices() -> None:
    assert render.is_a_choice(_QUESTION)
    assert not render.is_a_choice({"name": "python", "input": {}})
    assert render.withdrawn_answer(_QUESTION) == ""
    assert render.withdrawn_answer({"name": "python"}) is False


def test_the_keys_line_is_drawn_from_the_choices() -> None:
    assert render.choice_keys(_QUESTION) == (
        "o  once (for this session)     a  always (for this project)     n / Esc  no     Ctrl-C  withdraw"
    )


async def test_each_key_answers_its_value_once_armed() -> None:
    for key, value in [("o", "once"), ("a", "always"), ("n", "no")]:
        app = BhApp()
        async with app.run_test(size=_SIZE) as pilot:
            answer = _choose(app)
            await _armed(pilot)
            await pilot.press(key)
            assert await asyncio.wait_for(answer, 1) == value
            await pilot.pause(0.05)
            assert not isinstance(app.screen, ApprovalScreen)


async def test_escape_answers_the_questions_escape_value() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answer = _choose(app, {**_QUESTION, "escape": "always"})
        await _armed(pilot)
        await pilot.press("escape")
        assert await asyncio.wait_for(answer, 1) == "always"


async def test_keys_pressed_before_it_is_armed_answer_nothing() -> None:
    app = BhApp(grace=5)
    async with app.run_test(size=_SIZE) as pilot:
        answer = _choose(app)
        screen = await _shown(pilot)
        assert not screen.armed
        await pilot.press("a", "o", "escape")
        await pilot.pause(0.1)
        assert not answer.done()
        assert isinstance(app.screen, ChoiceScreen)


async def test_a_key_that_is_no_choice_answers_nothing() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answer = _choose(app)
        await _armed(pilot)
        await pilot.press("y", "x")
        await pilot.pause(0.1)
        assert not answer.done()


async def test_it_shows_each_line_and_the_warning() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        _choose(app, {**_QUESTION, "warning": "the jail's network would be violated"})
        screen = await _shown(pilot)
        shown = [str(each.content) for each in screen.query(Static)]
        assert "What: net example.com:443" in shown
        assert "Asked by: row python, because: it fetches" in shown
        assert "Warning: the jail's network would be violated" in shown


async def test_ctrl_c_with_nothing_running_answers_nothing_chosen() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answer = _choose(app)
        await _armed(pilot)
        await pilot.press("ctrl+c")
        assert await asyncio.wait_for(answer, 1) == ""
        await pilot.pause(0.05)
        assert not isinstance(app.screen, ApprovalScreen)


async def test_a_cancelled_asker_takes_its_choice_down() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        output = TuiOutput(app.post_message, app.bridge)
        asking = asyncio.ensure_future(output.choose(_QUESTION))
        await _armed(pilot)
        asking.cancel()
        await pilot.pause(0.1)
        assert not isinstance(app.screen, ApprovalScreen)


async def test_an_app_that_has_ended_answers_nothing_chosen() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        output = TuiOutput(app.post_message, app.bridge)
        asking = asyncio.ensure_future(output.choose(_QUESTION))
        await _armed(pilot)
        app.bridge.end()
        assert await asyncio.wait_for(asking, 1) == ""
        assert await output.choose(_QUESTION) == ""


async def test_two_choices_are_asked_one_at_a_time() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        first, second = _choose(app), _choose(app, {**_QUESTION, "title": "Allow net other.org:443?"})
        await _armed(pilot)
        assert sum(isinstance(s, ChoiceScreen) for s in app.screen_stack) == 1
        await pilot.press("o")
        assert await asyncio.wait_for(first, 1) == "once"
        await _armed(pilot)
        assert not second.done()
        await pilot.press("n")
        assert await asyncio.wait_for(second, 1) == "no"
