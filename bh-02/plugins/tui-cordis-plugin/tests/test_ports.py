"""The ports and the bridge they share with the app: every way the app ends settles them."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
from textual.message import Message

from tui_cordis_plugin import AppCrashed, Bridge, Frame, TuiInput, TuiOutput
from tui_cordis_plugin.messages import Asked, FrameChanged, Noted, RowsUp, Shown, TurnEnded, TurnStarted


class Posted:
    """Stands in for `app.post_message`: keeps what was posted."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    def __call__(self, message: Message) -> bool:
        self.messages.append(message)
        if isinstance(message, Shown) and message.drawn is not None and not message.drawn.done():
            message.drawn.set_result(None)  # as the app does once it has drawn them
        return True


async def test_a_line_typed_before_anyone_reads_is_kept_for_the_next_read() -> None:
    bridge = Bridge()
    bridge.submit("early")
    assert await TuiInput(bridge).read() == "early"
    waiting = asyncio.ensure_future(TuiInput(bridge).read())
    await asyncio.sleep(0)
    bridge.submit("later")
    assert await waiting == "later"


async def test_leaving_the_app_ends_the_input_and_settles_every_turn() -> None:
    bridge = Bridge()
    reading = asyncio.ensure_future(bridge.line())
    turn = asyncio.ensure_future(bridge.interrupted())
    await asyncio.sleep(0)
    bridge.end()
    assert await reading is None
    await asyncio.wait_for(turn, 1)
    assert await bridge.line() is None  # and every read after
    await asyncio.wait_for(bridge.interrupted(), 1)  # returns at once: nothing left to stop


async def test_a_crash_reaches_whoever_reads_next() -> None:
    bridge = Bridge()
    reading = asyncio.ensure_future(bridge.line())
    await asyncio.sleep(0)
    bridge.end(AppCrashed("the app crashed"))
    with pytest.raises(AppCrashed) as raised:
        await reading
    assert raised.value.kind == "ui_crashed" and raised.value.message == "the app crashed"
    with pytest.raises(AppCrashed):
        await bridge.line()


async def test_ctrl_c_stops_a_running_turn_and_says_whether_one_was() -> None:
    bridge = Bridge()
    assert not bridge.interrupt() and not bridge.turn_running
    turn = asyncio.ensure_future(TuiInput(bridge).interrupted())
    await asyncio.sleep(0)
    assert bridge.turn_running
    assert bridge.interrupt()
    await asyncio.wait_for(turn, 1)
    assert not bridge.turn_running


async def test_a_question_nobody_can_answer_is_a_no() -> None:
    posted, bridge = Posted(), Bridge()
    output = TuiOutput(posted, bridge)
    asking = asyncio.ensure_future(output.confirm({"name": "python", "input": {"code": "1"}}))
    await asyncio.sleep(0)
    (asked,) = posted.messages
    assert isinstance(asked, Asked) and asked.request["name"] == "python"
    bridge.end()  # the app left with the modal up
    assert await asking is False
    assert await output.confirm({"name": "python", "input": {}}) is False  # nothing posted now
    assert len(posted.messages) == 1


async def test_a_turn_is_posted_event_by_event_and_its_end_closes_the_stream() -> None:
    posted, bridge = Posted(), Bridge()

    async def reply() -> AsyncIterator[Mapping[str, Any]]:
        yield {"type": "text", "text": "a"}
        yield {"type": "text", "text": "b"}

    await TuiOutput(posted, bridge).show(reply())
    assert [type(m) for m in posted.messages] == [TurnStarted, Shown, Shown, TurnEnded]
    assert [e["text"] for m in posted.messages if isinstance(m, Shown) for e in m.events] == ["a", "b"]


