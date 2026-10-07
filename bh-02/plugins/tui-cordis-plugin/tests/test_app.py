"""The app under Pilot: the layout, the composer, Ctrl-C, a turn drawn as it streams, the
approval modal, the status bar; and `running`, which is how the ui row runs it."""

import asyncio
import re

import pytest
from textual.pilot import Pilot

from tui_cordis_plugin import AppCrashed, BhApp, running, theme
from tui_cordis_plugin.messages import Asked, Noted, RowsUp, Shown, TurnEnded
from tui_cordis_plugin.widgets import ApprovalScreen, Composer, StatusBar, Transcript

_SIZE = (120, 36)


def _blocks(app: BhApp) -> list[tuple[str, str]]:
    """The transcript's blocks as (kind, text)."""
    return app.query_one(Transcript).blocks()


async def test_the_conversation_fills_the_width_over_the_status_bar_in_bh_01_s_dark_theme() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        transcript, composer, bar = (app.query_one(widget) for widget in (Transcript, Composer, StatusBar))
        assert transcript.region.width == composer.region.width == bar.region.width == _SIZE[0]
        assert transcript.region.y < composer.region.y < bar.region.y == _SIZE[1] - 1
        assert app.theme == theme.NAME
        assert isinstance(app.focused, Composer)


def test_every_custom_token_a_widget_names_has_a_default() -> None:
    """A real launch parses every stylesheet at startup and dies on an undefined `$token`,
    which `run_test()` does not notice."""
    sheets = [cls.DEFAULT_CSS for cls in (Transcript, Composer, StatusBar)]
    named = {
        name for css in [*sheets, ApprovalScreen.DEFAULT_CSS] for name in re.findall(r"\$(bh-[\w-]+)", css)
    }
    assert named and named <= set(BhApp().get_theme_variable_defaults())


async def test_enter_sends_the_message_and_shows_it() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"hello", "enter")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "hello"
        assert ("user", "› hello") in _blocks(app)
        assert app.query_one(Composer).text == ""


async def test_ctrl_j_starts_a_new_line_instead_of_sending() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press("a", "ctrl+j", "b")
        assert app.query_one(Composer).text == "a\nb"
        await pilot.press("enter")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "a\nb"


async def test_exit_in_the_composer_leaves_without_sending_anything() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"/exit", "enter")
        await pilot.pause()
        assert app.return_code == 0
    assert not app.bridge.turn_running


async def test_ctrl_c_stops_the_running_turn_and_otherwise_says_how_to_leave() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press("ctrl+c")
        assert any(text.startswith("Nothing is running.") for _, text in _blocks(app))
        assert app.return_code is None  # still running: Ctrl-C never quits
        turn = asyncio.ensure_future(app.bridge.interrupted())
        await pilot.pause()
        await pilot.press("ctrl+c")
        await asyncio.wait_for(turn, 1)


