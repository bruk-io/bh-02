"""The one appender of a file bh-02 keeps for the person: bytes written in the order they were
queued, on a thread so the caller never waits on the disk, to a file made at 0600 through no link;
and a write that fails is raised, never lost silently."""

import asyncio
import datetime
import errno
import os
import stat
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from host_paths import Appender, Replaced


@pytest.fixture
def open_umask() -> Iterator[None]:
    """A umask that takes nothing away, so the mode a file has is the mode it was made with."""
    before = os.umask(0)
    try:
        yield
    finally:
        os.umask(before)


def _held(monkeypatch: pytest.MonkeyPatch, holds: bytes) -> tuple[threading.Event, threading.Event]:
    """The write of `holds` takes its time: it stays on the thread, `(reached, released)`, until
    the second event is set."""
    reached, released = threading.Event(), threading.Event()
    real = os.write

    def write(fd: int, data: bytes | memoryview) -> int:
        if holds in bytes(data) and not reached.is_set():
            reached.set()
            released.wait(10)
        return real(fd, data)

    monkeypatch.setattr(os, "write", write)
    return reached, released


def _closes_of(monkeypatch: pytest.MonkeyPatch, path: Path) -> list[int]:
    """The descriptors of the file at `path` that get closed, as they are: `os.close` is replaced
    for the whole process, so a close of any other descriptor (another test's, a thread's of
    the worker) is let through and not recorded."""
    file = path.stat()
    closed: list[int] = []
    real = os.close

    def close(fd: int) -> None:
        try:
            ours = os.path.samestat(os.fstat(fd), file)
        except OSError:  # not open (or not ours to look at): not the appender's descriptor
            ours = False
        if ours:
            closed.append(fd)
        real(fd)

    monkeypatch.setattr(os, "close", close)
    return closed


def _full(monkeypatch: pytest.MonkeyPatch, *, after: int, once: bool = False) -> None:
    """The writes past the `after`th fail: the disk is full. With `once`, only the next one does
    (and there is room again after it)."""
    real, written = os.write, []

    def write(fd: int, data: bytes | memoryview) -> int:
        if len(written) == after or (len(written) > after and not once):
            written.append(data)
            raise OSError(errno.ENOSPC, "No space left on device")
        written.append(data)
        return real(fd, data)

    monkeypatch.setattr(os, "write", write)


async def test_bytes_are_appended_in_the_order_they_were_queued(tmp_path: Path) -> None:
    path = tmp_path / "log"
    appender = Appender(str(path))
    for n in range(200):
        appender.append(f"{n}\n".encode())
    await appender.flush()
    assert path.read_text().splitlines() == [str(n) for n in range(200)]
    appender.append(b"more\n")
    await appender.close()
    assert path.read_text().splitlines()[-2:] == ["199", "more"]


