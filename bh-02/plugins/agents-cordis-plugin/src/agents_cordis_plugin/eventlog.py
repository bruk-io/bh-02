"""A child's event log: `<session>/agents/NAME/events.jsonl`, one JSON object a line, written as
the child's reply goes on and read by `bh-02 watch` (and by no jailed input: the sessions' state
directory is in the `host` value's `secrets`, so the jail can neither read nor forge it).

The file is created with mode 0600 in the one call that makes it (`O_CREAT | O_EXCL`, no window
in which it is wider), never through a link (`O_NOFOLLOW`), and only by this module; the viewer
opens nothing for writing. Writes go through a thread, so the event loop is never blocked on a
disk. A log that can't be written (the disk is full) stops writing; the child goes on, since the
log is for the person, not the run.
"""

import asyncio
import contextlib
import datetime
import json
import os
from collections.abc import Mapping
from typing import Any

__all__ = ["LOG", "EventLog", "record_line"]

# The log's file name beside the child's transcript.
LOG = "events.jsonl"

type Json = Mapping[str, Any]


def record_line(at: datetime.datetime, event: Json) -> bytes:
    """One record of the log: when, and the event (a reply's, or the child's own `agent_start` and
    `agent_end`), as one line of JSON that ends in a newline. An event that is not JSON is written
    as text, so a record is always one line."""
    body = json.dumps({"at": at.isoformat(timespec="milliseconds"), "event": event}, default=str)
    return f"{body}\n".encode()


class EventLog:
    """One child's open log. With no file (a session kept in memory) every write is nothing."""

    def __init__(self, fd: int | None) -> None:
        self._fd = fd
        self._broken = False
        self._writing: asyncio.Future[None] | None = None  # the write on its thread, if one is

    @classmethod
    def open(cls, path: str) -> EventLog:
        """Create the log at `path`, 0600, which must not be there already and must not be a link.

        Raises:
            OSError: it exists (a child of that name has run) or can't be created.
        """
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        return cls(os.open(path, flags, 0o600))

    @classmethod
    def none(cls) -> EventLog:
        """A log that keeps nothing."""
        return cls(None)

    async def write(self, event: Json) -> None:
        """Append `event`, stamped with the time, off the event loop."""
        if self._fd is None or self._broken:
            return
        line = record_line(datetime.datetime.now().astimezone(), event)
        self._writing = asyncio.ensure_future(asyncio.to_thread(self._append, self._fd, line))
        try:  # shielded: a cancelled caller leaves the write to finish before `close` closes the file
            await asyncio.shield(self._writing)
        except OSError:
            self._broken = True  # the log stops here; the child goes on

    async def close(self) -> None:
        """Wait for a write on its thread, then close the file; later writes are nothing."""
        if self._writing is not None:
            await asyncio.gather(self._writing, return_exceptions=True)
        if self._fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._fd)
            self._fd = None

    @staticmethod
    def _append(fd: int, line: bytes) -> None:
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view) :]
