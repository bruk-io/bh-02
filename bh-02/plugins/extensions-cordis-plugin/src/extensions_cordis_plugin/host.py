"""The `extensions` row's value: the model's own plugins, loaded into bh-02 while it runs.

The model writes a module of cordis components into the project's extensions directory
(`.bh-02/plugins/NAME.py`); this notices (it looks every `watch` seconds), and loads it into a
worker the `runner` starts (`worker.py`), so the model's code runs as confined as its inputs
do, never in bh-02's own process. A changed file is loaded afresh, a deleted one unloaded.
Each load is put to the `approval` rule first, with the source, exactly as an input is: at once
when the runner confines what runs in it; otherwise (`--no-jail`) the person decides
(`output.confirm`).

What an extension adds reaches bh-02 as data over the worker's socket: a slash command, which
this registers in `commands` and runs by asking the worker; a status-bar field, pushed into
`frame` under the extension's own name; a section of the model's prompt, added to `system`; a
tool, whose spec this checks (`offered.offered_tool`) and registers in `tools` as running in the
runner, each call shown by its name and arguments and run by asking the worker, so the `approval`
rule decides each call as it does an input. Each is kept with its remover, and taken back when the
worker says so or the worker ends.

The model hears how each extension went in two places: its prompt (`section`, read per
request) and `status.json` in the extensions directory, written as soon as a load ends, so an
input can read it at once. The worker starts with the first extension there is to load; one that
ends (an extension may end it) takes every extension down with it, and they are loaded again,
in a new worker, at the next change in the directory. One `/release` stopped is not one that
failed: the row registers this worker's stop with the runner (`stopped`, its `on_release`), so
the paths its jail holds are free, and while the runner is `released` no worker starts until
something does: the next input's Python process, when every extension there is loads again, in a
new worker, with nothing changed; or a change to one of them, whose worker's start ends the
release.

The model writes the extensions directory from the jail, and this reads it on the host, so it
follows no link there (`_opened`, `_read`, through `host_paths`): the directory is opened from
the project's root one name at a time, with `O_NOFOLLOW`, and a file is read only if the
descriptor it was opened as says it is a regular file with one name (`watch.refusal`), of at
most 256 KiB. A link, or a hard link, could otherwise hand
the model a file the jail hides (`local.env`), as an extension's source, or as the line of its
SyntaxError in status.json. status.json is written through the same descriptor, as a new file
renamed over the old, so a link there leads no write elsewhere either.
"""

import asyncio
import contextlib
import functools
import importlib.util
import itertools
import json
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from sys import executable
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from extensions_cordis_plugin.offered import RESERVED, offered_tool, shown_tool_call
from extensions_cordis_plugin.watch import (
    Status,
    changes,
    extension_name,
    instructions,
    linked,
    refusal,
    status_file,
    status_forms,
    too_large,
)
from host_paths import Link, Linked, NotOneFile, TooLarge, directory_beneath, read_beneath

__all__ = [
    "Commands",
    "Confirm",
    "Extensions",
    "ExtensionsConfig",
    "Frame",
    "Rule",
    "Runner",
    "System",
    "Tools",
    "worker_argv",
]

_WORKER = Path(__file__).with_name("worker.py")
_LINE_LIMIT = 1 << 20  # the worker caps each text it sends at 20,000 characters, as the kernel does
_ANSWER_S = 30.0  # a load's answer: the worker waits up to 10 s for an extension's rows to come up
_STATUS = "status.json"
_FIELD = "extensions"
_ENDED = (
    "the extensions process ended (an extension may have ended it, or the jail did); change a "
    "file in the extensions directory to load them all again"
)
_SOURCE_LIMIT = 256 * 1024  # an extension larger than this is not read (the worker's line holds it)
_NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC  # status.json's next

_RELEASED = (
    "/release stopped the extensions process; every extension loads again, in a new one, once "
    "something starts in the runner again (the next input) or one of them changes"
)


@runtime_checkable
class _Jailed(Protocol):
    """A program a jail started."""

    async def stop(self) -> None: ...


@runtime_checkable
class Runner(Protocol):
    """What the extensions need of the `runner` value (CONTRACTS.md: runner): their worker
    started, and whether `/release` has stopped what runs until the next start (`released`),
    when it waits rather than start again only to come back."""

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Jailed: ...
    def released(self) -> bool: ...


@runtime_checkable
class Commands(Protocol):
    """What the extensions need of the `commands` value: a registration and its remover. Never
    `claim`: a line prefix takes every line the person starts with it, so only a row in a layer
    may claim one, and nothing an extension sends is passed on as one."""

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

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]: ...


