"""A child's event log: a record is written after the one before it, so a cancelled child's end
record never overtakes or interleaves with a write its cancellation left on its thread."""

import asyncio
import datetime
import json
import os
import threading
from pathlib import Path

import pytest

from host_paths import Appender, Replaced
from subagents_cordis_plugin import EventLog, ended_record


def _kinds(path: Path) -> list[str]:
    return [json.loads(line)["event"]["type"] for line in path.read_text().splitlines()]


async def test_a_cancelled_write_finishes_before_the_end_record_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child is cancelled (Ctrl-C) while a record is on the disk: the caller's cancellation
    leaves that write to finish (it is shielded), and the end record the run writes next waits
    for it, so the file reads in the order the records were asked and never mixes two of them."""
    path = tmp_path / "events.jsonl"
    log = EventLog.open(str(path))
    on_disk, release = threading.Event(), threading.Event()
    real = os.write

    def held(fd: int, data: bytes | memoryview) -> int:
        """The first record's write takes its time: it is on the disk's thread until released."""
        if b'"first"' in bytes(data) and not on_disk.is_set():
            on_disk.set()
            release.wait(10)
        return real(fd, data)

    monkeypatch.setattr(os, "write", held)
    try:
        first = asyncio.ensure_future(log.write({"type": "text", "text": "first"}))
        async with asyncio.timeout(10):
            await asyncio.to_thread(on_disk.wait, 10)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        end = asyncio.ensure_future(log.write(ended_record("stopped before it answered")))
        await asyncio.sleep(0.2)  # long enough for a write that did not wait to have been made
        assert not end.done()
        assert path.read_text() == ""  # nothing overtook the record on the disk
    finally:
        release.set()
    async with asyncio.timeout(10):
        await end
        await log.close()
    assert _kinds(path) == ["text", "agent_end"]


async def test_close_waits_for_a_cancelled_write_and_later_writes_are_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog.open(str(path))
    on_disk, release = threading.Event(), threading.Event()
    real = os.write

    def held(fd: int, data: bytes | memoryview) -> int:
        if b'"first"' in bytes(data) and not on_disk.is_set():
            on_disk.set()
            release.wait(10)
        return real(fd, data)

    monkeypatch.setattr(os, "write", held)
    try:
        first = asyncio.ensure_future(log.write({"type": "text", "text": "first"}))
        async with asyncio.timeout(10):
            await asyncio.to_thread(on_disk.wait, 10)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        closing = asyncio.ensure_future(log.close())
        await asyncio.sleep(0.2)
        assert not closing.done()  # the file is not closed under a write that is still on its thread
    finally:
        release.set()
    async with asyncio.timeout(10):
        await closing
        await log.write({"type": "text", "text": "late"})
    assert _kinds(path) == ["text"]


async def test_a_log_that_keeps_nothing_writes_and_closes_as_nothing() -> None:
    log = EventLog.none()
    await log.write({"type": "text", "text": "x"})
    await log.close()


async def test_a_log_that_kept_every_record_never_stopped(tmp_path: Path) -> None:
    log = EventLog.open(str(tmp_path / "events.jsonl"))
    await log.write({"type": "text", "text": "kept"})
    assert log.stopped is None
    await log.close()
    assert log.stopped is None
    assert EventLog.none().stopped is None


async def test_a_log_removed_under_the_appender_stops_at_the_write_it_refused(tmp_path: Path) -> None:
    """The file is removed while the child runs: the next record is refused (`Replaced`), the log
    keeps that error and the moment the write failed, and nothing after it is written, nor does a
    later failure replace the first."""
    path = tmp_path / "events.jsonl"
    log = EventLog.open(str(path))
    await log.write({"type": "text", "text": "kept"})
    os.remove(path)
    before = datetime.datetime.now(datetime.UTC)
    await log.write({"type": "text", "text": "refused"})
    after = datetime.datetime.now(datetime.UTC)
    stopped = log.stopped
    assert stopped is not None and isinstance(stopped.error, Replaced)
    assert before <= stopped.at <= after
    await log.write(ended_record("late"))
    await log.close()
    assert log.stopped is stopped  # the first failure stays the one told
    assert not path.exists()  # nothing was made in the file's place


async def test_a_failure_only_the_close_hears_of_stops_the_log_at_the_time_it_happened(
    tmp_path: Path,
) -> None:
    """The caller of a write is stopped (Ctrl-C) while the record is on the disk's thread, and the
    write fails after it: `write` never hears of it, `close` does, and the log says it stopped, with
    the time the write failed on its thread and not the time `close` found out. The file is a pipe
    whose reader does not read, so the record (past what a pipe holds) blocks the thread until the
    reader goes, which fails the write (a broken pipe)."""
    fifo = tmp_path / "events.jsonl"
    os.mkfifo(fifo)
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        log = EventLog(Appender(str(fifo)))
        write = asyncio.ensure_future(log.write({"type": "text", "text": "x" * 1_000_000}))
        await asyncio.sleep(0.1)  # the record is queued, and its write is blocked on the pipe
        write.cancel()
        await asyncio.gather(write, return_exceptions=True)
    finally:
        os.close(reader)  # the blocked write fails on its thread, with nobody waiting for it
    await asyncio.sleep(0.2)
    assert log.stopped is None  # nobody has heard of it
    before_close = datetime.datetime.now(datetime.UTC)
    await log.close()
    stopped = log.stopped
    assert stopped is not None and isinstance(stopped.error, BrokenPipeError)
    assert stopped.at < before_close
