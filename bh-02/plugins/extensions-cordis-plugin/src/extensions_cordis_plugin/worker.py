"""The extensions' own process: a cordis runtime of the components the model wrote.

Run by path (``python -I worker.py SOCKET``) by the `runner`, so it is confined as the
Python process's inputs are: the model's code runs here, never in bh-02's own process. What it
reaches of bh-02 is four keys, bound per extension, each of which only adds: `commands.register`,
a slash command for the person; `frame.status`, a status-bar field; `system.add`, text in the
model's own prompt; `tools.register`, a tool offered to the model, whose calls run here. Each
sends what it added to the host and returns the remover that takes it back, so `acquire` makes a
registration last exactly as long as the component.

An extension is a module: its source arrives in a `load`, runs as a module of its own, and
every component it defines is mounted as a child of one fiber per extension, the one that binds
the four keys (isolated, so each extension's registrations carry its name). An extension may
`bind` keys of its own for another to depend on: those are shared, as in any composition.

Wire: newline-delimited JSON. The host sends ``{"op": "hello"}`` once (a readiness probe
connects and closes without a word, so the worker keeps accepting until one speaks), then:

- ``{"op": "load", "name", "path", "source"}``, answered ``{"op": "loaded", "name", "rows",
  "error"}``: each row's state as text (`active`, `waiting on: KEY`, `failed: ...`), or the
  error that kept the module from loading at all. A name loaded again replaces what it was.
- ``{"op": "unload", "name"}``, answered ``{"op": "unloaded", "name"}``.
- ``{"op": "run", "call", "command", "args"}``, answered ``{"op": "ran", "call", "answer"}``.
- ``{"op": "call", "call", "tool", "input"}`` (a call to a tool, `input` its arguments),
  answered ``{"op": "ran", "call", "answer"}``, `answer` the text the model reads.

and the worker sends, whenever an extension adds or takes back an entry,
``{"op": "add", "id", "extension", "kind", ...}`` (`command` with `spec`, `status` with `field`
and `forms`, `context` with `text`, `tool` with `spec`) and ``{"op": "remove", "id"}``. A
worker nobody says hello to exits once its parent is gone or after `_HELLO_S`; one whose host
disconnects exits too.
"""

import asyncio
import contextlib
import itertools
import json
import os
import re
import time
import traceback
import types
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from sys import argv, modules
from typing import Any

from cordis import Component, Effects, Fiber, Inspection, Runtime, State, bind, scan, use

__all__ = ["main"]

type Run = Callable[[Any], Awaitable[object]]  # a command's (its argument text) or a tool's (its input)

_OFFERED = ("commands", "frame", "system", "tools")  # the keys an extension reaches bh-02 through
_COMMAND = re.compile(r"[a-z][a-z-]*")  # a name the `commands` broker can parse back out of a line
_MAX_TEXT = 20_000  # an answer, a field or a section: the host reads one line per message
_HELLO_S = 60.0
_LOOK_S = 0.5
_LINE_LIMIT = 2 << 20  # a load's line: a source of up to 256 KiB (the host's cap), JSON-escaped
_SETTLE_S = 10.0  # how long a load waits for its rows to come up before saying how they are


class _Bridge:
    """The socket's writing end, every entry extensions added (by id, with whose it is), and
    the commands and tools among them."""

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer
        self._ids = itertools.count(1)
        self._live: dict[int, str] = {}  # entry: the extension that added it
        self.runs: dict[int, Run] = {}

    def send(self, message: Mapping[str, Any]) -> None:
        self._writer.write((json.dumps(message) + "\n").encode("utf-8"))

    def add(
        self, extension: str, kind: str, fields: Mapping[str, Any], run: Run | None = None
    ) -> Callable[[], None]:
        """Send an entry the host is to add; returns its remover, which sends its removal once."""
        entry = next(self._ids)
        self._live[entry] = extension
        if run is not None:
            self.runs[entry] = run
        self.send({"op": "add", "id": entry, "extension": extension, "kind": kind, **fields})

        def remove() -> None:
            if self._live.pop(entry, None) is not None:
                self.runs.pop(entry, None)
                self.send({"op": "remove", "id": entry})

        return remove

    def clear(self, extension: str) -> None:
        """Take back whatever `extension` added and never removed (a field pushed from
        background work, say, rather than through `acquire`): it leaves with the extension."""
        for entry in [entry for entry, owner in self._live.items() if owner == extension]:
            del self._live[entry]
            self.runs.pop(entry, None)
            self.send({"op": "remove", "id": entry})


