"""The `extensions` row's value: the model's own plugins, loaded into bh-02 while it runs.

The model writes a module of cordis components into the project's extensions directory
(`.bh-02/plugins/NAME.py`); this notices (it looks every `watch` seconds), and loads it into a
worker the `jail` row starts (`worker.py`), so the model's code runs as confined as its inputs
do, never in bh-02's own process. A changed file is loaded afresh, a deleted one unloaded.
When the jail confines nothing (`--no-jail`), each load is put to the person first, with the
source, exactly as an unjailed input is.

What an extension adds reaches bh-02 as data over the worker's socket: a slash command, which
this registers in `commands` and runs by asking the worker; a status-bar field, pushed into
`frame` under the extension's own name; a section of the model's prompt, added to `system`.
Each is kept with its remover, and taken back when the worker says so or the worker ends.

The model hears how each extension went in two places: its prompt (`section`, read per
request) and `status.json` in the extensions directory, written as soon as a load ends, so a
input can read it at once. The worker starts with the first extension there is to load; one that
ends (an extension may end it) takes every extension down with it, and they are loaded again,
in a new worker, at the next change in the directory.
"""

import asyncio
import contextlib
import functools
import importlib.util
import itertools
import json
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from sys import executable
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from extensions_cordis_plugin.watch import (
    Status,
    changes,
    extension_name,
    instructions,
    is_confined,
    status_file,
    status_forms,
)

__all__ = [
    "Asks",
    "Commands",
    "Extensions",
    "ExtensionsConfig",
    "Frame",
    "Jail",
    "System",
    "worker_argv",
]

_WORKER = Path(__file__).with_name("worker.py")
_LINE_LIMIT = 1 << 20  # the worker caps each text it sends at 20,000 characters, as the kernel does
_ANSWER_S = 30.0  # a load's answer: the worker waits up to 10 s for an extension's rows to come up
_STATUS = "status.json"
_FIELD = "extensions"
_ENDED = (
    "the extensions' worker ended (an extension may have ended it, or the jail did); change a "
    "file in the extensions directory to load them all again"
)


@runtime_checkable
class _Jailed(Protocol):
    """A program a jail started."""

    async def stop(self) -> None: ...


@runtime_checkable
class Jail(Protocol):
    """What the extensions need of the `jail` value (CONTRACTS.md: jail)."""

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Jailed: ...
    def report(self) -> Mapping[str, str]: ...


