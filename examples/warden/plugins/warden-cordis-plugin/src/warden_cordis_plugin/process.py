"""A supervised subprocess: spawned on entry, terminated on exit.

Nothing is spawned until entered (`yield enter(managed_process(config.command))`), the same
promise bh-02's `models_cordis_plugin.claude_code.ClaudeCodeModel` makes for a Claude Code process.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

__all__ = ["Process", "ProcessConfig", "managed_process"]


@dataclass(frozen=True, slots=True)
class ProcessConfig:
    name: str
    command: tuple[str, ...] = ("sleep", "100")


@dataclass(frozen=True, slots=True)
class Process:
    pid: int


@contextlib.asynccontextmanager
async def managed_process(command: Sequence[str]) -> AsyncIterator[Process]:
    """Spawn `command`; terminate it on exit if it is still running."""
    raw = await asyncio.create_subprocess_exec(*command)
    try:
        yield Process(pid=raw.pid)
    finally:
        if raw.returncode is None:
            raw.terminate()
            await raw.wait()