@runtime_checkable
class Tools(Protocol):
    """What the extensions need of the `tools` value (CONTRACTS.md: tools): a tool registered, and
    its remover back; and the tools registered, whose names are bh-02's own, not an extension's."""

    def register(
        self,
        spec: Mapping[str, Any],
        run: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
        *,
        runs: str = ...,
        show: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = ...,
    ) -> Callable[[], None]: ...
    def specs(self) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class Rule(Protocol):
    """What the extensions need of the `approval` value (CONTRACTS.md: approval): whether the
    runner confines what runs in it (which the model is told), and whether a load runs unasked."""

    @property
    def confined(self) -> bool: ...
    def unasked(self, request: Mapping[str, Any]) -> bool: ...


@runtime_checkable
class Confirm(Protocol):
    """What the extensions need of the `output` value: the person's yes or no about a load the
    rule does not let run unasked."""

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
    """Something an extension added to bh-02: whose, what kind (`command`, `tool`, ...), what
    (`/todo`, a field, a tool's name), and its remover (None when bh-02 refused it)."""

    extension: str
    kind: str
    label: str
    remove: Callable[[], None] | None


class _Gone(Exception):
    """The worker is not there to answer: it would not start, or it ended."""


class _Refused(Exception):
    """bh-02 does not read what the model wrote there (a link, a hard link), and says why."""


def worker_argv(endpoint: str) -> list[str]:
    """The worker, run by path under this interpreter, isolated (-I: no PYTHON* env, no cwd on path)."""
    return [executable, "-I", str(_WORKER), endpoint]