async def test_events_gather_while_the_app_draws_and_ctrl_c_is_heard_mid_burst() -> None:
    """A reply that yields every event at once (it never waits) is posted in batches, no
    faster than the app draws; and the loop gets a turn between events, so an interrupt
    arriving mid-burst cancels the turn instead of waiting for all of it."""
    bridge = Bridge()
    shown: list[Shown] = []
    output = TuiOutput(lambda m: shown.append(m) or True if isinstance(m, Shown) else True, bridge)
    read = 0

    async def burst() -> AsyncIterator[Mapping[str, Any]]:
        nonlocal read
        for n in range(100_000):
            read += 1
            yield {"type": "text", "text": f"line {n}\n"}

    turn = asyncio.ensure_future(output.show(burst()))
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(shown) == 1  # the first batch is posted, and nothing more until it is drawn
    assert shown[0].drawn is not None and not shown[0].drawn.done()
    shown[0].drawn.set_result(None)  # the app draws it
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(shown) == 2 and len(shown[1].events) > 1  # what gathered meanwhile, as one batch
    turn.cancel()  # Ctrl-C: the chat session cancels the turn it is racing
    await asyncio.gather(turn, return_exceptions=True)
    assert read < 2_000  # the burst was not read to its end first


class _ProviderFailed(Exception):
    def __init__(self) -> None:
        super().__init__("overloaded")
        self.kind, self.message = "overloaded", "overloaded"


@pytest.mark.parametrize("ending", ["raises", "cancelled"])
async def test_every_event_read_is_posted_when_a_turn_stops_while_the_app_is_behind(ending: str) -> None:
    """The app is still drawing the first batch when the reply fails or Ctrl-C cancels the
    turn: what gathered meanwhile (a usage event among it, already in the status bar's total)
    is still posted, so it is drawn and recorded, before the turn's end."""
    bridge = Bridge()
    posted: list[Message] = []
    frame = Frame(lambda m: True)
    output = TuiOutput(lambda m: posted.append(m) or True, bridge, frame.status)  # draws nothing
    gathered = asyncio.Event()

    async def reply() -> AsyncIterator[Mapping[str, Any]]:
        for n in range(4):
            yield {"type": "text", "text": f"t{n} "}
        yield {"type": "usage", "input_tokens": 7, "output_tokens": 3}
        gathered.set()
        if ending == "raises":
            raise _ProviderFailed()
        await asyncio.Event().wait()  # a reply still streaming when Ctrl-C comes

    turn = asyncio.ensure_future(output.show(reply()))
    await asyncio.wait_for(gathered.wait(), 1)
    if ending == "cancelled":
        await asyncio.sleep(0)
        turn.cancel()
    outcome = (await asyncio.gather(turn, return_exceptions=True))[0]
    assert isinstance(outcome, _ProviderFailed if ending == "raises" else asyncio.CancelledError)
    events = [e for m in posted if isinstance(m, Shown) for e in m.events]
    assert [e.get("text") for e in events] == ["t0 ", "t1 ", "t2 ", "t3 ", None]
    assert events[-1]["type"] == "usage" and frame.fields() == {"usage": "7 in · 3 out"}
    assert isinstance(posted[-1], TurnEnded)


async def test_what_gathered_is_posted_once_the_app_has_drawn_even_if_the_reply_pauses() -> None:
    """An event that came while the app drew the last batch is posted when the app is done
    drawing, not when the next event comes: a reply that pauses (thinking) shows what it said."""
    bridge = Bridge()
    shown: list[Shown] = []
    output = TuiOutput(lambda m: shown.append(m) or True if isinstance(m, Shown) else True, bridge)
    both = asyncio.Event()

    async def reply() -> AsyncIterator[Mapping[str, Any]]:
        yield {"type": "text", "text": "first "}
        yield {"type": "text", "text": "second"}
        both.set()
        await asyncio.Event().wait()  # the model thinks, for as long as it likes

    turn = asyncio.ensure_future(output.show(reply()))
    await asyncio.wait_for(both.wait(), 1)
    assert [[e["text"] for e in m.events] for m in shown] == [["first "]]  # "second" gathers
    assert shown[0].drawn is not None
    shown[0].drawn.set_result(None)  # the app draws the first batch
    for _ in range(3):
        await asyncio.sleep(0)
    assert [[e["text"] for e in m.events] for m in shown] == [["first "], ["second"]]
    turn.cancel()
    await asyncio.gather(turn, return_exceptions=True)


