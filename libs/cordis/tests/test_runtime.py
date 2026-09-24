"""The guarantees an author gets without writing for them."""

import asyncio
from typing import Any, Protocol, runtime_checkable

import pytest

from cordis import (
    Context,
    ContractViolation,
    Effects,
    Inspection,
    Runtime,
    State,
    Undo,
    background,
    bind,
    component,
    effect,
    use,
)


def step(ctx: Context, log: list[str], name: str) -> tuple[str, Undo]:
    log.append(f"do {name}")
    return name, lambda: log.append(f"undo {name}")


def failing_step(ctx: Context, log: list[str]) -> tuple[None, Undo]:
    log.append("do boom")
    raise RuntimeError("index build failed")


# -- ordering --------------------------------------------------------------------------


async def test_undos_run_last_in_first_out() -> None:
    log: list[str] = []

    @component
    async def three() -> Effects:
        yield effect(step, log, "one")
        yield effect(step, log, "two")
        yield effect(step, log, "three")

    rt = Runtime()
    f = rt.mount(three)
    await rt.settle()
    assert log == ["do one", "do two", "do three"]
    await f.retire()
    await rt.settle()
    assert log[3:] == ["undo three", "undo two", "undo one"]


async def test_a_failure_part_way_reverts_only_what_landed() -> None:
    log: list[str] = []

    @component
    async def partial() -> Effects:
        yield effect(step, log, "one")
        yield effect(failing_step, log)
        yield effect(step, log, "never")

    rt = Runtime()
    f = rt.mount(partial)
    await rt.settle()
    assert f.state is State.FAILED
    assert isinstance(f.error, RuntimeError)
    assert log == ["do one", "do boom", "undo one"]
    assert Inspection(rt).bindings == {}


async def test_a_dependency_is_readable_during_teardown_and_dependents_go_first() -> None:
    order: list[str] = []

    @component
    async def provider() -> Effects:
        yield effect(step, order, "provider")
        yield bind("thing", "value")

    @component
    async def consumer(*, thing: Any) -> Effects:
        def undo() -> None:
            order.append(f"consumer teardown still sees {thing}")

        yield effect(lambda ctx: (None, undo))

    rt = Runtime()
    p = rt.mount(provider)
    rt.mount(consumer)
    await rt.settle()
    await p.retire()
    await rt.settle()
    assert order == [
        "do provider",
        "consumer teardown still sees value",  # the dependent unwound first
        "undo provider",
    ]


# -- reactivity ------------------------------------------------------------------------


async def test_replacing_a_binding_reloads_exactly_its_dependents() -> None:
    seen: list[str] = []

    @component
    async def p(*, config: dict[str, Any] | None = None) -> Effects:
        yield bind("k", (config or {}).get("v", "first"))

    @component
    async def dependent(*, k: Any) -> Effects:
        seen.append(k)
        yield bind("dependent", k)

    @component
    async def unrelated() -> Effects:
        seen.append("unrelated loaded")
        yield bind("unrelated", True)

    rt = Runtime()
    first = rt.mount(p)
    rt.mount(dependent)
    rt.mount(unrelated)
    await rt.settle()
    assert sorted(seen) == ["first", "unrelated loaded"]

    await first.retire()
    rt.mount(p, config={"v": "second"})
    await rt.settle()
    assert seen[-1] == "second"
    assert seen.count("unrelated loaded") == 1  # unrelated never reloaded


async def test_a_dependent_waits_and_activates_when_its_provider_appears() -> None:
    @component
    async def dependent(*, k: Any) -> Effects:
        yield bind("dependent", k)

    @component
    async def p() -> Effects:
        yield bind("k", 1)

    rt = Runtime()
    d = rt.mount(dependent)
    await rt.settle()
    assert d.state is State.INACTIVE
    assert Inspection(rt).waiting_on(d) == ["k"]
    assert "waiting on: k" in Inspection(rt).explain("dependent")

    rt.mount(p)
    await rt.settle()
    assert d.state is State.ACTIVE


async def test_a_failed_fiber_is_never_retried() -> None:
    attempts: list[int] = []

    @component
    async def flaky(*, k: Any) -> Effects:
        attempts.append(1)
        raise RuntimeError("no")
        yield  # pragma: no cover

    @component
    async def p() -> Effects:
        yield bind("k", 1)

    rt = Runtime()
    first = rt.mount(p)
    f = rt.mount(flaky)
    await rt.settle()
    assert f.state is State.FAILED and len(attempts) == 1

    await first.retire()  # take the dependency away and put it back
    rt.mount(p)
    await rt.settle()
    assert f.state is State.FAILED and len(attempts) == 1


# -- realms ----------------------------------------------------------------------------