def test_append_needs_no_running_event_loop(tmp_path: Path) -> None:
    """The transcript's `append` is synchronous and is called wherever the loop's code is, so
    queueing a write asks nothing of an event loop; only waiting for it does."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    appender.append(b"one\n")
    appender.append(b"two\n")
    asyncio.run(appender.close())
    assert path.read_bytes() == b"one\ntwo\n"


async def test_append_returns_before_a_held_write_is_done_and_flush_waits_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write is on its thread, held: the caller is not (the event loop is free), the next
    write waits behind it, and `flush` returns only once both are in the file, in order."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    reached, released = _held(monkeypatch, b"first")
    try:
        appender.append(b"first\n")
        async with asyncio.timeout(10):
            await asyncio.to_thread(reached.wait, 10)
        appender.append(b"second\n")  # returned: the first write is still held
        flushing = asyncio.ensure_future(appender.flush())
        await asyncio.sleep(0.2)
        assert not flushing.done()
        assert path.read_bytes() == b""  # nothing overtook the held write
    finally:
        released.set()
    async with asyncio.timeout(10):
        await flushing
        assert path.read_bytes() == b"first\nsecond\n"
        await appender.close()


async def test_a_cancelled_flush_leaves_the_writes_to_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whoever waits may be stopped (a reply is cancelled mid-flush); what was queued is written,
    the write still waiting for its turn included."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    reached, released = _held(monkeypatch, b"first")
    try:
        appender.append(b"first\n")
        async with asyncio.timeout(10):
            await asyncio.to_thread(reached.wait, 10)
        appender.append(b"second\n")  # waiting for the first
        flushing = asyncio.ensure_future(appender.flush())
        await asyncio.sleep(0.05)
        flushing.cancel()
        await asyncio.gather(flushing, return_exceptions=True)
        appender.append(b"third\n")
    finally:
        released.set()
    async with asyncio.timeout(10):
        await appender.close()
    assert path.read_bytes() == b"first\nsecond\nthird\n"


async def test_a_write_can_be_split_by_the_system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "log"
    real = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: real(fd, bytes(data)[:3]))
    appender = Appender(str(path))
    appender.append(b"a line longer than three bytes\n")
    await appender.close()
    assert path.read_bytes() == b"a line longer than three bytes\n"


@pytest.mark.usefixtures("open_umask")
async def test_the_file_is_made_readable_by_its_owner_alone(tmp_path: Path) -> None:
    """With a umask that takes nothing away, so the mode is the one the file was made with: a
    plain `open()` would have made it 0666."""
    lazy, eager = tmp_path / "lazy", tmp_path / "eager"
    appender, opened = Appender(str(lazy)), Appender.open(str(eager))
    assert not lazy.exists()  # nothing is made until the first write
    assert stat.S_IMODE(eager.stat().st_mode) == 0o600  # made by `open`, before any write
    appender.append(b"x")
    await appender.close()
    await opened.close()
    assert stat.S_IMODE(lazy.stat().st_mode) == 0o600
    assert eager.read_bytes() == b""


@pytest.mark.usefixtures("open_umask")
async def test_a_file_that_was_there_keeps_its_mode(tmp_path: Path) -> None:
    path = tmp_path / "log"
    path.write_text("before\n")
    path.chmod(0o640)
    appender = Appender(str(path))
    appender.append(b"after\n")
    await appender.close()
    assert path.read_text() == "before\nafter\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.parametrize("eagerly", [True, False])
async def test_a_link_at_the_name_is_refused_not_followed(tmp_path: Path, eagerly: bool) -> None:
    """The link someone left to a file elsewhere: nothing is written through it, whether the
    appender opens at once (`open` raises) or by its first write (`flush` raises)."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("not yours\n")
    link = tmp_path / "log"
    link.symlink_to(elsewhere)
    if eagerly:
        with pytest.raises(OSError) as raised:
            Appender.open(str(link))
        assert raised.value.errno == errno.ELOOP
    else:
        appender = Appender(str(link))
        appender.append(b"forged\n")
        with pytest.raises(OSError) as raised:
            await appender.flush()
        assert raised.value.errno == errno.ELOOP
        assert str(link) in "".join(raised.value.__notes__)  # it says which file
    assert elsewhere.read_text() == "not yours\n"


async def test_a_dangling_link_is_not_created_through(tmp_path: Path) -> None:
    target, link = tmp_path / "target", tmp_path / "log"
    link.symlink_to(target)
    with pytest.raises(OSError):
        Appender.open(str(link))
    assert not target.exists()


async def test_a_new_file_must_not_be_there_already(tmp_path: Path) -> None:
    path = tmp_path / "log"
    path.write_text("a child of that name ran\n")
    with pytest.raises(FileExistsError):
        Appender.open(str(path), new=True)
    lazily = Appender(str(path), new=True)
    lazily.append(b"x")
    with pytest.raises(FileExistsError):
        await lazily.flush()
    assert path.read_text() == "a child of that name ran\n"
    fresh = Appender.open(str(tmp_path / "fresh"), new=True)
    fresh.append(b"x")
    await fresh.close()
    assert (tmp_path / "fresh").read_bytes() == b"x"


async def test_a_failed_write_is_raised_by_the_next_append_and_flush_and_nothing_after_it_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk fills on the second write. The caller that queued it has gone on; the next
    `append` says so, and so does `flush`, now and again. The third entry was queued before the
    failure was known and is not written: the file has the first and no hole."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    _full(monkeypatch, after=1, once=True)  # the second write fails, and there is room again after it
    appender.append(b"one\n")
    appender.append(b"two\n")
    appender.append(b"three\n")
    with pytest.raises(OSError) as raised:
        await appender.flush()
    assert raised.value.errno == errno.ENOSPC
    assert str(path) in "".join(raised.value.__notes__) and "dropped" in "".join(raised.value.__notes__)
    with pytest.raises(OSError):
        appender.append(b"four\n")
    with pytest.raises(OSError):
        await appender.flush()
    with pytest.raises(OSError):
        await appender.close()
    assert path.read_bytes() == b"one\n"


