"""The loader: composition from configuration, itself a component (paper 5.2).

Rows are mounted as children of the loader's fiber, concurrently; order in the file means
nothing, dependencies decide when a row activates. `reload()` re-reads the layers and swaps
only the rows that changed, through the same path a first mount takes, and the loader calls
it itself whenever a layer file changes on disk: the layer files are the composition's
source of truth, and whoever edits one (a person, a script, a model with a file tool)
reshapes the running program. A reload that fails leaves the composition as it was and is
reported, never fatal. The values and the
plan are in `cordis.composition`; this module is the I/O around them: reading a layer file,
resolving a name to a component, and mounting.
"""

import asyncio
import contextlib
import importlib
import importlib.metadata
import os
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from cordis.authoring import component, lookup, scan
from cordis.component import Component, derive
from cordis.composition import Entry, Mount, Row, Unmount, compose, parse_layer, plan
from cordis.decisions import Declared, State, unsatisfiable
from cordis.effects import Effects
from cordis.inspection import Inspection
from cordis.runtime import Fiber, Performer, Runtime, bind, enter, performer, use

_ENTRY_POINT_GROUP = "cordis.plugins"


def read_layer(path: str | Path) -> list[Row]:
    """A layer file; see `parse_layer`."""
    return parse_layer(Path(path).read_text(), str(path))


def resolve(spec: str) -> Component:
    """`plugin:component` (scan that plugin's package) or `module:attribute`.

    A plugin is a `cordis.plugins` entry point, read from installed metadata: a name added to
    a pyproject is not seen until the distribution is reinstalled.
    """
    left, sep, right = spec.partition(":")
    if not sep:
        raise ValueError(f"{spec!r} must be 'plugin:component' or 'module:attribute'")
    plugins = {ep.name: ep for ep in importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)}
    if (ep := plugins.get(left)) is not None:
        return lookup(scan(ep.load()), right)
    try:
        module = importlib.import_module(left)
    except ImportError as e:
        e.add_note(f"no {left!r} plugin either; installed plugins: {_listed(plugins)}")
        raise
    if (obj := getattr(module, right, None)) is None:
        raise LookupError(f"{left} has no attribute {right!r}, and no {left!r} plugin is installed")
    return derive(obj)


def _listed(plugins: Mapping[str, object]) -> str:
    return ", ".join(sorted(plugins)) or "none"


def _entries(config: LoaderConfig) -> list[Entry]:
    layers: list[Iterable[Row]] = [read_layer(p) for p in config.layers]
    return compose([*layers, config.overrides])


def _unsatisfiable_rows(entries: Iterable[Entry]) -> dict[str, frozenset[str]]:
    """Which enabled rows' injects no row in `entries` declares `provides` for.

    Resolves each row's `use` the same way `_mount` does; a row that does not resolve is
    left out here too, since that failure is `_mount`'s to report once mounting starts.
    """
    # The loader is not a row, but its rows can depend on the handle it binds.
    declared = [Declared("loader", frozenset(), frozenset({"loader"}))]
    for entry in entries:
        if entry.disabled:
            continue
        try:
            component = resolve(entry.use)
        except Exception:  # importing a module can raise anything; `_mount` reports it
            continue
        declared.append(Declared(entry.id, component.inject, component.provides))
    return unsatisfiable(declared)


@dataclass(frozen=True, slots=True)
class LoaderConfig:
    """Where the composition comes from: layer files, then rows the bootstrap adds itself.

    `watch` is how often, in seconds, the layer files are checked for a change; `None` never
    checks, and a bootstrap calls `reload()` itself. `report` hears about a reload that failed
    (a layer that no longer parses, a file that went away) as one line; the composition stays
    as it was until the next change.
    """

    layers: tuple[str, ...] = ()
    overrides: tuple[Row, ...] = ()
    watch: float | None = 0.5
    report: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class Disabled:
    """A row that is present but switched off."""

    entry: Entry


@dataclass(frozen=True, slots=True)
class Unresolved:
    """A row whose `use` could not be turned into a component; its siblings still run."""

    entry: Entry
    error: str


@dataclass(frozen=True, slots=True)
class Live:
    """A row with a fiber."""

    entry: Entry
    fiber: Fiber


type Mounted = Disabled | Unresolved | Live


def describe(mounted: Mounted) -> str:
    """One row's status: disabled | unresolved: ... | the fiber's state (with its error when
    FAILED, or when ACTIVE but its owned background work died under it)."""
    match mounted:
        case Disabled():
            return "disabled"
        case Unresolved(error=error):
            return f"unresolved: {error}"
        case Live(fiber=fiber) if fiber.state is State.FAILED:
            return f"failed: {fiber.error!r}"
        case Live(fiber=fiber) if fiber.state is State.ACTIVE and fiber.error is not None:
            return f"active, work failed: {fiber.error!r}"
        case Live(fiber=fiber):
            return fiber.state.value


