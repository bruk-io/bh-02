"""Copying (TASK-0089.05): Ctrl-C copies a selection and otherwise stops a reply, Cmd-C is
Textual's own `super+c`, a mouse selection is copied when it ends, and Ctrl-T copies the newest
reply. The clipboard is the terminal's (OSC 52, through `App.copy_to_clipboard`), which a Pilot
test cannot read: it asserts what the app asked to copy (Textual's own record, `app.clipboard`)
and the line it showed (a toast)."""

import asyncio

import pytest
from textual import events
from textual.app import App
from textual.binding import Binding
from textual.geometry import Offset
from textual.pilot import Pilot
from textual.screen import Screen
from textual.selection import Selection
from textual.widgets import Static

from tui_cordis_plugin import BhApp, render
from tui_cordis_plugin.messages import Asked, Shown
from tui_cordis_plugin.widgets import ApprovalScreen, Composer, Transcript

_SIZE = (100, 30)
_SAID = "Hello brave new world, here is the answer."


def test_a_copy_says_how_many_characters_in_one_short_line() -> None:
    assert render.copied_line("abc") == "Copied 3 characters"
    assert render.copied_line("a") == "Copied 1 character"


def test_the_newest_reply_is_the_text_after_the_last_message_in_order_as_written() -> None:
    blocks = [
        ("user", "› first"),
        ("text", "old answer"),
        ("user", "› second"),
        ("thinking", ""),
        ("text", "I will look.\n\n**bold**, `code`\n"),
        ("tool_call", ""),
        ("tool_result", ""),
        ("text", "  Found it.  "),
        ("usage", ""),
    ]
    assert render.newest_reply(blocks) == "I will look.\n\n**bold**, `code`\n\nFound it."


def test_while_the_newest_message_has_no_text_yet_the_reply_before_it_is_the_newest() -> None:
    blocks = [("user", "› a"), ("text", "answer a"), ("user", "› b"), ("tool_call", ""), ("note", "x")]
    assert render.newest_reply(blocks) == "answer a"


def test_with_nothing_said_there_is_no_reply() -> None:
    assert render.newest_reply([]) is None
    assert render.newest_reply([("user", "› a"), ("note", "n"), ("text", "  \n")]) is None


def _forget(app: BhApp) -> None:
    """Empty Textual's record of the clipboard, past `BhApp`'s line saying so."""
    App.copy_to_clipboard(app, "")


def _told(app: BhApp) -> list[str]:
    """The lines on screen as toasts, newest last."""
    return [str(toast.render()) for toast in app.screen.query("Toast")]


async def _reply_running(app: BhApp, pilot: Pilot[None]) -> asyncio.Future[None]:
    turn = asyncio.ensure_future(app.bridge.interrupted())
    await pilot.pause()
    assert app.bridge.turn_running
    return turn


async def _say(app: BhApp, pilot: Pilot[None], text: str = _SAID) -> Static:
    """The model says `text`; the block that shows it."""
    app.post_message(Shown({"type": "text", "text": text}))
    await pilot.pause()
    return next(s for s in app.query_one(Transcript).query(Static) if text.split("\n")[0] in _plain(s))


def _plain(block: Static) -> str:
    content = block.content
    return content if isinstance(content, str) else content.plain


async def _select(pilot: Pilot[None], block: Static, first: int, last: int) -> None:
    """Drag over cells `first` to `last` of the block's first row, as a person does."""
    await pilot.mouse_down(block, offset=(first, 0))
    await pilot.hover(block, offset=(last, 0))
    await pilot.mouse_up(block, offset=(last, 0))
    await pilot.pause()


async def test_a_mouse_selection_in_the_transcript_is_copied_when_it_ends() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot)
        await _select(pilot, block, 0, 10)
        assert app.screen.get_selected_text() == "Hello brave"  # still shown selected
        assert app.clipboard == "Hello brave"
        assert _told(app) == ["Copied 11 characters"]


async def test_a_click_or_a_one_character_selection_copies_nothing_and_says_nothing() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot)
        await pilot.click(block, offset=(4, 0))  # a click: nothing selected
        await pilot.pause()
        assert app.clipboard == "" and _told(app) == []
        # a drag that ended on one character (Pilot's mouse always moves on to where it lets go,
        # so the selection is what the screen holds then, and its own word that the mouse is up)
        app.screen.selections = {block: Selection.from_offsets(Offset(3, 0), Offset(4, 0))}
        app.screen.post_message(events.TextSelected())
        await pilot.pause()
        assert app.screen.get_selected_text() == "l"
        assert app.clipboard == "" and _told(app) == []


async def test_ctrl_c_with_text_selected_copies_it_and_stops_nothing_a_second_one_stops_the_reply() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot)
        turn = await _reply_running(app, pilot)
        await _select(pilot, block, 6, 10)  # "brave", copied as the mouse let go
        _forget(app)  # what Ctrl-C copies is what is asked
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.clipboard == "brave" and not turn.done()  # copied, and the reply runs on
        assert app.screen.get_selected_text() is None  # cleared, so the next one is a stop
        await pilot.press("ctrl+c")
        await asyncio.wait_for(turn, 1)


async def test_ctrl_c_with_no_selection_stops_a_reply_as_before() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        turn = await _reply_running(app, pilot)
        await pilot.press("ctrl+c")
        await asyncio.wait_for(turn, 1)
        assert app.clipboard == "" and _told(app) == []


