"""The `executor` value: where the loop runs what may block, off the event loop, one call at a time.

`agent:loop` reads the prompt (every section function, which may read many files and search the
project) and asks `memory` (whose functions may read rule files) here, never on the event loop,
which the TUI shares: a slow section freezes nothing. Nothing stops such a call part-way, so a
reply stopped meanwhile leaves it running to its end, unused; the next call waits for it rather
than starting beside it, so however often a reply is stopped, one runs at a time.

The value is a row of its own (`agent:executor`) that depends on nothing, so a loop that reloads
(`/clear`, `/model`) keeps it, and with it the call in flight: the `system` value's caches, and
what a `memory` function keeps, outlive the loop too and take no lock. Only a new `executor`
(its row restarted, or replaced by a layer) starts a call beside one the last one left running.

Each call runs in a daemon thread of its own, not the default executor (`asyncio.to_thread`'s),
whose threads `asyncio.run` and the interpreter join as they end: a call left running never holds
bh-02 open, and its answer to an event loop that has closed goes nowhere.
"""

import asyncio
import contextlib
import threading
from collections.abc import Callable
from typing import cast

__all__ = ["OneAtATime"]

# How a call ended: its result, or what it raised. A future holds it as its result, never as its
# exception, so one nobody waits for any more (its reply was stopped) leaves asyncio nothing to log.
type _Outcome = tuple[object, BaseException | None]


def _settle(
    loop: asyncio.AbstractEventLoop, future: asyncio.Future[_Outcome], fn: Callable[[], object]
) -> None:
    """What the thread `OneAtATime.run` starts runs: `fn()`, and how it ended handed to `future`
    on `loop` (`call_soon_threadsafe`: only the event loop's thread may set it). An event loop
    closed meanwhile (bh-02 left while `fn` ran) is told nothing: nobody waits."""
    result: object = None
    error: BaseException | None = None
    try:
        result = fn()
    except BaseException as raised:  # handed on, as `asyncio.to_thread` would, to whoever waits
        error = raised
    with contextlib.suppress(RuntimeError):  # 'Event loop is closed'
        loop.call_soon_threadsafe(_settled, future, (result, error))


def _settled(future: asyncio.Future[_Outcome], outcome: _Outcome) -> None:
    """`_settle`'s outcome, set on the event loop's own thread."""
    if not future.done():  # nothing cancels it (it is only waited for), but a done one can't be set
        future.set_result(outcome)


class OneAtATime:
    """Implements `Executor` (CONTRACTS.md: executor): `await run(fn)` is `fn()` in a daemon
    thread, once the call before it has ended, and its result, or what it raised.

    A caller stopped while it waits (a stopped reply) stops waiting, and nothing else: the call
    it was waiting for runs to its end in its thread, for the next to wait on, and how it ended
    is dropped, logged nowhere. Neither the wait for the call before nor the wait for its own
    cancels a call."""

    def __init__(self) -> None:
        # the call last started, which a stopped reply may have left running
        self._working: asyncio.Future[_Outcome] | None = None

    async def run[T](self, fn: Callable[[], T]) -> T:
        while self._working is not None and not self._working.done():
            await asyncio.wait([self._working])  # never cancels it
        loop = asyncio.get_running_loop()
        working: asyncio.Future[_Outcome] = loop.create_future()
        threading.Thread(
            target=_settle, args=(loop, working, fn), name="bh-02 agent:executor", daemon=True
        ).start()
        self._working = working
        await asyncio.wait([working])  # a stop ends this wait, never the call
        result, error = working.result()
        if error is not None:
            raise error
        return cast(T, result)
