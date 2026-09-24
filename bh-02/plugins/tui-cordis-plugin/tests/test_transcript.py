"""The transcript under Pilot: each kind of event as it streams, a long reply staying quick,
wrapped lines keeping their gutter, and a session's history drawn again when the app starts."""

import asyncio
import json
import time
from pathlib import Path

from textual.widgets import Collapsible, Static

from tui_cordis_plugin import BhApp, History, replayable
from tui_cordis_plugin.messages import Noted, Shown, TurnEnded, TurnStarted
from tui_cordis_plugin.widgets import Stream, Transcript

_SIZE = (120, 36)


def _screen(app: BhApp) -> str:
    """What the terminal shows, as text."""
    return "\n".join(
        "".join(segment.text for segment in app.screen._compositor.render_update(full=True).strips[y])  # noqa: SLF001
        for y in range(app.size.height)
    )


async def test_every_kind_of_event_gets_a_block_of_its_own_kind() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = app.query_one(Transcript)
        before = len(transcript.blocks())
        for event in (
            {"type": "thinking", "text": "Let me "},
            {"type": "thinking", "text": "check.\nThen answer."},
            {"type": "text", "text": "Here is **the** plan:\n- run it"},
            {"type": "tool_call", "id": "c", "name": "python", "input": {"code": "print(1)"}},
            {"type": "tool_result", "call_id": "c", "content": "boom", "is_error": True},
            {"type": "usage", "input_tokens": 1200, "output_tokens": 30, "cost_usd": 0.01},
            {"type": "note", "text": "rows: 12"},
            {"type": "stop", "reason": "end_turn"},  # quiet: no block
        ):
            app.post_message(Shown(event))
        app.post_message(TurnEnded())
        await pilot.pause()
        assert transcript.blocks()[before:] == [
            ("thinking", "Let me check.\nThen answer."),
            ("text", "Here is the plan:\n• run it"),
            ("tool_call", "⏺ python\nprint(1)"),
            ("tool_result", "⎿ boom"),
            ("usage", "1,200 in · 30 out · $0.0100"),
            ("note", "rows: 12"),
        ]
        (result,) = transcript.query(".tool_result")
        assert result.has_class("-error")


async def test_a_model_step_s_usage_in_parts_is_one_line_after_what_it_said() -> None:
    """Anthropic sends what a turn read as it starts and the rest as it ends: one line, the sum,
    under the turn; the next model step (after a result) gets a line of its own."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = app.query_one(Transcript)
        for event in (
            {"type": "usage", "input_tokens": 1000, "output_tokens": 0, "cost_usd": 0.001, "partial": True},
            {"type": "text", "text": "Running it."},
            {"type": "tool_call", "id": "c", "name": "python", "input": {"code": "1"}},
            {"type": "usage", "input_tokens": 0, "output_tokens": 30, "cost_usd": 0.0002},
            {"type": "tool_result", "call_id": "c", "content": "1", "is_error": False},
            {"type": "usage", "input_tokens": 1100, "output_tokens": 0, "partial": True},
            {"type": "stop", "reason": "interrupted"},  # stopped before the end: what was read stands
        ):
            app.post_message(Shown(event))
        app.post_message(TurnEnded())
        await pilot.pause()
        assert [b for b in transcript.blocks() if b[0] != "note"] == [
            ("text", "Running it."),
            ("tool_call", "⏺ python\n1"),
            ("usage", "1,000 in · 30 out · $0.0012"),
            ("tool_result", "⎿ 1"),
            ("usage", "1,100 in · output not counted"),  # its output count never came
            ("stop", "stopped: interrupted"),
        ]


async def test_a_line_typed_while_a_reply_streams_is_drawn_after_it() -> None:
    """The line goes in at once but is drawn when the reply ends: the reply's text and its one
    usage line stay together above it."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        transcript = app.query_one(Transcript)
        app.post_message(TurnStarted())
        app.post_message(Shown({"type": "usage", "input_tokens": 900, "output_tokens": 0, "partial": True}))
        app.post_message(Shown({"type": "text", "text": "twenty-"}))
        await pilot.pause()
        app.send("What is 3+4?")
        await pilot.pause()
        app.post_message(Shown({"type": "text", "text": "eight"}))
        app.post_message(Shown({"type": "usage", "input_tokens": 0, "output_tokens": 118}))
        app.post_message(TurnEnded())
        await pilot.pause()
        assert [b for b in transcript.blocks() if b[0] != "note"] == [
            ("text", "twenty-eight"),
            ("usage", "900 in · 118 out"),
            ("user", "› What is 3+4?"),
        ]
        app.send("and 5+5?")  # no reply streaming: drawn at once
        await pilot.pause()
        assert transcript.blocks()[-1] == ("user", "› and 5+5?")


