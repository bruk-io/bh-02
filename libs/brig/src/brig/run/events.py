"""Stamping: turning a mechanism's `EventPayload` into a `core.Event`.

`Event`, `EventKind`, `EVENT_VERSION` and `DataValue` are pure data and live
in `brig/core/events.py`. This module imports them from `brig.core` rather
than defining its own copy (`brig.run.Event is brig.core.Event` holds, proven
by `tests/unit/test_public_surface.py`).

What stays here, per decision-052 point 2 ("The run-layer appender supplies
the clock") as amended by decision-152: `run` is still the only layer that
reads a clock in the event path, and it is still the only layer permitted to
stamp `ts` and `jail_id`. What it no longer does is WRITE. decision-152
(2026-09-08) deleted `EventLog` and the per-jail `events.jsonl` file it
appended to; `stamp`/`stamp_all` below are what replaced it, and the stamped
`Event`s are RETURNED to the embedder -- on `Handle.compile_events` for the
facts a sensor knows at compile time, and from `Handle.exit_events()` for the
ones a sensor can only make of an ending.

The atomicity claim this module's docstring used to carry went with the file:
there is no file, no `O_APPEND` fd, and no concurrent-appender question left
to answer. An embedder that wants a durable log writes these records into its
own, where the atomicity question is its own log's to answer -- which is the
whole reason the stream is gone: brig was shipping a second, worse log beside
every embedder's real one.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

from brig.core import EVENT_VERSION as EVENT_VERSION
from brig.core import DataValue as DataValue
from brig.core import Event as Event
from brig.core import EventKind as EventKind
from brig.mech import EventPayload


def stamp(
    payload: EventPayload,
    jail_id: str,
    *,
    clock: Callable[[], float] = time.time,
) -> Event:
    """One `EventPayload` plus the two fields only `run` may supply.

    `EventPayload.__post_init__` already refuses a payload whose `data`
    carries `ts` or `jail_id`, so this can never overwrite a mechanism's
    own key: a mechanism that tried is refused at construction, loudly,
    rather than silently corrected here.
    """
    return Event(ts=clock(), kind=payload.kind, jail_id=jail_id, data=payload.data)


def stamp_all(
    payloads: Iterable[EventPayload],
    jail_id: str,
    *,
    clock: Callable[[], float] = time.time,
) -> tuple[Event, ...]:
    """`stamp` over an iterable, order preserved."""
    return tuple(stamp(payload, jail_id, clock=clock) for payload in payloads)
