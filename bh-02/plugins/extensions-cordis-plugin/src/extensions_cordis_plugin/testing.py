"""A `jail` for tests: the program as a plain subprocess, confining nothing, and saying so.

Whether an extension loads without asking is the `approval` value's to say, not the jail's, so a
test drives either path with a fake approval over this. Never bind it in a running bh-02.
"""

import asyncio
import contextlib
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path

__all__ = ["PlainJail"]

_READY_S = 10.0


class _Started:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process

    async def stop(self) -> None:
        if self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
        await self.process.wait()


class PlainJail:
    """Implements `jail` for tests (module docstring). `started` is every program it started.
    `release` stops every one of them, as a Linux `brig:jail`'s does, and the jail is released
    until it next starts one."""

    def __init__(self) -> None:
        self.started: list[_Started] = []
        self._released = False

    def report(self) -> Mapping[str, str]:
        return {"fs_write": "unenforced", "network": "unenforced"}

    def released(self) -> bool:
        return self._released

    async def release(self) -> str:
        self._released = True
        for started in self.started:
            await started.stop()
        return ""

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Started:
        self._released = False
        with Path(endpoint).with_name("stderr.log").open("wb") as stderr:
            process = await asyncio.create_subprocess_exec(
                *argv, cwd=cwd, stdin=asyncio.subprocess.DEVNULL, stderr=stderr, start_new_session=True
            )
        started = _Started(process)
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
