"""A running jail's egress, live (decision-0012 items 4 and 6): what is granted reaches the jail's
proxy while the program runs, and what the proxy refuses becomes a question while the call runs.

`Egress` is one jail's: it follows the broker's `on_change` (a destination granted since the jail
started is allowed, one revoked is revoked, off the event loop) and, about every `PERIOD_S`, drains
the proxy's decisions (never blocking) and puts each refusal to the person through the broker: a
destination that was not granted is asked as the name, one that resolved to a private address as
that IP literal alone (never a wildcard), and what cannot be granted (an unresolved name, an
address or authority that could not be read) is told to the model instead, through the broker.

The jail is reached through `_Wire`, a seam: `jail` makes the one over brig, so nothing here imports
brig and a test drives it with a fake.
"""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from runner_cordis_plugin import prompting
from runner_cordis_plugin.broker import Outcome
from runner_cordis_plugin.grants import Asker, Grant, Grants, Invalid, Kind, Request, Source

__all__ = ["PERIOD_S", "Decision", "Egress", "Ended"]

#: How often a jail's decisions are drained.
PERIOD_S = 0.2


class Ended(Exception):
    """A change was sent to a jail whose proxy has ended: the jail is ending, and nothing was sent."""


class _Named(Protocol):
    """A destination a decision names."""

    @property
    def host(self) -> str: ...
    @property
    def port(self) -> int: ...


class Decision(Protocol):
    """What the egress needs of one decision of a jail's proxy (brig's `EgressDecision`): `verdict`
    (`allowed` or `refused`), the `destination` the request named, `reason` (`not-granted`,
    `private-address`, `unresolved`, `address-unparseable`, `authority-unparseable`) and `address`
    (the private address a name resolved to, else '')."""

    @property
    def verdict(self) -> str: ...
    @property
    def destination(self) -> _Named: ...
    @property
    def reason(self) -> str: ...
    @property
    def address(self) -> str: ...


class _Wire(Protocol):
    """A running jail's egress as `Egress` needs it."""

    def allow(self, grant: Grant) -> None:
        """Grant `grant`'s destination to the running jail.

        Raises:
            Ended: the jail's proxy has ended."""
        ...

    def revoke(self, grant: Grant) -> None:
        """Take `grant`'s destination back (an open connection stays open).

        Raises:
            Ended: the jail's proxy has ended."""
        ...

    def decisions(self) -> Iterable[Decision]:
        """The decisions made since the last call; never blocks."""
        ...

    def ended(self) -> bool:
        """Whether the jail is gone, and its decisions need no more draining."""
        ...


class _Brokered(Protocol):
    """What `Egress` needs of the `grants` value (CONTRACTS.md: grants)."""

    async def granted(self) -> Grants: ...
    async def ask(self, request: Request) -> Outcome: ...
    def tell(self, text: str) -> None: ...
    def on_change(self, fn: Callable[[], None]) -> Callable[[], None]: ...


@dataclass(frozen=True, slots=True)
class _Ask:
    """A refusal that is put to the person."""

    request: Request


@dataclass(frozen=True, slots=True)
class _Tell:
    """A refusal that is told to the model: there is nothing to ask."""

    text: str


def _judged(decision: Decision, owner: str) -> _Ask | _Tell | None:
    """What a decision of the proxy comes to: nothing when it allowed, an ask for a destination
    that was not granted (as the name) or one that resolved to a private address (as that address
    alone, the name is never offered), else a tell. `owner` is the row that started the program."""
    if decision.verdict != "refused":
        return None
    host, port = decision.destination.host, decision.destination.port
    match decision.reason:
        case "not-granted":
            target = host
        case "private-address" if decision.address:
            target = decision.address
        case reason:
            return _Tell(prompting.unasked(reason, host, port))
    try:
        grant = Grant(Kind.NET, target, port)
    except Invalid as error:
        return _Tell(prompting.ungrantable(host, port, str(error)))
    why = prompting.refusal_reason(host, port, decision.reason, decision.address)
    return _Ask(Request(grant, Asker(Source.INPUT, owner), why))


class Egress:
    """One running jail's live egress: `held` are the destinations its proxy was given (what the
    start passed), kept current from the broker's changes. `begin` starts it, `end` stops it and
    waits for what it started."""

    def __init__(
        self,
        wire: _Wire,
        grants: _Brokered,
        *,
        owner: str,
        held: Iterable[Grant],
        period: float = PERIOD_S,
    ) -> None:
        self._wire = wire
        self._grants = grants
        self._owner = owner
        self._held = set(held)
        self._period = period
        self._unsubscribe: Callable[[], None] | None = None
        self._dirty = False
        self._syncing: asyncio.Task[None] | None = None
        self._polling: asyncio.Task[None] | None = None
        self._asks: dict[Grant, asyncio.Task[Outcome]] = {}
        self._told: set[str] = set()

    def begin(self) -> None:
        """Follow the broker and drain the proxy's decisions, until `end` or the jail's own end.
        Catches up at once with what was granted since the start read it."""
        loop = asyncio.get_running_loop()
        self._unsubscribe = self._grants.on_change(self._changed)
        self._polling = loop.create_task(self._poll())
        self._changed()

    async def end(self) -> None:
        """Stop following and polling, and wait for the tasks to end."""
        self._stop_following()
        tasks = [task for task in (self._polling, self._syncing, *self._asks.values()) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _stop_following(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _changed(self) -> None:
        self._dirty = True
        if self._syncing is None or self._syncing.done():
            self._syncing = asyncio.get_running_loop().create_task(self._sync())

    async def _sync(self) -> None:
        """Make the jail hold what is granted: the destinations it holds that are no longer granted
        are revoked and the ones it lacks are allowed, off the event loop."""
        while self._dirty:
            self._dirty = False
            granted = set((await self._grants.granted()).of(Kind.NET))
            try:
                for grant in sorted(self._held - granted, key=str):
                    await asyncio.to_thread(self._wire.revoke, grant)
                    self._held.discard(grant)
                for grant in sorted(granted - self._held, key=str):
                    await asyncio.to_thread(self._wire.allow, grant)
                    self._held.add(grant)
            except Ended:
                return  # the jail is ending
            except Exception as error:
                self._grants.tell(prompting.unapplied(error))

    async def _poll(self) -> None:
        try:
            while not self._wire.ended():
                for decision in self._wire.decisions():
                    self._refused(decision)
                await asyncio.sleep(self._period)
        finally:
            self._stop_following()

    def _answered(self, grant: Grant, _: asyncio.Future[Outcome]) -> None:
        self._asks.pop(grant, None)

    def _refused(self, decision: Decision) -> None:
        match _judged(decision, self._owner):
            case None:
                return
            case _Tell(text=text):
                if text not in self._told:
                    self._told.add(text)
                    self._grants.tell(text)
            case _Ask(request=request):
                grant = request.grant
                if grant not in self._asks:  # one question, whatever the repeats
                    task = asyncio.get_running_loop().create_task(self._grants.ask(request))
                    self._asks[grant] = task
                    task.add_done_callback(partial(self._answered, grant))
