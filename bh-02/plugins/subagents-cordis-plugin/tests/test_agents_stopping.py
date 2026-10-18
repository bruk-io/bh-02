"""`Agents` itself, with a child mounted by a fake (the cordis performer is the boundary): what
`/agents stop` does about a child that ends on its own meanwhile, and what a background run that
failed and was never waited for leaves behind."""

import asyncio
import gc
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any

from subagents_cordis_plugin import GENERAL, Agents, AgentsConfig, AgentType, ChildRow, Hand

type Json = Mapping[str, Any]


class _Screen:
    """The parent's `output`: the person says yes, and what is shown is dropped."""

    async def confirm(self, question: Json) -> bool:
        return True

    async def show(self, events: AsyncIterator[Json]) -> None:
        async for _ in events:
            pass


class _NoRows:
    """The parent's `loader`: it mounted no rows, so a child has only its own two."""

    rows: Mapping[str, Any] = {}


class _Reply:
    """A child's loop: its reply begins (`begun`), then waits to be let finish, then answers."""

    def __init__(self, fails: bool = False) -> None:
        self.begun, self.finish = asyncio.Event(), asyncio.Event()
        self.fails = fails  # its loop has a bug: its reply raises

    async def reply(self, message: str) -> AsyncIterator[Json]:
        self.begun.set()
        if self.fails:
            raise RuntimeError("a bug in the child's loop")
        await self.finish.wait()
        yield {"type": "text", "text": "done"}
        yield {"type": "stop", "reason": "answered"}


class _Mounted:
    """A mounted child: retiring it waits for `released`, then says it is gone (its row leaving)."""

    def __init__(self, gone: Callable[[], None], released: asyncio.Event) -> None:
        self._gone, self._released = gone, released

    async def retire(self) -> None:
        await self._released.wait()
        self._gone()

    def stalled(self) -> str:
        return ""


class _Mounts:
    """The way `Agents` mounts a child: each child's loop is passed through the `hand` its rows
    carry, as the `subagents:child` row would, and its retirement is held until `released[name]`."""

    def __init__(self, *names: str, fails: bool = False) -> None:
        self.replies = {name: _Reply(fails) for name in names}
        self.released = {name: asyncio.Event() for name in names}

    async def __call__(self, name: str, rows: Sequence[ChildRow]) -> _Mounted:
        hand: Hand = next(row.config["hand"] for row in rows if "hand" in row.config)
        return _Mounted(hand.give(self.replies[name]), self.released[name])


async def _types() -> Mapping[str, AgentType | str]:
    return {"general": GENERAL}


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(10):
        while not condition():
            await asyncio.sleep(0.01)


async def _bounded[T](awaitable: Awaitable[T], seconds: float = 10) -> T:
    async with asyncio.timeout(seconds):
        return await awaitable


async def test_stopping_all_skips_a_child_that_ended_on_its_own_while_an_earlier_stop_was_awaited() -> None:
    """general-1 is being retired (slowly) when general-2 finishes by itself: the stop goes on to
    the children that are still there, and says it stopped only general-1."""
    mounts = _Mounts("general-1", "general-2")
    agents = Agents(_NoRows(), mounts, _Screen(), _types, AgentsConfig())
    for _ in range(2):
        await _bounded(agents.agent({"prompt": "p", "type": "general", "background": True}))
    await _bounded(asyncio.gather(*(reply.begun.wait() for reply in mounts.replies.values())))
    stopping = asyncio.ensure_future(agents.command("stop"))
    await _until(lambda: agents.running() == 1)  # general-1 is stopped, its retirement waits
    mounts.replies["general-2"].finish.set()
    mounts.released["general-2"].set()
    await _until(lambda: agents.running() == 0)  # general-2 answered and left on its own
    mounts.released["general-1"].set()
    said = await _bounded(stopping)
    assert said == "Stopped general-1: each conversation ended, with its python program."
    assert await _bounded(agents.command("")) == "No sub-agents are running."
    await _bounded(agents.held()())


async def _failing_in_the_background() -> None:
    """One background child whose loop has a bug, run to its end by an `Agents` nothing keeps."""
    mounts = _Mounts("general-1", fails=True)
    mounts.released["general-1"].set()
    agents = Agents(_NoRows(), mounts, _Screen(), _types, AgentsConfig())
    await _bounded(agents.agent({"prompt": "p", "type": "general", "background": True}))
    await _until(lambda: agents.running() == 0)  # the run ended, with the failure
    await asyncio.sleep(0)


async def test_a_background_run_that_failed_and_was_never_waited_for_leaves_no_failure_unretrieved() -> None:
    """A bug in a child's loop ends its run with the failure (the event log says so); when no
    `agent_wait` ever collects it, asyncio must not log it as a task exception never retrieved."""
    heard: list[Json] = []
    asyncio.get_running_loop().set_exception_handler(lambda loop, context: heard.append(context))
    await _failing_in_the_background()
    gc.collect()
    assert heard == []