async def test_a_failure_nobody_waited_for_still_comes_with_a_later_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No one flushed: the caller went on queueing, and the failure is not lost, it is raised by
    an append made once the thread has met it."""
    appender = Appender(str(tmp_path / "log"))
    _full(monkeypatch, after=0)
    appender.append(b"one\n")
    async with asyncio.timeout(10):
        while True:
            try:
                appender.append(b"more\n")
            except OSError as raised:
                assert raised.errno == errno.ENOSPC
                break
            await asyncio.sleep(0.01)


async def test_the_first_failure_says_when_its_write_failed_not_when_the_caller_heard_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk fills on the second write, on the thread, and the caller hears of it 100 ms later. `failure`
    says when the write failed (UTC, on the thread), with the error that was raised; a later failure, or the
    close's, does not replace it."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    appender.append(b"one\n")
    await appender.flush()
    assert appender.failure is None
    before = datetime.datetime.now(datetime.UTC)
    _full(monkeypatch, after=0)
    appender.append(b"two\n")
    async with asyncio.timeout(10):
        while appender.failure is None:
            await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)
    with pytest.raises(OSError) as raised:
        appender.append(b"three\n")
    heard = datetime.datetime.now(datetime.UTC)
    failure = appender.failure
    assert failure is not None and failure.error is raised.value
    assert failure.at.utcoffset() == datetime.timedelta(0)
    assert before <= failure.at and failure.at + datetime.timedelta(milliseconds=50) < heard
    with pytest.raises(OSError):
        await appender.close()
    assert appender.failure is failure
    assert path.read_bytes() == b"one\n"


async def test_close_waits_for_the_last_write_then_closes_the_file_and_takes_no_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "log"
    appender = Appender.open(str(path))
    closed = _closes_of(monkeypatch, path)
    reached, released = _held(monkeypatch, b"first")
    try:
        appender.append(b"first\n")
        async with asyncio.timeout(10):
            await asyncio.to_thread(reached.wait, 10)
        closing = asyncio.ensure_future(appender.close())
        await asyncio.sleep(0.2)
        os.close(os.open(os.devnull, os.O_RDONLY))  # someone else's close, as in a busy worker
        assert not closing.done() and closed == []  # not closed under a write still on its thread
    finally:
        released.set()
    async with asyncio.timeout(10):
        await closing
        await appender.close()  # again: nothing more to wait for
    assert len(closed) == 1 and path.read_bytes() == b"first\n"
    with pytest.raises(ValueError, match="is closed"):
        appender.append(b"late\n")


async def test_the_file_is_closed_after_a_failure_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "log"
    appender = Appender.open(str(path))
    closed = _closes_of(monkeypatch, path)
    _full(monkeypatch, after=0)
    appender.append(b"one\n")
    with pytest.raises(OSError):
        await appender.close()
    assert len(closed) == 1


async def test_closing_an_appender_nothing_was_written_to_makes_no_file(tmp_path: Path) -> None:
    path = tmp_path / "log"
    await Appender(str(path)).close()
    assert not path.exists()


async def test_an_appender_with_nothing_queued_flushes_and_closes_at_once(tmp_path: Path) -> None:
    appender = Appender(str(tmp_path / "log"))
    async with asyncio.timeout(5):
        await appender.flush()
        await appender.close()


def _renamed_over(path: Path) -> None:
    """What `/clear` does to a transcript: the new file is made beside it and renamed over it."""
    other = path.with_name("other")
    other.write_text("the new conversation\n")
    other.replace(path)


def _removed(path: Path) -> None:
    path.unlink()


def _linked(path: Path) -> None:
    """The model's doing, if it could write where the file is: a link to a file of its choosing."""
    path.with_name("elsewhere").write_text("not yours\n")
    path.unlink()
    path.symlink_to(path.with_name("elsewhere"))


