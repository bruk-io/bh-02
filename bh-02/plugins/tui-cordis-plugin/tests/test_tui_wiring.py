"""The rows driven by hand (what each binds or acquires, performed by nobody), and the ui row
booted for real, headless, under a runtime."""

import asyncio
from collections.abc import Mapping, Sequence
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
    render,
    status,
    tui,
)


class _Kernel:
    def __init__(self, confined: bool, report: Mapping[str, str]) -> None:
        self.confined = confined
        self._report = report

    def report(self) -> Mapping[str, str]:
        return self._report


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


async def test_the_status_row_pushes_the_session_the_jail_and_the_model_and_hears_the_model_row() -> None:
    frame = Frame(lambda message: True)
    kernel = _Kernel(True, {"fs_write": "enforced", "network": "enforced"})
    sessions = _Sessions("20260923-011910-58d9", resumed=True)
    effects = await drive(
        status(
            kernel=kernel,
            loader=_Loader(),
            models=_Models(),
            sessions=sessions,
            frame=frame,
            config=StatusConfig(),
        )
    )
    assert [e.name for e in effects] == ["acquire", "acquire", "acquire", "observe"]
    assert effects[0].args == (frame.status, "session", "20260923-011910-58d9 (resumed)", "58d9 ↻")
    assert effects[1].args == (frame.status, "jail", *render.jail_forms(True, kernel.report()))
    assert effects[1].args[2] == "jailed fs_write ✓ network ✓"
    shown, heard = effects[2].args[0], effects[3].args[0]
    assert heard.__self__ is shown.__self__  # the model field, shown and moved by its row's events
    remove = shown()
    assert frame.fields() == {"model": "haiku (claude-code)"}
    remove()


async def test_with_no_session_the_status_row_shows_no_session_field() -> None:
    frame = Frame(lambda message: True)
    effects = await drive(
        status(
            kernel=_Kernel(False, {}),
            loader=_Loader(),
            models=_Models(),
            sessions=_Sessions(),
            frame=frame,
            config=StatusConfig(),
        )
    )
    assert [e.args[1] for e in effects if e.name == "acquire" and len(e.args) > 1] == ["jail"]


async def test_the_app_row_under_a_runtime_and_a_row_over_frame_leaving_first() -> None:
    """Booted for real (headless): the ports and frame are bound, a row that acquires a status
    field shows in the app, and retiring the ui unbinds everything and ends its input."""

    @component(provides=("kernel", "loader", "models", "sessions"))
    async def reported() -> Effects:
        yield bind("kernel", _Kernel(False, {"fs_write": "unenforced"}))
        yield bind("loader", _Loader())
        yield bind("models", _Models())
        yield bind("sessions", _Sessions("20260924-1"))

    rt = Runtime()
    ui = rt.mount(tui, config={"headless": True}, id="ui")
    rt.mount(reported, id="reported")
    rt.mount(status, id="status")
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