async def test_a_draw_settled_after_the_turn_ended_posts_nothing_more() -> None:
    bridge = Bridge()
    posted: list[Message] = []
    output = TuiOutput(lambda m: posted.append(m) or True, bridge)  # draws when told to

    async def reply() -> AsyncIterator[Mapping[str, Any]]:
        for text in ("a", "b", "c"):
            yield {"type": "text", "text": text}

    await asyncio.wait_for(output.show(reply()), 1)
    assert isinstance(posted[-1], TurnEnded)
    for message in posted:
        if isinstance(message, Shown) and message.drawn is not None and not message.drawn.done():
            message.drawn.set_result(None)  # the app catches up after the turn's end
    for _ in range(3):
        await asyncio.sleep(0)
    assert isinstance(posted[-1], TurnEnded)  # nothing drawn twice, nothing after the end
    events = [e["text"] for m in posted if isinstance(m, Shown) for e in m.events]
    assert events == ["a", "b", "c"]


async def test_a_turn_waiting_for_the_app_to_draw_ends_when_the_app_does() -> None:
    bridge = Bridge()
    output = TuiOutput(lambda m: True, bridge)  # an app that never draws

    async def burst() -> AsyncIterator[Mapping[str, Any]]:
        for n in range(10_000):
            yield {"type": "text", "text": f"{n}"}

    turn = asyncio.ensure_future(output.show(burst()))
    await asyncio.sleep(0.05)
    assert not turn.done()  # waiting for a draw that never comes
    bridge.end()  # Ctrl-Q
    await asyncio.wait_for(turn, 1)


async def test_a_turn_stops_being_read_once_the_app_has_ended() -> None:
    posted, bridge = Posted(), Bridge()
    read: list[str] = []

    async def reply() -> AsyncIterator[Mapping[str, Any]]:
        for text in ("a", "b", "c"):
            read.append(text)
            if text == "b":
                bridge.end()
            yield {"type": "text", "text": text}

    await TuiOutput(posted, bridge).show(reply())
    assert read == ["a", "b"]  # the reply was not drained into nowhere


def test_reloads_and_failures_become_notes() -> None:
    class Event:
        def __init__(self, kind: str, fiber: str, error: str | None = None) -> None:
            self.kind, self.fiber, self.error = kind, fiber, error

    posted = Posted()
    output = TuiOutput(posted, Bridge())
    for event in (Event("active", "loop"), Event("active", "loop"), Event("failed", "kernel", "boom")):
        output.lifecycle(event)
    notes = [(m.text, m.kind) for m in posted.messages if isinstance(m, Noted)]
    assert notes == [("↻ loop reloaded", "note"), ("✗ kernel failed: boom", "failure")]


def test_a_row_up_before_the_app_heard_it_says_reloaded_the_first_time_it_comes_back() -> None:
    """The model row depends on nothing, so it is up before the app observes: its first
    activation the app hears follows its going down (`reload` precedes every setup, the first
    one too, so it is not what marks a reload)."""

    class Event:
        def __init__(self, kind: str, fiber: str) -> None:
            self.kind, self.fiber, self.error = kind, fiber, None

    posted = Posted()
    output = TuiOutput(posted, Bridge())
    for kind, fiber in (
        ("reload", "loop"),
        ("active", "loop"),
        ("unloading", "model"),
        ("reload", "model"),
        ("active", "model"),
    ):
        output.lifecycle(Event(kind, fiber))
    notes = [m.text for m in posted.messages if isinstance(m, Noted)]
    assert notes == ["↻ model reloaded"]  # the loop's first start says nothing


