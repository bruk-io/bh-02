"""The app under Pilot: the layout, the composer, Ctrl-C, a turn drawn as it streams, the
approval modal, the status bar; and `running`, which is how the ui row runs it."""

import asyncio
import re
import threading

import pytest
from textual.pilot import Pilot
from textual.widgets import OptionList

from tui_cordis_plugin import AppCrashed, BhApp, running, theme
from tui_cordis_plugin.messages import Asked, Noted, RowsUp, Shown, TurnEnded
from tui_cordis_plugin.widgets import (
    ActivityBar,
    ApprovalScreen,
    Composer,
    SidebarPanel,
    StatusBar,
    Transcript,
)

_SIZE = (120, 36)


def _blocks(app: BhApp) -> list[tuple[str, str]]:
    """The transcript's blocks as (kind, text)."""
    return app.query_one(Transcript).blocks()


async def test_the_layout_carries_bh_01_s_names_and_bh_01_s_dark_theme() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE):
        for widget in (ActivityBar, SidebarPanel, Transcript, Composer, StatusBar):
            assert app.query_one(widget) is not None
        assert app.theme == theme.NAME
        assert isinstance(app.focused, Composer)


def test_every_custom_token_a_widget_names_has_a_default() -> None:
    """A real launch parses every stylesheet at startup and dies on an undefined `$token`,
    which `run_test()` does not notice."""
    sheets = [cls.DEFAULT_CSS for cls in (ActivityBar, SidebarPanel, Transcript, Composer, StatusBar)]
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


async def test_the_status_bar_and_sidebar_show_what_rows_push() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        remove = app.frame.status("jail", "jailed fs_write ✓")
        app.frame.status("session", "20260922-1")
        app.frame.sessions(lambda: [{"id": "20260922-1"}])
        await pilot.pause()
        await app.workers.wait_for_complete()  # the sessions are read on a thread
        assert str(app.query_one(StatusBar).content) == "session: 20260922-1  │  jail: jailed fs_write ✓"
        assert [item["id"] for item in app.query_one(SidebarPanel).items] == ["20260922-1"]
        remove()
        await pilot.pause()
        assert str(app.query_one(StatusBar).content) == "session: 20260922-1"


async def test_a_broken_session_record_is_listed_and_named_in_the_transcript_once() -> None:
    broken = {"id": "20260101-dead", "broken": "session record /s/meta.json can't be read (not JSON)"}
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.sessions(lambda: [{"id": "20260922-1"}, broken])
        for _ in range(3):  # the sidebar is read again each time a sessions entry changes
            app.frame.sessions(lambda: [])()
            await pilot.pause()
            await app.workers.wait_for_complete()
        assert [item["id"] for item in app.query_one(SidebarPanel).items] == ["20260922-1", "20260101-dead"]
        notes = [text for kind, text in _blocks(app) if kind == "failure"]
        assert notes == [broken["broken"]]


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


def _options(app: BhApp) -> list[str]:
    """The sidebar's session entries as plain text, one per option."""
    listed = app.query_one("#sessions", OptionList)
    return [str(listed.get_option_at_index(i).prompt) for i in range(listed.option_count)]


async def test_the_sidebar_lists_sessions_once_marks_the_running_one_and_says_how_to_resume() -> None:
    app = BhApp()
    items = [
        {"id": "20260922-2", "created": "2026-09-22T10:05:00", "stack": "claude", "current": True},
        {"id": "20260922-1", "created": "2026-09-21T09:00:00", "stack": "ollama", "current": False},
    ]
    async with app.run_test(size=_SIZE) as pilot:
        assert _options(app) == ["(none listed)"]
        app.frame.sessions(lambda: items)
        for n in range(5):  # status pushes redraw the frame; the list stays one list
            app.frame.status(f"f{n}", "x")
        await pilot.pause()
        assert _options(app) == [
            "20260922-2\n2026-09-22 10:05 · claude\n current ",
            "20260922-1\n2026-09-21 09:00 · ollama",
        ]
        app.query_one("#sessions", OptionList).focus()
        await pilot.press("home", "down", "enter")
        await pilot.pause()
        note = "to continue session 20260922-1, leave (Ctrl-Q) and run `bh-02 --resume 20260922-1`"
        assert ("note", note) in _blocks(app)
        await pilot.press("up", "enter")
        await pilot.pause()
        assert any("is this one" in text for kind, text in _blocks(app) if kind == "note")


async def test_the_sidebar_reads_the_sessions_again_when_it_is_focused() -> None:
    app = BhApp()
    items = [{"id": "20260922-1", "created": "2026-09-21T09:00:00", "stack": "claude"}]
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.sessions(lambda: list(items))
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert [i["id"] for i in app.query_one(SidebarPanel).items] == ["20260922-1"]
        items.insert(0, {"id": "20260922-2", "created": "2026-09-22T10:05:00", "stack": "claude"})
        app.query_one("#sessions", OptionList).focus()  # started since, from another terminal
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert [i["id"] for i in app.query_one(SidebarPanel).items] == ["20260922-2", "20260922-1"]


async def test_on_a_narrow_screen_ctrl_b_opens_the_sidebar_ready_to_choose_a_session() -> None:
    """80x24: Ctrl-B, Down, Down, Enter says how to continue the session chosen, with no Tab."""
    app = BhApp()
    items = [
        {"id": f"20260923-01223{n}-aaa{n}", "created": f"2026-09-23T01:22:3{n}", "stack": "claude"}
        for n in (5, 4, 3)
    ]
    async with app.run_test(size=(80, 24)) as pilot:
        app.frame.sessions(lambda: [{**items[0], "current": True}, *items[1:]])
        await pilot.pause()
        await pilot.press("ctrl+b")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        notes = [text for kind, text in _blocks(app) if kind == "note"]
        assert any("bh-02 --resume 20260923-01223" in text for text in notes), notes


async def test_the_sessions_are_read_off_the_loop() -> None:
    """Reading them scans the state directory; the loop (cordis's too) goes on meanwhile."""
    app = BhApp()
    reading = threading.Event()
    threads: list[threading.Thread] = []

    def slow() -> list[dict[str, str]]:
        threads.append(threading.current_thread())
        reading.wait(5)
        return [{"id": "20260922-1"}]

    async with app.run_test(size=_SIZE) as pilot:
        app.frame.sessions(slow)
        await pilot.pause()
        ticked = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(ticked.set_result, None)
        await asyncio.wait_for(ticked, 1)  # the loop is not held while the reader waits
        assert app.query_one(SidebarPanel).items == ()
        reading.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert [i["id"] for i in app.query_one(SidebarPanel).items] == ["20260922-1"]
        assert threads and threads[0] is not threading.main_thread()


async def test_status_changes_do_not_read_the_sessions_again() -> None:
    """Usage pushes the status bar twice per event; the sessions reader scans disk, so only a
    sessions entry changing (or the sidebar shown or focused) reads it."""
    app = BhApp()
    reads = 0

    def listed() -> list[dict[str, str]]:
        nonlocal reads
        reads += 1
        return [{"id": "20260922-1", "created": "2026-09-21T09:00:00", "stack": "claude"}]

    async with app.run_test(size=_SIZE) as pilot:
        app.frame.sessions(listed)
        await pilot.pause()
        before = reads
        assert before >= 1
        for n in range(10):
            remove = app.frame.status("usage", f"{n} in")
            remove()
        app.frame.status("usage", "done")
        await pilot.pause()
        assert reads == before and "usage: done" in str(app.query_one(StatusBar).content)
        app.frame.sessions(lambda: [])  # another sessions entry: read again
        await pilot.pause()
        assert reads == before + 1


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
