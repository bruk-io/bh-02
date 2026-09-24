"""Cancelling a caller that waits on a lifecycle transition must not wedge the fiber it waits on.

Regression: settle() and Fiber.settled() awaited the fiber's shared transition future directly,
so cancelling the waiter (Ctrl-C during a mount) cancelled the future; the fiber then failed to
end its transition and reloaded forever.
"""

import asyncio

from cordis import Effects, Inspection, Runtime, Undo, bind, component, effect


async def test_cancelling_a_waiter_while_a_fiber_loads_lets_it_finish_loading_once() -> None:
    setups = 0

    @component
    async def slow() -> Effects:
        nonlocal setups
        setups += 1
        await asyncio.sleep(0.05)
        yield bind("slow", 1)

    rt = Runtime()
    fiber = rt.mount(slow)
    waiting = asyncio.create_task(fiber.settled())
    await asyncio.sleep(0.01)
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)

    await asyncio.wait_for(rt.settle(), 2)
    await asyncio.sleep(0.2)  # a wedged fiber would keep reloading here
    assert setups == 1
    assert rt.root.get("slow") == 1


async def test_cancelling_a_waiter_while_a_fiber_unloads_lets_it_finish_unloading() -> None:
    closes = 0

    def slow_close(ctx: object) -> tuple[None, Undo]:
        async def close() -> None:
            nonlocal closes
            await asyncio.sleep(0.05)
            closes += 1

        return None, close

    @component
    async def slow() -> Effects:
        yield effect(slow_close)
        yield bind("slow", 1)

    rt = Runtime()
    fiber = rt.mount(slow)
    await rt.settle()
    waiting = asyncio.create_task(fiber.retire())
    await asyncio.sleep(0.01)
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)

    await asyncio.wait_for(rt.settle(), 2)
    assert closes == 1
    assert rt.root.get("slow") is None


async def test_retiring_a_fiber_removes_its_bindings_whatever_the_row_is_called() -> None:
    @component
    async def thing() -> Effects:
        yield bind("thing", 1)

    rt = Runtime()
    fiber = rt.mount(thing, id="renamed")
    await rt.settle()
    assert rt.root.get("thing") == 1
    assert Inspection(rt).fiber("renamed") is fiber
    await fiber.retire()
    await rt.settle()
    assert rt.root.get("thing") is None
