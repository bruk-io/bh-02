"""The python tool's Python process: the host's end of the worker's socket, the process the
runner started, and the `python(code)` tool's call (`call`), which runs an input in it; the
python row registers that with `tools`.

An input is one request and one answer: the worker runs the code and says it is done. Whether
the person is asked first is the `approval` rule's to answer and the loop's to ask, so the
process depends on its runner alone and a new ui keeps the namespace. It reads `confined` from
that rule (`Rule`) only to decide what the model is told and whether the startup files run
unasked: one place decides what runs unasked. The python row starts and stops it, and on
`/release` stops it itself (`stopped`), so nothing else ever ends it. Every failure the process knows of (a
worker that died, an answer too long or garbled to read, a worker that won't start again)
comes back as the input's text, never as an exception. Interrupting an input (cancelling `run`) sends SIGINT
through the jail, which the worker turns into `KeyboardInterrupt` in the input, and waits for the
input to say it ended: the namespace survives. A worker that dies is started again on the next
input, and that input is told its earlier variables are gone, and why, when the jail ended it.
After each input, `touched()` is the project's files it opened, read or written (the worker's
audit hook): what a `notes` function is given to say what applies to them.

bh-02's other tools are functions in the namespace (`tools.NAME(...)`): each input carries their
specs, read from `tools` as it is sent, and the worker rebuilds `tools` from them; a call one
makes comes back here and goes to `tools.call`, which runs it as the model's own calls run
(the loop serves it: asked about, noted). The namespace is a view of the registry, never where a
tool is registered. What changed in it since the model was last told is told before the input's
own output (`_offered`).

A new Python process runs its startup files before its first input (`KernelConfig.startup`), when its
inputs are confined: the person's own (`$XDG_CONFIG_HOME/bh-02/kernel.py`, else
`~/.config/bh-02/kernel.py`), then the project's (`.bh-02/kernel.py`). The project's is read by
the worker, in the jail, which decides: the model can write it, and a link there could lead to a
file the jail hides. The person's is outside the project, where a Linux jail (which reads by
allowlist, the home directory absent) can't see it, so the host reads it and sends its source;
but only when reading it goes nowhere an input may write (`host_paths.walked`, the walk the
models file and memory files outside the project are held to: no directory or link on the way
is in the project, or in another root the worker's jail lets an input write, its `writes()`).
One that is there, or whose way passes through there, the worker reads, as it does the
project's, and if that fails the note says why the host did not; it is still the person's, not
the model's to edit, which is what the model is told. (The jail also keeps an input from
writing in the person's config directory, so a session run from the home directory can't
choose what a later one reads there: brig's `trusted`.) A startup file that ends the worker is
passed over by the workers after it, until `/restart python`, and the input it cut short says
which it was, after what the opening had to tell by then (that the worker was started again,
and why).
"""

import asyncio
import contextlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from sys import executable
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from host_paths import config_home, walked
from python_cordis_plugin.python import PYTHON, instructions_for

__all__ = ["Access", "Jailed", "Kernel", "KernelConfig", "Rule", "Runner", "worker_argv"]

_WORKER = Path(__file__).with_name("worker.py")
# The longest line the worker sends: its output and its error are capped at 20,000 characters
# each, and JSON escapes a character to at most 12 bytes (a surrogate pair, `\ud83d\ude00`),
# so a `done` is under 500 KB. asyncio's default of 64 KiB would fail on 20,000 emoji.
_LINE_LIMIT = 1 << 20
_CONFIG_HOME = "$XDG_CONFIG_HOME/"  # a startup file in the person's config directory


@runtime_checkable
class Jailed(Protocol):
    """A program a jail started: it can be interrupted and stopped, and says why, when the jail
    ended it itself (`ended`: a Linux `runner:confined` whose hold on a path the host undid; "" when
    it did not), and what its start is (`report`, `notice`, `reads`, `writes`: this program's
    jail's, whatever else the jail starts)."""

    def interrupt(self) -> bool: ...
    def ended(self) -> str: ...
    async def stop(self) -> None: ...
    def report(self) -> Mapping[str, str]: ...
    def notice(self) -> str: ...
    def reads(self) -> tuple[str, ...]: ...
    def writes(self) -> tuple[str, ...]: ...


