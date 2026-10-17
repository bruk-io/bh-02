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

**Poll schedule: 2ms, growing to 20ms (TASK-0079.21).** A jail's process binds its
socket some milliseconds after it starts (a jailed `python3` is up in about 15ms),
and a fixed 20ms interval saw that bind late: on the 20ms mark when it was a few
milliseconds old, on the 40ms mark when the first check had landed just before it,
about 10ms late on average. Each wait is now a tenth of the time already spent
waiting, no shorter than 2ms and no longer than the old 20ms (`_next_wait`): a bind
in the first 20ms is seen within 2ms, one at time `t` within `t / 10`, and one
past 200ms, or a deadline, is overshot by at most the 20ms the fixed interval
always bounded it by. That bound is what the elapsed-time assertions of
`tests/integration/test_wait_ready.py` were chosen against (the positive case, a
bind appearing after a ~0.5s workload sleep with timeout=10s, and the negative
case, a timeout=1.0s deadline expected to fire within [1.0, 3.0)s), so they hold
as they did. A check that finds
nothing is an `lstat` that fails with `ENOENT`: the 25 extra checks in the first
200ms (35 against 10) cost microseconds each.
"""

from __future__ import annotations

import time
from collections.abc import Callable

#: The wait after a refused check never falls below this (so a bind in the first 20ms is seen
#: within it), ...
_POLL_FIRST_S = 0.002

#: ... never rises above this (the fixed interval this schedule replaced, which bounds the
#: overshoot of a bind or a deadline), ...
_POLL_LAST_S = 0.02

#: ... and between them is this share of the time already spent waiting.
_POLL_SHARE = 0.1


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


def _next_wait(elapsed: float) -> float:
    """How long to sleep before asking again, `elapsed` seconds after the first ask: a tenth of
    `elapsed`, kept between `_POLL_FIRST_S` and `_POLL_LAST_S`. Pure."""
    return min(_POLL_LAST_S, max(_POLL_FIRST_S, elapsed * _POLL_SHARE))


def poll_ready(ready: Callable[[], bool], *, channel: str, endpoint: str, timeout: float) -> None:
    """Block until `ready()` is true, asked on the schedule in this module's docstring
    (`_next_wait`), or raise a named timeout: `Process.wait_ready`'s loop, with the runtime's
    own readiness (`Runtime.ready`, decision-184) as `ready`.

    Whatever `ready()` raises propagates at once, never waited out: a
    runtime's `EndpointRefused` (decision-185) is a refusal, not "not yet".

    Raises:
        WaitReadyTimeout: `ready()` was still false `timeout` seconds after
            entry.
    """
    started = time.monotonic()
    deadline = started + timeout
    while not ready():
        now = time.monotonic()
        if now >= deadline:
            raise WaitReadyTimeout(channel, endpoint, timeout)
        time.sleep(_next_wait(now - started))