class Loader:
    """What the loader binds (under `loader`): the mounted rows, and the operator's actions on
    them: reload, restart one row, explain one row.

    One change at a time: a reload the watcher started and a restart a command asked for
    never interleave on `rows`.
    """

    def __init__(self, config: LoaderConfig, host: Performer) -> None:
        self.config = config
        self.rows: dict[str, Mounted] = {}
        self._host = host
        self._changing = asyncio.Lock()

    def entries(self) -> list[Entry]:
        return _entries(self.config)

    async def apply(self, entries: Iterable[Entry]) -> None:
        """Walk the plan from what is mounted to `entries`; see `plan` for the order."""
        async with self._changing:
            current = {rid: m.entry for rid, m in self.rows.items()}
            for step in plan(current, entries):
                match step:
                    case Unmount(id=rid):
                        await self._unmount(rid)
                    case Mount(entry=entry):
                        await self._mount(entry)

    async def restart(self, *rids: str) -> None:
        """Retire rows and mount them again from the same entries: fresh fibers, so fresh
        state, and every row depending on what they bind reloads against the new ones. Several
        rows restart together: all retire before any comes back, so a row depending on more
        than one of them reloads once, not once per row."""
        async with self._changing:
            if missing := [rid for rid in rids if rid not in self.rows]:
                raise LookupError(
                    f"no row {missing[0]!r}; the rows are {', '.join(sorted(self.rows)) or 'none'}"
                )
            entries = [self.rows[rid].entry for rid in dict.fromkeys(rids)]
            for entry in entries:
                await self._unmount(entry.id)
            for entry in entries:
                await self._mount(entry)

    def explain(self, rid: str) -> str:
        """cordis's diagnosis of one row: its state, what it binds, waits on, and did last."""
        match self.rows.get(rid):
            case None:
                return f"{rid}: no such row; the rows are {', '.join(sorted(self.rows)) or 'none'}"
            case Live(fiber=fiber):
                return Inspection(fiber.ctx.runtime).explain(rid)
            case mounted:
                return f"{rid}: {describe(mounted)}"

    async def reload(self) -> None:
        """Re-read the layers and swap only the rows that changed."""
        await self.apply(self.entries())

    async def _mount(self, entry: Entry) -> None:
        if entry.disabled:
            self.rows[entry.id] = Disabled(entry)
            return
        try:
            what = resolve(entry.use)
        except Exception as e:
            # An unresolvable row is reported, not fatal: its siblings still run. Importing a
            # module runs it, so a row's module can fail any way code can (a SyntaxError in a
            # model-written plugin is the usual one), not just with an ImportError.
            self.rows[entry.id] = Unresolved(entry, f"{type(e).__name__}: {e}")
            return
        fiber = await self._host.perform(use(what, config=entry.config, id=entry.id))
        self.rows[entry.id] = Live(entry, fiber)

    async def _unmount(self, rid: str) -> None:
        mounted = self.rows.pop(rid)
        if isinstance(mounted, Live):
            await mounted.fiber.retire()

    def status(self) -> dict[str, str]:
        """Row id -> `describe` of its outcome."""
        return {rid: describe(m) for rid, m in self.rows.items()}


@dataclass(frozen=True, slots=True)
class Booted:
    """What a bootstrap gets back: the runtime, and the loader handle for reloads."""

    runtime: Runtime
    loader: Loader


@component
async def loader(*, config: LoaderConfig) -> Effects:
    """Mounts the composition as children of its own fiber; unloading it unwinds the tree.

    The watcher is entered, not `background` work: it is a daemon the loader keeps while it
    lives, not work the composition owes, so `Runtime.idle()` does not wait for it.
    """
    host: Performer = yield performer()
    handle = Loader(config, host)
    await handle.apply(handle.entries())
    if config.watch is not None and config.layers:
        yield enter(_watching(handle, config))
    yield bind("loader", handle)


@contextlib.asynccontextmanager
async def _watching(handle: Loader, config: LoaderConfig) -> AsyncIterator[None]:
    """Reload whenever a layer file's modification time changes, until the loader leaves."""
    task = asyncio.ensure_future(_watch(handle, config))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _watch(handle: Loader, config: LoaderConfig) -> None:
    seen = _stamps(config.layers)
    while True:
        await asyncio.sleep(config.watch or 0.5)
        now = _stamps(config.layers)
        if now == seen:
            continue
        seen = now
        try:
            await handle.reload()
        except Exception as error:  # the composition stays as it was; the next change tries again
            if config.report is not None:
                config.report(f"reload failed: {type(error).__name__}: {error}")


def _stamps(paths: Iterable[str]) -> tuple[int | None, ...]:
    """Each layer file's modification time, or None for one that is not there."""
    out: list[int | None] = []
    for path in paths:
        try:
            out.append(os.stat(path).st_mtime_ns)
        except OSError:
            out.append(None)
    return tuple(out)


async def boot(
    layers: Iterable[str | Path] = (),
    overrides: Iterable[Row] = (),
    rt: Runtime | None = None,
    *,
    watch: float | None = 0.5,
    report: Callable[[str], None] | None = None,
) -> Booted:
    """The bootstrap: a runtime, one row (the loader), and the layers it composes.

    The loader then watches those layer files and reloads on its own; `watch=None` turns
    that off, and `report` hears about a reload that failed, and about a row whose declared
    provides can't satisfy another row's declared inject, checked once here before any
    effect runs (mounting the loader is the first one).
    """
    rt = rt or Runtime()
    config = LoaderConfig(tuple(str(p) for p in layers), tuple(overrides), watch, report)
    if report is not None:
        for rid, missing in _unsatisfiable_rows(_entries(config)).items():
            report(f"{rid} needs {', '.join(sorted(missing))}; no row provides it")
    rt.mount(loader, config=config, id="loader")
    await rt.settle()
    handle: Loader = rt.root.get("loader")
    return Booted(rt, handle)