def test_frame_entries_leave_with_their_remover_and_the_latest_push_shows() -> None:
    posted = Posted()
    frame = Frame(posted)
    remove_session = frame.status("session", "abc")
    remove_old = frame.status("jail", "unjailed")
    remove_new = frame.status("jail", "jailed")
    assert frame.fields() == {"session": "abc", "jail": "jailed"}
    remove_new()
    assert frame.fields() == {"session": "abc", "jail": "unjailed"}
    remove_old()
    remove_session()
    remove_session()  # twice is harmless, and posts nothing more
    assert frame.fields() == {}
    assert sum(isinstance(m, FrameChanged) for m in posted.messages) == 6


class _Event:
    """A cordis lifecycle event, as the output's `lifecycle` reads one."""

    def __init__(self, kind: str, fiber: str, error: str | None = None) -> None:
        self.kind, self.fiber, self.error = kind, fiber, error


def test_a_line_kept_between_a_restarted_row_s_old_fiber_and_its_new_one_says_it_waits() -> None:
    """`/clear` restarts `loop`: its old fiber ends `inactive` and the new one's `reload` comes
    later. A line typed in between is kept with no row coming up; the `reload` says it waits."""
    posted = Posted()
    bridge = Bridge()
    output = TuiOutput(posted, bridge)
    for kind in ("bind", "active", "unloading", "inactive"):  # up (binding `loop`), then restarting
        output.lifecycle(_Event(kind, "loop"))
    assert bridge.waiting_on == frozenset()
    assert not bridge.submit("hello")  # kept, and nothing to say it waits for yet
    output.lifecycle(_Event("reload", "loop"))
    output.lifecycle(_Event("reload", "kernel"))  # said once, not per row
    notes = [m.text for m in posted.messages if isinstance(m, Noted)]
    assert notes == ["⧗ waiting for loop to start; this message is sent once it is up"]


def test_a_row_never_heard_binding_is_named_once_it_binds() -> None:
    """A row the ui never heard bind a key (it came up before the ui listened) may be a
    status-bar row, which no line waits on: a kept line names it once it binds one."""
    posted = Posted()
    bridge = Bridge()
    output = TuiOutput(posted, bridge)
    for kind in ("unloading", "inactive"):
        output.lifecycle(_Event(kind, "transcript"))
    assert not bridge.submit("hello")
    output.lifecycle(_Event("reload", "transcript"))
    assert not [m for m in posted.messages if isinstance(m, Noted)]  # not known to bind yet
    output.lifecycle(_Event("bind", "transcript"))
    notes = [m.text for m in posted.messages if isinstance(m, Noted)]
    assert notes == ["⧗ waiting for transcript to start; this message is sent once it is up"]


async def test_a_line_read_before_any_row_comes_up_says_nothing_later() -> None:
    posted = Posted()
    bridge = Bridge()
    output = TuiOutput(posted, bridge)
    bridge.submit("hello")
    assert await bridge.line() == "hello"
    output.lifecycle(_Event("reload", "loop"))
    assert not [m for m in posted.messages if isinstance(m, Noted)]


async def _answered(*events: Mapping[str, Any]) -> AsyncIterator[Mapping[str, Any]]:
    for event in events:
        yield event


def _notes(posted: Posted) -> list[str]:
    return [m.text for m in posted.messages if isinstance(m, Noted)]


async def test_a_line_typed_right_after_model_waits_for_the_new_model_not_the_old() -> None:
    """`/model` answers `restarting` (CONTRACTS.md) before the restart begins, and the chat row
    reads again at once: a line typed then is held, not handed to that reader (the old model
    would answer it, or the restart stop it), and says it waits. It goes to the chat row that
    reads once the model is up again, through the `inactive` inside the restart."""
    posted = Posted()
    bridge = Bridge()
    output = TuiOutput(posted, bridge)
    reading = asyncio.ensure_future(bridge.line())
    await asyncio.sleep(0)
    assert bridge.submit("/model sonnet") and await reading == "/model sonnet"
    await output.show(
        _answered({"type": "note", "text": "switching"}, {"type": "restarting", "rows": ["loop"]})
    )
    old = asyncio.ensure_future(bridge.line())  # the chat row reads again, still up
    await asyncio.sleep(0)
    assert bridge.waiting_on == {"loop"}
    assert not bridge.submit("hello") and not old.done()  # held, not handed to the old chat
    for kind in ("unloading", "inactive"):
        output.lifecycle(_Event(kind, "loop"))
    old.cancel()  # the restart takes the chat row down with the model
    output.lifecycle(_Event("reload", "loop"))
    assert bridge.holding and bridge.waiting_on == {"loop"}
    output.lifecycle(_Event("active", "loop"))
    assert not bridge.holding
    assert await asyncio.wait_for(bridge.line(), 1) == "hello"  # the new chat row reads it


