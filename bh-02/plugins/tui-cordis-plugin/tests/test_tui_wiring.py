"""The rows driven by hand (what each binds or acquires, performed by nobody), and the ui row
booted for real, headless, under a runtime."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cordis import Effects, Runtime, bind, component
from cordis.testing import drive
from tui_cordis_plugin import (
    BhApp,
    Frame,
    History,
    StatusConfig,
    TuiConfig,
    TuiInput,
    TuiOutput,
    grades,
    render,
    status,
    tui,
)

_CONFINED = {"fs_write": "enforced", "network": "enforced"}


class _Start:
    """A start the runner tells: its grades and its notice."""

    def __init__(self, report: Mapping[str, str], notice: str = "") -> None:
        self._report = report
        self._notice = notice

    def report(self) -> Mapping[str, str]:
        return self._report

    def notice(self) -> str:
        return self._notice


class _Runner:
    """The `runner` value's grades before any start and its `on_start`, a start told by hand
    (`started`)."""

    def __init__(self, report: Mapping[str, str]) -> None:
        self._report = report
        self.watches: list[Any] = []

    def report(self) -> Mapping[str, str]:
        return self._report

    def on_start(self, watch: Any) -> Any:
        self.watches.append(watch)
        return lambda: self.watches.remove(watch)

    def started(self, start: _Start) -> None:
        self._report = start.report()
        for watch in tuple(self.watches):
            watch(start)


class _Rule:
    """The `approval` rule's `confined`: read from the runner's grades, as the real one is."""

    def __init__(self, runner: _Runner) -> None:
        self._runner = runner

    @property
    def confined(self) -> bool:
        report = self._runner.report()
        return report.get("fs_write") == "enforced" and report.get("network") == "enforced"


class _Output:
    """The `output` value's `show`: the events it was given, drained."""

    def __init__(self) -> None:
        self.shown: list[Mapping[str, Any]] = []

    async def show(self, events: AsyncIterator[Mapping[str, Any]]) -> None:
        self.shown += [event async for event in events]


@dataclass
class _Entry:
    id: str
    config: dict[str, Any]
    disabled: bool = False


class _Loader:
    """The loader's `entries()` and `status()`: the model row up, choosing `haiku`."""

    def entries(self) -> Sequence[Any]:
        return [_Entry("model", {"default": "haiku"})]

    def status(self) -> Mapping[str, str]:
        return {"model": "active"}


class _Models:
    """The `models` value's `current`: haiku, on Claude Code."""

    def current(self) -> Mapping[str, str]:
        return {"name": "haiku", "provider": "claude-code"}


@dataclass(frozen=True)
class _Sessions:
    current: str = ""
    resumed: bool = False


async def test_the_app_row_binds_input_output_and_frame_from_the_app_it_runs() -> None:
    app = BhApp()
    effects = await drive(tui(config=TuiConfig(headless=True)), replies=[app])
    assert [e.name for e in effects] == ["enter", "acquire", "observe", "bind", "bind", "bind"]
    assert [e.args[0] for e in effects[3:]] == ["input", "output", "frame"]
    output = effects[4].args[1]
    assert isinstance(effects[3].args[1], TuiInput) and isinstance(output, TuiOutput)
    assert effects[5].args[1] is app.frame
    assert effects[1].args[0] == output.usage_field  # the usage field is the output's own
    assert effects[2].args[0] == output.lifecycle  # it hears the composition change
    assert hasattr(effects[0].args[0], "__aenter__")  # the app, run for as long as the row is up


async def test_with_a_history_the_app_row_enters_it_first_then_the_app(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"type": "user", "text": "hi"}\n{"type": "usage", "input_tokens": 5, "output_tokens": 2}\n'
    )
    app = BhApp()
    async with History(str(path)) as history:
        assert history.recorded[0] == {"type": "user", "text": "hi"}  # entering reads it
        effects = await drive(tui(config=TuiConfig(headless=True, history=str(path))), replies=[history, app])
    assert [e.name for e in effects] == ["enter", "enter", "acquire", "observe", "bind", "bind", "bind"]
    entered = effects[0].args[0]
    assert isinstance(entered, History) and entered.path == str(path)
    remove = effects[2].args[0]()  # the usage field starts from the session's history
    assert app.frame.fields() == {"usage": "5 in · 2 out"}
    remove()
    assert app.frame.fields() == {}


