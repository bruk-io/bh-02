"""A `jail` that confines nothing: the worker as a plain subprocess, and a report that says so.

For a platform brig can't jail, or a person who chooses not to. Every axis is reported
`unenforced`, so the kernel is not `confined`: an input can do anything the person running
bh-02 can, and agent:loop puts each input to the person before it runs.
"""

import asyncio
import contextlib
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path

__all__ = ["Unjailed", "UNENFORCED"]

UNENFORCED: Mapping[str, str] = {
    axis: "unenforced"
    for axis in ("fs_read", "fs_write", "network", "limits", "env", "channel_exclusivity", "control")
}
_READY_TIMEOUT_S = 10.0
# A group that has already ended: ESRCH, or on darwin EPERM when all that is left is a zombie
# nobody has reaped yet (the worker exits on its own when the host disconnects).
_GONE = (ProcessLookupError, PermissionError)
_STOP_GRACE_S = 2.0
# Claude credentials are the host's, never an input's: bh-02's own (CLAUDE_CODE_OAUTH_TOKEN, which
# bh-02 reads from local.env and never puts in its environment, but a person may export), any
# ANTHROPIC_* of the person's shell, and whatever a Claude Code that launched bh-02 left in it
# (CLAUDECODE, CLAUDE_PID, CLAUDE_CODE_* such as a messaging token). The worker needs none of
# them. Unjailed confines nothing else, so this keeps a secret out of `os.environ` in an input,
# not out of reach: the input can still read local.env itself, or the environment of any process
# of the same user (`ps eww`), the Claude Code child's included.
_HOST_ONLY = ("ANTHROPIC_", "CLAUDE")


class _Process:
    """The worker in a session of its own, so a terminal's Ctrl-C never reaches it directly."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    def interrupt(self) -> bool:
        if self._process.returncode is not None:
            return False
        with contextlib.suppress(*_GONE):
            os.killpg(self._process.pid, signal.SIGINT)
            return True
        return False

    async def stopped(self) -> None:
        """Return once the process has ended, however it ended."""
        await self._process.wait()

    async def stop(self) -> None:
        if self._process.returncode is None:
            with contextlib.suppress(*_GONE):
                os.killpg(self._process.pid, signal.SIGTERM)
            try:
                async with asyncio.timeout(_STOP_GRACE_S):
                    await self._process.wait()
            except TimeoutError:
                with contextlib.suppress(*_GONE):
                    os.killpg(self._process.pid, signal.SIGKILL)
                await self._process.wait()


class Unjailed:
    """Implements `Jail` with no confinement at all."""

    def report(self) -> Mapping[str, str]:
        return UNENFORCED

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Process:
        log = Path(endpoint).with_name("stderr.log")
        with log.open("wb") as stderr:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env={name: value for name, value in os.environ.items() if not name.startswith(_HOST_ONLY)},
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=stderr,
                start_new_session=True,
            )
        started = _Process(process)
        try:
            await _until_listening(endpoint, process)
        except BaseException:
            await started.stop()
            raise
        return started


async def _until_listening(endpoint: str, process: asyncio.subprocess.Process) -> None:
    """Wait until something accepts on `endpoint` (connect, then leave without a word)."""
    async with asyncio.timeout(_READY_TIMEOUT_S):
        while True:
            if process.returncode is not None:
                log = Path(endpoint).with_name("stderr.log").read_text(errors="replace")[-2000:]
                raise RuntimeError(f"the kernel exited before it was ready ({process.returncode}):\n{log}")
            with contextlib.suppress(OSError):
                _, writer = await asyncio.open_unix_connection(endpoint)
                writer.close()
                return
            await asyncio.sleep(0.05)