async def test_ctrl_c_while_a_command_runs_says_it_does_not_stop_one_and_a_starting_turn_hears_it() -> None:
    """A Ctrl-C held for the line being handled: a turn starting hears it at once and nothing is
    said; a command (a `!` one may take minutes) never does, so the app says Ctrl-C doesn't stop
    it, and how to leave."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"!sleep 600", "enter")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "!sleep 600"
        await pilot.press("ctrl+c")
        await pilot.pause(0.5)
        said = [text for _, text in _blocks(app) if text.startswith("A command is running")]
        assert said == [
            "A command is running, and Ctrl-C stops only a turn: a `!` command runs until it ends "
            "or its timeout stops it. Ctrl-Q, /exit or /quit leaves, and stops it too."
        ]
        await pilot.press(*"hello", "enter")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "hello"  # a turn starts
        await pilot.press("ctrl+c")
        await asyncio.wait_for(app.bridge.interrupted(), 1)  # and hears the held Ctrl-C
        await pilot.pause(0.5)
        assert len([text for _, text in _blocks(app) if text.startswith("A command is running")]) == 1


async def test_a_reply_streams_into_one_block_and_other_events_get_their_own() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        before = len(_blocks(app))
        for event in (
            {"type": "text", "text": "Hel"},
            {"type": "text", "text": "lo"},
            {"type": "tool_call", "name": "python", "input": {"code": "1 + 1"}},
            {"type": "tool_result", "call_id": "c", "content": "2", "is_error": False},
            {"type": "text", "text": "Two."},
            {"type": "something_new"},
            {"type": "stop", "reason": "interrupted"},
        ):
            app.post_message(Shown(event))
        app.post_message(TurnEnded())
        app.post_message(Shown({"type": "text", "text": "Next"}))
        app.post_message(Noted("error: slow down", "failure"))
        await pilot.pause()
        assert _blocks(app)[before:] == [
            ("text", "Hello"),
            ("tool_call", "⏺ python\n1 + 1"),
            ("tool_result", "⎿ 2"),
            ("text", "Two."),
            ("stop", "stopped: interrupted"),
            ("text", "Next"),  # a new turn: a new block, not appended to the last one
            ("failure", "error: slow down"),
        ]


async def test_a_question_is_a_modal_and_its_answer_goes_back() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"name": "python", "input": {"code": "print(1)"}}, answer))
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)
        while not app.screen.armed:  # it answers nothing for a moment after it is shown
            await pilot.pause(0.05)
        await pilot.press("y")
        assert await asyncio.wait_for(answer, 1) is True
        await pilot.pause()
        assert not isinstance(app.screen, ApprovalScreen)


async def test_a_question_nobody_waits_for_is_taken_down() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"name": "python", "input": {"code": "1"}}, answer))
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)
        answer.cancel()  # the turn asking was interrupted
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, ApprovalScreen)


async def test_the_status_bar_shows_what_rows_push() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        remove = app.frame.status("jail", "jailed fs_write ✓")
        app.frame.status("session", "20260922-1")
        await pilot.pause()
        assert str(app.query_one(StatusBar).content) == "session: 20260922-1  │  jail: jailed fs_write ✓"
        remove()
        await pilot.pause()
        assert str(app.query_one(StatusBar).content) == "session: 20260922-1"


async def test_running_enters_once_the_app_is_up_and_leaving_ends_its_input() -> None:
    app = BhApp()
    async with running(app, headless=True) as up:
        assert up is app and app.is_running
        reading = asyncio.ensure_future(app.bridge.line())
        await asyncio.sleep(0)
    assert await asyncio.wait_for(reading, 1) is None


async def test_exit_while_running_ends_the_input() -> None:
    app = BhApp()
    async with running(app, headless=True):
        await Pilot(app).press(*"/exit", "enter")
        assert await asyncio.wait_for(app.bridge.line(), 2) is None


class _Unprintable:
    def __str__(self) -> str:
        raise RuntimeError("cannot draw this")


async def test_a_crash_ends_the_app_and_reaches_whoever_reads_next(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = BhApp()
    async with running(app, headless=True):
        app.post_message(Shown({"type": "text", "text": _Unprintable()}))
        with pytest.raises(AppCrashed) as raised:
            await asyncio.wait_for(app.bridge.line(), 2)
    assert "crashed (exit code 1)" in raised.value.message
    assert "cannot draw this" in capsys.readouterr().err  # Textual's own traceback


async def test_a_message_typed_while_the_model_comes_back_up_says_it_waits_and_is_read_after() -> None:
    """`/model` and `/clear` restart the model row, and the chat row with it: a line typed
    then has no reader for seconds. It says what it waits for, and it is not dropped."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        for kind, row in [("unloading", "loop"), ("unloading", "chat"), ("inactive", "chat")]:
            app.bridge.row_changed(kind, row)  # as the output's lifecycle hears them
        await pilot.press(*"hello", "enter")
        await pilot.pause()
        assert _blocks(app)[-2:] == [
            ("user", "› hello"),
            ("note", "⧗ waiting for loop to start; this message is sent once it is up"),
        ]
        app.bridge.row_changed("active", "loop")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "hello"  # read once the chat is back

        reading = asyncio.ensure_future(app.bridge.line())  # a reader waits: no note
        await pilot.pause()
        await pilot.press(*"again", "enter")
        assert await asyncio.wait_for(reading, 1) == "again"
        await pilot.pause()
        assert _blocks(app)[-1] == ("user", "› again")