async def test_the_status_row_pushes_the_session_and_the_model_and_hears_the_model_row() -> None:
    frame = Frame(lambda message: True)
    sessions = _Sessions("20260923-011910-58d9", resumed=True)
    effects = await drive(
        status(loader=_Loader(), models=_Models(), sessions=sessions, frame=frame, config=StatusConfig())
    )
    assert [e.name for e in effects] == ["acquire", "acquire", "observe"]
    assert effects[0].args == (frame.status, "session", "20260923-011910-58d9 (resumed)", "58d9 ↻")
    shown, heard = effects[1].args[0], effects[2].args[0]
    assert heard.__self__ is shown.__self__  # the model field, shown and moved by its row's events
    remove = shown()
    assert frame.fields() == {"model": "haiku (claude-code)"}
    remove()


async def test_with_no_session_the_status_row_shows_no_session_field() -> None:
    frame = Frame(lambda message: True)
    effects = await drive(
        status(loader=_Loader(), models=_Models(), sessions=_Sessions(), frame=frame, config=StatusConfig())
    )
    assert [e.name for e in effects] == ["acquire", "observe"]  # the model field alone


async def test_the_grades_row_shows_each_start_s_grades_and_tells_a_new_notice_once() -> None:
    """The jail field is the runner's last start's grades, as the `approval` rule counts them: a
    Python process started again in place (no row reloading) moves it. A start's notice (a
    Linux jail's paths held with a mount the host can undo) is a note in the conversation, once
    for as long as it reads the same: the extensions' worker's start says what the Python
    process's did."""
    frame, output = Frame(lambda message: True), _Output()
    runner = _Runner({"fs_write": "unenforced"})
    effects = await drive(grades(runner=runner, approval=_Rule(runner), frame=frame, output=output))
    assert [e.name for e in effects] == ["background", "acquire", "acquire"]
    telling = effects[0].args[0]
    told = asyncio.ensure_future(telling)
    try:
        remove = effects[1].args[0]()
        assert frame.fields() == {"jail": "unjailed fs_write ✗"}  # before any start: the runner's
        stop_watching = effects[2].args[0](*effects[2].args[1:])
        held = "The jail keeps inputs from reading /w/local.env"
        runner.started(_Start(_CONFINED, held))
        assert frame.fields() == {"jail": render.jail_forms(True, _CONFINED)[0]}
        assert frame.fields()["jail"] == "jailed fs_write ✓ network ✓"
        runner.started(_Start(_CONFINED, held))  # the extensions' worker: the same notice
        runner.started(_Start({**_CONFINED, "network": "best_effort"}))  # nothing to say
        assert frame.fields()["jail"].startswith("unjailed")
        await asyncio.sleep(0)
        assert output.shown == [{"type": "note", "text": held}]
        stop_watching()
        remove()
        assert frame.fields() == {}
    finally:
        told.cancel()
        await asyncio.gather(told, return_exceptions=True)


async def test_the_app_row_under_a_runtime_and_a_row_over_frame_leaving_first() -> None:
    """Booted for real (headless): the ports and frame are bound, a row that acquires a status
    field shows in the app, and retiring the ui unbinds everything and ends its input."""

    runner = _Runner({"fs_write": "unenforced"})

    @component(provides=("runner", "approval", "loader", "models", "sessions"))
    async def reported() -> Effects:
        yield bind("runner", runner)
        yield bind("approval", _Rule(runner))
        yield bind("loader", _Loader())
        yield bind("models", _Models())
        yield bind("sessions", _Sessions("20260924-1"))

    rt = Runtime()
    ui = rt.mount(tui, config={"headless": True}, id="ui")
    rt.mount(reported, id="reported")
    rt.mount(status, id="status")
    rt.mount(grades, id="grades")
    await rt.settle()
    frame = rt.root.get("frame")
    assert isinstance(frame, Frame)
    assert frame.fields() == {
        "session": "20260924-1",
        "jail": "unjailed fs_write ✗",
        "model": "haiku (claude-code)",
    }
    input = rt.root.get("input")
    reading = asyncio.ensure_future(input.read())
    await ui.retire()
    await rt.settle()
    assert await asyncio.wait_for(reading, 2) is None
    assert rt.root.get("frame") is None and frame.fields() == {}  # status left before the app
    await rt.shutdown()
