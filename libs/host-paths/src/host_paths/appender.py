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

A write that fails (the disk is full, the file was removed, a link stands at the name) is not
lost silently: it is kept, nothing queued after it is written (a file with a hole in it would
read as another conversation), and every `append`, `flush` and `close` after it raises it. Whoever
wants the writes best-effort (the event log) catches it and stops.
"""

import asyncio
import concurrent.futures
import os

__all__ = ["Appender"]

_APPEND = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOCTTY
_MODE = 0o600


class Appender:
    """One file, appended to off the event loop, in the order the bytes were queued.

    Nothing is opened until the first write, which opens it on the writing thread; `open` opens it
    now instead, for a caller that wants to know at once whether it can.
    """

    def __init__(self, path: str, *, new: bool = False) -> None:
        """An appender of `path`, which is opened by its first write: made at 0600 if it is not
        there. With `new`, it must not be there (the first write fails if it is)."""
        self._path = path
        self._new = new
        self._fd: int | None = None  # opened, written and closed on the thread, in that order
        self._writer = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="appender")
        self._last: concurrent.futures.Future[None] | None = None
        self._failed: OSError | None = None
        self._closed = False

    @classmethod
    def open(cls, path: str, *, new: bool = False) -> Appender:
        """An appender of `path`, opened now (as `__init__` says it will be by its first write): on
        the calling thread, so a caller on the event loop runs it on a thread.

        Raises:
            OSError: the file can't be opened for append: a link stands at `path` (never
                followed), `new` and it is there, or its directory is missing or not writable.
        """
        appender = cls(path, new=new)
        appender._fd = _opened(path, new=new)
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
            raise self._failed

    def _failing(self, error: OSError) -> None:
        """Keep the first failure, and say what it cost."""
        if self._failed is None:
            error.add_note(
                f"appending to {self._path} failed: this write and every one queued after it were "
                "dropped, so the file ends before them"
            )
            self._failed = error

    def _write(self, data: bytes) -> None:
        """Append `data`, on the thread, unless a write failed before it."""
        if self._failed is not None:
            return
        try:
            if self._fd is None:
                self._fd = _opened(self._path, new=self._new)
            view = memoryview(data)
            while view:
                view = view[os.write(self._fd, view) :]
        except OSError as error:
            self._failing(error)

    def _close(self) -> None:
        """Close the file, on the thread, after the writes queued before it."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError as error:
            self._failing(error)


def _opened(path: str, *, new: bool) -> int:
    return os.open(path, _APPEND | (os.O_EXCL if new else 0), _MODE)
