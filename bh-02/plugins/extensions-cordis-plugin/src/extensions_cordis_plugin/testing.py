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
import socket
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

__all__ = ["PlainJail"]

_READY_S = 10.0


_UNENFORCED: Mapping[str, str] = {"fs_write": "unenforced", "network": "unenforced"}


class _Started:
    def __init__(self, process: asyncio.subprocess.Process, endpoint: str) -> None:
        self.process = process
        self.endpoint = endpoint
        self._connection: socket.socket | None = None  # the runner's connection, set once it listens

    @property
    def connection(self) -> socket.socket:
        if self._connection is None:
            raise RuntimeError("the worker is not ready: it has no connection yet")
        return self._connection

    def report(self) -> Mapping[str, str]:
        return _UNENFORCED

    def notice(self) -> str:
        return ""

    async def stop(self) -> None:
        if self._connection is not None:
            self._connection.close()
        if self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
        await self.process.wait()
        shutil.rmtree(Path(self.endpoint).parent, ignore_errors=True)


class PlainJail:
    """A runner's mechanism for tests (module docstring). `started` is every program it started.
    `release` holds nothing, so it frees nothing: each program's owner stops its own."""

    def __init__(self) -> None:
        self.started: list[_Started] = []

    def report(self) -> Mapping[str, str]:
        return _UNENFORCED

    async def release(self) -> str:
        return ""

    async def start(self, argv_for: Callable[[str], Sequence[str]], *, cwd: str, owner: str) -> _Started:
        # A Unix socket path must fit in about 100 bytes, so it lives in a short directory of its own.
        endpoint = str(Path(tempfile.mkdtemp(prefix="bh-t-", dir="/tmp"), "k.sock"))
        with Path(endpoint).with_name("stderr.log").open("wb") as stderr:
            process = await asyncio.create_subprocess_exec(
                *argv_for(endpoint),
                cwd=cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stderr=stderr,
                start_new_session=True,
            )
        started = _Started(process, endpoint)
        self.started.append(started)
        async with asyncio.timeout(_READY_S):
            while True:  # until it accepts: that connection is the owner's, who never dials again
                if process.returncode is not None:
                    raise RuntimeError(f"the worker exited before it listened ({process.returncode})")
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    connection.connect(endpoint)
                except OSError:
                    connection.close()
                else:
                    started._connection = connection  # noqa: SLF001
                    return started
                await asyncio.sleep(0.02)
