"""A child's event log: `<session>/agents/NAME/events.jsonl`, one JSON object a line, written as
the child's reply goes on and read by `bh-02 watch` (and by no jailed input: the sessions' state
directory is in the `host` value's `secrets`, so the jail can neither read nor forge it).

The file is created with mode 0600 in the one call that makes it (`O_CREAT | O_EXCL`, no window
in which it is wider), never through a link (`O_NOFOLLOW`), and only by this module; the viewer
opens nothing for writing. Writes go through `host_paths.Appender`, the one appender for the
family, on a thread, so the event loop is never blocked on a disk, one after the other: a record
waits for the write before it, even one whose caller was cancelled and left it to finish (a
cancelled child's end record, written next, would otherwise overtake it or mix with it), and
closing waits for the last. A log that can't be written (the disk is full, the file removed or
replaced under it) stops writing; the child goes on, since the log is for the person, not the run.
(The transcript's failed write is raised instead: it is the conversation.) Best effort is the
write policy, not silence: the log keeps its first failure and when it happened (`stopped`, found
by a write, or by `close` when no write heard of it), so the agents row can tell the person once
the child's run ends. Without it `bh-02 watch`, which ends only at the `agent_end` record the
stopped log never writes, would follow the file for good.
"""

import contextlib
import datetime
import json
from collections.abc import Mapping
from typing import Any

from host_paths import Appender, Failure

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

    def __init__(self, appender: Appender | None) -> None:
        self._appender = appender
        self._stopped: Failure | None = None

    @property
    def stopped(self) -> Failure | None:
        """The first write that failed and when (the appender's own time, taken on its thread where
        the write failed, not when the caller heard of it), or None while every record has gone.
        Read it after `close`: a failure no write heard of is found there. Set once, then kept."""
        return self._stopped

    @classmethod
    def open(cls, path: str) -> EventLog:
        """Create the log at `path`, 0600, which must not be there already and must not be a link.

        Raises:
            OSError: it exists (a child of that name has run) or can't be created.
        """
        return cls(Appender.open(path, new=True))

    @classmethod
    def none(cls) -> EventLog:
        """A log that keeps nothing."""
        return cls(None)

    async def write(self, event: Json) -> None:
        """Append `event`, stamped with the time, off the event loop, after every write asked
        before it has finished (whatever it came to). A caller stopped meanwhile leaves the write
        to finish, which the next one waits for."""
        if (appender := self._appender) is None or self._stopped is not None:
            return
        line = record_line(datetime.datetime.now().astimezone(), event)
        try:
            appender.append(line)
            await appender.flush()
        except OSError:
            # the log stops here and the child goes on; the appender kept when the write failed
            self._stopped = appender.failure

    async def close(self) -> None:
        """Wait for the last write, which has waited for the rest, then close the file (off the
        event loop); later writes are nothing. A failure no write heard of (a write whose caller was
        stopped, a file that would not close) stops the log here: it is kept, not raised."""
        appender, self._appender = self._appender, None
        if appender is not None:
            with contextlib.suppress(OSError):  # best-effort, as `write` is: `stopped` tells
                await appender.close()
            self._stopped = self._stopped or appender.failure
