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
    ui,
)

_CONFINED = {"fs_write": "enforced", "network": "enforced"}


class _Start:
    """A start the runner tells: its grades and its notice."""

    def __init__(self, report: Mapping[str, str], notice: str = "", degraded: str = "") -> None:
        self._report = report
        self._notice = notice
        self._degraded = degraded

    def report(self) -> Mapping[str, str]:
        return self._report

    def notice(self) -> str:
        return self._notice

    def degraded(self) -> str:
        return self._degraded


class _Runner:
    """The `runner` value's grades before any start and its `on_start`, a start told by hand
    (`started`)."""

    def __init__(self, report: Mapping[str, str], last: _Start | None = None) -> None:
        self._report = report
        self._last = last
        self.watches: list[Any] = []

    def report(self) -> Mapping[str, str]:
        return self._report

    def notice(self) -> str:
        return self._last.notice() if self._last is not None else ""

    def degraded(self) -> str:
        return self._last.degraded() if self._last is not None else ""

    def on_start(self, watch: Any) -> Any:
        self.watches.append(watch)
        return lambda: self.watches.remove(watch)

    def started(self, start: _Start) -> None:
        self._report, self._last = start.report(), start
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
    effects = await drive(ui(config=TuiConfig(headless=True)), replies=[app])
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
        effects = await drive(ui(config=TuiConfig(headless=True, history=str(path))), replies=[history, app])
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
        status(loader=_Loader(), models=_Models(), session=sessions, frame=frame, config=StatusConfig())
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
        status(loader=_Loader(), models=_Models(), session=_Sessions(), frame=frame, config=StatusConfig())
    )
    assert [e.name for e in effects] == ["acquire", "observe"]  # the model field alone


async def test_the_grades_row_shows_each_start_s_grades_and_tells_a_new_notice_once() -> None:
    """The jail field is the runner's last start's grades, as the `approval` rule counts them: a
    Python process started again in place (no row reloading) moves it. A start's notice (a
    Linux jail's paths held with a mount the host can undo) is a note in the conversation, once
    for as long as it reads the same: the extensions process's start says what the Python
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
        held = "The jail keeps inputs from reading /w/private.txt"
        runner.started(_Start(_CONFINED, held))
        assert frame.fields() == {"jail": render.jail_forms(True, _CONFINED)[0]}
        assert frame.fields()["jail"] == "jailed fs_write ✓ network ✓"
        runner.started(_Start(_CONFINED, held))  # the extensions process: the same notice
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

    @component(provides=("runner", "approval", "loader", "models", "session"))
    async def reported() -> Effects:
        yield bind("runner", runner)
        yield bind("approval", _Rule(runner))
        yield bind("loader", _Loader())
        yield bind("models", _Models())
        yield bind("session", _Sessions("20260924-1"))

    rt = Runtime()
    app_row = rt.mount(ui, config={"headless": True}, id="ui")
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
    await app_row.retire()
    await rt.settle()
    assert await asyncio.wait_for(reading, 2) is None
    assert rt.root.get("frame") is None and frame.fields() == {}  # status left before the app
    await rt.shutdown()


_LOST = (
    "the kernel refused a mount on /dev/pts: Operation not permitted, so this jail's processes have "
    "no namespaces of their own: ... So each program keeps a jail of its own"
)


async def test_the_jail_field_shows_a_refused_mount_while_that_jail_runs_and_warns_once() -> None:
    """A host refused a mount that keeps programs apart (brig's decision-212): the field itself says
    so beside the grades, for every start in that state, and the conversation is told once, as a
    failure, not a plain note. A start that lost nothing takes the mark away."""
    frame, output = Frame(lambda message: True), _Output()
    runner = _Runner(_CONFINED)
    effects = await drive(grades(runner=runner, approval=_Rule(runner), frame=frame, output=output))
    told = asyncio.ensure_future(effects[0].args[0])
    try:
        effects[1].args[0]()
        effects[2].args[0](*effects[2].args[1:])
        lost = _Start(_CONFINED, _LOST, "mount refused, a jail each")
        runner.started(lost)
        assert frame.fields()["jail"] == "jailed fs_write ✓ network ✓ ⚠ mount refused, a jail each"
        runner.started(lost)  # the extensions process, in a jail of its own: still shown
        assert "⚠ mount refused" in frame.fields()["jail"]
        await asyncio.sleep(0)
        assert output.shown == [{"type": "note", "text": _LOST, "kind": "failure"}]
        runner.started(_Start(_CONFINED))
        assert frame.fields()["jail"] == "jailed fs_write ✓ network ✓"
    finally:
        told.cancel()
        await asyncio.gather(told, return_exceptions=True)


async def test_a_start_that_came_before_the_grades_row_still_shows() -> None:
    """The runner may start a program before this row subscribes (rows come up in any order): what
    that start's jail lost, and its notice, are read when the row comes up, not lost."""
    frame, output = Frame(lambda message: True), _Output()
    before = _Start(_CONFINED, _LOST, "mount refused, a jail each")
    runner = _Runner(_CONFINED, last=before)
    effects = await drive(grades(runner=runner, approval=_Rule(runner), frame=frame, output=output))
    told = asyncio.ensure_future(effects[0].args[0])
    try:
        effects[1].args[0]()
        assert "⚠ mount refused, a jail each" in frame.fields()["jail"]
        await asyncio.sleep(0)
        assert output.shown == [{"type": "note", "text": _LOST, "kind": "failure"}]
    finally:
        told.cancel()
        await asyncio.gather(told, return_exceptions=True)