async def test_a_message_waiting_on_restarted_rows_does_not_name_a_status_bar_row() -> None:
    """`/clear` restarts the kernel, and `status` (which binds no key, only pushes a
    status field) reloads after it: a line typed then waits for the rows the chat depends on
    and does not name `status`, whose reload no message waits for."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        for kind, row in [("reload", "status"), ("active", "status")]:
            app.bridge.row_changed(kind, row)  # at boot: it came up binding nothing
        for kind, row in [("unloading", "loop"), ("unloading", "status"), ("reload", "status")]:
            app.bridge.row_changed(kind, row)
        await pilot.press(*"hello", "enter")
        await pilot.pause()
        assert _blocks(app)[-1] == (
            "note",
            "⧗ waiting for loop to start; this message is sent once it is up",
        )
        assert app.bridge.waiting_on == {"loop"}
        app.bridge.row_changed("active", "loop")
        assert app.bridge.waiting_on == frozenset()  # only the status-bar row still coming up
        assert await asyncio.wait_for(app.bridge.line(), 1) == "hello"


async def test_a_kept_status_field_goes_once_every_row_has_stayed_up_a_moment() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        remove = app.frame.status("jail", "jailed")
        app.bridge.row_changed("unloading", "kernel")
        remove()
        await pilot.pause()
        assert "jail: jailed" in str(app.query_one(StatusBar).content)  # kept while it comes up
        app.bridge.row_changed("inactive", "kernel")
        app.post_message(RowsUp())
        app.bridge.row_changed("reload", "kernel")  # coming up again before the grace ends
        await pilot.pause(1.2)
        assert "jail: jailed" in str(app.query_one(StatusBar).content)
        app.bridge.row_changed("active", "kernel")
        app.post_message(RowsUp())
        await pilot.pause(1.2)
        assert "jail" not in str(app.query_one(StatusBar).content)  # nobody pushed it again


async def test_the_grace_before_a_kept_field_goes_runs_from_the_last_time_rows_came_up() -> None:
    """Rows settle, start again at once and settle again later: the field stays a full grace
    after the second settle, not just what is left of the first one's."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        remove = app.frame.status("jail", "jailed")
        app.bridge.row_changed("unloading", "kernel")
        remove()
        app.bridge.row_changed("inactive", "kernel")
        app.post_message(RowsUp())  # settled at t=0
        await pilot.pause(0.1)
        app.bridge.row_changed("reload", "kernel")
        await pilot.pause(0.6)
        app.bridge.row_changed("active", "kernel")
        app.post_message(RowsUp())  # settled again at t≈0.7
        await pilot.pause(0.6)  # t≈1.3: the first grace is over, the second is not
        assert "jail: jailed" in str(app.query_one(StatusBar).content)
        await pilot.pause(0.7)
        assert "jail" not in str(app.query_one(StatusBar).content)


async def test_a_line_typed_after_clear_and_not_read_yet_stays_on_screen_after_the_clear() -> None:
    """`cleared` drops the old conversation; a line typed after `/clear` is sent in the new one,
    so it is drawn again after the clear, not wiped while it waits."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.send("before")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "before"
        app.send("/clear")  # nobody reads yet: kept, with the line typed after it
        app.send("again")
        assert app.bridge.kept == ("/clear", "again")
        assert await asyncio.wait_for(app.bridge.line(), 1) == "/clear"  # the command runs
        app.post_message(Shown({"type": "cleared"}, {"type": "note", "text": "cleared"}))
        await pilot.pause()
        assert _blocks(app) == [("user", "› again"), ("note", "cleared")]
