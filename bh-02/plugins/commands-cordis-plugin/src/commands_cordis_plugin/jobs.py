"""The `jobs` value: the restarts commands queue, run one at a time, and whether any is pending.

A command runs in the chat row's task, and a restart replaces a row the chat row depends on,
which would cancel that task half-way: so a command that restarts rows (`/clear`, `/compact`,
`/model NAME`, `/restart ROW`) puts the restart here and answers. The `jobs` row runs them in its
own work (cordis-helpers' `perform`), in the order they were put, and tells the person through
`output.notice` when one fails (each job says how). The chat row waits until none is pending
(`settled`) before it reads the next line, so a line typed during a restart reaches the new
loop, never the old, and is never dropped: the chat row the restart replaces was not reading.
"""

import asyncio
from collections.abc import Awaitable, Callable

from cordis_helpers import Job

__all__ = ["Jobs"]

type Notice = Callable[[str], Awaitable[None]]


class Jobs:
    """Implements `jobs` (CONTRACTS.md: jobs) over the `output` value's `notice`."""

    def __init__(self, notice: Notice) -> None:
        self._notice = notice
        self.queue: asyncio.Queue[Job] = asyncio.Queue()  # the row's `perform` runs what is put here
        self._pending = 0
        self._settled = asyncio.Event()
        self._settled.set()

    def put(self, job: Job, failed: Callable[[str], str]) -> None:
        """Queue `job` behind those already put; `failed(why)` is what the person is told if it
        fails (`why`: one line naming the error). Pending from now until it has run."""
        self._pending += 1
        self._settled.clear()

        async def run() -> None:
            try:
                await job()
            except Exception as error:
                await self._notice(failed(f"{type(error).__name__}: {error}"))
            finally:
                self._pending -= 1
                if not self._pending:
                    self._settled.set()

        self.queue.put_nowait(run)

    def pending(self) -> bool:
        """Whether a job is queued or running."""
        return self._pending > 0

    async def settled(self) -> None:
        """Return once no job is queued or running (at once when none is)."""
        await self._settled.wait()
