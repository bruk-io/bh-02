"""The `kernel` value: the host's end of the worker's socket, the process a jail started, and
the model's one tool, `python(code)`, which runs an input in it.

An input is one request and one answer: the worker runs the code and says it is done. Whether
the person is asked first is the `approval` row's to answer and the loop's to ask, so the kernel
depends on its jail alone and a new ui keeps the namespace. Its own `confined` (the same rule,
`approval.is_confined`, over the same jail) decides only what the model is told and whether the
startup file runs unasked. Every failure the kernel knows of (a
worker that died, an answer too long or garbled to read, a worker that won't start again)
comes back as the input's text, never as an exception. Interrupting an input (cancelling `run`) sends SIGINT
through the jail, which the worker turns into `KeyboardInterrupt` in the input, and waits for the
input to say it ended: the namespace survives. A worker that dies is started again on the next
input, and that input is told its earlier variables are gone, and why, when the jail ended it.
After each input, `touched()` is the project's files it opened, read or written (the worker's
audit hook): what a `memory` function is given to say what applies to them.
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

from kernel_cordis_plugin.approval import is_confined
from kernel_cordis_plugin.python import PYTHON, instructions_for

__all__ = ["Jail", "Jailed", "Kernel", "KernelConfig", "worker_argv"]

_WORKER = Path(__file__).with_name("worker.py")
# The longest line the worker sends: its output and its error are capped at 20,000 characters
# each, and JSON escapes a character to at most 12 bytes (a surrogate pair, `\ud83d\ude00`),
# so a `done` is under 500 KB. asyncio's default of 64 KiB would fail on 20,000 emoji.
_LINE_LIMIT = 1 << 20


@runtime_checkable
class Jailed(Protocol):
    """A program a jail started: it can be interrupted and stopped, and says why, when the jail
    ended it itself (`ended`: a Linux `brig:jail` whose hold on a path the host undid; "" when
    it did not)."""

    def interrupt(self) -> bool: ...
    def ended(self) -> str: ...
    async def stop(self) -> None: ...


@runtime_checkable
class Jail(Protocol):
    """What the kernel needs of the `jail` value (CONTRACTS.md: jail)."""

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Jailed: ...
    def report(self) -> Mapping[str, str]: ...
    def notice(self) -> str: ...
    def reads(self) -> tuple[str, ...]: ...
    async def release(self) -> str: ...


@dataclass(frozen=True, slots=True)
class KernelConfig:
    """`root` is the working directory inputs run in; `grace` how long an interrupted input gets
    to say it ended before the worker is stopped and started again; `startup` the project's own
    file (relative to `root`) a new kernel runs before its first input, when its inputs are
    confined: the model's helpers, kept across sessions."""

    root: str = "."
    grace: float = 5.0
    startup: str = ".bh-02/kernel.py"


@dataclass(frozen=True, slots=True)
class _Output:
    """What running one input produced: what it printed, the error it ended with, if any, and
    the files it opened (absolute paths, each once)."""

    output: str
    error: str | None = None
    touched: tuple[str, ...] = ()

    def text(self) -> str:
        """The input as the model reads it."""
        parts = [self.output.rstrip("\n")] if self.output.strip() else []
        if self.error:
            parts.append(self.error)
        return "\n".join(parts) or "(no output)"


