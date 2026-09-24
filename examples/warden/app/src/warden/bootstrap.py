"""Boot a composition and run it: on this thread until interrupted, or under a tray app
that needs the main thread for itself.
"""

import asyncio
import threading
from collections.abc import Callable, Iterable
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol, runtime_checkable

from cordis import Booted, Inspection, Row, Runtime, boot

__all__ = ["CompositionError", "layers", "run", "run_with_tray"]


class CompositionError(Exception):
    """A row that never started, with cordis's own diagnosis."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@runtime_checkable
class _Tray(Protocol):
    """The shape `run_with_tray` needs of whatever a `tray` row binds (CONTRACTS.md): a
    quit hook it can set before handing control to the tray's own run loop, which `.run()`
    then blocks the calling thread on until that hook fires.
    """

    on_quit: Callable[[], None] | None

    def run(self) -> None: ...


def layers(*, tray: bool = False) -> list[Traversable]:
    """The shipped layers: the process registry, plus the tray under `--tray`."""
    shipped = resources.files("warden")
    names = ["supervisor.toml"] + (["tray.toml"] if tray else [])
    return [shipped / name for name in names]


async def _boot(
    layers: Iterable[str | Path | Traversable],
    overrides: Iterable[Row],
    *,
    trace: Callable[[str], None] | None,
    report: Callable[[str], None] | None,
) -> Booted:
    rt = Runtime()
    if trace is not None:
        rt.listeners.append(lambda event: trace(str(event)))
    return await boot([str(layer) for layer in layers], list(overrides), rt, report=report)


async def _serve(booted: Booted) -> None:
    """Fail loudly if the composition never started; otherwise run until cancelled. Either
    way, unwind: a row that never starts still mounted a `Runtime` with background work of
    its own (the loader's file watch, at least), and leaving it running would leak it
    exactly as leaking a supervised process would.

    There is no mode row yet (nothing has its own notion of being "done" the way `bh-02`'s
    chat session does), so this waits on cancellation directly rather than on a `done`
    binding the way `bh_02.bootstrap.run` does. The layer files stay watched while this runs:
    editing a layer file reshapes the running composition.
    """
    try:
        _raise_if_stalled(booted)
        await asyncio.Event().wait()
    finally:
        await booted.runtime.shutdown()


async def run(
    layers: Iterable[str | Path | Traversable],
    overrides: Iterable[Row] = (),
    *,
    trace: Callable[[str], None] | None = None,
    report: Callable[[str], None] | None = None,
) -> None:
    """Boot, then run until cancelled, then unwind. Call this from any thread."""
    booted = await _boot(layers, overrides, trace=trace, report=report)
    await _serve(booted)


def run_with_tray(
    layers: Iterable[str | Path | Traversable],
    overrides: Iterable[Row] = (),
    *,
    trace: Callable[[str], None] | None = None,
    report: Callable[[str], None] | None = None,
) -> None:
    """Like `run`, but the composition runs in a background thread and this thread blocks
    on the tray's own run loop instead: AppKit needs the main thread, so this is the one
    reversed. Quitting the tray is what ends the composition (wired as `_Tray.on_quit`), not
    a signal. Call this from the main thread only; `run` from any thread.
    """
    ready = threading.Event()
    booted_box: list[Booted] = []
    task_box: list[asyncio.Task[None]] = []
    error_box: list[BaseException] = []

    def worker() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def main() -> None:
            booted = await _boot(layers, overrides, trace=trace, report=report)
            try:
                _raise_if_stalled(booted)
                booted_box.append(booted)
                current = asyncio.current_task()
                assert current is not None
                task_box.append(current)
                ready.set()
                await asyncio.Event().wait()
            except BaseException as error:
                if not ready.is_set():  # a boot-time failure; a later cancel is the normal quit
                    error_box.append(error)
                    ready.set()
                raise
            finally:
                await booted.runtime.shutdown()

        try:
            loop.run_until_complete(main())
        except BaseException:  # already in error_box, or an ordinary cancel; nothing more to do here
            pass
        finally:
            loop.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    ready.wait()
    if error_box:
        raise error_box[0]

    booted, task = booted_box[0], task_box[0]
    loop = task.get_loop()
    make_tray: Callable[[], _Tray] = booted.runtime.root.get("tray")
    tray = make_tray()

    def on_quit() -> None:
        loop.call_soon_threadsafe(task.cancel)
        thread.join(timeout=5)

    tray.on_quit = on_quit
    tray.run()


def _raise_if_stalled(booted: Booted) -> None:
    """Fail with cordis's own diagnosis for any row that is not active or disabled."""
    stalled = {
        row: state for row, state in booted.loader.status().items() if state not in ("active", "disabled")
    }
    if not stalled:
        return
    view = Inspection(booted.runtime)
    lines = [
        view.explain(row) if view.fiber(row) is not None else f"{row}: {state}"
        for row, state in stalled.items()
    ]
    raise CompositionError("could not start:\n" + "\n".join(lines))
