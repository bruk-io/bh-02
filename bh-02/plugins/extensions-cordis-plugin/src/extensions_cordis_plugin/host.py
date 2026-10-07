"""The `extensions` row's value: the model's own plugins, loaded into bh-02 while it runs.

The model writes a module of cordis components into the project's extensions directory
(`.bh-02/plugins/NAME.py`); this notices (it looks every `watch` seconds), and loads it into a
worker the `jail` row starts (`worker.py`), so the model's code runs as confined as its inputs
do, never in bh-02's own process. A changed file is loaded afresh, a deleted one unloaded.
Each load is put to `approval` first, with the source, exactly as an input is: at once when the
jail confines what runs in it; otherwise (`--no-jail`) the person decides.

What an extension adds reaches bh-02 as data over the worker's socket: a slash command, which
this registers in `commands` and runs by asking the worker; a status-bar field, pushed into
`frame` under the extension's own name; a section of the model's prompt, added to `system`.
Each is kept with its remover, and taken back when the worker says so or the worker ends.

The model hears how each extension went in two places: its prompt (`section`, read per
request) and `status.json` in the extensions directory, written as soon as a load ends, so an
input can read it at once. The worker starts with the first extension there is to load; one that
ends (an extension may end it) takes every extension down with it, and they are loaded again,
in a new worker, at the next change in the directory. One `/release` stopped (the jail stops
every program it started, so the paths their jails hold are free) is not one that failed: while
the jail is `released` no worker starts, whatever changes, and once the next input has started
the kernel every extension there is loads again, in a new worker, with nothing changed.

The model writes the extensions directory from the jail, and this reads it on the host, so it
follows no link there (`_opened`, `_read`): the directory is opened from the project's root one
name at a time, with `O_NOFOLLOW`, and a file is read only if the descriptor it was opened as says
it is a regular file with one name (`watch.refusal`). A link, or a hard link, could otherwise hand
the model a file the jail hides (`local.env`), as an extension's source, or as the line of its
SyntaxError in status.json. status.json is written through the same descriptor, as a new file
renamed over the old, so a link there leads no write elsewhere either.
"""

import asyncio
import contextlib
import errno
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

from extensions_cordis_plugin.watch import (
    Status,
    changes,
    extension_name,
    instructions,
    linked,
    refusal,
    status_file,
    status_forms,
)