@runtime_checkable
class Access(Protocol):
    """What the Python process needs of the `access` value (CONTRACTS.md: access): the kinds of opening
    some row is asked about, and its answer about one file, called off the event loop."""

    def asking(self) -> tuple[str, ...]: ...
    def refusal(self, kind: str, path: str) -> str | None: ...


@runtime_checkable
class Runner(Protocol):
    """What the Python process needs of the `runner` value (CONTRACTS.md: runner): its start,
    and the runner's own grades before any."""

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Jailed: ...
    def report(self) -> Mapping[str, str]: ...


@runtime_checkable
class Calls(Protocol):
    """What the Python process needs of the `tools` value (CONTRACTS.md: tools): the tools there
    are, offered to an input as functions, and a call one makes run as the model's own are."""

    def specs(self) -> Sequence[Mapping[str, Any]]: ...
    async def call(self, name: str, input: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class Rule(Protocol):
    """What the Python process needs of the `approval` value (CONTRACTS.md: approval): whether
    the runner confines its inputs, so none is asked about."""

    @property
    def confined(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class KernelConfig:
    """`root` is the working directory inputs run in; `grace` how long an interrupted input gets
    to say it ended before the worker is stopped and started again; `startup` the files a new
    kernel runs, in order, before its first input, when its inputs are confined: helpers kept
    across sessions. The person's own first (`$XDG_CONFIG_HOME/` is their config directory: that
    variable's value, else `~/.config`, as for the models file; `~/` is their home), then the
    project's (a relative name is from `root`), the one the model may write. A single string is
    one file."""

    root: str = "."
    grace: float = 5.0
    startup: Sequence[str] = ("$XDG_CONFIG_HOME/bh-02/kernel.py", ".bh-02/kernel.py")

    def __post_init__(self) -> None:
        names = (self.startup,) if isinstance(self.startup, str) else self.startup
        if not isinstance(names, Sequence) or not all(isinstance(name, str) for name in names):
            raise TypeError(
                "`startup` must be a file name or a list of them, as in "
                '`startup = ["$XDG_CONFIG_HOME/bh-02/kernel.py", ".bh-02/kernel.py"]`, '
                f"not {self.startup!r}"
            )


@dataclass(frozen=True, slots=True)
class _Startup:
    """A startup file as configured: `name`, how the model is told of it (the project's as
    configured, from the root; the person's by its absolute path), `path`, where it is, and
    whether it is the project's (named from the root), the model's to edit, rather than the
    person's (named from their config directory, their home or `/`). Whose it is is not where
    it is read: a person's file in the project is read in the jail all the same (`_ready`)."""

    name: str
    path: Path
    project: bool


@dataclass(frozen=True, slots=True)
class _Ready:
    """A startup file that is there: `name` as the model is told of it, `path` what the code
    that runs it opens, and `source`, its text when the host read it (None: the worker reads
    `path`, in the jail), or `problem`, why the host could not; `why`, when the worker reads a
    person's file, why the host did not (said if it then fails)."""

    name: str
    path: str
    source: str | None = None
    problem: str = ""
    why: str = ""


class _StartupEnded(ConnectionError):
    """The worker's process ended as the startup file `name` ran; `told`, what the opening had
    to tell before it (`_told`: the worker started again and why, the files before it), which
    the input it cut short still tells."""

    def __init__(self, name: str, told: str = "") -> None:
        super().__init__(f"the REPL's process ended as {name} ran")
        self.name = name
        self.told = told


@dataclass(frozen=True, slots=True)
class _Output:
    """What running one input produced: what it printed, the error it ended with, if any, the
    files it opened (absolute paths, each once), and what it was refused (`access`)."""

    output: str
    error: str | None = None
    touched: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()

    def text(self) -> str:
        """The input as the model reads it: a refusal last, each in brackets, so it is told
        whether or not the input's code caught the error it raised."""
        parts = [self.output.rstrip("\n")] if self.output.strip() else []
        if self.error:
            parts.append(self.error)
        parts += [f"({refused})" for refused in self.refused]
        return "\n".join(parts) or "(no output)"


def _told(notes: Sequence[str]) -> str:
    """What an input is told before its own output: `notes`, in one parenthesis on a line of its
    own; "" for none."""
    return f"({'. '.join(notes)})\n" if notes else ""


def _startup_input(path: str, source: str | None = None) -> str:
    """The input that runs a startup file in the namespace and prints, last and on a line of its
    own, the public names it defined or bound afresh ("nothing" for none): each its code stores
    at the top (as the compiler says: the same object bound again counts) or that is new or
    changed after it. `source` is its text when the host read it (the person's own, which a jail
    that reads by allowlist can't see), registered with `linecache` under `path` so a traceback
    shows its lines; without it the worker reads `path` itself, in the jail. Either way a UTF-8
    byte order mark is no part of it. The input's own names are gone after it, however it ends."""
    read = (
        [
            f"    _bh_source = {source!r}",
            "    import linecache as _bh_lines",
            f"    _bh_lines.cache[{path!r}] = (len(_bh_source), None, _bh_source.splitlines(True), {path!r})",
        ]
        if source is not None
        else [
            "    import pathlib as _bh_path",
            f"    _bh_source = _bh_path.Path({path!r}).read_text(encoding='utf-8-sig')",
        ]
    )
    return "\n".join(
        [
            "_bh_before = dict(globals())",
            "try:",
            *read,
            f"    _bh_code = compile(_bh_source, {path!r}, 'exec')",
            "    exec(_bh_code, globals())",
            "    import dis as _bh_dis",
            "    _bh_bound = {i.argval for i in _bh_dis.get_instructions(_bh_code)"
            " if i.opname == 'STORE_NAME'}",
            "    print('\\n' + (', '.join(sorted(n for n, v in globals().items() if not n.startswith('_')"
            " and (n in _bh_bound or n not in _bh_before or _bh_before[n] is not v))) or 'nothing'))",
            "finally:",
            "    for _bh_name in ('_bh_before', '_bh_source', '_bh_code', '_bh_bound', '_bh_path',"
            " '_bh_lines', '_bh_dis', '_bh_name'):",
            "        globals().pop(_bh_name, None)",
        ]
    )


def _located(name: str, root: Path, home: Path, environ: Mapping[str, str]) -> Path:
    """Where the startup file `name` is: one starting `$XDG_CONFIG_HOME/` in the person's config
    directory (`host_paths.config_home`: that variable's value, else `home`'s `.config`, as the
    models file is; a relative value counts as unset), one starting `~/` in `home`, and any other
    from the project's `root` (an absolute one is itself)."""
    if name.startswith(_CONFIG_HOME):
        return config_home(environ, home) / name.removeprefix(_CONFIG_HOME)
    return home / name[2:] if name == "~" or name.startswith("~/") else root / name


def _placed(names: Sequence[str], root: Path, home: Path, environ: Mapping[str, str]) -> tuple[_Startup, ...]:
    """The startup files `names` (`KernelConfig.startup`; a string is one) name, in order, each
    where it is (from the absolute `root`) and whether it is the project's: named from the root,
    not from the person's config directory, their home or `/`."""
    listed = (names,) if isinstance(names, str) else tuple(names)
    placed = []
    for name in listed:
        path = Path(os.path.normpath(_located(name, root, home, environ)))
        project = not (name.startswith(("/", "~/", _CONFIG_HOME)) or name == "~")
        placed.append(_Startup(name if project else str(path), path, project))
    return tuple(placed)


def worker_argv(endpoint: str) -> list[str]:
    """The worker, run by path under this interpreter, isolated (-I: no PYTHON* env, no cwd on path)."""
    return [executable, "-I", str(_WORKER), endpoint]


def _inside(paths: Sequence[str], root: str) -> tuple[str, ...]:
    """Those of `paths` that are under `root` (absolute), normalised (`a/../b` is `b`), in order.
    The worker is the model's process, so these are what it says it opened, not proof: a reader
    may match them against files it chose, never open one because it is named here."""
    under = root.rstrip(os.sep) + os.sep
    return tuple(p for p in map(os.path.normpath, paths) if p.startswith(under))


class Kernel:
    """The Python process: a persistent namespace, and the `python` tool's call (`call(input)`,
    over `run(code)`) and what the model is told about it (`instructions()`). An async context
    manager: entering starts the worker in the runner, leaving stops it."""

    def __init__(
        self,
        runner: Runner,
        config: KernelConfig,
        access: Access | None = None,
        *,
        rule: Rule,
        tools: Calls | None = None,
    ) -> None:
        self._runner = runner
        self._rule = rule
        self._tools = tools  # bh-02's other tools, offered to an input as functions
        self._told_tools: dict[str, str] | None = None  # what the model was last told of them
        self._config = config
        self._access = access  # asked before an input opens a project file, for what it asks about
        self._lock = asyncio.Lock()
        self._dir: str | None = None
        self._process: Jailed | None = None
        # the last worker this python row started, kept once it has stopped: what its jail is (`reads`,
        # `notice`, `report`, `writes`) is this row's, never another program's of the same jail,
        # and stays what the model was told until a new worker starts
        self._worker: Jailed | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._restarted = False  # a worker started again, not the row's first
        self._fresh = False  # a worker no input has run in yet
        self._why = ""  # why the jail ended the last worker itself, told with the restart
        self._touched: tuple[str, ...] = ()  # the project's files the last input opened
        self._passed: dict[str, str] = {}  # startup files later workers pass over, and why
        self._pending = ""  # what the next input is told of an opening cut short (Ctrl-C)

    @property
    def confined(self) -> bool:
        """Whether the runner confines its inputs, so none is asked about: the `approval` rule's."""
        return self._rule.confined

    def report(self) -> Mapping[str, str]:
        """The grades of the jail the worker runs in (before any worker, the jail's own)."""
        return self._worker.report() if self._worker is not None else self._runner.report()

    def notice(self) -> str:
        """What the person should know about the jail the worker runs in ("" when nothing)."""
        return self._worker.notice() if self._worker is not None else ""

    def reads(self) -> tuple[str, ...]:
        """The trees an input can read, when the worker's jail reads by allowlist; empty when it
        reads everything but what it hides (or is no jail at all)."""
        return self._worker.reads() if self._worker is not None else ()

    def instructions(self) -> str:
        """What the model is told about the tool and where its code runs, read per request: the
        project's startup files are the model's to edit, the person's are theirs; and where its
        worker's jail lets it write besides the project (its `writes()`: the auto memory
        directory, a `write` the person added)."""
        root = Path(self._config.root).resolve()
        placed = _placed(self._config.startup, root, Path.home(), os.environ)
        writes = self._worker.writes() if self._worker is not None else ()
        return instructions_for(
            self.confined,
            tuple(s.name for s in placed if s.project),
            self.reads(),
            theirs=tuple(s.name for s in placed if not s.project),
            elsewhere=tuple(w for w in writes if not Path(w).is_relative_to(root)),
        )

    async def __aenter__(self) -> Kernel:
        await self._start()
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self._stop()

    async def call(self, input: Mapping[str, Any]) -> dict[str, Any]:
        """One call of the `python` tool (CONTRACTS.md: tools): its `code` run as an input,
        answered with what the model reads (`content`) and the files under the root it opened
        (`touched`, as `touched()` gives them). A call with no `code` string runs nothing and
        says why."""
        code = input.get("code")
        if not isinstance(code, str):
            return {"content": f"error: {PYTHON['name']} takes `code`, the Python to run, as a string"}
        content = await self.run(code)
        return {"content": content, "touched": list(self._touched)}

    async def run(self, code: str) -> str:
        """Run one input and return it as the model reads it: what it printed and its error."""
        self._touched = ()
        ran = await self._execute(code)
        self._touched = _inside(ran.touched, str(Path(self._config.root).resolve()))
        return ran.text()

    def touched(self) -> tuple[str, ...]:
        """The files under the root the last input opened with `open` or `pathlib`, read or
        written: absolute paths, each once, in the order first opened, at most 1,000. Not a file
        a program it ran opened (`cat x` through subprocess), a module it imported, an `os.open`
        (`shutil.rmtree` opens by names relative to a directory), nor a source file its
        traceback was formatted from. Empty before any input, and after one that did not run to
        the end."""
        return self._touched

    async def stopped(self) -> str:
        """`/release` (the python row registers it with the runner): end the worker now, so the
        runner can let go of what its jail holds on the host, and say so ("" when none ran). The
        next input starts a new worker, told its earlier variables are gone. An input that is
        running is left to finish, nothing ends, and the answer says so."""
        if self._lock.locked():
            return "An input is running: stop the reply (Ctrl-C), then /release again."
        async with self._lock:
            had = self._process is not None
            await self._stop()
        if not had:
            return ""
        return "The Python process is stopped; the next input starts it again, without the earlier variables."

    async def _execute(self, code: str) -> _Output:
        async with self._lock:
            if self._reader is not None and (self._reader.at_eof() or self._ended()):
                # the worker ended between inputs (its jail ended it): start it again for this one.
                # The jail may say so before the socket's end has reached this event loop, and an
                # input sent then would go to the worker that ended
                self._why = self._ended()
                await self._stop()
            if self._writer is None:
                try:
                    await self._start()
                except Exception as error:  # the jail would not start it: the input says so
                    await self._stop()
                    return _Output(
                        "",
                        f"error: the REPL could not be started again ({error}), so this input did "
                        "not run; the next input tries again, and if it keeps failing, tell the "
                        "person (`/restart python` starts the row afresh)",
                    )
                self._restarted = True
            prefix, self._pending = (f"({self._pending})\n" if self._pending else ""), ""
            try:
                if self._fresh:
                    # never twice in one worker: an opening stopped part-way (Ctrl-C) is not rerun
                    self._fresh = False
                    prefix, self._restarted = prefix + await self._opening(), False
                prefix += self._offered()
                ran = await self._exchange(code)
            except ConnectionError as error:
                why = self._ended()
                await self._stop()
                said = f" because {why}" if why else ""
                if isinstance(error, _StartupEnded):
                    return _Output(
                        prefix + error.told,
                        f"the REPL's process ended as {error.name} ran, before this input{said}, so this "
                        f"input did not run; a new one starts with the next, without {error.name} "
                        "(`/restart python` runs it again)",
                    )
                return _Output(
                    prefix,
                    f"the REPL's process ended during this input{said}; a new one starts with the next",
                )
            except ValueError as error:
                # a line over the limit, or one that is not JSON: what follows can't be trusted
                # to line up with an input, so the worker is replaced rather than read on
                await self._stop()
                return _Output(
                    prefix,
                    f"error: the REPL's answer to this input could not be read ({error}); a new "
                    "REPL starts with the next input, without the earlier variables",
                )
            return _Output(prefix + ran.output, ran.error, ran.touched, ran.refused) if prefix else ran

    async def _opening(self) -> str:
        """What a new Python process's first input is told before its own output, when there is anything
        to tell: that the worker was started again, and what the startup files did. Jailed, each
        runs here, in order, whether or not the one before failed; unjailed, they would run
        unasked with the person's permissions, so the model is told to run them as an input of
        its own. A file that ends the worker, or is stopped, cuts it short, and what it had to
        tell by then goes with that (`_StartupEnded.told`, `_pending`): the reason taken from
        `_why` is told nowhere else."""
        why, self._why = (f", because {self._why}" if self._why else ""), ""
        notes = (
            [f"the REPL was started again{why}; what earlier inputs defined is gone"]
            if self._restarted
            else []
        )
        confined = self.confined
        try:
            ready = await asyncio.to_thread(self._ready, confined)
        except Exception as error:  # the input still runs, and says why its helpers are missing
            ready = []
            notes.append(f"the startup files could not be looked at ({error}), so none ran")
        if ready and not confined:
            one = len(ready) == 1
            runs = "; ".join(f"exec(open({r.path!r}).read())" for r in ready)
            notes.append(
                f"{' and '.join(r.name for r in ready)} {'was' if one else 'were'} not run: inputs here "
                f"are put to the person, so run {'it' if one else 'them'} as an input of your own if you "
                f"want {'it' if one else 'them'}: {runs}"
            )
        for index, startup in enumerate(ready if confined else ()):
            if startup.name in self._passed:
                notes.append(
                    f"{startup.name} was not run: {self._passed[startup.name]} when it last ran, so what "
                    "it defines is missing (`/restart python` runs it again)"
                )
                continue
            if startup.problem:
                notes.append(
                    f"{startup.name} could not be read ({startup.problem}), so what it defines is missing"
                )
                continue
            try:
                ran = await self._exchange(_startup_input(startup.path, startup.source))
            except ConnectionError:
                self._passed[startup.name] = "it ended the REPL's process"
                raise _StartupEnded(startup.name, _told(notes)) from None
            except asyncio.CancelledError:
                if self._writer is None:  # it would not stop: the next worker would only run it again
                    self._passed[startup.name] = "it would not stop at Ctrl-C"
                else:  # the worker carries on, without the files again: its next input is told
                    self._pending = ". ".join(
                        [
                            *notes,
                            f"{startup.name} was stopped as it ran, so what it defines may be missing, "
                            "and no startup file after it ran",
                        ]
                    )
                raise
            when = "first" if index == 0 else "next"
            if ran.error:
                left = f" ({startup.why})" if startup.why else ""
                notes.append(
                    f"{startup.name} ran {when} and failed{left}, so what it defines is missing:\n{ran.error}"
                )
            else:
                lines = ran.output.strip().splitlines()
                notes.append(f"{startup.name} ran {when} and defined: {lines[-1] if lines else 'nothing'}")
        return _told(notes)

    def _ready(self, read: bool) -> list[_Ready]:
        """The startup files that are there, in order, each once (at its first place), and how
        each is run (in a worker thread: it looks at the filesystem). The project's is the
        worker's to read, in the jail. The person's, when reading it goes nowhere an input may
        write, the host reads (when `read`: inputs are confined, so it is about to run); one in
        the project or another root the worker's jail lets an input write (its `writes()`), or
        whose way passes through one, is read by the worker as the project's is."""
        given = Path(os.path.normpath(Path(self._config.root).absolute()))
        root = given.resolve()
        writes = self._worker.writes() if self._worker is not None else ()
        writable = (given, root, *(Path(w) for w in writes))
        ready: list[_Ready] = []
        seen: set[Path] = set()
        for startup in _placed(self._config.startup, root, Path.home(), os.environ):
            real = startup.path.resolve()
            if not startup.path.is_file() or real in seen:
                continue
            seen.add(real)
            way = (startup.path, *walked(startup.path))
            meets = next((r for p in way for r in writable if p.is_relative_to(r)), None)
            if startup.project:  # the worker reads it by its name, from the root it starts in
                ready.append(_Ready(startup.name, startup.name))
            elif meets is not None:
                # in the project, or reached through it or another root an input may write (bh-02
                # run from the home directory, a config directory linked into the project): the
                # model could have written it, or chosen where it leads, so the worker reads it,
                # where the jail can see it if anywhere
                inside = any(real.is_relative_to(r) for r in writable)
                why = f"its way passes through {meets}, where inputs can write, so bh-02 left it to the jail"
                ready.append(_Ready(startup.name, str(real if inside else startup.path), why=why))
            elif not read:
                ready.append(_Ready(startup.name, str(startup.path)))
            else:
                try:
                    source = startup.path.read_text(encoding="utf-8-sig")
                except FileNotFoundError:  # gone since it was looked at
                    continue
                except (OSError, UnicodeDecodeError) as error:
                    ready.append(_Ready(startup.name, str(startup.path), problem=str(error)))
                    continue
                ready.append(_Ready(startup.name, str(startup.path), source))
        return ready

    def _ended(self) -> str:
        """Why the jail ended the worker itself, or ""."""
        return self._process.ended() if self._process is not None else ""

    async def _exchange(self, code: str) -> _Output:
        asking = list(self._access.asking()) if self._access is not None else []
        self._send({"op": "exec", "code": code, "ask": asking, "tools": self._offered_specs()})
        try:
            return await self._until_done()
        except asyncio.CancelledError:
            await self._interrupt()
            raise

    async def _until_done(self) -> _Output:
        """Read the worker until the input ends, answering what it asks on the way: whether the
        input may open a file (`access.refusal`, in a thread: a row's answer may read files), and
        what a call to one of bh-02's tools answered (`tools.call`)."""
        while True:
            message = await self._receive()
            if message.get("op") == "ask":
                refusal = await self._refusal(message)
                self._send({"op": "answer", "id": message.get("id"), "refuse": refusal})
            elif message.get("op") == "call":
                answer = await self._called(message)
                self._send({"op": "answer", "id": message.get("id"), **answer})
            elif message.get("op") == "done":
                touched, refused = message.get("touched"), message.get("refused")
                return _Output(
                    str(message.get("output", "")),
                    message.get("error"),
                    tuple(str(p) for p in touched) if isinstance(touched, list) else (),
                    tuple(str(r) for r in refused) if isinstance(refused, list) else (),
                )

    async def _called(self, question: Mapping[str, Any]) -> dict[str, Any]:
        """A call the input made to one of bh-02's tools (`tools.NAME(...)`), run as the model's
        own calls are (`tools.call`): `{"content", "failed"}`. Never `python` itself, whose
        input this is (the worker's code is the model's to run, so what it sends is read as
        data)."""
        name, input = question.get("name"), question.get("input")
        if not isinstance(name, str) or not isinstance(input, Mapping):
            return {"content": "error: a call names a tool and gives its arguments by name", "failed": True}
        if name == PYTHON["name"] or self._tools is None:
            return {"content": f"error: there is no {name} tool to call from an input", "failed": True}
        answer = await self._tools.call(name, input)
        return {"content": str(answer.get("content", "")), "failed": bool(answer.get("failed"))}

    def _offered_specs(self) -> list[Mapping[str, Any]]:
        """bh-02's tools as an input is offered them: every one but `python`."""
        if self._tools is None:
            return []
        return [spec for spec in self._tools.specs() if spec.get("name") != PYTHON["name"]]

    def _offered(self) -> str:
        """What the model is told before an input's own output of bh-02's tools as functions in
        its namespace, when that changed since it was last told: which there are, the first
        time; then which were added, redefined or removed. "" when nothing changed."""
        now = {str(spec.get("name")): str(spec.get("description", "")) for spec in self._offered_specs()}
        before, self._told_tools = self._told_tools, now
        if before is None:
            if not now:
                return ""
            listed = ", ".join(f"tools.{name}" for name in sorted(now))
            return (
                f"(bh-02's other tools are functions in your namespace: {listed}; "
                "help(tools.NAME) says what one takes)\n"
            )
        added = sorted(now.keys() - before.keys())
        removed = sorted(before.keys() - now.keys())
        redefined = sorted(name for name in now.keys() & before.keys() if now[name] != before[name])
        said = [
            f"{', '.join(f'tools.{name}' for name in names)} {what}"
            for names, what in ((added, "added"), (redefined, "redefined"), (removed, "removed"))
            if names
        ]
        return f"(bh-02's tools in your namespace changed: {'; '.join(said)})\n" if said else ""

    async def _refusal(self, question: Mapping[str, Any]) -> str | None:
        """What `access` says about the file the worker asks about; None (go ahead) when there is
        no `access`, or the question is not one it answers (the worker's code is the model's to
        run, so what it sends is read as data)."""
        kind, path = question.get("kind"), question.get("path")
        if self._access is None or not isinstance(kind, str) or not isinstance(path, str):
            return None
        if kind not in self._access.asking():
            return None
        return await asyncio.to_thread(self._access.refusal, kind, path)

    async def _interrupt(self) -> None:
        """Stop the running input and wait for it to end; a worker that won't is restarted."""
        if self._process is None:
            return
        self._process.interrupt()
        try:
            async with asyncio.timeout(self._config.grace):
                await asyncio.shield(self._until_done())
        except TimeoutError, ConnectionError, ValueError:
            await self._stop()

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._writer is None:
            raise ConnectionError("the Python process is not running")
        self._writer.write((json.dumps(message) + "\n").encode("utf-8"))

    async def _receive(self) -> dict[str, Any]:
        if self._reader is None:
            raise ConnectionError("the Python process is not running")
        line = await self._reader.readline()
        if not line:
            raise ConnectionError("the Python process ended")
        message: dict[str, Any] = json.loads(line)
        return message

    async def _start(self) -> None:
        # A Unix socket path must fit in about 100 bytes, so it lives in a short directory of its own.
        self._dir = tempfile.mkdtemp(prefix="bh-k-", dir="/tmp")
        endpoint = str(Path(self._dir) / "k.sock")
        root = str(Path(self._config.root).resolve())
        self._process = self._worker = await self._runner.start(
            worker_argv(endpoint), cwd=root, endpoint=endpoint
        )
        self._reader, self._writer = await asyncio.open_unix_connection(endpoint, limit=_LINE_LIMIT)
        self._send({"op": "hello"})
        self._fresh, self._pending = True, ""  # a new worker runs its startup files afresh

    async def _stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(ConnectionError):
                await self._writer.wait_closed()
        self._reader = self._writer = None
        if self._process is not None:
            await self._process.stop()
            self._process = None
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None
