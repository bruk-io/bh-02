"""A row's job queue: run one at a time, a failure reported, and the work its own to cancel."""

import asyncio
from typing import Any

from cordis import Effects, Runtime, background, bind, component
from cordis_helpers import Job, perform


async def test_a_failed_job_is_reported_and_the_next_one_still_runs() -> None:
    jobs: asyncio.Queue[Job] = asyncio.Queue()
    ran: list[str] = []
    failures: list[str] = []

    async def fails() -> None:
        raise RuntimeError("boom")

    async def works() -> None:
        ran.append("ok")

    await jobs.put(fails)
    await jobs.put(works)
    worker = asyncio.create_task(perform(jobs, failures.append))
    await asyncio.sleep(0.01)
    worker.cancel()
    assert failures == ["RuntimeError: boom"] and ran == ["ok"]


async def test_jobs_run_one_at_a_time_in_order_as_the_row_s_own_work_until_it_leaves() -> None:
    """Put from outside the row (a command another row's task runs), performed by the row's
    `background`, which leaves with it: a job put after that never runs."""
    ran: list[str] = []
    gate = asyncio.Event()

    def job(name: str, wait: bool = False) -> Job:
        async def run() -> None:
            ran.append(f"{name} starts")
            if wait:
                await gate.wait()
            ran.append(f"{name} ends")

        return run

    @component
    async def row() -> Effects:
        jobs: asyncio.Queue[Job] = asyncio.Queue()
        yield background(perform(jobs, lambda failure: None))
        yield bind("jobs", jobs)

    rt = Runtime()
    fiber = rt.mount(row, id="row")
    await rt.settle()
    jobs: asyncio.Queue[Any] = rt.root.get("jobs")
    await jobs.put(job("first", wait=True))
    await jobs.put(job("second"))
    await asyncio.sleep(0.01)
    assert ran == ["first starts"]  # the second waits for the first
    gate.set()
    await asyncio.sleep(0.01)
    assert ran == ["first starts", "first ends", "second starts", "second ends"]
    await fiber.retire()
    await jobs.put(job("late"))
    await asyncio.sleep(0.01)
    assert "late starts" not in ran
    await rt.shutdown()
