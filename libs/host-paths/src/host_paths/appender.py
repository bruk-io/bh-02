"""Appending to one file bh-02 keeps for the person, off the event loop: the one appender for
every package that writes such a file (a conversation's transcript, a sub-agent's event log, a
session's row log).

One `Appender` is one file, opened for append, with these flags, each for a reason:

- `O_APPEND`: every write lands at the end, so a second process appending to the same file (a
  session resumed twice) interleaves whole writes, never overwrites one.
- `O_CREAT` at 0600: the file is made in the one call that opens it, readable by its owner
  alone, with no window in which it is wider. A file that was there keeps the mode it had.
- `O_EXCL` when `new`: the file must not be there already (a sub-agent's name was used before).
- `O_NOFOLLOW`: a link at the name is refused, never followed, so nothing that planted one
  chooses what is written.
- `O_CLOEXEC` and `O_NOCTTY`: a program bh-02 starts meanwhile inherits nothing, and a terminal
  device at the name never becomes bh-02's.

`append` only queues: it takes the bytes, hands them to one thread and returns, so the caller
(the event loop the TUI shares) never waits on a disk, and needs no running loop to do it. The
thread writes them in the order they were queued, each after the one before it, so a write is
never overtaken or mixed with another, whoever asked and whatever became of the one that asked
(a cancelled caller leaves its write to finish). `flush` waits for the last write; `close` waits
for it, then closes the file.

An appender writes to one file, the one it means: the file it holds open, or, before its first
write, the one standing at the path when the appender was made (none, if there was none). The
thread checks before each write that the file at the path is still that one (`os.path.samestat`
of the file held, or found when the appender was made, against a `stat` of the path that follows
no link). A file renamed over, removed, or turned into a link is another file or none: the write
would land in the old file's inode, which nobody reads, or in a file that holds another
conversation, so it is refused as `Replaced` and never made. The thread has not looked at the file
since its last write, so a caller about to rely on it before it has anything to write (a reply
that begins) asks it to look now: `check` queues the same look, without a write, on the thread
and waits for it, so the stat is the thread's and the caller's event loop waits on none.

A write that fails (the disk is full, a link stands at the name, the file was replaced or removed)
is not lost silently: it is kept, nothing queued after it is written (a file with a hole in it
would read as another conversation), and every `append`, `flush` and `close` after it raises it.
The first failure is kept with the time it happened, on the thread (`failure`), so a caller that
hears of it later can say when the write failed, not when it heard. Whoever wants the writes
best-effort (the event log) catches it and stops.
"""

import asyncio
import concurrent.futures
import datetime
import os
from dataclasses import dataclass

__all__ = ["Appender", "Failure", "Replaced"]

_APPEND = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOCTTY
_MODE = 0o600


class Replaced(OSError):
    """The file at an appender's path is no longer the one it means: it was renamed over, removed
    or turned into a link since the appender held it open (or was made, if it had not opened it
    yet). What the appender had queued from then on was not written, so the file ends before it."""


@dataclass(frozen=True, slots=True)
class Failure:
    """The first write an appender could not make: when it failed, on its thread (aware, UTC), and
    the error it raised. Set once, with both fields together, so a reader never sees one without the
    other."""

    at: datetime.datetime
    error: OSError