def _content(path: Path) -> str | None:
    """What a reader of `path` finds (through a link, as a reader would), or None for no file."""
    return path.read_text() if path.exists() else None


REPLACED_BY: dict[str, tuple[Callable[[Path], None], str | None]] = {
    "renamed over": (_renamed_over, "the new conversation\n"),
    "removed": (_removed, None),
    "turned into a link": (_linked, "not yours\n"),
}


@pytest.mark.parametrize("held", [True, False], ids=["held open", "not yet opened"])
@pytest.mark.parametrize("how", REPLACED_BY)
async def test_a_file_replaced_under_the_appender_is_refused_and_neither_file_is_written(
    tmp_path: Path, how: str, held: bool
) -> None:
    """The descriptor an appender holds stays on the inode it opened, so a write after a rename
    would land in a file nobody reads, and one to a path opened late in the new file, after the
    old conversation: either way the file is another's. The write is refused as `Replaced`, kept
    like any failed write, and neither the old inode nor what the path holds now is touched."""
    replace, now = REPLACED_BY[how]
    path = tmp_path / "log"
    path.write_text("before\n")
    old = tmp_path / "old"
    os.link(path, old)  # keeps the inode we mean in reach, whatever happens to the name
    appender = Appender.open(str(path)) if held else Appender(str(path))
    if held:
        appender.append(b"one\n")
        await appender.flush()
    replace(path)
    appender.append(b"two\n")
    with pytest.raises(Replaced) as raised:
        await appender.flush()
    assert isinstance(raised.value, OSError) and str(path) in str(raised.value)
    assert str(path) in "".join(raised.value.__notes__) and "dropped" in "".join(raised.value.__notes__)
    with pytest.raises(Replaced):
        appender.append(b"three\n")  # kept, as a full disk is: nothing after it is written either
    with pytest.raises(Replaced):
        await appender.close()
    assert old.read_text() == ("before\none\n" if held else "before\n")
    assert _content(path) == now  # the new file as it was, or no file made in its place
    assert not (tmp_path / "log.new").exists()


async def test_what_was_written_before_the_file_was_replaced_stays_written(tmp_path: Path) -> None:
    """The check is at the write: the lines written while the file was the one stay in it."""
    path = tmp_path / "log"
    appender = Appender.open(str(path))
    for n in range(20):
        appender.append(f"{n}\n".encode())
    await appender.flush()
    old = tmp_path / "old"
    os.link(path, old)
    _renamed_over(path)
    appender.append(b"late\n")
    with pytest.raises(Replaced):
        await appender.flush()
    assert old.read_text().splitlines() == [str(n) for n in range(20)]


async def test_a_replaced_file_closes_the_descriptor_it_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "log"
    appender = Appender.open(str(path))
    closed = _closes_of(monkeypatch, path)
    _renamed_over(path)
    appender.append(b"one\n")
    with pytest.raises(Replaced):
        await appender.close()
    assert len(closed) == 1


async def test_a_file_rewritten_in_place_is_still_the_file(tmp_path: Path) -> None:
    """The same inode: truncated or written to by someone else, it is the file the appender
    means and it goes on appending (a second process appending to it is the point of `O_APPEND`)."""
    path = tmp_path / "log"
    path.write_text("before\n")
    appender = Appender.open(str(path))
    appender.append(b"one\n")
    await appender.flush()
    path.write_text("")  # truncated in place
    appender.append(b"two\n")
    await appender.flush()
    with path.open("ab") as other:  # another process's append
        other.write(b"theirs\n")
    appender.append(b"three\n")
    await appender.close()
    assert path.read_text() == "two\ntheirs\nthree\n"


