"""A runner's mechanism for tests: the program as a plain subprocess, confining nothing, and
saying so. A test wraps it in the runner plugin's `Runner`, as `runner:unconfined` does its own.

Whether an extension loads without asking is the `approval` rule's to say, not the runner's, so
a test drives either path with a fake rule over this. Never bind it in a running bh-02.
"""

import asyncio
import contextlib
import os
import shutil
import signal
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

__all__ = ["PlainJail"]

_READY_S = 10.0


_UNENFORCED: Mapping[str, str] = {"fs_write": "unenforced", "network": "unenforced"}


class _Started:
    def __init__(self, process: asyncio.subprocess.Process, endpoint: str, directory: str) -> None:
        self.process = process
        self._endpoint = endpoint
        self._directory = directory
        self.connects = 0  # how often its owner dialled it: through `connect`, the only way
        self.why = ""  # why the jail ended it itself: a test sets it, as a tripwire would

    def report(self) -> Mapping[str, str]:
        return _UNENFORCED

    def notice(self) -> str:
        return ""

    def ended(self) -> str:
        return self.why

    def degraded(self) -> str:
        return ""

    async def connect(self, *, limit: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """A plain connect to the worker's socket: this fake confines nothing, so nothing checks
        what answers."""
        self.connects += 1
        return await asyncio.open_unix_connection(self._endpoint, limit=limit)

    async def stop(self) -> None:
        if self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
        await self.process.wait()
        shutil.rmtree(self._directory, ignore_errors=True)


class PlainJail:
    """A runner's mechanism for tests (module docstring). `started` is every program it started.
    `release` holds nothing, so it frees nothing: each program's owner stops its own."""

    def __init__(self) -> None:
        self.started: list[_Started] = []

    def report(self) -> Mapping[str, str]:
        return _UNENFORCED

    async def release(self) -> str:
        return ""

    async def start(self, argv_for: Callable[[str], Sequence[str]], *, cwd: str) -> _Started:
        """Reserve-then-start, this fake's own way of it: a socket path of its own, that
        `argv_for` gets, as a brig jail's reserved path is."""
        directory = tempfile.mkdtemp(prefix="bh-x-", dir="/tmp")
        endpoint = str(Path(directory) / "x.sock")
        with Path(endpoint).with_name("stderr.log").open("wb") as stderr:
            process = await asyncio.create_subprocess_exec(
                *argv_for(endpoint),
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stderr=stderr,
                start_new_session=True,
            )
        started = _Started(process, endpoint, directory)
        self.started.append(started)
        async with asyncio.timeout(_READY_S):
            while True:  # until it accepts: connect, then leave without a word (a probe)
                if process.returncode is not None:
                    raise RuntimeError(f"the worker exited before it listened ({process.returncode})")
                with contextlib.suppress(OSError):
                    _, writer = await asyncio.open_unix_connection(endpoint)
                    writer.close()
                    return started
                await asyncio.sleep(0.02)