__all__ = [
    "Approval",
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
# How the extensions directory is opened beneath the root, a name at a time, and an extension in
# it: following no link, and never waiting on a FIFO the model left in a file's place.
_ROOT = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
_DIRECTORY = _ROOT | os.O_NOFOLLOW | os.O_NONBLOCK
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC  # status.json's next

_RELEASED = (
    "/release stopped the extensions' worker; every extension loads again, in a new one, once the "
    "next input has started the kernel"
)


@runtime_checkable
class _Jailed(Protocol):
    """A program a jail started."""

    async def stop(self) -> None: ...


@runtime_checkable
class Jail(Protocol):
    """What the extensions need of the `jail` value (CONTRACTS.md: jail): their worker started,
    and whether `/release` has stopped the jail's programs until the next input (`released`),
    when it must not start again."""

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

    def add(self, section: Callable[[], str]) -> Callable[[], None]: ...


@runtime_checkable
class Approval(Protocol):
    """What the extensions need of the `approval` value: whether the jail confines what runs in
    it (which the model is told), and whether an extension may load."""

    @property
    def confined(self) -> bool: ...
    async def approve(self, request: Mapping[str, Any]) -> bool: ...


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
        jail: Jail,
        commands: Commands,
        frame: Frame,
        system: System,
        approval: Approval,
        config: ExtensionsConfig,
    ) -> None:
        self._jail = jail
        self._commands = commands
        self._frame = frame
        self._system = system
        self._approval = approval
        self._config = config
        self._statuses: dict[str, Status] = {}
        self._seen: dict[str, tuple[int, int]] = {}  # each file as last loaded: (mtime_ns, size)
        self._halted: dict[str, tuple[int, int]] | None = None  # the directory when the worker ended
        self._ended = False  # the worker ended (or `/release` kept one from starting) since the last look
        self._waiting = False  # `/release` stopped the worker: all load again once the jail runs again
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
        the jail's report, a value)."""
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

    async def look(self) -> None:
        """Look at the extensions directory once: load what is new or changed, unload what is
        gone. The watcher does this every `watch` seconds."""
        found = self._found()
        if self._ended:
            self._stopped(found)
            return
        resumed = self._waiting
        if self._waiting:
            if self._jail.released():
                return  # until the next input has started the kernel, no worker starts
            self._waiting, self._seen, self._statuses = False, {}, {}  # a new worker: all load again
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
        jail is `released` (`/release` stopped its programs), every one loads again once it runs
        again (`look`); otherwise nothing loads until the directory differs from `found`, so an
        extension that ends the worker as it loads is not loaded again and again."""
        self._ended = False
        if self._jail.released():
            self._waiting = True
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
        it is theirs to follow) one name at a time, following no link: the descriptor it is
        listed, read and written through. Raises `_Refused` when a name on the way (`.bh-02`, the
        directory itself) is a link, and OSError when there is no such directory."""
        at = os.open(Path(self._config.root).resolve(), _ROOT)
        try:
            way = Path()
            for name in Path(self._config.path).parts:
                way /= name
                try:
                    below = os.open(name, _DIRECTORY, dir_fd=at)
                except OSError:  # a link is ENOTDIR here, or ELOOP: which it was, for the model
                    if stat.S_ISLNK(os.stat(name, dir_fd=at, follow_symlinks=False).st_mode):
                        raise _Refused(linked(self._config.path, str(way))) from None
                    raise
                os.close(at)
                at = below
            yield at
        finally:
            os.close(at)

    def _read(self, name: str) -> str:
        """The extension `name`'s source, read from the descriptor it was opened as, beneath the
        root and following no link (`_opened`, then the file with `O_NOFOLLOW`), and only when
        that descriptor says it may be (`refusal`): so a file swapped for a link after it was
        found, or as it is opened, is not read. Raises `_Refused` with why it is not read, or
        OSError, or UnicodeDecodeError."""
        file = f"{name}.py"
        shown = str(Path(self._config.path) / file)
        with self._opened() as directory:
            try:
                descriptor = os.open(file, _FILE, dir_fd=directory)
            except OSError as error:
                if error.errno == errno.ELOOP:  # O_NOFOLLOW's answer for a link
                    raise _Refused(refusal(shown, stat.S_IFLNK, 1)) from None
                raise
            with open(descriptor, "rb") as opened:
                found = os.fstat(opened.fileno())
                if (why := refusal(shown, found.st_mode, found.st_nlink)) is not None:
                    raise _Refused(why)
                return opened.read().decode("utf-8")

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
            self._ended = self._ended or self._jail.released()  # `/release`: all wait for the jail
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
        """Whether an extension may load (`approval`): at once when the jail confines it;
        unjailed, the model's code would run with the person's permissions, so they are asked."""
        return await self._approval.approve(
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
                    remove = self._system.add(lambda: text)
                case _:  # a line prefix among them: only a layer's row may claim one
                    raise ValueError(
                        "an extension adds a slash command, a status field or a prompt section, "
                        "and nothing else"
                    )
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
        """Start the worker in the jail, unless it is running, or `/release` has stopped the
        jail's programs until the next input (`jail.released()`, asked with nothing awaited
        between it and the start, which would end the release)."""
        if self._writer is not None:
            return
        if self._process is not None:  # what is left of a worker that ended: its jail's teardown
            await self._stop()
        if self._jail.released():
            raise _Gone(_RELEASED)
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