async def test_a_line_kept_while_the_command_ran_says_it_waits_once_the_restart_is_announced() -> None:
    posted = Posted()
    bridge = Bridge()
    output = TuiOutput(posted, bridge)
    bridge.submit("/clear")
    assert await bridge.line() == "/clear"
    assert not bridge.submit("again")  # typed while /clear runs: it waits for the command
    assert _notes(posted) == []
    await output.show(_answered({"type": "cleared"}, {"type": "restarting", "rows": ["loop", "kernel"]}))
    assert _notes(posted) == ["⧗ waiting for kernel, loop to start; this message is sent once they are up"]
    reading = asyncio.ensure_future(bridge.line())
    await asyncio.sleep(0)
    assert not reading.done()  # even a kept line is held
    reading.cancel()


async def test_a_restart_announced_that_never_begins_lapses_and_the_line_goes_out() -> None:
    """`/model` to the model already running changes nothing, so no row restarts: the line
    is held only for a moment (the bridge's `lapse`), then handed to the chat row reading."""
    bridge = Bridge(lapse=0.05)
    reading = asyncio.ensure_future(bridge.line())
    await asyncio.sleep(0)
    assert bridge.announce(["loop"]) == frozenset()  # nothing kept to note
    assert not bridge.submit("hello")
    assert await asyncio.wait_for(reading, 1) == "hello"
    assert not bridge.holding


async def test_a_held_row_that_goes_inactive_and_never_comes_back_lapses() -> None:
    bridge = Bridge(lapse=0.05)
    bridge.announce(["loop"])
    for kind in ("unloading", "inactive"):
        bridge.row_changed(kind, "loop")
    assert bridge.holding  # the moment inside a restart, for now
    await asyncio.sleep(0.1)
    assert not bridge.holding  # no new fiber came: down for good


async def test_a_line_kept_during_a_command_names_no_row_reloading_meanwhile() -> None:
    """`/restart status`: the chat row is busy with the command, not down; a line typed
    meanwhile waits for the command, and a row reloading then is not what it waits on."""
    posted = Posted()
    bridge = Bridge()
    output = TuiOutput(posted, bridge)
    bridge.submit("/restart status")
    assert await bridge.line() == "/restart status"
    assert not bridge.submit("hello")
    for kind in ("unloading", "inactive", "reload"):
        output.lifecycle(_Event(kind, "status"))
    assert bridge.waiting_on == frozenset() and not [n for n in _notes(posted) if n.startswith("⧗")]
    assert await bridge.line() == "hello"


def test_a_status_field_removed_while_rows_come_up_stays_until_pushed_again_or_released() -> None:
    """`/clear` restarts the kernel, and so the `status` row: its field is not blank for
    the second it takes to come back. When every row is up the output says so (`RowsUp`), and
    the app `release`s a field no row pushed again."""
    posted = Posted()
    bridge = Bridge()
    frame = Frame(posted, lambda: bridge.settling)
    output = TuiOutput(posted, bridge)
    remove_jail = frame.status("jail", "jailed")
    remove_gone = frame.status("gone", "soon")
    output.lifecycle(_Event("unloading", "kernel"))
    remove_jail()
    remove_gone()
    assert frame.fields() == {"jail": "jailed", "gone": "soon"}  # the last text, kept
    output.lifecycle(_Event("inactive", "kernel"))  # the old kernel is gone, the new not yet up
    assert [m for m in posted.messages if isinstance(m, RowsUp)]
    output.lifecycle(_Event("reload", "kernel"))
    output.lifecycle(_Event("active", "kernel"))
    frame.status("jail", "unjailed")  # status came back and pushed again: that shows
    assert frame.fields() == {"jail": "unjailed", "gone": "soon"}
    posted.messages.clear()
    frame.release()
    assert frame.fields() == {"jail": "unjailed"}
    assert [m.what for m in posted.messages if isinstance(m, FrameChanged)] == ["status"]  # redrawn
    remove = frame.status("x", "y")
    remove()  # removed while every row is up: gone at once
    assert "x" not in frame.fields()


