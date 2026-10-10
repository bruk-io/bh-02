"""What the frame's rows need: somewhere to push (`frame`), and what they report on; and
`ModelField`, the status row's one piece of state (its `model` field)."""

import contextlib
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from tui_cordis_plugin import frame, render

__all__ = [
    "CommandSink",
    "CommandSource",
    "Confinement",
    "Entries",
    "GradesField",
    "ModelField",
    "ModelSource",
    "Notes",
    "Running",
    "Started",
    "Starts",
    "StatusConfig",
    "StatusSink",
    "TuiConfig",
]

type Remover = Callable[[], None]


@dataclass(frozen=True, slots=True)
class TuiConfig:
    """`headless` runs the app with no terminal (tests; a real run never sets it). `history`
    is a file the app keeps what it shows in and draws again when it starts (a session's
    `events.jsonl`); `replay` is how many of its entries it draws again at most."""

    headless: bool = False
    history: str | None = None
    replay: int = 400


@dataclass(frozen=True, slots=True)
class StatusConfig:
    """The status row's config. `model_row`: the model row, whose lifecycle the model field
    follows (`model`)."""

    model_row: str = "model"


@runtime_checkable
class StatusSink(Protocol):
    """What a status row needs of the `frame` value (CONTRACTS.md: frame)."""

    def status(self, field: str, text: str, *shorter: str) -> Callable[[], None]: ...


@runtime_checkable
class Started(Protocol):
    """A start the runner reports (CONTRACTS.md: runner): its grades, and what the person should
    know of it."""

    def report(self) -> Mapping[str, str]: ...
    def notice(self) -> str: ...


@runtime_checkable
class Starts(Protocol):
    """What the grades row needs of the `runner` value (CONTRACTS.md: runner): the grades before
    any start, and each start told as it happens."""

    def report(self) -> Mapping[str, str]: ...
    def on_start(self, watch: Callable[[Started], None]) -> Callable[[], None]: ...


@runtime_checkable
class Confinement(Protocol):
    """What the grades row needs of the `approval` value (CONTRACTS.md: approval): whether the
    runner confines what runs in it."""

    @property
    def confined(self) -> bool: ...


@runtime_checkable
class Notes(Protocol):
    """What the status row needs of the `output` value (CONTRACTS.md: output): somewhere to show
    a note in the conversation."""

    async def show(self, events: AsyncIterator[Mapping[str, Any]]) -> None: ...


@runtime_checkable
class Running(Protocol):
    """What the status row needs of the `session` value (CONTRACTS.md: session): the running
    session's id (empty when the composition runs without one) and whether it was resumed."""

    @property
    def current(self) -> str: ...
    @property
    def resumed(self) -> bool: ...


@runtime_checkable
class Entries(Protocol):
    """What the status row needs of the `loader` value (CONTRACTS.md: loader): the rows as the
    layers compose them now (each with an `id` and a `config`), and each row's state."""

    def entries(self) -> Sequence[Any]: ...
    def status(self) -> Mapping[str, str]: ...


@runtime_checkable
class ModelSource(Protocol):
    """What the status row needs of the `models` value (CONTRACTS.md: models): the model the
    model row names now, its `name` and `provider`."""

    def current(self) -> Mapping[str, str]: ...


@runtime_checkable
class CommandSource(Protocol):
    """What the palette row needs of the `commands` value (CONTRACTS.md: commands)."""

    def specs(self) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class CommandSink(Protocol):
    """What the palette row needs of the `frame` value: a place to offer commands."""

    def commands(self, specs: Callable[[], Sequence[Mapping[str, Any]]]) -> Remover: ...


class _Lifecycle(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def fiber(self) -> str: ...


class _Push(Protocol):
    def __call__(self, field: str, text: str, /, *shorter: str) -> Remover: ...


class ModelField:
    """The status bar's `model` field, `sonnet (claude-code)`: what the `models` value says the
    model row names (`current`), shown again at each lifecycle event of the model row
    (`model`): `sonnet (claude-code, starting…)` from the moment the row unloads
    (a `/model` edits the session's layer and reloads it; `/clear` restarts it) until it is
    active again, however long that takes (`frame.model_forms`).

    `show` pushes the field and returns the remover of whichever push is current, so the
    status row `acquire`s it; `lifecycle` is what it `observe`s. The first push reads the row's
    phase from the loader's `status()`; after that, the row's own events move it
    (`frame.phase_after`). A layer that cannot be read just now (a half-written file) keeps
    the last text shown.
    """

    def __init__(
        self, status: _Push, loader: Entries, row: str, current: Callable[[], Mapping[str, str]]
    ) -> None:
        self._status = status
        self._loader = loader
        self._row = row
        self._current = current
        self._model = ("", "")
        self._phase: str | None = None  # read from the loader at the first push
        self._shown: Remover | None = None

    def show(self) -> Remover:
        """Push the field as the layers say now; return the remover of the current push."""
        # a layer mid-write, or broken (the loader reports it): the last text stays
        with contextlib.suppress(OSError, ValueError, KeyError):
            self._model = frame.model_text(self._current())
        if self._phase is None:
            self._phase = frame.phase_of(self._loader.status().get(self._row))
        pushed = self._status("model", *frame.model_forms(self._model, self._phase))
        if self._shown is not None:
            self._shown()
        self._shown = pushed
        return self.hide

    def hide(self) -> None:
        """Take the field down (the row is leaving)."""
        if self._shown is not None:
            self._shown()
            self._shown = None

    def lifecycle(self, event: _Lifecycle) -> None:
        """Show the field again at each event of the model row, while it is shown: starting
        from its unloading, the new model once it is active, and no longer starting once it
        is down for good (`frame.phase_after`)."""
        if event.fiber == self._row and self._shown is not None:
            self._phase = frame.phase_after(event.kind, self._phase or "up", self._listed())
            self.show()

    def _listed(self) -> bool:
        """Whether the layers still name the row (a layer that cannot be read: assume so)."""
        try:
            return frame.listed(self._loader.entries(), self._row)
        except OSError, ValueError, KeyError:
            return True


class GradesField:
    """The status bar's `jail` field, `jailed fs_write ✓ network ✓`: the grades of the runner's
    last start (before any, the runner's own), and whether the `approval` rule counts them as
    confined (`render.jail_forms`). The runner tells each start (`started`, its `on_start`), so
    the field follows a Python process started again in place, never showing a start gone by.
    What a start says the person should know (`notice`: on Linux, the paths its jail holds with a
    mount the host can undo) is shown once as a note in the conversation, `note` (it is
    `output.show`), each time it reads differently from the last told.

    `show` pushes the field and returns the remover of whichever push is current, so the row
    `acquire`s it."""

    def __init__(
        self, status: _Push, rule: Confinement, report: Mapping[str, str], note: Callable[[str], None]
    ) -> None:
        self._status = status
        self._rule = rule
        self._report = report
        self._note = note
        self._told = ""
        self._shown: Remover | None = None

    def show(self) -> Remover:
        """Push the field for the grades last told; return the remover of the current push."""
        pushed = self._status("jail", *render.jail_forms(self._rule.confined, self._report))
        if self._shown is not None:
            self._shown()
        self._shown = pushed
        return self.hide

    def hide(self) -> None:
        """Take the field down (the row is leaving)."""
        if self._shown is not None:
            self._shown()
            self._shown = None

    def started(self, started: Started) -> None:
        """A start the runner made: show its grades, and its notice when it is new."""
        self._report = started.report()
        if self._shown is not None:
            self.show()
        if (notice := started.notice()) and notice != self._told:
            self._told = notice
            self._note(notice)