class Appender:
    """One file, appended to off the event loop, in the order the bytes were queued.

    Nothing is opened until the first write, which opens it on the writing thread; `open` opens it
    now instead, for a caller that wants to know at once whether it can.
    """

    def __init__(self, path: str, *, new: bool = False) -> None:
        """An appender of `path`, which is opened by its first write: made at 0600 if it is not
        there. With `new`, it must not be there (the first write fails if it is). The file at
        `path` now, if there is one, is the one it means (a stat, the one touch of the disk here)."""
        self._path = path
        self._new = new
        self._fd: int | None = None  # opened, written and closed on the thread, in that order
        # the file it means, once there is one: what it opens must be it, and so must what is at the path
        self._meant = _stat_of(path)
        self._writer = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="appender")
        self._last: concurrent.futures.Future[None] | None = None
        self._failed: Failure | None = None
        self._closed = False

    @property
    def failure(self) -> Failure | None:
        """The first write that failed and when it did (on the thread, the moment the write returned
        its error), or None while every write has gone. Set once and never changed after."""
        return self._failed

    @classmethod
    def open(cls, path: str, *, new: bool = False) -> Appender:
        """An appender of `path`, opened now (as `__init__` says it will be by its first write): on
        the calling thread, so a caller on the event loop runs it on a thread.

        Raises:
            OSError: the file can't be opened for append: a link stands at `path` (never
                followed), `new` and it is there, or its directory is missing or not writable.
        """
        appender = cls(path, new=new)
        appender._fd = appender._hold()
        return appender

    def append(self, data: bytes) -> None:
        """Queue `data` to be appended after every byte queued before it; returns at once.

        Raises:
            OSError: an earlier write failed (nothing after it is written).
            ValueError: the appender is closed.
        """
        self._raise()
        if self._closed:
            raise ValueError(f"{self._path} is closed, so nothing more can be appended to it")
        self._last = self._writer.submit(self._write, data)

    async def flush(self) -> None:
        """Return once everything queued so far has been written. A caller stopped meanwhile only
        stops waiting: the writes go on.

        Raises:
            OSError: a write failed, this one's or an earlier one's.
        """
        if self._last is not None:
            await asyncio.shield(asyncio.wrap_future(self._last))
        self._raise()

    async def check(self) -> None:
        """Return once the writing thread has looked, after every write queued before this, at the
        file at the path and found it the one this appender means: the look it makes before each
        write, made now, with nothing written. A caller whose next write is not queued yet uses it
        to learn at once that the file was replaced, not at the write that finds it. The stat is
        the thread's; the caller waits only for the thread, never for a disk of its own. A file
        found replaced is kept as a failed write is: nothing queued after it is written, and every
        `append`, `flush` and `close` after it raises it.

        Raises:
            Replaced: the file at the path is another than the one meant, or none.
            OSError: a write failed before this, or the stat did.
            ValueError: the appender is closed.
        """
        self._raise()
        if self._closed:
            raise ValueError(f"{self._path} is closed, so it can't be checked")
        self._last = self._writer.submit(self._look)
        await self.flush()

    async def close(self) -> None:
        """Wait for everything queued, then close the file (a file nothing was written to is never
        opened); the appender takes no more. Closing again waits for the first.

        Raises:
            OSError: a write failed, or the file would not close; it is closed all the same.
        """
        if not self._closed:
            self._closed = True
            self._last = self._writer.submit(self._close)
            self._writer.shutdown(wait=False)  # the thread ends once it has run what it was given
        await self.flush()

    def _raise(self) -> None:
        if self._failed is not None:
            raise self._failed.error

    def _failing(self, error: OSError) -> None:
        """Keep the first failure, with the time it happened (taken here, on the thread, before
        anything else), and say what it cost."""
        at = datetime.datetime.now(datetime.UTC)
        if self._failed is None:
            error.add_note(
                f"appending to {self._path} failed: this write and every one queued after it were "
                "dropped, so the file ends before them"
            )
            self._failed = Failure(at, error)

    def _write(self, data: bytes) -> None:
        """Append `data`, on the thread, unless a write failed before it."""
        if self._failed is not None:
            return
        try:
            self._unreplaced()
            if self._fd is None:
                self._fd = self._hold()
            view = memoryview(data)
            while view:
                view = view[os.write(self._fd, view) :]
        except OSError as error:
            self._failing(error)

    def _look(self) -> None:
        """Check the file at the path is the one meant, on the thread, unless a write failed before it."""
        if self._failed is not None:
            return
        try:
            self._unreplaced()
        except OSError as error:
            self._failing(error)

    def _hold(self) -> int:
        """Open the file, on the calling thread, and make it the one this appender means (the file
        found at the path when it was made, if there was one, else the one opened, made if need
        be).

        Raises:
            Replaced: the file opened is not the one found when the appender was made.
        """
        fd = os.open(self._path, _APPEND | (os.O_EXCL if self._new else 0), _MODE)
        try:
            opened = os.fstat(fd)
            if self._meant is not None and not os.path.samestat(self._meant, opened):
                raise self._replaced()
        except BaseException:
            os.close(fd)
            raise
        self._meant = opened
        return fd

    def _unreplaced(self) -> None:
        """Return unless the file at the path is another than the one this appender means (a link
        counts as another, and so does none); nothing is meant before a file is there to mean.

        Raises:
            Replaced: it is another, or none.
        """
        if self._meant is None:
            return
        try:
            here = os.stat(self._path, follow_symlinks=False)
        except FileNotFoundError:
            raise self._replaced() from None
        if not os.path.samestat(self._meant, here):
            raise self._replaced()

    def _replaced(self) -> Replaced:
        return Replaced(
            f"{self._path} is no longer the file this appender writes to: it was replaced by another "
            "file, or removed, so nothing more is written to it"
        )

    def _close(self) -> None:
        """Close the file, on the thread, after the writes queued before it."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError as error:
            self._failing(error)


def _stat_of(path: str) -> os.stat_result | None:
    """The file at `path` as it stands (a link is itself), or None when there is none to stat."""
    try:
        return os.stat(path, follow_symlinks=False)
    except OSError:
        return None
