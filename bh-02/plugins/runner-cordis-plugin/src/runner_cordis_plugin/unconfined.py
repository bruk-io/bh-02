"""The unconfined runner's mechanism: a program as a plain subprocess, and a report that says so.

For a platform brig can't jail, or a person who chooses not to (`--no-jail`). Every axis is
reported `unenforced`, so nothing is `confined`: an input can do anything the person running
bh-02 can, and `approval`'s rule puts each input (and each extension to load) to the person.
"""

import asyncio
import contextlib
import os
import signal
import socket
from collections.abc import Mapping
from pathlib import Path

from runner_cordis_plugin.runner import ArgvFor, reserved_endpoint, unreserve_endpoint

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
# the person exports for a claude-code endpoint's `key = { env = ... }`, and which bh-02 hands only
# to the Claude Code child), any ANTHROPIC_* of the person's shell, and whatever a Claude Code that
# launched bh-02 left in it (CLAUDECODE, CLAUDE_PID, CLAUDE_CODE_* such as a messaging token).
# The worker needs none of them. Unjailed confines nothing else, so this keeps a secret out of
# `os.environ` in an input, not out of reach: the input can still read the environment of any
# process of the same user (`ps eww`), the Claude Code child's included. Every other variable
# passes, a model's provider key (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`) among them: under
# `--no-jail` the model's code can read them.
_HOST_ONLY = ("ANTHROPIC_", "CLAUDE")
# tmux's: `TMUX` names the server's socket and `TMUX_PANE` the pane bh-02 runs in (decision-0002,
# Watching). The confined runner's allowlist never passes them; this one passes everything else, so
# it drops them by name. Hygiene, not a boundary: an input without a jail can find the socket itself.
_TMUX = ("TMUX", "TMUX_PANE")


def _program_env(environ: Mapping[str, str]) -> dict[str, str]:
    """The environment of a program the unconfined runner starts: the host's, less the Claude
    credentials and anything Claude's (`_HOST_ONLY`) and tmux's (`_TMUX`)."""
    return {
        name: value
        for name, value in environ.items()
        if not name.startswith(_HOST_ONLY) and name not in _TMUX
    }


class _Process:
    """The worker in a session of its own, so a terminal's Ctrl-C never reaches it directly."""

    def __init__(self, process: asyncio.subprocess.Process, endpoint: str) -> None:
        self._process = process
        self.endpoint = endpoint
        self._connection: socket.socket | None = None

    @property
    def connection(self) -> socket.socket:
        """The connected socket to the program, made when it was ready (see `runner.Started`)."""
        if self._connection is None:
            raise RuntimeError("the program is not ready: it has no connection yet")
        return self._connection

    def ready(self, connection: socket.socket) -> None:
        """Keep the connection made once the program listened: this start owns it until its owner takes it."""
        self._connection = connection

    def interrupt(self) -> bool:
        if self._process.returncode is not None:
            return False
        with contextlib.suppress(*_GONE):
            os.killpg(self._process.pid, signal.SIGINT)
            return True
        return False

    def ended(self) -> str:
        """Nothing ends the worker of its own accord here."""
        return ""

    def report(self) -> Mapping[str, str]:
        return UNENFORCED

    def notice(self) -> str:
        """Nothing: the status bar says it is unjailed, and every input asks."""
        return ""

    def reads(self) -> tuple[str, ...]:
        """No allowlist: an input reads what the person can."""
        return ()

    def writes(self) -> tuple[str, ...]:
        """None named: it confines no writes, so an input writes what the person can (and is put
        to them first; nothing runs unasked here, a startup file included)."""
        return ()

    async def stopped(self) -> None:
        """Return once the process has ended, however it ended."""
        await self._process.wait()

    async def stop(self) -> None:
        """End the process, then close the connection and remove the directory its socket and log
        were in."""
        try:
            await self._ended()
        finally:
            if self._connection is not None:
                self._connection.close()
            unreserve_endpoint(self.endpoint)

    async def _ended(self) -> None:
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
    """The unconfined runner's mechanism (`runner.Mechanism`): no confinement at all."""

    def report(self) -> Mapping[str, str]:
        return UNENFORCED

    def notice(self) -> str:
        """Nothing: the status bar says it is unjailed, and every input asks."""
        return ""

    async def release(self) -> str:
        """Nothing: no jail holds anything on the host."""
        return ""

    async def start(self, argv_for: ArgvFor, *, cwd: str, owner: str) -> _Process:
        """Start the program; `owner` is the runner's (nothing here asks for a destination)."""
        endpoint = reserved_endpoint()
        log = Path(endpoint).with_name("stderr.log")
        try:
            with log.open("wb") as stderr:
                process = await asyncio.create_subprocess_exec(
                    *argv_for(endpoint),
                    cwd=cwd,
                    env=_program_env(os.environ),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=stderr,
                    start_new_session=True,
                )
        except BaseException:
            unreserve_endpoint(endpoint)
            raise
        started = _Process(process, endpoint)
        try:
            started.ready(await _until_listening(endpoint, process))
        except BaseException:
            await started.stop()
            raise
        return started


async def _until_listening(endpoint: str, process: asyncio.subprocess.Process) -> socket.socket:
    """Wait until something accepts on `endpoint`, and return that connection, the one the owner
    uses (it never dials `endpoint` again: the contract is the same as a jail's)."""
    async with asyncio.timeout(_READY_TIMEOUT_S):
        while True:
            if process.returncode is not None:
                log = Path(endpoint).with_name("stderr.log").read_text(errors="replace")[-2000:]
                raise RuntimeError(f"the program exited before it was ready ({process.returncode}):\n{log}")
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                connection.connect(endpoint)
            except OSError:
                connection.close()
            else:
                return connection
            await asyncio.sleep(0.05)