def _startup_input(path: str) -> str:
    """The input that runs the startup file at `path` in the namespace and prints, last, the
    public names it defined."""
    return "\n".join(
        [
            "import pathlib as _bh_path",
            "_bh_before = set(globals())",
            f"_bh_source = _bh_path.Path({path!r}).read_text(encoding='utf-8')",
            f"exec(compile(_bh_source, {path!r}, 'exec'), globals())",
            "print(', '.join(sorted(n for n in set(globals()) - _bh_before if not n.startswith('_'))))",
            "del _bh_path, _bh_before, _bh_source",
        ]
    )


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
    """Implements `kernel` (CONTRACTS.md): a persistent namespace, and the model's one tool
    (`spec`, `instructions()`, `run(code)`). An async context manager: entering starts the
    worker in the jail, leaving stops it."""

    def __init__(self, jail: Jail, config: KernelConfig) -> None:
        self._jail = jail
        self._config = config
        self._lock = asyncio.Lock()
        self._dir: str | None = None
        self._process: Jailed | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._restarted = False  # a worker started again, not the row's first
        self._fresh = False  # a worker no input has run in yet
        self._why = ""  # why the jail ended the last worker itself, told with the restart
        self._touched: tuple[str, ...] = ()  # the project's files the last input opened

    @property
    def confined(self) -> bool:
        """Whether the jail confines its inputs, so none is asked about (`approval`'s rule)."""
        return is_confined(self._jail.report())

    def report(self) -> Mapping[str, str]:
        return self._jail.report()

    def notice(self) -> str:
        """What the person should know about the jail the worker runs in ("" when nothing)."""
        return self._jail.notice()

    def reads(self) -> tuple[str, ...]:
        """The trees an input can read, when a jail reads by allowlist; empty when it reads
        everything but what it hides (or is no jail at all)."""
        return self._jail.reads()

    @property
    def spec(self) -> Mapping[str, Any]:
        """The one tool, as the model is offered it."""
        return PYTHON

    def instructions(self) -> str:
        """What the model is told about the tool and where its code runs, read per request."""
        return instructions_for(self.confined, self._config.startup, self.reads())

    async def __aenter__(self) -> Kernel:
        await self._start()
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self._stop()

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

    async def release(self) -> str:
        """End the worker now, and with it its jail, so the jail lets go of what it holds on the
        host while none runs (`jail.release()` says what that freed: on Linux, where bh-02 looks
        for its credential). The next input starts a new worker, told its earlier variables are
        gone. An input that is running is left to finish, and nothing ends."""
        if self._lock.locked():
            return "An input is running: stop the reply (Ctrl-C), then /release again."
        async with self._lock:
            await self._stop()
        freed = await self._jail.release()
        said = "The kernel is stopped; the next input starts it again, without the earlier variables."
        return f"{said} {freed}" if freed else said

    async def _execute(self, code: str) -> _Output:
        async with self._lock:
            if self._reader is not None and self._reader.at_eof():
                # the worker ended between inputs (its jail ended it): start it again for this one
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
                        "person (`/restart kernel` starts the row afresh)",
                    )
                self._restarted = True
            prefix = ""
            try:
                if self._fresh:
                    prefix, self._fresh, self._restarted = await self._opening(), False, False
                ran = await self._exchange(code)
            except ConnectionError:
                why = self._ended()
                await self._stop()
                said = f" because {why}" if why else ""
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
            return _Output(prefix + ran.output, ran.error, ran.touched) if prefix else ran

    async def _opening(self) -> str:
        """What a new kernel's first input is told before its own output, when there is anything
        to tell: that the worker was started again, and what the startup file did. Jailed, the
        file runs here; unjailed, it would run unasked with the person's permissions, so the
        model is told to run it as an input of its own."""
        why, self._why = (f", because {self._why}" if self._why else ""), ""
        notes = (
            [f"the REPL was started again{why}; what earlier inputs defined is gone"]
            if self._restarted
            else []
        )
        startup = self._config.startup
        if (Path(self._config.root) / startup).is_file():
            if not self.confined:
                notes.append(
                    f"{startup} was not run: inputs here are put to the person, so run it as an input "
                    f"of your own if you want it: exec(open({startup!r}).read())"
                )
            elif (ran := await self._exchange(_startup_input(startup))).error:
                notes.append(f"{startup} ran first and failed, so what it defines is missing:\n{ran.error}")
            else:
                lines = ran.output.strip().splitlines()
                notes.append(f"{startup} ran first and defined: {lines[-1] if lines else 'nothing'}")
        return f"({'. '.join(notes)})\n" if notes else ""

    def _ended(self) -> str:
        """Why the jail ended the worker itself, or ""."""
        return self._process.ended() if self._process is not None else ""

    async def _exchange(self, code: str) -> _Output:
        self._send({"op": "exec", "code": code})
        try:
            return await self._until_done()
        except asyncio.CancelledError:
            await self._interrupt()
            raise

    async def _until_done(self) -> _Output:
        """Read the worker until the input ends."""
        while True:
            message = await self._receive()
            if message.get("op") == "done":
                touched = message.get("touched")
                return _Output(
                    str(message.get("output", "")),
                    message.get("error"),
                    tuple(str(p) for p in touched) if isinstance(touched, list) else (),
                )

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
            raise ConnectionError("the kernel is not running")
        self._writer.write((json.dumps(message) + "\n").encode("utf-8"))

    async def _receive(self) -> dict[str, Any]:
        if self._reader is None:
            raise ConnectionError("the kernel is not running")
        line = await self._reader.readline()
        if not line:
            raise ConnectionError("the kernel process ended")
        message: dict[str, Any] = json.loads(line)
        return message

    async def _start(self) -> None:
        # A Unix socket path must fit in about 100 bytes, so it lives in a short directory of its own.
        self._dir = tempfile.mkdtemp(prefix="bh-k-", dir="/tmp")
        endpoint = str(Path(self._dir) / "k.sock")
        root = str(Path(self._config.root).resolve())
        self._process = await self._jail.start(worker_argv(endpoint), cwd=root, endpoint=endpoint)
        self._reader, self._writer = await asyncio.open_unix_connection(endpoint, limit=_LINE_LIMIT)
        self._send({"op": "hello"})
        self._fresh = True

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
