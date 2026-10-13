"""Readiness for a LISTEN channel: the poll `Process.wait_ready` runs.

SPEC.md §10.1 (folded by decision-036, ambiguity A5, verbatim): "a LISTEN
channel is ready when its bind is observable... **Observable means a connect
succeeds** -- not that the endpoint path exists. A socket file outlives the
process that bound it, so path existence reports ready for a jail that has
already died. Readiness connects and closes; path-existence is never
readiness."

The connect itself is the runtime's (`Runtime.ready`, decision-184), which
for `HostRuntime` is its verified dial closed at once (decision-185). This
module only polls it. `Jail.wait_ready(channel)` and the helper here that
connected to a declared endpoint as found are gone (decision-186): a channel
names no path, and every dial goes through the runtime.

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

import time
from collections.abc import Callable

_POLL_INTERVAL_S = 0.02


class UnknownChannel(KeyError):
    """Raised when a jail is asked about a channel name its `Spec` does not
    declare at all: by `Jail.channel` and `Jail.start` reserving or binding a
    socket for it (decision-184). `where` names the call."""

    def __init__(self, channel: str, where: str) -> None:
        self.channel = channel
        self.where = where
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"{self.where}: no channel named {self.channel!r} on this jail; declare it in "
            f"its Spec's channels (Channel(name={self.channel!r}, kind=ChannelKind.LISTEN)) "
            "and compile the jail again"
        )


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


def poll_ready(ready: Callable[[], bool], *, channel: str, endpoint: str, timeout: float) -> None:
    """Block until `ready()` is true, asked every `_POLL_INTERVAL_S`, or raise
    a named timeout: `Process.wait_ready`'s loop, with the runtime's own
    readiness (`Runtime.ready`, decision-184) as `ready`.

    Whatever `ready()` raises propagates at once, never waited out: a
    runtime's `EndpointRefused` (decision-185) is a refusal, not "not yet".

    Raises:
        WaitReadyTimeout: `ready()` was still false `timeout` seconds after
            entry.
    """
    deadline = time.monotonic() + timeout
    while not ready():
        if time.monotonic() >= deadline:
            raise WaitReadyTimeout(channel, endpoint, timeout)
        time.sleep(_POLL_INTERVAL_S)