@runtime_checkable
class Commands(Protocol):
    """What the extensions need of the `commands` value: a registration and its remover."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@runtime_checkable
class Frame(Protocol):
    """What the extensions need of the `frame` value: a status-bar field and its remover."""

    def status(self, field: str, text: str, *shorter: str) -> Callable[[], None]: ...


@runtime_checkable
class System(Protocol):
    """What the extensions need of the `system` value: a prompt section and its remover."""

    def add(self, section: Callable[[], str]) -> Callable[[], None]: ...


@runtime_checkable
class Asks(Protocol):
    """What the extensions need of the `output` value: a yes or no about code (unjailed)."""

    async def confirm(self, request: Mapping[str, Any]) -> bool: ...


@dataclass(frozen=True, slots=True)
class ExtensionsConfig:
    """`root`: the project; `path`: the extensions directory, relative to it, where the model
    writes `NAME.py`; `watch`: how often, in seconds, the directory is looked at."""

    root: str = "."
    path: str = ".bh-02/plugins"
    watch: float = 0.5


@dataclass(frozen=True, slots=True)
class _Entry:
    """Something an extension added to bh-02: whose, what (`/todo`, a field), and its remover
    (None when bh-02 refused it)."""

    extension: str
    label: str
    remove: Callable[[], None] | None


class _Gone(Exception):
    """The worker is not there to answer: it would not start, or it ended."""


def worker_argv(endpoint: str) -> list[str]:
    """The worker, run by path under this interpreter, isolated (-I: no PYTHON* env, no cwd on path)."""
    return [executable, "-I", str(_WORKER), endpoint]


class Extensions:
    """The model's extensions: loaded from the extensions directory into a jailed worker, and
    what they add put into bh-02. An async context manager: entering starts watching, leaving
    stops it, takes back everything the extensions added and stops the worker."""

    def __init__(
        self,
        jail: Jail,
        commands: Commands,
        frame: Frame,
        system: System,
        output: Asks,
        config: ExtensionsConfig,
    ) -> None:
        self._jail = jail
        self._commands = commands
        self._frame = frame
        self._system = system
        self._output = output
        self._config = config
        self._statuses: dict[str, Status] = {}
        self._seen: dict[str, tuple[int, int]] = {}  # each file as last loaded: (mtime_ns, size)
        self._halted: dict[str, tuple[int, int]] | None = None  # the directory when the worker ended
        self._ended = False  # the worker ended since the last look
        self._leaving = False
        self._entries: dict[int, _Entry] = {}
        self._problems: dict[str, list[str]] = {}
        self._answers: dict[str, asyncio.Future[Mapping[str, Any]]] = {}
        self._calls: dict[int, asyncio.Future[str]] = {}
        self._call_ids = itertools.count(1)
        self._process: _Jailed | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._listener: asyncio.Task[None] | None = None
        self._socket_dir: str | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._field: Callable[[], None] | None = None
        # cordis's own design doc, to point the model at: beside the package in the workspace
        # (an editable install); an installed wheel carries none, and the model is not pointed
        cordis = importlib.util.find_spec("cordis")
        readme = Path(cordis.origin).parents[2] / "README.md" if cordis and cordis.origin else None
        self._reference = str(readme) if readme is not None and readme.is_file() else None

    @property
    def directory(self) -> Path:
        """Where the model writes extensions."""
        return Path(self._config.root).resolve() / self._config.path

    @property
    def statuses(self) -> Mapping[str, Status]:
        """Each extension, as last heard of."""
        return dict(self._statuses)

    def section(self) -> str:
        """What the model is told about extending bh-02, and how its extensions are: a section
        of its prompt (`system.add`), read per request. The loop reads the prompt in a worker
        thread while this row's watcher changes `_statuses` on the event loop, so it reads a copy
        (`statuses`, taken in one step) and nothing that needs the event loop."""
        confined = is_confined(self._jail.report())
        return instructions(self._config.path, confined, self.statuses, self._reference)

    async def __aenter__(self) -> Extensions:
        await self.look()  # what is there already loads before the row is up
        self._watcher = asyncio.ensure_future(self._watch())
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._watcher is not None:
            self._watcher.cancel()
            await asyncio.gather(self._watcher, return_exceptions=True)
        self._leaving = True
        await self._stop()
        if self._field is not None:
            self._field()
            self._field = None

    async def look(self) -> None:
        """Look at the extensions directory once: load what is new or changed, unload what is
        gone. The watcher does this every `watch` seconds."""
        found = self._found()
        if self._ended:
            self._halt(found)
            return
        if self._halted is not None:
            if found == self._halted:
                return  # the worker ended: nothing loads again until something changes
            self._halted, self._seen = None, {}  # a new worker: every extension loads again
        load, unload = changes(self._seen, found)
        for name in unload:
            del self._seen[name]
            await self._unload(name)
        for name in load:
            self._seen[name] = found[name]
            await self._load(name)
            if self._ended:  # this one ended the worker: the rest wait for a change
                self._halt(found)
                return
        if load or unload:
            self._publish()

    def _halt(self, found: Mapping[str, tuple[int, int]]) -> None:
        """The worker ended: say so for every extension there is, and load nothing until the
        directory differs from `found`, so an extension that ends the worker as it loads is not
        loaded again and again."""
        self._ended = False
        self._halted = dict(found)
        self._statuses = {name: Status(error=_ENDED) for name in found}
        self._publish()

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(self._config.watch)
            await self.look()

    def _found(self) -> dict[str, tuple[int, int]]:
        found: dict[str, tuple[int, int]] = {}
        with contextlib.suppress(OSError):
            for path in self.directory.iterdir():
                if (name := extension_name(path.name)) is not None and path.is_file():
                    stat = path.stat()
                    found[name] = (stat.st_mtime_ns, stat.st_size)
        return found

    # -- one extension ---------------------------------------------------------------------

    async def _load(self, name: str) -> None:
        path = self.directory / f"{name}.py"
        try:
            source = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            self._statuses[name] = Status(error=f"bh-02 could not read {path} as UTF-8 text")
            return
        if not is_confined(self._jail.report()) and not await self._approved(name, source):
            await self._unload(name)  # what an earlier version added goes; this one never loads
            self._statuses[name] = Status(error="the person declined to load it")
            return
        self._statuses[name] = Status(loading=True)
        self._problems[name] = []
        self._publish()
        try:
            await self._start()
            answer = await self._ask(name, {"op": "load", "name": name, "path": str(path), "source": source})
        except _Gone as gone:
            self._statuses[name] = Status(error=str(gone))
            return
        error = answer.get("error")
        rows = answer.get("rows") or {}
        self._statuses[name] = Status(
            rows={str(row): str(state) for row, state in rows.items()},
            error=None if error is None else str(error),
            commands=tuple(
                e.label for e in self._entries.values() if e.extension == name and e.label.startswith("/")
            ),
            problems=tuple(self._problems.get(name, ())),
        )

    async def _approved(self, name: str, source: str) -> bool:
        """Unjailed, the model's code would run with the person's permissions: ask them."""
        return await self._output.confirm(
            {
                "name": "extension",
                "title": f"Load the model's extension {name} into bh-02, unjailed?",
                "input": {"code": source},
            }
        )

    async def _unload(self, name: str) -> None:
        self._statuses.pop(name, None)
        self._problems.pop(name, None)
        if self._writer is not None:
            with contextlib.suppress(_Gone):
                await self._ask(name, {"op": "unload", "name": name})

    def _publish(self) -> None:
        """Tell the model (status.json) and the person (the status bar) how the extensions are."""
        with contextlib.suppress(OSError):
            if self.directory.is_dir():
                text = json.dumps(status_file(self._statuses), indent=2) + "\n"
                (self.directory / _STATUS).write_text(text, encoding="utf-8")
        if self._field is not None:
            self._field()
            self._field = None
        if forms := status_forms(self._statuses):
            self._field = self._frame.status(_FIELD, *forms)

    # -- what the extensions add -----------------------------------------------------------

    def _take(self, message: Mapping[str, Any]) -> None:
        match message.get("op"):
            case "add":
                self._add(message)
            case "remove":
                if (entry := self._entries.pop(int(message["id"]), None)) is not None and entry.remove:
                    entry.remove()
            case "loaded" | "unloaded":
                if (answer := self._answers.pop(str(message["name"]), None)) and not answer.done():
                    answer.set_result(message)
            case "ran":
                if (call := self._calls.pop(int(message["call"]), None)) and not call.done():
                    call.set_result(str(message.get("answer", "")))

    def _add(self, message: Mapping[str, Any]) -> None:
        entry, extension, kind = int(message["id"]), str(message["extension"]), message.get("kind")
        label, remove = kind or "?", None
        try:
            match kind:
                case "command":
                    spec = dict(message["spec"])
                    label = f"/{spec['name']}"
                    remove = self._commands.register(spec, functools.partial(self._run, entry))
                case "status":
                    field, forms = str(message["field"]), [str(form) for form in message["forms"]]
                    label = f"status field {field!r}"
                    remove = self._frame.status(f"{extension}:{field}", *forms)
                case "context":
                    text = str(message["text"])
                    label = "a prompt section"
                    remove = self._system.add(lambda: text)
        except Exception as error:  # bh-02 refused it: a command name another row has, say
            self._problems.setdefault(extension, []).append(f"{label} was not added: {error}")
        self._entries[entry] = _Entry(extension, label, remove)

    async def _run(self, entry: int, args: str) -> str:
        """A command an extension registered: run in the worker, its answer shown to the person."""
        call = next(self._call_ids)
        answer: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._calls[call] = answer
        try:
            self._send({"op": "run", "call": call, "command": entry, "args": args})
            return await answer
        except _Gone as gone:
            return str(gone)
        finally:
            self._calls.pop(call, None)

    # -- the worker ------------------------------------------------------------------------

    async def _ask(self, name: str, message: Mapping[str, Any]) -> Mapping[str, Any]:
        answer: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
        self._answers[name] = answer
        self._send(message)
        try:
            async with asyncio.timeout(_ANSWER_S):
                return await answer
        except TimeoutError:
            raise _Gone(f"the extensions' worker did not answer within {_ANSWER_S:.0f} s") from None
        finally:
            self._answers.pop(name, None)

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._writer is None:
            raise _Gone(_ENDED)
        self._writer.write((json.dumps(message) + "\n").encode("utf-8"))

    async def _start(self) -> None:
        """Start the worker in the jail, unless it is running."""
        if self._writer is not None:
            return
        # A Unix socket path must fit in about 100 bytes, so it lives in a short directory of its own.
        self._socket_dir = tempfile.mkdtemp(prefix="bh-x-", dir="/tmp")
        endpoint = str(Path(self._socket_dir) / "x.sock")
        root = str(Path(self._config.root).resolve())
        try:
            self._process = await self._jail.start(worker_argv(endpoint), cwd=root, endpoint=endpoint)
            reader, self._writer = await asyncio.open_unix_connection(endpoint, limit=_LINE_LIMIT)
        except Exception as error:
            await self._stop()
            raise _Gone(f"the extensions' jailed worker could not be started: {error}") from None
        self._send({"op": "hello"})
        self._listener = asyncio.ensure_future(self._listen(reader))

    async def _listen(self, reader: asyncio.StreamReader) -> None:
        try:
            while line := await reader.readline():
                self._take(json.loads(line))
        except ConnectionError, ValueError:
            pass
        finally:
            self._lost()

    def _lost(self) -> None:
        """The worker ended: everything its extensions added goes, every question to it fails,
        and nothing loads again until the directory changes."""
        if self._writer is None:
            return
        self._writer.close()
        self._writer = None
        self._ended = not self._leaving
        for entry in self._entries.values():
            if entry.remove is not None:
                entry.remove()
        self._entries.clear()
        waiting: list[asyncio.Future[Any]] = [*self._answers.values(), *self._calls.values()]
        for question in waiting:
            if not question.done():
                question.set_exception(_Gone(_ENDED))
        self._answers.clear()
        self._calls.clear()

    async def _stop(self) -> None:
        if self._listener is not None:
            self._listener.cancel()
            await asyncio.gather(self._listener, return_exceptions=True)
            self._listener = None
        self._lost()
        if self._process is not None:
            await self._process.stop()
            self._process = None
        if self._socket_dir is not None:
            shutil.rmtree(self._socket_dir, ignore_errors=True)
            self._socket_dir = None