class Extensions:
    """The model's extensions: loaded from the extensions directory into a jailed worker, and
    what they add put into bh-02. An async context manager: entering starts watching, leaving
    stops it, takes back everything the extensions added and stops the worker."""

    def __init__(
        self,
        runner: Runner,
        commands: Commands,
        frame: Frame,
        system: System,
        tools: Tools,
        approval: Rule,
        output: Confirm,
        config: ExtensionsConfig,
    ) -> None:
        self._runner = runner
        self._tools = tools
        self._output = output
        self._commands = commands
        self._frame = frame
        self._system = system
        self._approval = approval
        self._config = config
        self._statuses: dict[str, Status] = {}
        self._seen: dict[str, tuple[int, int]] = {}  # each file as last loaded: (mtime_ns, size)
        self._halted: dict[str, tuple[int, int]] | None = None  # the directory when the worker ended
        self._ended = False  # the worker ended (or `/release` kept one from starting) since the last look
        self._waiting = False  # `/release` stopped the worker: all load again once the runner starts again
        self._at_release: dict[str, tuple[int, int]] = {}  # the directory when `/release` stopped it
        self._leaving = False
        self._entries: dict[int, _Entry] = {}
        self._own_tools: set[str] = set()  # the tools the extensions registered, by name
        self._reserved: set[str] = set(RESERVED)  # every tool name a row of bh-02's own registered
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
        self._refused = ""  # why nothing loads from the extensions directory: a link on the way
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
        (`statuses`, taken in one step) and nothing that needs the event loop (`confined` reads
        the runner's report, a value)."""
        return instructions(
            self._config.path, self._approval.confined, self.statuses, self._reference, self._refused
        )

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

    async def stopped(self) -> str:
        """`/release`: stop the worker, and take back what the extensions added with it, so the
        runner can let go of what its jail holds on the host; every extension loads again, in a
        new worker, once something starts in the runner or one of them changes (`look`)."""
        if self._process is None and self._writer is None:
            return ""
        await self._stop()
        found = self._found()
        self._ended, self._waiting, self._at_release = False, True, dict(found)
        self._statuses = {name: Status(error=_RELEASED) for name in found}
        self._publish()
        return (
            "The extensions process is stopped, and what the extensions added with it: they load "
            "again once something starts in the runner (the next input) or one of them changes."
        )

    async def look(self) -> None:
        """Look at the extensions directory once: load what is new or changed, unload what is
        gone. The watcher does this every `watch` seconds."""
        self._note_reserved()
        found = self._found()
        if self._ended:
            self._stopped(found)
            return
        resumed = self._waiting
        if self._waiting:
            if self._runner.released() and found == self._at_release:
                return  # until something starts in the runner, or the model changes one of them
            # a new worker, whose start ends the release if nothing else's has: all load again
            self._waiting, self._seen, self._statuses = False, {}, {}
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
            if self._ended:  # this one ended the worker, or none may start: the rest wait
                self._stopped(found)
                return
        if load or unload or resumed:
            self._publish()

    def _stopped(self, found: Mapping[str, tuple[int, int]]) -> None:
        """The worker ended, or none could start: say so for every extension there is. When the
        runner is `released` (`/release` stopped what runs in it), every one loads again once
        something starts in it (`look`); otherwise nothing loads until the directory differs
        from `found`, so an extension that ends the worker as it loads is not loaded again and
        again."""
        self._ended = False
        if self._runner.released():
            self._waiting, self._at_release = True, dict(found)
            self._statuses = {name: Status(error=_RELEASED) for name in found}
        else:
            self._halted = dict(found)
            self._statuses = {name: Status(error=_ENDED) for name in found}
        self._publish()

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(self._config.watch)
            await self.look()

    def _found(self) -> dict[str, tuple[int, int]]:
        """Each extension file in the extensions directory, by name, with its stamp (mtime, size)
        as it is there: a link's own, not what it leads to (`_load` refuses one, and says why).
        Nothing when there is no directory, or when the way to it has a link (`_refused` says
        so, in the model's prompt: nothing is written through the link, status.json included)."""
        found: dict[str, tuple[int, int]] = {}
        self._refused = ""
        try:
            with self._opened() as directory, os.scandir(directory) as entries:
                for entry in entries:
                    if (name := extension_name(entry.name)) is None:
                        continue
                    with contextlib.suppress(OSError):  # gone since it was listed
                        if not entry.is_dir(follow_symlinks=False):
                            seen = entry.stat(follow_symlinks=False)
                            found[name] = (seen.st_mtime_ns, seen.st_size)
        except _Refused as refused:
            self._refused = str(refused)
        except OSError:
            pass
        return found

    @contextlib.contextmanager
    def _opened(self) -> Iterator[int]:
        """The extensions directory, opened from the project's root (the person's, so a link to
        it is theirs to follow) one name at a time, following no link
        (`host_paths.directory_beneath`): the descriptor it is listed, read and written through.
        Raises `_Refused` when a name on the way (`.bh-02`, the directory itself) is a link, and
        OSError when there is no such directory."""
        try:
            with directory_beneath(Path(self._config.root).resolve(), Path(self._config.path).parts) as at:
                yield at
        except Linked as way:
            raise _Refused(linked(self._config.path, str(way.part))) from None

    def _read(self, name: str) -> str:
        """The extension `name`'s source, read from the descriptor it was opened as, beneath the
        root and following no link (`_opened`, then `host_paths.read_beneath`), and only when
        that descriptor says it may be (`refusal`): so a file swapped for a link after it was
        found, or as it is opened, is not read. Raises `_Refused` with why it is not read, or
        OSError, or UnicodeDecodeError."""
        file = f"{name}.py"
        shown = str(Path(self._config.path) / file)
        with self._opened() as directory:
            try:
                found = read_beneath(directory, [file], cap=_SOURCE_LIMIT)
            except NotOneFile as error:
                raise _Refused(refusal(shown, error.mode, error.names) or str(error)) from None
            except TooLarge:
                raise _Refused(too_large(shown, _SOURCE_LIMIT)) from None
        if isinstance(found, Link):
            raise _Refused(refusal(shown, stat.S_IFLNK, 1))
        return found.decode("utf-8")

    # -- one extension ---------------------------------------------------------------------

    async def _load(self, name: str) -> None:
        path = self.directory / f"{name}.py"
        try:
            source = self._read(name)
        except _Refused as refused:
            await self._unload(name)  # what an earlier version added goes; this one is not read
            self._statuses[name] = Status(error=str(refused))
            return
        except OSError, UnicodeDecodeError:
            await self._unload(name)
            self._statuses[name] = Status(error=f"bh-02 could not read {path} as UTF-8 text")
            return
        if not await self._approved(name, source):
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
            self._ended = self._ended or self._runner.released()  # `/release`: all wait for a start
            return
        error = answer.get("error")
        rows = answer.get("rows") or {}
        self._statuses[name] = Status(
            rows={str(row): str(state) for row, state in rows.items()},
            error=None if error is None else str(error),
            commands=tuple(
                e.label for e in self._entries.values() if e.extension == name and e.kind == "command"
            ),
            tools=tuple(
                e.label
                for e in self._entries.values()
                if e.extension == name and e.kind == "tool" and e.remove is not None
            ),
            problems=tuple(self._problems.get(name, ())),
        )

    async def _approved(self, name: str, source: str) -> bool:
        """Whether an extension may load: at once when the `approval` rule says it runs unasked
        (the runner confines it); else the model's code would run with the person's permissions,
        so they are asked (`output.confirm`)."""
        request = {
            "name": "extension",
            "title": f"Load the model's extension {name} into bh-02, unjailed?",
            "input": {"code": source},
        }
        return self._approval.unasked(request) or await self._output.confirm(request)

    async def _unload(self, name: str) -> None:
        self._statuses.pop(name, None)
        self._problems.pop(name, None)
        if self._writer is not None:
            with contextlib.suppress(_Gone):
                await self._ask(name, {"op": "unload", "name": name})

    def _publish(self) -> None:
        """Tell the model (status.json) and the person (the status bar) how the extensions are.
        status.json is written through the directory opened following no link (`_opened`), as a
        new file renamed over the old: a link the model left (status.json itself, or a name on
        the way to it) leads no write elsewhere, and an input never reads half of one."""
        text = (json.dumps(status_file(self._statuses), indent=2) + "\n").encode("utf-8")
        with contextlib.suppress(OSError, _Refused), self._opened() as directory:
            fresh = f".{_STATUS}.{uuid.uuid4().hex}"
            descriptor = os.open(fresh, _NEW, 0o666, dir_fd=directory)
            try:
                with open(descriptor, "wb") as written:
                    written.write(text)
                os.replace(fresh, _STATUS, src_dir_fd=directory, dst_dir_fd=directory)
            except OSError:
                os.unlink(fresh, dir_fd=directory)
                raise
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
                    remove = self._system.add(f"extensions: {extension}", lambda: text)
                case "tool":
                    sent = message.get("spec")
                    name = str(sent.get("name")) if isinstance(sent, Mapping) else "?"
                    label = f"the tool {name!r}"
                    remove = self._tool(entry, extension, sent)
                    label = name  # registered: status.json lists it by name
                case _:  # a line prefix among them: only a layer's row may claim one
                    raise ValueError(
                        "an extension adds a slash command, a status field, a prompt section or a "
                        "tool, and nothing else"
                    )
        except Exception as error:  # bh-02 refused it: a command name another row has, say
            self._problems.setdefault(extension, []).append(f"{label} was not added: {error}")
        self._entries[entry] = _Entry(extension, str(kind), label, remove)

    def _tool(self, entry: int, extension: str, sent: object) -> Callable[[], None]:
        """Register a tool an extension sent, once its spec passes (`offered_tool`: a name of its
        own, not bh-02's, a JSON Schema, a size cap), as running in the runner: the `approval`
        rule decides each call as it does an input, and a call is shown by its name and
        arguments. Returns its remover. Raises ValueError saying why bh-02 refused it."""
        self._note_reserved()
        spec = offered_tool(sent, self._reserved)
        name = spec["name"]
        unregister = self._tools.register(
            spec,
            functools.partial(self._call, entry),
            runs="jail",
            show=functools.partial(shown_tool_call, extension, name),
        )
        self._own_tools.add(name)

        def remove() -> None:
            self._own_tools.discard(name)
            unregister()

        return remove

    def _note_reserved(self) -> None:
        """Keep every tool name a row of bh-02's own has registered as bh-02's, for good: an
        extension can't take it while that row restarts."""
        self._reserved |= {str(spec.get("name")) for spec in self._tools.specs()} - self._own_tools

    async def _call(self, entry: int, input: Mapping[str, Any]) -> dict[str, Any]:
        """A call to a tool an extension registered (CONTRACTS.md: tools, `run`): run in the
        worker, its answer what the model reads."""
        call = next(self._call_ids)
        answer: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._calls[call] = answer
        try:
            self._send({"op": "call", "call": call, "tool": entry, "input": dict(input)})
            return {"content": await answer}
        except _Gone as gone:
            return {"content": f"error: {gone}"}
        finally:
            self._calls.pop(call, None)

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
            raise _Gone(f"the extensions process did not answer within {_ANSWER_S:.0f} s") from None
        finally:
            self._answers.pop(name, None)

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._writer is None:
            raise _Gone(_ENDED)
        self._writer.write((json.dumps(message) + "\n").encode("utf-8"))

    async def _start(self) -> None:
        """Start the worker in the runner, unless it is running. A start ends a release
        (`look` starts one while released only for a change the person or the model made)."""
        if self._writer is not None:
            return
        if self._process is not None:  # what is left of a worker that ended: its jail's teardown
            await self._stop()
        # A Unix socket path must fit in about 100 bytes, so it lives in a short directory of its own.
        self._socket_dir = tempfile.mkdtemp(prefix="bh-x-", dir="/tmp")
        endpoint = str(Path(self._socket_dir) / "x.sock")
        root = str(Path(self._config.root).resolve())
        try:
            self._process = await self._runner.start(worker_argv(endpoint), cwd=root, endpoint=endpoint)
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
