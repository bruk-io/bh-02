"""The frame's rows: the palette's (what it acquires), and the status row's model field as
the model row reloads (the status row itself: test_tui_wiring)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from cordis.testing import drive
from tui_cordis_plugin import Frame, ModelField, palette


@dataclass
class _Entry:
    id: str
    config: dict[str, Any] = field(default_factory=dict)
    disabled: bool = False


class _Loader:
    """The loader's `entries()`, as a layer file would compose them now, and its `status()`."""

    def __init__(self, *entries: _Entry) -> None:
        self.entries_now: list[_Entry] | Exception = list(entries)
        self.states: dict[str, str] = {e.id: "active" for e in entries}

    def status(self) -> Mapping[str, str]:
        return self.states

    def entries(self) -> Sequence[Any]:
        if isinstance(self.entries_now, Exception):
            raise self.entries_now
        return self.entries_now


def _current(loader: _Loader, row: str, provider: str = "") -> Callable[[], Mapping[str, str]]:
    """The `models` value's `current`, as the catalog reads it: the model row's `default`
    from the loader's entries now (a layer mid-write raises, as the loader does)."""

    def current() -> Mapping[str, str]:
        entry = next((e for e in loader.entries() if e.id == row), None)
        return {"name": (entry.config if entry else {}).get("default", "none"), "provider": provider}

    return current


@dataclass
class _Event:
    kind: str
    fiber: str


def _frame() -> Frame:
    return Frame(lambda message: True)


async def test_the_palette_row_offers_the_broker_s_specs_read_when_the_palette_opens() -> None:
    class Commands:
        def specs(self) -> Sequence[Mapping[str, Any]]:
            return [{"name": "rows", "help": "the rows", "usage": ""}]

    commands, frame = Commands(), _frame()
    effects = await drive(palette(commands=commands, frame=frame))
    assert [e.name for e in effects] == ["acquire"]
    assert effects[0].args == (frame.commands, commands.specs)  # the method, not a snapshot


def test_the_model_field_follows_the_model_row_as_it_reloads() -> None:
    frame, loader = _frame(), _Loader(_Entry("model", {"state": "/s"}))
    model_field = ModelField(frame.status, loader, "model", _current(loader, "model", "claude-code"))
    remove: Callable[[], None] = model_field.show()
    assert frame.fields() == {"model": "none (claude-code)"}
    loader.entries_now = [_Entry("model", {"default": "haiku"})]  # /model edited the session's layer
    model_field.lifecycle(_Event("active", "kernel"))  # another row: nothing to read
    assert frame.fields() == {"model": "none (claude-code)"}
    model_field.lifecycle(_Event("active", "model"))
    assert frame.fields() == {"model": "haiku (claude-code)"}
    assert frame.forms() == {"model": ("haiku (claude-code)", "haiku")}  # a narrow bar: the name
    loader.entries_now = ValueError("a layer half-written")
    model_field.lifecycle(_Event("active", "model"))
    assert frame.fields() == {"model": "haiku (claude-code)"}  # the last text stays
    loader.entries_now = RuntimeError("a bug in the loader")
    with pytest.raises(RuntimeError):  # a bug is not swallowed as if it were a half-written layer
        model_field.lifecycle(_Event("active", "model"))
    remove()
    assert frame.fields() == {}
    model_field.lifecycle(_Event("active", "model"))  # gone: a late event pushes nothing
    assert frame.fields() == {}


def test_the_model_field_says_the_new_model_is_starting_until_its_row_is_active() -> None:
    """`/model haiku`: the layer is edited, the row unloads, the CLI takes seconds to start."""
    frame, loader = _frame(), _Loader(_Entry("loop", {"default": "sonnet"}))
    loader.states["loop"] = "loading"  # the program is starting: the row isn't up yet
    model_field = ModelField(frame.status, loader, "loop", _current(loader, "loop"))
    model_field.show()
    assert frame.forms() == {"model": ("sonnet (starting…)", "sonnet…")}
    model_field.lifecycle(_Event("active", "loop"))
    assert frame.fields() == {"model": "sonnet"}
    loader.entries_now = [_Entry("loop", {"default": "haiku"})]
    model_field.lifecycle(_Event("unloading", "loop"))
    assert frame.fields() == {"model": "haiku (starting…)"}  # the new model, at once
    for kind in ("inactive", "reload", "bind"):
        model_field.lifecycle(_Event(kind, "loop"))
        assert frame.fields() == {"model": "haiku (starting…)"}
    model_field.lifecycle(_Event("unloading", "kernel"))  # another row's: not the model's
    model_field.lifecycle(_Event("active", "loop"))
    assert frame.fields() == {"model": "haiku"}


def test_the_model_field_stops_saying_starting_when_a_layer_edit_takes_the_row_down() -> None:
    """A layer disables the model row: it unloads and goes inactive, and nothing brings it
    back, so the field must not keep saying it is starting."""
    frame, loader = _frame(), _Loader(_Entry("loop", {"default": "sonnet"}))
    model_field = ModelField(frame.status, loader, "loop", _current(loader, "loop"))
    model_field.show()
    loader.entries_now = [_Entry("loop", {"default": "sonnet"}, disabled=True)]
    model_field.lifecycle(_Event("unloading", "loop"))
    assert frame.fields() == {"model": "sonnet (starting…)"}
    model_field.lifecycle(_Event("inactive", "loop"))
    assert frame.fields() == {"model": "sonnet"}