async def test_thinking_folds_to_one_line_once_the_reply_moves_on() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.post_message(Shown({"type": "thinking", "text": "first\nsecond"}))
        await pilot.pause()
        (thinking,) = app.query(Collapsible)
        assert not thinking.collapsed  # open while it streams
        app.post_message(Shown({"type": "text", "text": "Answer."}))
        await pilot.pause()
        assert thinking.collapsed and thinking.title == "thinking · 2 lines"
        assert "second" not in _screen(app) and "thinking · 2 lines" in _screen(app)


async def test_a_long_reply_streams_without_slowing_down() -> None:
    """2,000 lines a few words at a time: the last quarter takes about as long as the first,
    because a chunk only re-draws the open piece of the stream, never the whole reply."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        quarters = []
        for quarter in range(4):
            started = time.perf_counter()
            for n in range(quarter * 500, (quarter + 1) * 500):
                for chunk in (f"Line {n} ", "has a **few** ", "words.\n"):
                    app.post_message(Shown({"type": "text", "text": chunk}))
                if n % 50 == 49:
                    await pilot.pause()
            await pilot.pause()
            quarters.append(time.perf_counter() - started)
        stream = app.query_one(Stream)
        assert stream.text.count("\n") == 2000 and stream.text.startswith("Line 0 has")
        assert stream.pieces <= 2000 // 20  # a widget per couple of dozen lines, not per chunk
        assert quarters[-1] < 2 * quarters[0] + 0.5, quarters
        assert "Line 1999 has a few words." in _screen(app)  # and it followed the end


async def test_a_long_paragraph_with_no_newline_streams_without_slowing_down() -> None:
    """3,000 chunks of one line (no newline at all): the stream still settles pieces, by size,
    so the last chunks cost about what the first did, and the text is kept exactly."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        quarters = []
        for quarter in range(4):
            started = time.perf_counter()
            for n in range(quarter * 750, (quarter + 1) * 750):
                app.post_message(Shown({"type": "text", "text": f"word{n:05} and **some** more "}))
                if n % 50 == 49:
                    await pilot.pause()
            await pilot.pause()
            quarters.append(time.perf_counter() - started)
        stream = app.query_one(Stream)
        assert "\n" not in stream.text and stream.text.count("word") == 3000
        assert stream.text.startswith("word00000 and **some** more word00001")
        assert stream.pieces > 20  # settled by size, not held open as one growing piece
        assert quarters[-1] < 2 * quarters[0] + 0.5, quarters
        assert "word02999" in _screen(app)  # and it followed the end


async def test_wrapped_lines_keep_their_gutter() -> None:
    long = " ".join(f"word{n}" for n in range(60))
    app = BhApp()
    async with app.run_test(size=(80, 40)) as pilot:
        app.post_message(Shown({"type": "tool_call", "id": "c", "name": "python", "input": {"code": long}}))
        app.post_message(Shown({"type": "tool_result", "call_id": "c", "content": long, "is_error": False}))
        await pilot.pause()
        code = app.query_one(".tool_call .code", Static)
        body = app.query_one(".tool_result .body", Static)
        marker = app.query_one(".tool_result .marker", Static)
        assert code.size.height > 1 and body.size.height > 1  # both wrapped
        lines = _screen(app).splitlines()
        code_rows = lines[code.region.y : code.region.bottom]
        assert all(row[code.region.x] == "│" for row in code_rows)  # the gutter, on every row
        body_rows = lines[body.region.y : body.region.bottom]
        assert body.region.x == marker.region.right  # the body hangs beside its marker
        assert all(row[marker.region.x : body.region.x].strip() in ("", "⎿") for row in body_rows)
        assert all(row[body.region.x] != " " for row in body_rows)  # nothing wraps under the marker


