"""Readiness for a LISTEN channel.

SPEC.md §10.1 (folded by decision-036, ambiguity A5, verbatim): "a LISTEN
channel is ready when its bind is observable... **Observable means a connect
succeeds** -- not that the endpoint path exists. A socket file outlives the
process that bound it, so path existence reports ready for a jail that has
already died. Readiness connects and closes; path-existence is never
readiness."

**The readiness definition this module resolves to, for M2's unix-socket
LISTEN endpoint**: ready means opening an `AF_UNIX`/`SOCK_STREAM` socket,
calling `connect(endpoint)`, and closing it immediately on success --
`os.path.exists(endpoint)` is never consulted anywhere in this module. A
socket FILE that exists with nothing listening behind it (a dead process's
leftover, or a file `bind()`-then-`close()`d without ever `listen()`ing)
fails `connect()` with `ConnectionRefusedError` -- exactly the case path
existence cannot distinguish from a live bind, which is the whole reason
this module never calls `os.path.exists`.

**Poll interval: 20ms (50Hz)**, chosen so polling granularity does not skew
the elapsed-time assertions this task's ACs make: the positive case (a bind
appearing after a ~0.5s workload sleep, timeout=10s) and the negative case
(a timeout=1.0s deadline expected to fire within [1.0, 3.0)s) both carry at
least a full second of slack, and 50 polls/sec bounds the worst-case
overshoot past either the bind's true appearance or the deadline itself to
20ms -- negligible against that slack, and fast enough that the positive
case does not visibly stall past the sleep it is timing.
"""

from __future__ import annotations

import socket
import time
from typing import Any

_POLL_INTERVAL_S = 0.02


class UnknownChannel(KeyError):
    """Raised when `wait_ready` is asked about a channel name the handle
    does not declare at all."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"wait_ready: no channel named {self.channel!r} on this handle"


class WaitReadyTimeout(TimeoutError):
    """Raised when a LISTEN channel's bind never becomes observable within
    `timeout`. Carries `channel`, `endpoint`, and `timeout` as structured
    fields -- a caller inspects these, not `str(exc)`."""

    def __init__(self, channel: str, endpoint: str, timeout: float) -> None:
        self.channel = channel
        self.endpoint = endpoint
        self.timeout = timeout
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"wait_ready: channel {self.channel!r} (endpoint {self.endpoint!r}) "
            f"never became ready within {self.timeout}s"
        )


def _connect_succeeds(endpoint: str) -> bool:
    """True iff a fresh `AF_UNIX`/`SOCK_STREAM` socket can `connect()` to
    `endpoint` -- closed immediately either way, so this never leaves a
    connection open on the far side. Any `OSError` (no file at all --
    `FileNotFoundError`; a stale file with nothing listening --
    `ConnectionRefusedError`; anything else the platform raises) reads as
    "not yet ready". `os.path.exists` never appears in this function --
    that is the entire point of it existing separately from a path check."""
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(endpoint)
    except OSError:
        return False
    else:
        return True
    finally:
        probe.close()


def wait_ready(handle: Any, channel: str, timeout: float) -> None:
    """Block until `channel`'s bind is observable, or raise a named timeout.

    `handle` is duck-typed to anything carrying a `channels: Mapping[str,
    Channel]` attribute (in practice `brig.run.handle.Handle`) -- this
    module never imports `Handle` itself, since `run` importing its own
    sibling module by name would be circular (`handle.py` imports THIS
    module to build `Handle.wait_ready`'s delegate).

    Raises `UnknownChannel(channel)` immediately if `channel` names nothing
    on the handle -- answerable from the declared `Spec` alone, so it never
    waits or polls. A wrong-KIND refusal used to sit beside it; `LISTEN` is
    the only `ChannelKind` there is since decision-153, so the check would
    be a branch nothing can reach. Otherwise polls
    `_connect_succeeds` against the channel's endpoint every
    `_POLL_INTERVAL_S` until it returns `True` (this function then returns
    `None`) or `timeout` seconds have elapsed since entry (this function
    then raises `WaitReadyTimeout`).
    """
    channels = handle.channels
    if channel not in channels:
        raise UnknownChannel(channel)

    endpoint = channels[channel].endpoint
    deadline = time.monotonic() + timeout
    while True:
        if _connect_succeeds(endpoint):
            return
        if time.monotonic() >= deadline:
            raise WaitReadyTimeout(channel, endpoint, timeout)
        time.sleep(_POLL_INTERVAL_S)