async def test_an_isolated_key_is_private_to_the_subtree() -> None:
    @component
    async def host_ui() -> Effects:
        yield bind("ui", "host")

    @component
    async def session_ui() -> Effects:
        yield bind("ui", "session")

    @component
    async def reader(*, ui: Any) -> Effects:
        yield bind("seen", ui)

    @component
    async def session() -> Effects:
        yield use(session_ui)
        yield use(reader)

    rt = Runtime()
    rt.mount(host_ui)
    rt.mount(session, isolate=["ui", "seen"])
    await rt.settle()
    assert rt.root.get("ui") == "host"  # the host's binding is untouched
    seen = next(f for f in Inspection(rt).fibers if f.name == "reader")
    assert seen.ctx.get("seen") == "session"  # and the session's reader saw its own


async def test_a_sealed_subtree_sees_only_what_it_was_exposed_and_keeps_the_rest() -> None:
    """`use(..., expose=...)`: an allowlist realm. The subtree reads only the exposed keys from
    outside; any other key it reads is bound by nothing outside, and any key it binds (even
    one the host binds too) is its own, invisible outside and never an AlreadyBound."""
    heard: list[str] = []

    @component
    async def host() -> Effects:
        yield bind("tools", "the host's tools")
        yield bind("loader", "the host's loader")
        yield bind("llm", "the host's model")

    @component
    async def wants_tools(*, tools: Any) -> Effects:
        heard.append(tools)
        yield bind("llm", "a sealed model")  # the host binds `llm` too

    @component
    async def wants_loader(*, loader: Any) -> Effects:
        heard.append(loader)  # pragma: no cover
        yield bind("x", 1)  # pragma: no cover

    @component
    async def reads_its_own(*, llm: Any) -> Effects:
        heard.append(llm)
        yield bind("seen", llm)

    @component
    async def sealed() -> Effects:
        yield use(wants_tools)
        yield use(wants_loader)
        yield use(reads_its_own)  # a child of the sealed subtree inherits the seal

    rt = Runtime()
    rt.mount(host)
    outer = rt.mount(sealed, expose=["tools"])
    await rt.settle()
    assert sorted(heard) == ["a sealed model", "the host's tools"]  # never the loader
    assert rt.root.get("llm") == "the host's model"  # the sealed bind didn't leak or collide
    assert rt.root.get("seen") is None
    waiting = next(f for f in Inspection(rt).fibers if f.name == "wants_loader")
    assert waiting.state is State.INACTIVE and Inspection(rt).waiting_on(waiting) == ["loader"]
    await outer.retire()
    await rt.shutdown()


# -- provides ---------------------------------------------------------------------------


async def test_a_fiber_that_declares_a_key_it_never_bound_fails_at_activation() -> None:
    @component(provides=("a", "b"))
    async def half() -> Effects:
        yield bind("a", 1)  # "b" was declared but never bound

    rt = Runtime()
    f = rt.mount(half)
    await rt.settle()
    assert f.state is State.FAILED
    assert "declared provides ['b']" in str(f.error)
    assert "never bound it" in str(f.error)


async def test_check_provided_does_not_mask_the_setup_failure_it_ran_after() -> None:
    @component(provides=("a", "b"))
    async def half() -> Effects:
        yield bind("a", 1)
        raise RuntimeError("boom")
        yield bind("b", 2)  # pragma: no cover

    rt = Runtime()
    f = rt.mount(half)
    await rt.settle()
    assert f.state is State.FAILED
    assert isinstance(f.error, RuntimeError)  # the real failure, not check_provided's
    assert str(f.error) == "boom"


# -- contracts -------------------------------------------------------------------------


async def test_a_contract_must_be_runtime_checkable() -> None:
    class NotCheckable(Protocol):
        def go(self) -> None: ...

    @component
    async def p() -> Effects:
        yield bind("thing", object())

    @component
    async def c(*, thing: NotCheckable) -> Effects:
        yield bind("x", 1)  # pragma: no cover

    rt = Runtime()
    rt.mount(p)
    f = rt.mount(c)
    await rt.settle()
    assert "Decorate the Protocol with @runtime_checkable" in str(f.error)


async def test_a_contract_names_what_the_value_is_missing_and_holds_only_its_consumer() -> None:
    @runtime_checkable
    class Net(Protocol):
        async def send(self, msg: str) -> str: ...
        async def close(self) -> None: ...

    @runtime_checkable
    class Sender(Protocol):
        async def send(self, msg: str) -> str: ...

    class HalfNet:
        async def send(self, msg: str) -> str:
            return msg

    @component
    async def p() -> Effects:
        yield bind("net", HalfNet())

    @component
    async def wants_all(*, net: Net) -> Effects:
        yield bind("a", 1)  # pragma: no cover

    @component
    async def wants_send(*, net: Sender) -> Effects:
        yield bind("b", 1)

    rt = Runtime()
    rt.mount(p)
    strict, lenient = rt.mount(wants_all), rt.mount(wants_send)
    await rt.settle()
    assert isinstance(strict.error, ContractViolation) and "missing close" in str(strict.error)
    assert strict.state is State.FAILED
    assert lenient.state is State.ACTIVE  # two consumers, two contracts, one provider


# -- teardown robustness -----------------------------------------------------------------