def _text(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{what} must be a str, not {type(value).__name__}")
    return value[:_MAX_TEXT]


class _Commands:
    """`commands` as an extension sees it: it can only add a slash command for the person."""

    def __init__(self, bridge: _Bridge, extension: str) -> None:
        self._bridge = bridge
        self._extension = extension

    def register(self, spec: Mapping[str, Any], run: Run) -> Callable[[], None]:
        """Offer `/NAME` to the person (`spec`: `name`, `help`, `usage`); `run` is async, the
        command's argument text in, the text to show out. Returns the remover."""
        name = spec.get("name")
        if not isinstance(name, str) or not _COMMAND.fullmatch(name):
            raise ValueError(
                f"a command's name is lowercase letters and dashes, without the slash ('todo', "
                f"'run-tests'); got {name!r}"
            )
        if not callable(run):
            raise TypeError(f"/{name}: run must be an async function of the argument text")
        usage = spec.get("usage") or f"/{name}"
        fields = {
            "spec": {
                "name": name,
                "help": _text(spec.get("help", ""), "help"),
                "usage": _text(usage, "usage"),
            }
        }
        return self._bridge.add(self._extension, "command", fields, run)

    def claim(self, prefix: str, spec: Mapping[str, Any], run: Run) -> Callable[[], None]:
        """Refused: a prefix takes every line the person starts with it (`!` runs it in their
        shell, unjailed), so only a row in a layer may claim one, never an extension."""
        raise PermissionError(
            f"an extension can't claim a line prefix ({prefix!r}): a prefix takes every line the "
            "person starts with it, so only a row in a layer may claim one; register a slash "
            "command instead (commands.register)"
        )


class _Frame:
    """`frame` as an extension sees it: it can only show a field in the status bar."""

    def __init__(self, bridge: _Bridge, extension: str) -> None:
        self._bridge = bridge
        self._extension = extension

    def status(self, field: str, text: str, *shorter: str) -> Callable[[], None]:
        """Show `text` under `field` until the remover is called; `shorter` are shorter forms
        for a narrow terminal. To change it, push again: the latest push of a field shows."""
        forms = [_text(form, "a status field's text") for form in (text, *shorter)]
        return self._bridge.add(self._extension, "status", {"field": _text(field, "field"), "forms": forms})


class _System:
    """`system` as an extension sees it: it can only add text to the model's prompt."""

    def __init__(self, bridge: _Bridge, extension: str) -> None:
        self._bridge = bridge
        self._extension = extension

    def add(self, text: str) -> Callable[[], None]:
        """Add `text` to the model's system prompt until the remover is called."""
        return self._bridge.add(self._extension, "context", {"text": _text(text, "a prompt section")})


class _Tools:
    """`tools` as an extension sees it: it can only offer the model a tool, whose calls run here."""

    def __init__(self, bridge: _Bridge, extension: str) -> None:
        self._bridge = bridge
        self._extension = extension

    def register(self, spec: Mapping[str, Any], run: Run) -> Callable[[], None]:
        """Offer the model a tool (`spec`: `name`, `description`, and `parameters`, a JSON
        Schema object); `run` is async, the call's arguments (a dict) in, the text the model
        reads out (anything else is sent as JSON). Returns the remover. bh-02 checks the spec
        when it arrives: one it refuses is in status.json's `problems`, saying why."""
        name = spec.get("name") if isinstance(spec, Mapping) else None
        if not isinstance(name, str):
            raise ValueError(
                f"a tool's spec is a dict with a `name`, `description` and `parameters`; got {spec!r}"
            )
        if not callable(run):
            raise TypeError(f"the tool {name!r}: run must be an async function of the call's arguments")
        try:
            fields = {"spec": json.loads(json.dumps(dict(spec)))}
        except TypeError, ValueError:
            raise ValueError(
                f"the tool {name!r}'s spec must be plain JSON (dicts, lists, text, numbers)"
            ) from None
        return self._bridge.add(self._extension, "tool", fields, run)


@dataclass(frozen=True, slots=True)
class _Loaded:
    """One extension: its name, and the components its module defines."""

    name: str
    bridge: _Bridge
    components: tuple[Component, ...]
    rows: list[Fiber] = field(default_factory=list)


async def _extension(*, config: _Loaded) -> Effects:
    """One extension's fiber: binds its own `commands`, `frame`, `system` and `tools` (isolated,
    so each is the extension's alone and tagged with its name), then mounts its components."""
    yield bind("commands", _Commands(config.bridge, config.name))
    yield bind("frame", _Frame(config.bridge, config.name))
    yield bind("system", _System(config.bridge, config.name))
    yield bind("tools", _Tools(config.bridge, config.name))
    for made in config.components:
        row: Fiber = yield use(made, id=f"{config.name}.{made.name}")
        config.rows.append(row)


def _failure(error: BaseException, path: str) -> str:
    """An exception as the model reads it: from the first frame in its own file on, or (a
    syntax error, say, which has none) the exception alone: the worker's frames say nothing."""
    tb = error.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_filename != path:
        tb = tb.tb_next
    lines = (
        traceback.format_exception(type(error), error, tb)
        if tb is not None
        else traceback.format_exception_only(type(error), error)
    )
    return "".join(lines).rstrip()[:_MAX_TEXT]


def _state(rt: Runtime, row: Fiber, path: str) -> str:
    """A row's state as the model reads it."""
    match row.state:
        case State.ACTIVE if row.error is not None:
            return f"active, but its work failed:\n{_failure(row.error, path)}"
        case State.ACTIVE:
            return "active"
        case State.FAILED:
            return "failed:\n" + (_failure(row.error, path) if row.error else "(no error recorded)")
        case State.INACTIVE if waiting := Inspection(rt).waiting_on(row):
            keys = ", ".join(str(key) for key in waiting)
            return f"waiting on: {keys} (no extension binds it; bh-02 offers {', '.join(_OFFERED)})"
        case _:
            return row.state.value


class _Extensions:
    """The loaded extensions, by name."""

    def __init__(self, rt: Runtime, bridge: _Bridge) -> None:
        self._rt = rt
        self._bridge = bridge
        self._loaded: dict[str, tuple[Fiber, str]] = {}  # name: its fiber, its module's name
        self._modules = itertools.count(1)
        self.lock = asyncio.Lock()

    async def load(self, name: str, path: str, source: str) -> dict[str, Any]:
        await self.unload(name)
        module = types.ModuleType(f"bh02_extension_{name}_{next(self._modules)}")
        module.__file__ = path
        modules[module.__name__] = module  # a scan finds a component by its module's name
        try:
            exec(compile(source, path, "exec"), module.__dict__)
            found = scan(module)
        except BaseException as error:  # anything the module's code raises, SystemExit included
            modules.pop(module.__name__, None)
            return {"rows": {}, "error": _failure(error, path)}
        if not found:
            modules.pop(module.__name__, None)
            return {
                "rows": {},
                "error": "it defines no component: mark an async generator function with "
                "@component (from cordis import component)",
            }
        loaded = _Loaded(name, self._bridge, tuple(found.values()))
        fiber = self._rt.mount(_extension, config=loaded, isolate=_OFFERED, id=name)
        self._loaded[name] = (fiber, module.__name__)
        with contextlib.suppress(TimeoutError):  # a component still setting up is said to be loading
            async with asyncio.timeout(_SETTLE_S):
                await self._rt.settle()
        if fiber.state is State.FAILED and fiber.error is not None:
            return {"rows": {}, "error": _failure(fiber.error, path)}
        return {"rows": {row.name: _state(self._rt, row, path) for row in loaded.rows}, "error": None}

    async def unload(self, name: str) -> None:
        if (held := self._loaded.pop(name, None)) is not None:
            fiber, module = held
            await fiber.retire()
            self._bridge.clear(name)
            modules.pop(module, None)

    async def run(self, command: int, args: str) -> str:
        run = self._bridge.runs.get(command)
        if run is None:
            return "this command's extension has been unloaded"
        try:
            answer = await run(args)
        except Exception as error:
            return f"failed: {type(error).__name__}: {error}"
        return "" if answer is None else (answer if isinstance(answer, str) else str(answer))[:_MAX_TEXT]

    async def call(self, tool: int, input: Mapping[str, Any]) -> str:
        """A call to a tool an extension registered: what the model reads of it, its error
        included (the call's answer, not the reply's failure)."""
        run = self._bridge.runs.get(tool)
        if run is None:
            return "error: this tool's extension has been unloaded"
        try:
            answer = await run(dict(input))
        except Exception as error:
            return f"error: {type(error).__name__}: {error}"[:_MAX_TEXT]
        if answer is None or isinstance(answer, str):
            return (answer or "")[:_MAX_TEXT]
        return json.dumps(answer, ensure_ascii=False, default=str)[:_MAX_TEXT]


async def _serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Answer the host until it disconnects, then unload everything."""
    bridge = _Bridge(writer)
    rt = Runtime()
    extensions = _Extensions(rt, bridge)
    tasks: set[asyncio.Task[None]] = set()

    async def answer(message: Mapping[str, Any]) -> None:
        match message.get("op"):
            case "load":
                name = str(message["name"])
                async with extensions.lock:
                    loaded = await extensions.load(name, str(message["path"]), str(message["source"]))
                bridge.send({"op": "loaded", "name": name, **loaded})
            case "unload":
                name = str(message["name"])
                async with extensions.lock:
                    await extensions.unload(name)
                bridge.send({"op": "unloaded", "name": name})
            case "run":
                said = await extensions.run(int(message["command"]), str(message.get("args", "")))
                bridge.send({"op": "ran", "call": message["call"], "answer": said})
            case "call":
                given = message.get("input")
                said = await extensions.call(
                    int(message["tool"]), given if isinstance(given, Mapping) else {}
                )
                bridge.send({"op": "ran", "call": message["call"], "answer": said})

    try:
        while line := await reader.readline():
            if line.strip():
                task = asyncio.ensure_future(answer(json.loads(line)))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await rt.shutdown()


async def _main(endpoint: str, hello_s: float) -> None:
    parent = os.getppid()
    deadline = time.monotonic() + hello_s
    heard = asyncio.Event()
    served: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if heard.is_set() or not (await reader.readline()).strip():
            writer.close()  # a readiness probe: connected, said nothing, left
            return
        heard.set()
        try:
            await _serve(reader, writer)
        finally:
            writer.close()  # the server's close waits for every connection it handed out
            served.set_result(None)

    server = await asyncio.start_unix_server(connected, path=endpoint, limit=_LINE_LIMIT)
    async with server:
        while not heard.is_set():
            if os.getppid() != parent or time.monotonic() > deadline:
                return  # the host that started this worker is gone, or never came
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(_LOOK_S):
                    await heard.wait()
        await served


def main(argv: Sequence[str]) -> None:
    """Listen on the socket at `argv[0]`, wait for the host's hello (for `argv[1]` seconds at
    most, `_HELLO_S` by default, and only while the parent lives), then serve it."""
    asyncio.run(_main(argv[0], float(argv[1]) if len(argv) > 1 else _HELLO_S))


if __name__ == "__main__":
    main(argv[1:])
