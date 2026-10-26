"""Asking an OpenAI-compatible endpoint which models it serves, and keeping what it said.

`Get` is the one seam to the network: `await get(url, headers)` is a `Reply` or a `Down`, never
an exception for a server that isn't there. `httpx_get` is the real one, over httpx2, and
`openai.testing.FakeGet` the tests'. `Discovery` is the cache the `models` value keeps, and it is
filled only by `refresh`, which `/model` awaits when it lists (a coroutine of its own: an async
request never blocks the event loop the TUI shares). Everything that only reads, `/model`'s
choices, the composer's completion, the status bar, reads `found` and never asks the server.

A listing is kept under the endpoint's `base_url` and where its key comes from (the variable's
name or the command, `KeySpec.label`), never under the key: what is kept is ids, and the key goes
only into the headers of the one request that asks (`Ask`). A reader never expires an entry; only
`refresh` decides to ask again, when what it has is `FRESH` seconds old or is no list at all (a
failure is never fresh, so `/model` typed again after the server was started asks at once). One that
fails drops the ids it had.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol, assert_never

import httpx2

from models_cordis_plugin.openai.listing import (
    BODY_LIMIT,
    Down,
    Listed,
    Reply,
    Unlisted,
    cleaned,
    read_listing,
)
from models_cordis_plugin.openai.wire import scrubbed

__all__ = ["FRESH", "Ask", "Discovery", "Get", "ListingKey", "httpx_get"]

FRESH: Final = 30.0  # seconds a listing is not asked for again
_CONNECT: Final = 3.0
_DEADLINE: Final = 6.0  # the whole request, however slowly a server drips its answer
_DETAIL: Final = 120  # how much of a library's error text a line quotes

# what a listing is kept under: an endpoint's base_url and where its key comes from (`KeySpec.label`)
type ListingKey = tuple[str, str | None]


class Get(Protocol):
    """The network, as `Discovery` needs it: GET `url` with `headers`, and the answer, or why there
    is none. It never raises for a request that fails; it returns `Down`."""

    async def __call__(self, url: str, headers: Mapping[str, str]) -> Reply | Down: ...


@dataclass(frozen=True, slots=True)
class Ask:
    """One request: `url`, and the `headers` it is sent with (the key, if the endpoint names
    one, is in them and nowhere else)."""

    url: str
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _Found:
    outcome: Listed | Unlisted
    at: float


async def httpx_get(
    url: str,
    headers: Mapping[str, str],
    *,
    deadline: float = _DEADLINE,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> Reply | Down:
    """GET `url` over httpx2: connecting within 3 s, the whole request within `deadline`, a
    redirect not followed (a key is sent to its `base_url` alone) and at most `BODY_LIMIT` bytes of
    an answer read and held (a chunk that would pass it is not taken), none of one that is not a
    success (a body is never quoted)."""
    try:
        async with (
            asyncio.timeout(deadline),
            httpx2.AsyncClient(
                timeout=httpx2.Timeout(deadline, connect=min(_CONNECT, deadline)), transport=transport
            ) as client,
            client.stream("GET", url, headers=dict(headers)) as response,
        ):
            if not 200 <= response.status_code < 300:
                return Reply(response.status_code, b"")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > BODY_LIMIT:  # before it is held: never more than the limit is
                    return Down(
                        f"its answer is over {BODY_LIMIT // 1024 // 1024} MiB, more than a model list is"
                    )
                body += chunk
            return Reply(response.status_code, bytes(body))
    except TimeoutError, httpx2.TimeoutException:
        return Down(f"no answer within {deadline:g} s")
    except httpx2.ConnectError as error:
        return Down(f"can't connect: {_detail(error, headers)}; is the server running?")
    except (httpx2.HTTPError, httpx2.InvalidURL, OSError) as error:
        return Down(f"the request failed ({type(error).__name__})")


def _detail(error: Exception, headers: Mapping[str, str]) -> str:
    """A library's error text for a line: without control characters, the key the request sent
    taken out, cut short."""
    return scrubbed(cleaned(str(error)), headers)[:_DETAIL]


class Discovery:
    """What endpoints listed, by `ListingKey`, and the way to ask again (module docstring). `get` is the
    network, `clock` says what time it is (seconds, steady): both are given, so a test needs neither
    a server nor a wait."""

    def __init__(self, get: Get, clock: Callable[[], float] = time.monotonic) -> None:
        self._get = get
        self._clock = clock
        self._found: dict[ListingKey, _Found] = {}

    def found(self, key: ListingKey) -> Listed | Unlisted | None:
        """What was last found for `key`, however long ago; None when it was never asked."""
        entry = self._found.get(key)
        return None if entry is None else entry.outcome

    async def refresh(self, wanted: Mapping[ListingKey, Callable[[], Awaitable[Ask | Unlisted]]]) -> None:
        """Ask for each endpoint of `wanted` (its request, made only now: it reads its key's variable
        or runs its key command) that
        has no listing, a failed one, or one `FRESH` seconds old; all at once. Whatever is kept for
        an endpoint not in `wanted` is dropped. An `Unlisted` in place of a request is the
        endpoint's answer, as when its key's line is missing."""
        now = self._clock()
        stale = {
            key: ask
            for key, ask in wanted.items()
            if (entry := self._found.get(key)) is None
            or isinstance(entry.outcome, Unlisted)
            or now - entry.at >= FRESH
        }
        outcomes = await asyncio.gather(*(self._asked(ask) for ask in stale.values()))
        at = self._clock()
        self._found = {
            key: entry for key, entry in self._found.items() if key in wanted and key not in stale
        } | {key: _Found(outcome, at) for key, outcome in zip(stale, outcomes, strict=True)}

    async def _asked(self, request: Callable[[], Awaitable[Ask | Unlisted]]) -> Listed | Unlisted:
        ask = await request()
        if isinstance(ask, Unlisted):
            return ask
        outcome = read_listing(await self._get(ask.url, ask.headers))
        match outcome:
            case Unlisted(why):
                return Unlisted(scrubbed(cleaned(why), ask.headers))
            case Listed():
                return outcome
            case _ as unreachable:
                assert_never(unreachable)