async def test_a_file_made_before_the_first_write_when_there_was_none_is_the_file(tmp_path: Path) -> None:
    """An appender made over no file means the one its first write finds or makes: a second
    process that got there first (a session resumed twice) is appended to, not refused."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    path.write_text("theirs\n")
    appender.append(b"ours\n")
    appender.append(b"more\n")
    await appender.close()
    assert path.read_text() == "theirs\nours\nmore\n"


@pytest.mark.parametrize("held", [True, False], ids=["held open", "not yet opened"])
@pytest.mark.parametrize("how", REPLACED_BY)
async def test_check_finds_a_replaced_file_before_anything_is_queued_for_it(
    tmp_path: Path, how: str, held: bool
) -> None:
    """The thread looks at the file only before a write, so a caller with nothing queued yet (a
    reply that begins) asks it to look: the file replaced is `Replaced` at once, kept as a failed
    write is, and the first write that follows it is refused without the thread having to find
    the file replaced again. Neither the old inode nor what the path holds now is written."""
    replace, now = REPLACED_BY[how]
    path = tmp_path / "log"
    path.write_text("before\n")
    old = tmp_path / "old"
    os.link(path, old)
    appender = Appender.open(str(path)) if held else Appender(str(path))
    await appender.check()  # the file is the one meant: nothing to say
    replace(path)
    with pytest.raises(Replaced) as raised:
        await appender.check()
    assert isinstance(raised.value, OSError) and str(path) in str(raised.value)
    assert appender.failure is not None and appender.failure.error is raised.value
    with pytest.raises(Replaced):
        appender.append(b"two\n")  # refused by the caller's thread, with no write queued for it
    with pytest.raises(Replaced):
        await appender.flush()
    with pytest.raises(Replaced):
        await appender.close()
    assert old.read_text() == "before\n" and _content(path) == now
    assert not (tmp_path / "log.new").exists()


async def test_check_of_a_file_nothing_was_made_for_finds_nothing_to_refuse_and_makes_none(
    tmp_path: Path,
) -> None:
    """Nothing is meant before a file is there to mean: the check says yes, and writes and opens
    nothing (the file is made by the first write, as it was)."""
    path = tmp_path / "log"
    appender = Appender(str(path))
    await appender.check()
    assert not path.exists()
    appender.append(b"one\n")
    await appender.close()
    assert path.read_text() == "one\n"


async def test_check_is_made_by_the_writing_thread_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stat is the thread's, so the caller (the event loop the TUI shares) waits for the
    thread, not for a disk of its own; and the file is only looked at."""
    path = tmp_path / "log"
    path.write_text("before\n")
    appender = Appender.open(str(path))
    threads: set[int] = set()
    writes: list[bytes] = []
    real_stat, real_write = os.stat, os.write

    def stat(file: object, *args: object, **kwargs: object) -> os.stat_result:
        if file == str(path):
            threads.add(threading.get_ident())
        return real_stat(file, *args, **kwargs)  # type: ignore[arg-type]

    def write(fd: int, data: bytes | memoryview) -> int:
        writes.append(bytes(data))
        return real_write(fd, data)

    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(os, "write", write)
    await appender.check()
    monkeypatch.undo()
    assert threads and threading.get_ident() not in threads
    assert writes == [] and path.read_text() == "before\n"
    await appender.close()


async def test_check_comes_after_the_writes_queued_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The look is queued like a write: a write held on the thread is waited for, and the file
    it was written to (the one meant when it began) keeps it though the check finds the file
    replaced since."""
    path = tmp_path / "log"
    path.write_text("before\n")
    old = tmp_path / "old"
    os.link(path, old)
    appender = Appender.open(str(path))
    reached, released = _held(monkeypatch, b"one")
    appender.append(b"one\n")
    await asyncio.to_thread(reached.wait, 10)
    _renamed_over(path)  # while the write is under way
    checking = asyncio.ensure_future(appender.check())
    await asyncio.sleep(0.05)
    assert not checking.done()  # behind the write
    released.set()
    with pytest.raises(Replaced):
        await checking
    assert old.read_text() == "before\none\n"
    with pytest.raises(Replaced):
        await appender.close()


async def test_check_raises_the_failure_of_an_earlier_write_and_looks_no_further(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "log"
    appender = Appender.open(str(path))
    _full(monkeypatch, after=0)
    appender.append(b"one\n")
    with pytest.raises(OSError, match="No space left"):
        await appender.flush()
    with pytest.raises(OSError, match="No space left"):
        await appender.check()
    monkeypatch.undo()
    with pytest.raises(OSError, match="No space left"):
        await appender.close()


async def test_a_closed_appender_can_not_be_checked(tmp_path: Path) -> None:
    appender = Appender(str(tmp_path / "log"))
    await appender.close()
    with pytest.raises(ValueError, match="closed"):
        await appender.check()