async def test_ctrl_c_copies_the_composer_s_own_selection_too_and_stops_nothing() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        turn = await _reply_running(app, pilot)
        await pilot.press(*"hello", "shift+left", "shift+left", "shift+left")
        assert app.query_one(Composer).selected_text == "llo"
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.clipboard == "llo" and not turn.done()
        assert app.query_one(Composer).text == "hello" and app.query_one(Composer).selected_text == ""
        await pilot.press("ctrl+c")  # nothing selected now: the stop
        await asyncio.wait_for(turn, 1)


@pytest.mark.parametrize("focus", [Composer, Transcript])
async def test_cmd_c_copies_the_transcript_selection_as_textual_reports_it_and_stops_nothing(
    focus: type,
) -> None:
    """Where a terminal passes Cmd through (the kitty keyboard protocol), it is `super+c`,
    which Textual binds to the screen's copy (and the composer's own): the app's priority Ctrl-C
    does not shadow it. With the focus in the composer (its copy has nothing selected and
    passes) or in the transcript, where a mouse selection leaves it."""
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot)
        turn = await _reply_running(app, pilot)
        await _select(pilot, block, 6, 10)
        app.query_one(focus).focus()
        _forget(app)
        await pilot.press("super+c")
        await pilot.pause()
        assert app.clipboard == "brave" and not turn.done()
        assert "Copied 5 characters" in _told(app)


async def test_cmd_c_with_nothing_selected_does_nothing() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        turn = await _reply_running(app, pilot)
        await pilot.press("super+c")
        await pilot.pause()
        assert app.clipboard == "" and _told(app) == [] and not turn.done()


async def test_ctrl_t_copies_the_newest_reply_whole_as_the_model_wrote_it() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        for event in (
            {"type": "text", "text": "Looking at **it**.\n\n"},
            {"type": "tool_call", "name": "python", "input": {"code": "1 + 1"}},
            {"type": "tool_result", "call_id": "c", "content": "2", "is_error": False},
            {"type": "text", "text": "It is `2`."},
        ):
            app.post_message(Shown(event))
        await pilot.pause()
        await pilot.press(*"my draft", "ctrl+t")
        await pilot.pause()
        assert app.clipboard == "Looking at **it**.\n\nIt is `2`."
        assert _told(app) == [f"Copied {len(app.clipboard)} characters"]
        assert app.query_one(Composer).text == "my draft"  # a key the composer does not use


async def test_ctrl_t_with_no_reply_copies_nothing_and_says_so() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert app.clipboard == "" and _told(app) == ["Nothing to copy: no reply yet"]


def _keys(owner: type, *, but: str = "") -> set[str]:
    """The keys the class `owner` itself binds (its `BINDINGS`), but those of action `but`."""
    return {
        key.strip()
        for binding in owner.__dict__.get("BINDINGS", [])
        if isinstance(binding, Binding) and binding.action != but
        for key in binding.key.split(",")
    }


def test_ctrl_t_shadows_no_key_of_the_composer_a_screen_or_the_app() -> None:
    taken = set().union(*(_keys(owner) for owner in (*Composer.__mro__, Screen, *App.__mro__)))
    taken |= _keys(BhApp, but="copy_reply") | {App.COMMAND_PALETTE_BINDING}
    assert "ctrl+t" not in taken and "ctrl+c" in taken  # the walk reaches TextArea's bindings
    assert "ctrl+t" in _keys(BhApp)


async def test_ctrl_t_copies_while_a_reply_streams() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        turn = await _reply_running(app, pilot)
        app.post_message(Shown({"type": "text", "text": "so far"}))
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert app.clipboard == "so far" and not turn.done()


async def test_esc_stops_a_reply_and_never_copies_a_selection() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot)
        turn = await _reply_running(app, pilot)
        await _select(pilot, block, 6, 10)
        _forget(app)
        await pilot.press("escape")
        await asyncio.wait_for(turn, 1)
        assert app.clipboard == ""


async def test_with_a_question_up_ctrl_c_answers_it_no_and_nothing_is_copied() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot)
        turn = await _reply_running(app, pilot)
        _forget(app)
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"tool": "python", "input": {"code": "print(1 + 1)"}}, answer))
        await pilot.pause(0.2)
        assert isinstance(app.screen, ApprovalScreen)
        source = app.screen.query_one("#approval-source", Static)
        app.screen.selections = {source: Selection.from_offsets(Offset(0, 0), Offset(5, 0))}  # in the modal
        assert app.screen.get_selected_text() == "print"
        await pilot.press("ctrl+t")  # the modal cuts off the app's keys
        await pilot.pause()
        assert app.clipboard == "" and _told(app) == []
        await pilot.press("ctrl+c")
        await asyncio.wait_for(turn, 1)  # the stop, as ever
        assert app.clipboard == ""
        await pilot.pause(0.6)
        assert await answer is False
        assert block.is_attached  # (the reply drawn before is untouched)


async def test_what_was_copied_is_said_off_the_conversation_so_a_streaming_reply_is_not_split() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE, notifications=True) as pilot:
        block = await _say(app, pilot, "Streaming reply, first part")
        turn = await _reply_running(app, pilot)
        await _select(pilot, block, 0, 8)
        app.post_message(Shown({"type": "text", "text": " and the rest."}))
        await pilot.press("ctrl+c")
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert _told(app) == ["Copied 9 characters", "Copied 9 characters", "Copied 41 characters"]
        texts = [text for kind, text in app.query_one(Transcript).blocks() if kind == "text"]
        assert texts == ["Streaming reply, first part and the rest."]  # one block, whole
        assert app.clipboard == "Streaming reply, first part and the rest." and not turn.done()
