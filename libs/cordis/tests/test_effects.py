"""Effects: the deferred step, its undo, and the ones the framework ships."""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol, runtime_checkable

import pytest

from cordis import (
    AlreadyBound,
    Context,
    ContractViolation,
    Effect,
    Effects,
    Event,
    Inspection,
    Performer,
    Runtime,
    State,
    Undo,
    acquire,
    background,
    bind,
    component,
    effect,
    enter,
    observe,
    performer,
    use,
)


def subscribe_step(ctx: Context, feed: list[str]) -> tuple[str, Undo]:
    feed.append("subscribed")
    return "sub", lambda: feed.append("unsubscribed")


def note_step(ctx: Context, log: list[str], what: str) -> tuple[str, None]:
    """A step that changes nothing reversible."""
    log.append(what)
    return what.upper(), None


# -- the value ---------------------------------------------------------------------


def test_an_effect_is_deferred_and_prints_as_its_call() -> None:
    feed: list[str] = []
    e = effect(subscribe_step, feed)
    assert isinstance(e, Effect)
    assert feed == []  # nothing has happened yet
    assert e.name == "subscribe"  # the _step suffix is the convention, not the name
    assert str(e) == "subscribe([])"


def test_a_step_is_a_plain_function_testable_on_its_own() -> None:
    feed: list[str] = []
    result, undo = subscribe_step(object(), feed)  # type: ignore[arg-type]
    assert result == "sub" and feed == ["subscribed"]
    undo()
    assert feed == ["subscribed", "unsubscribed"]


async def test_an_undo_may_be_none() -> None:
    log: list[str] = []
    result, undo = note_step(object(), log, "hello")  # type: ignore[arg-type]  # a step is a plain function
    assert result == "HELLO" and undo is None


async def test_a_step_that_does_not_return_a_pair_says_so() -> None:
    def bad_step(ctx: Context) -> Any:
        return "just a value"

    @component
    async def wrong() -> Effects:
        yield effect(bad_step)

    rt = Runtime()
    fiber = rt.mount(wrong)
    await rt.settle()
    assert fiber.state is State.FAILED
    assert "a step returns (result, undo)" in str(fiber.error)


async def test_a_step_whose_undo_is_not_callable_says_so() -> None:
    def odd_step(ctx: Context) -> Any:
        return "value", "not an undo"

    @component
    async def wrong() -> Effects:
        yield effect(odd_step)

    rt = Runtime()
    fiber = rt.mount(wrong)
    await rt.settle()
    assert fiber.state is State.FAILED
    assert "returned a str as its undo" in str(fiber.error)


async def test_yielding_a_non_effect_names_the_component_and_the_fix() -> None:
    @component
    async def confused() -> Effects:
        yield "not an effect"  # type: ignore[misc]

    rt = Runtime()
    f = rt.mount(confused)
    await rt.settle()
    assert f.state is State.FAILED
    assert "confused yielded a str" in str(f.error)
    assert "yield bind(key, value)" in str(f.error)


# -- the five ------------------------------------------------------------------------


async def test_bind_binds_and_the_undo_unbinds() -> None:
    @component
    async def p() -> Effects:
        yield bind("greeting", "hello")

    rt = Runtime()
    f = rt.mount(p)
    await rt.settle()
    assert Inspection(rt).bindings["greeting"].value == "hello"
    await f.retire()
    await rt.settle()
    assert Inspection(rt).bindings == {}


async def test_bind_refuses_a_second_binding_of_one_key_and_names_the_owner() -> None:
    @component
    async def p() -> Effects:
        yield bind("k", 1)

    rt = Runtime()
    first = rt.mount(p, id="first")
    second = rt.mount(p, id="second")
    await rt.settle()
    assert second.state is State.FAILED
    assert isinstance(second.error, AlreadyBound)
    assert "first#" in str(second.error) and "isolate" in str(second.error)
    assert first.state is State.ACTIVE


async def test_a_dependency_s_annotation_is_its_contract_checked_when_committed() -> None:
    @runtime_checkable
    class Clock(Protocol):
        def now(self) -> str: ...

    @component
    async def wrong() -> Effects:
        yield bind("clock", "not a clock")  # anything goes under a name

    @component
    async def reader(*, clock: Clock) -> Effects:
        yield bind("time", clock.now())  # pragma: no cover - never reached

    rt = Runtime()
    provider = rt.mount(wrong)
    consumer = rt.mount(reader)
    await rt.settle()
    assert provider.state is State.ACTIVE  # the provider is fine: the contract is the consumer's
    assert consumer.state is State.FAILED
    assert isinstance(consumer.error, ContractViolation)
    assert "reader: clock is bound to a str, which is missing now" in str(consumer.error)


async def test_acquire_calls_a_function_and_keeps_what_it_returns_as_the_undo() -> None:
    log: list[str] = []

    def register(name: str) -> Callable[[], None]:
        log.append(f"+{name}")
        return lambda: log.append(f"-{name}")

    @component
    async def contributor() -> Effects:
        yield acquire(register, "a")
        yield acquire(register, "b")
        yield acquire(lambda: None)  # nothing to reverse

    @component
    async def wrong() -> Effects:
        yield acquire(lambda: 42)

    rt = Runtime()
    f = rt.mount(contributor)
    await rt.settle()
    assert log == ["+a", "+b"]
    await f.retire()
    assert log == ["+a", "+b", "-b", "-a"]  # last acquired, first released
    w = rt.mount(wrong)
    await rt.settle()
    assert w.state is State.FAILED and "must be callable" in str(w.error)


