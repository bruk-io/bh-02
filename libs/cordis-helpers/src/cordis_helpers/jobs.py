"""Work a row owns, queued by code that runs in another row's task.

A row's function may be called from another row's task: a slash command runs in the task of the
row that read the line. Work that restarts a row that caller depends on would cancel the task
running it, half-way through. So the row that offers the function keeps a queue and yields
`background(perform(jobs, failed))`, which cordis cancels when the row leaves; the function puts
the work there and returns. Jobs run one at a time, in the order they were put; one that fails
is reported to `failed` and the next still runs.
"""

import asyncio
from collections.abc import Awaitable, Callable

__all__ = ["Job", "perform"]

type Job = Callable[[], Awaitable[None]]


async def perform(jobs: asyncio.Queue[Job], failed: Callable[[str], Awaitable[None] | None]) -> None:
    """Run the queued jobs one at a time, for as long as the row is up. A job that fails is
    reported (`failed`, one line naming the error; awaited before the next job when it returns
    an awaitable, as a row that tells the person through `output.notice` does) and the next one
    still runs. A `failed` that raises ends the work, which cordis keeps on the row."""
    while True:
        job = await jobs.get()
        try:
            await job()
        except Exception as error:
            told = failed(f"{type(error).__name__}: {error}")
            if told is not None:
                await told