def test_frame_offers_commands_read_afresh() -> None:
    frame = Frame(Posted())
    registered = [{"name": "clear", "help": "start afresh", "usage": ""}]
    withdraw = frame.commands(lambda: registered)
    assert [c["name"] for c in frame.offered_commands()] == ["clear"]
    registered.append({"name": "model", "help": "switch", "usage": "[NAME]"})  # registered later
    assert [c["name"] for c in frame.offered_commands()] == ["clear", "model"]
    withdraw()
    assert frame.offered_commands() == []


async def test_a_ctrl_c_before_the_turn_listens_is_held_for_it() -> None:
    """Between a line being handed out and its turn racing `interrupted()`, Ctrl-C is not lost."""
    bridge = Bridge()
    reading = asyncio.ensure_future(bridge.line())
    await asyncio.sleep(0)
    assert not bridge.interrupt()  # waiting for a line: nothing is running
    bridge.submit("go")
    assert await reading == "go"
    assert bridge.interrupt() and bridge.interrupt_held  # the turn has not started listening
    await asyncio.wait_for(bridge.interrupted(), 1)  # it hears the held Ctrl-C at once
    assert not bridge.interrupt_held


async def test_a_held_ctrl_c_is_dropped_by_the_next_read() -> None:
    """A slash command is not interrupted: its held Ctrl-C must not kill the next turn."""
    bridge = Bridge()
    bridge.submit("/rows")
    assert await bridge.line() == "/rows"
    assert bridge.interrupt()  # busy with the command
    bridge.submit("hello")
    assert await bridge.line() == "hello"
    assert not bridge.interrupt_held
    turn = asyncio.ensure_future(bridge.interrupted())
    await asyncio.sleep(0.01)
    assert not turn.done()  # the next turn runs until its own Ctrl-C
    assert bridge.interrupt()
    await asyncio.wait_for(turn, 1)


async def test_usage_adds_up_into_the_status_bar() -> None:
    posted, bridge = Posted(), Bridge()
    frame = Frame(posted)
    output = TuiOutput(posted, bridge, frame.status)

    async def turn(tokens: int, cost: float | None) -> AsyncIterator[Mapping[str, Any]]:
        yield {"type": "text", "text": "hi"}
        used = {"type": "usage", "input_tokens": tokens, "output_tokens": 10}
        yield used | ({"cost_usd": cost} if cost is not None else {})

    await output.show(turn(1000, None))
    assert frame.fields() == {"usage": "1,000 in · 10 out"}
    await output.show(turn(2000, 0.25))
    assert frame.fields() == {"usage": "3,000 in · 20 out · $0.2500"}


async def test_a_turn_stopped_before_its_output_count_marks_the_totals_as_lower_bounds() -> None:
    posted, bridge = Posted(), Bridge()
    frame = Frame(posted)
    output = TuiOutput(posted, bridge, frame.status)

    async def turn(stopped: bool) -> AsyncIterator[Mapping[str, Any]]:
        yield {"type": "usage", "input_tokens": 1000, "output_tokens": 0, "partial": True}
        yield {"type": "text", "text": "hi"}
        if not stopped:  # the provider's final count
            yield {"type": "usage", "input_tokens": 0, "output_tokens": 10}

    await output.show(turn(stopped=False))
    assert frame.fields() == {"usage": "1,000 in · 10 out"}  # partial only until the count came
    await output.show(turn(stopped=True))
    assert frame.fields() == {"usage": "2,000 in · 10+ out"}