async def test_enter_uses_the_context_managers_exit_as_the_undo() -> None:
    log: list[str] = []

    @asynccontextmanager
    async def resource() -> Any:
        log.append("open")
        try:
            yield "handle"
        finally:
            log.append("closed")

    @component
    async def holder() -> Effects:
        handle = yield enter(resource())
        yield bind("handle", handle)

    rt = Runtime()
    f = rt.mount(holder)
    await rt.settle()
    assert log == ["open"] and Inspection(rt).bindings["handle"].value == "handle"
    await f.retire()
    await rt.settle()
    assert log == ["open", "closed"]


async def test_enter_refuses_something_that_is_not_a_context_manager() -> None:
    @component
    async def holder() -> Effects:
        yield enter(object())  # type: ignore[arg-type]

    rt = Runtime()
    f = rt.mount(holder)
    await rt.settle()
    assert "enter expects an async context manager" in str(f.error)


async def test_use_mounts_a_child_that_is_retired_with_its_parent() -> None:
    @component
    async def child() -> Effects:
        yield bind("child", True)

    @component
    async def parent() -> Effects:
        yield use(child)
        yield bind("parent", True)

    rt = Runtime()
    f = rt.mount(parent)
    await rt.settle()
    assert set(Inspection(rt).bindings) == {"parent", "child"}
    await f.retire()
    await rt.settle()
    assert Inspection(rt).bindings == {} and Inspection(rt).fibers == []


async def test_background_work_is_owned_and_cancelled_on_unload() -> None:
    log: list[str] = []

    async def forever() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            log.append("cancelled")
            raise

    @component
    async def worker() -> Effects:
        yield background(forever())

    rt = Runtime()
    f = rt.mount(worker)
    await rt.settle()
    await f.retire()
    await rt.settle()
    assert log == ["cancelled"]


async def test_idle_returns_once_owned_work_finishes() -> None:
    done: list[str] = []

    async def quick() -> None:
        await asyncio.sleep(0.01)
        done.append("finished")

    @component
    async def worker() -> Effects:
        yield background(quick())

    rt = Runtime()
    rt.mount(worker)
    await asyncio.wait_for(rt.idle(), 2)
    assert done == ["finished"]


async def test_observe_hears_lifecycle_events_until_its_fiber_leaves() -> None:
    heard: list[str] = []

    @component
    async def watcher() -> Effects:
        yield observe(lambda event: heard.append(str(event)))

    @component
    async def greeter() -> Effects:
        yield bind("greeting", "hi")

    rt = Runtime()
    w = rt.mount(watcher, id="watch")
    await rt.settle()
    g = rt.mount(greeter, id="greet")
    await rt.settle()
    assert "bind greeting by greet#" in " ".join(heard) and any(h.startswith("active greet") for h in heard)
    await w.retire()
    await rt.settle()
    before = len(heard)
    await g.retire()
    await rt.settle()
    assert len(heard) == before  # the undo stopped the hearing


async def test_a_listener_that_raises_is_taken_off_and_the_transition_carries_on() -> None:
    calls: list[Event] = []

    def broken(event: Event) -> None:
        calls.append(event)
        raise ValueError("listener fell over")

    @component
    async def watcher() -> Effects:
        yield observe(broken)

    @component
    async def greeter() -> Effects:
        yield bind("greeting", "hi")

    rt = Runtime()
    w = rt.mount(watcher, id="watch")
    await rt.settle()
    rt.mount(greeter, id="greet")
    await rt.settle()
    assert rt.root.get("greeting") == "hi"  # the transition it was told about still happened
    assert len(calls) == 1  # heard once, then taken off
    assert isinstance(w.error, ValueError)
    assert any(e.kind == "observe-failed" for e in rt.events)
    await w.retire()  # its undo is safe after it was already taken off
    await rt.shutdown()


# -- the performer ---------------------------------------------------------------------


async def test_a_performer_mounts_later_and_its_undos_are_still_the_fibers() -> None:
    @component
    async def child() -> Effects:
        yield bind("child", True)

    host: list[Performer] = []

    @component
    async def dynamic() -> Effects:
        got: Performer = yield performer()
        host.append(got)
        yield bind("dynamic", True)

    rt = Runtime()
    f = rt.mount(dynamic)
    await rt.settle()
    assert set(Inspection(rt).bindings) == {"dynamic"}

    await host[0].perform(use(child))  # after setup finished
    await rt.settle()
    assert set(Inspection(rt).bindings) == {"dynamic", "child"}

    await f.retire()  # the later mount is still the fiber's to unwind
    await rt.settle()
    assert Inspection(rt).bindings == {} and Inspection(rt).fibers == []


async def test_a_performer_stops_working_when_its_fiber_leaves() -> None:
    host: list[Performer] = []

    @component
    async def dynamic() -> Effects:
        got: Performer = yield performer()
        host.append(got)
        yield bind("dynamic", True)

    rt = Runtime()
    f = rt.mount(dynamic)
    await rt.settle()
    await f.retire()
    await rt.settle()
    with pytest.raises(RuntimeError, match="no longer usable"):
        await host[0].perform(bind("late", 1))


async def test_a_scope_unwinds_what_was_performed_inside_it() -> None:
    @component
    async def thing() -> Effects:
        yield bind("thing", True)

    rt = Runtime()
    async with rt.scope("turn") as host:
        await host.perform(use(thing))
        await rt.settle()
        assert "thing" in Inspection(rt).bindings
    assert Inspection(rt).bindings == {} and Inspection(rt).fibers == []