async def test_a_diff_result_and_an_unusual_stop_are_drawn() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new"
        app.post_message(Shown({"type": "tool_result", "call_id": "c", "content": diff, "is_error": False}))
        app.post_message(Shown({"type": "stop", "reason": "max_tokens"}))
        await pilot.pause()
        screen = _screen(app)
        assert "+new" in screen and "stopped: max_tokens" in screen


async def test_what_is_shown_is_kept_and_drawn_again_by_the_next_app(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    first = BhApp(history=History(str(path)))
    async with first.run_test(size=_SIZE) as pilot:
        await pilot.press(*"hello", "enter")
        for text in ("Hel", "lo ", "back"):
            first.post_message(Shown({"type": "text", "text": text}))
        first.post_message(Shown({"type": "tool_call", "id": "c", "name": "python", "input": {"code": "1"}}))
        first.post_message(TurnEnded())
        first.post_message(Noted("error: slow down", "failure"))
        await pilot.pause()
    kinds = [json.loads(line)["type"] for line in path.read_text().splitlines()]
    assert kinds == ["user", "text", "text", "text", "tool_call", "turn_end", "noted"]

    history = History(str(path))
    second = BhApp(history=history, replay=replayable(history.read(), 400))
    async with second.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        assert second.query_one(Transcript).blocks() == [
            ("user", "› hello"),
            ("text", "Hello back"),  # the streamed run, merged
            ("tool_call", "⏺ python\n1"),
            ("failure", "error: slow down"),
            ("note", "↑ the session so far (a resumed session's kernel starts empty)"),
            (
                "note",
                "Ctrl-Q, /exit or /quit leaves; Ctrl-C only stops a running turn; Ctrl-P lists commands.",
            ),
        ]
        await pilot.press(*"again", "enter")
        await pilot.pause()
    assert json.loads(path.read_text().splitlines()[-1]) == {"type": "user", "text": "again"}


async def test_a_history_that_cannot_be_kept_is_said_once_and_the_app_goes_on(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("")
    app = BhApp(history=History(str(tmp_path / "file" / "events.jsonl")), replay=None)
    async with app.run_test(size=_SIZE) as pilot:
        await pilot.press(*"one", "enter")
        await pilot.press(*"two", "enter")
        await pilot.pause()
        failures = [text for kind, text in app.query_one(Transcript).blocks() if kind == "failure"]
        assert len(failures) == 1 and failures[0].startswith("history is not being kept")
        assert app.return_code is None


async def test_cleared_drops_the_conversation_from_the_screen_and_a_resume_starts_after_it(
    tmp_path: Path,
) -> None:
    """`/clear` answers `cleared` then a note (CONTRACTS.md: event): the transcript keeps only
    the note, the history keeps everything (the session's usage), and a resume draws from the
    clear on."""
    path = tmp_path / "events.jsonl"
    used = {"type": "usage", "input_tokens": 100, "output_tokens": 10}
    first = BhApp(history=History(str(path)))
    async with first.run_test(size=_SIZE) as pilot:
        await pilot.press(*"hello", "enter")
        assert await asyncio.wait_for(first.bridge.line(), 1) == "hello"  # the chat row reads it
        first.post_message(Shown({"type": "text", "text": "old reply"}, used))
        first.post_message(TurnEnded())
        await pilot.pause()
        assert ("text", "old reply") in first.query_one(Transcript).blocks()
        cleared = {"type": "note", "text": "the conversation was cleared"}
        first.post_message(Shown({"type": "cleared"}, cleared))
        first.post_message(TurnEnded())
        await pilot.pause()
        assert first.query_one(Transcript).blocks() == [("note", "the conversation was cleared")]
        await pilot.press(*"after", "enter")
        await pilot.pause()
    kinds = [json.loads(line)["type"] for line in path.read_text().splitlines()]
    assert kinds == ["user", "text", "usage", "turn_end", "cleared", "note", "turn_end", "user"]

    history = History(str(path))
    replay = replayable(history.read(), 400)
    assert replay.skipped == 0  # cleared, not trimmed: nothing is said to be left out
    second = BhApp(history=history, replay=replay)
    async with second.run_test(size=_SIZE) as pilot:
        await pilot.pause()
        blocks = second.query_one(Transcript).blocks()
        assert blocks[:2] == [("note", "the conversation was cleared"), ("user", "› after")]
        assert all("old reply" not in text and "hello" not in text for _, text in blocks)