async def test_an_undo_that_raises_does_not_strand_the_fiber() -> None:
    log: list[str] = []

    def angry(ctx: Context) -> tuple[None, Undo]:
        def undo() -> None:
            raise RuntimeError("teardown exploded")

        return None, undo

    @component
    async def holder() -> Effects:
        yield effect(step, log, "first")
        yield effect(angry)

    rt = Runtime()
    f = rt.mount(holder)
    await rt.settle()
    await f.retire()
    await rt.settle()
    assert log == ["do first", "undo first"]  # the other undo still ran
    assert any(e.kind == "teardown-error" for e in Inspection(rt).events)
    assert Inspection(rt).fibers == []


async def test_shutdown_unwinds_the_whole_tree() -> None:
    @component
    async def leaf() -> Effects:
        yield bind("leaf", True)

    @component
    async def branch() -> Effects:
        yield use(leaf)
        yield bind("branch", True)

    rt = Runtime()
    rt.mount(branch)
    await rt.settle()
    assert len(Inspection(rt).fibers) == 2
    await rt.shutdown()
    assert Inspection(rt).fibers == [] and Inspection(rt).bindings == {}


# -- the read-only view --------------------------------------------------------------------


async def test_explain_reads_as_a_diagnosis() -> None:
    @component
    async def p() -> Effects:
        yield bind("k", 1)

    @component
    async def dependent(*, k: Any) -> Effects:
        yield bind("dependent", k)

    rt = Runtime()
    rt.mount(p)
    rt.mount(dependent)
    await rt.settle()
    text = Inspection(rt).explain("dependent")
    assert "dependent#" in text and "active" in text
    assert "binds: dependent" in text
    assert "performed: bind(dependent, 1)" in text
    assert "uses: k#" in text
    assert Inspection(rt).explain("absent") == "absent: not mounted"


async def test_explain_says_active_work_failed_when_owned_background_work_dies() -> None:
    @component
    async def worker() -> Effects:
        async def boom() -> None:
            raise RuntimeError("bang")

        yield background(boom())

    rt = Runtime()
    rt.mount(worker)
    await rt.settle()
    with pytest.raises(RuntimeError, match="bang"):
        await asyncio.wait_for(rt.idle(), 2)
    text = Inspection(rt).explain("worker")
    assert "worker#" in text and ": active, work failed" in text
    assert "error: RuntimeError('bang')" in text


async def test_a_stale_background_failure_does_not_survive_a_reload() -> None:
    calls = 0

    @component
    async def p(*, config: dict[str, Any] | None = None) -> Effects:
        yield bind("k", (config or {}).get("v", "first"))

    @component
    async def worker(*, k: Any) -> Effects:
        nonlocal calls

        async def flaky() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("bang")

        yield background(flaky())

    rt = Runtime()
    first = rt.mount(p)
    w = rt.mount(worker)
    await rt.settle()
    with pytest.raises(RuntimeError, match="bang"):
        await asyncio.wait_for(rt.idle(), 2)
    assert w.error is not None

    await first.retire()  # unsatisfies worker, then a fresh p resatisfies it: a real reload
    rt.mount(p, config={"v": "second"})
    await rt.settle()
    assert w.state is State.ACTIVE
    assert w.error is None  # the earlier failure must not outlive the reload that moved past it


async def test_an_inspection_keeps_reading_live_state() -> None:
    @component
    async def p() -> Effects:
        yield bind("k", 1)

    rt = Runtime()
    view = Inspection(rt)
    assert view.bindings == {}
    f = rt.mount(p)
    await rt.settle()
    assert set(view.bindings) == {"k"}
    await f.retire()
    await rt.settle()
    assert view.bindings == {}


@pytest.mark.parametrize("bad", ["not a component", 42])
def test_mounting_something_that_is_not_a_component_says_so(bad: Any) -> None:
    rt = Runtime()
    with pytest.raises(TypeError, match="is not a component"):
        rt.mount(bad)


async def test_settle_means_no_transition_in_flight() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @component
    async def slow() -> Effects:
        started.set()
        await release.wait()
        yield bind("k", 1)

    rt = Runtime()
    await rt.settle()  # nothing mounted: returns at once
    f = rt.mount(slow)
    waiter = asyncio.ensure_future(rt.settle())
    await started.wait()
    await asyncio.sleep(0)
    assert (waiter.done(), f.state) == (False, State.LOADING)
    release.set()
    await waiter
    assert f.state is State.ACTIVE


async def test_a_context_is_read_only() -> None:
    rt = Runtime()
    fiber = rt.mount(_no_effects)
    ctx = fiber.ctx
    for attr in ("runtime", "fiber", "isolate"):
        with pytest.raises(AttributeError):
            setattr(ctx, attr, None)
    assert ctx.runtime is rt and ctx.fiber is fiber and ctx.isolate == {}
    assert rt.root.fiber is rt.root_fiber and rt.root_fiber.parent is None


@component
async def _no_effects() -> Effects:
    return
    yield
