"""The runtime: fibers, the store, and the loop that performs effects.

Section 5.1 of "A Programming Paradigm for Spatiotemporal Composability" (Shi, Zhang, Cui)
on asyncio. One runtime, one store; contexts are views over it; components are instantiated
as fibers whose lifecycle is driven by which of their dependencies currently have a binding.

Paper -> here
  revertible effect     cordis.effects.Effect: a step of the context returning (result, undo)
  effect accumulator    an AsyncExitStack entered and exited by the fiber's own task
  effect iterator       `_perform_all`: drive the generator, perform what it yields, record
                        the undo, send the result back; stop at the next step boundary once
                        the target changed
  reload / unload       one task per fiber, `_live`, whose `async with` block IS the loaded
                        lifetime: perform, wait for deactivation, drain, unwind
  service broker        the store: `realm -> _Binding(value, fiber)`, keyed by class or name
  key collision (6.6)   a dependency's annotation is its contract, checked where the value is committed

This is the shell. Every rule it acts on is a function in `cordis.decisions`; what is left
here is what must touch a task, the store or a generator, and the classes hold the state
their own methods mutate. The six effects the framework ships are at the bottom, written
as a plugin author would write one.

Uses the 3.15 builtins `frozendict` (immutable views) and `sentinel` (PEP 661). Test the
sentinel with `if target is Unsatisfied:`; a bare `case Unsatisfied:` in a `match` would be
a capture pattern. Lines marked `# 3.15:` are 3.15 additions not adopted yet.
"""

import asyncio
import inspect
import itertools
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, aclosing, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from cordis.component import Component, arguments, derive
from cordis.decisions import (
    AfterSetup,
    AfterUnload,
    Next,
    ProviderLookup,
    State,
    Target,
    Unsatisfied,
    affected,
    after_setup,
    after_unload,
    check_contract,
    check_provided,
    decide,
    resolve_target,
)
from cordis.effects import Effect, Effects, Key, Result, Undo, effect, key_name


class AlreadyBound(RuntimeError):
    """A key is already bound in this realm (the paper's bind precondition)."""


@dataclass(frozen=True, slots=True)
class _Binding:
    value: Any
    fiber: Fiber


@dataclass(eq=False, slots=True)
class Fiber:
    """A component running. Mutable by nature: it is the state machine."""

    component: Component
    parent: Context | None  # None only for the root fiber
    config: Any
    id: str | None = None
    uid: int = 0  # assigned from the runtime's own counter; see _mount
    ctx: Context = field(init=False)
    state: State = State.INACTIVE
    target: Target = Unsatisfied
    committed: frozendict[Key, Any] | None = None
    bound: set[Key] = field(default_factory=set)  # what it provides: the keys it bound
    performed: list[Effect[Any]] = field(default_factory=list)
    stack: AsyncExitStack = field(default_factory=AsyncExitStack)  # the live task's undos
    deactivate: asyncio.Event = field(default_factory=asyncio.Event)
    inertia: asyncio.Future[None] | None = None  # resolved when the transition in flight completes
    error: Exception | None = None
    retired: bool = False  # the paper's tau: a retire stays retired

    @property
    def name(self) -> str:
        """The row id it was mounted under, else its component's name."""
        return self.id or self.component.name

    async def settled(self) -> None:
        """Wait until no transition is in flight (follows inertial chaining).

        Shields the shared transition future: cancelling a waiter must not cancel the
        transition every other waiter is watching.
        """
        while (inertia := self.inertia) is not None:
            await asyncio.shield(inertia)

    async def perform[T](self, what: Effect[T]) -> T:
        """Perform one effect on this fiber after setup; its undo joins the fiber's stack (see Performer)."""
        if self.state not in (State.ACTIVE, State.LOADING):
            raise RuntimeError(
                f"{self.name}#{self.uid} is {self.state.value}; its performer is no longer usable"
            )
        result, undo = await _run_step(what, self.ctx)
        if undo is not None:
            self.stack.push_async_callback(_run, undo)
        self.performed.append(what)
        return result

    async def retire(self) -> None:
        """Unload this fiber and forget it. Idempotent; children drain first."""
        rt = self.ctx.runtime
        if not self.retired:
            self.retired = True
            _apply_target(self, Unsatisfied)
        await self.settled()
        if self in rt.registry:
            rt.registry.remove(self)


@dataclass(frozen=True, slots=True)
class Event:
    """One lifecycle observation. `kind` is the trace verb: reload, active, unloading,
    inactive, failed, failed-inactive, teardown-error, cancelled, bind, unbind, work-failed,
    observe-failed."""

    kind: str
    fiber: str
    uid: int
    key: str | None = None
    error: str | None = None

    def __str__(self) -> str:
        head = f"{self.kind} {self.fiber}#{self.uid}"
        if self.key:
            head = f"{self.kind} {self.key} by {self.fiber}#{self.uid}"
        return f"{head}: {self.error}" if self.error else head


class Runtime:
    """Holds what the paper calls gamma: the store and every live fiber."""

    def __init__(self) -> None:
        self.store: dict[object, _Binding] = {}
        self.registry: list[Fiber] = []
        self.events: list[Event] = []
        self.listeners: list[Callable[[Event], None]] = []  # a harness may append; called on every emit

        self._tasks: set[asyncio.Task[Any]] = set()  # lifecycle tasks
        self._work: set[asyncio.Task[Any]] = set()  # background work fibers own; see idle()
        self._failure: BaseException | None = None  # the first failure in owned work
        self._in_flight = 0  # transitions begun and not yet ended; see settle()
        self._quiet: asyncio.Future[None] | None = None  # resolved when _in_flight returns to 0
        self._uids = itertools.count(1)  # fiber ids, per runtime: two runtimes do not share them
        root = Component("root", frozenset(), (), False, None, _no_apply)
        self.root_fiber = Fiber(root, None, None, uid=next(self._uids), state=State.ACTIVE)
        self.root = Context(self, self.root_fiber)
        self.root_fiber.ctx = self.root

    def mount(
        self,
        what: Component | Callable[..., Any],
        *,
        config: Any = None,
        isolate: Iterable[Key] = (),
        id: str | None = None,
        expose: Iterable[Key] | None = None,
    ) -> Fiber:
        """Instantiate a component at the root. The bootstrap's one call."""
        return _mount(self.root, what, config=config, isolate=isolate, id=id, expose=expose)

    def emit(self, kind: str, fiber: Fiber, *, key: Key | None = None, error: str | None = None) -> None:
        ev = Event(kind, fiber.name, fiber.uid, None if key is None else key_name(key), error)
        self.events.append(ev)
        for fn in tuple(self.listeners):  # a listener may leave while being told (see observe)
            fn(ev)

    def spawn[T](self, coro: Awaitable[T]) -> asyncio.Task[T]:
        """Run a coroutine the runtime keeps a reference to, so it cannot be collected."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @asynccontextmanager
    async def scope(self, name: str = "scope") -> AsyncGenerator[Performer]:
        """A parent fiber as a `with` block: everything performed through the yielded
        performer belongs to that fiber, and is unwound when the block ends."""
        fiber = _mount(self.root, Component(name, frozenset(), (), False, None, _no_apply))
        await self.settle()
        try:
            yield Performer(fiber)
        finally:
            await fiber.retire()
            await self.settle()

    async def settle(self) -> None:
        """Wait until no fiber has a transition in flight.

        Exact, not heuristic: every transition is counted when it begins and uncounted when
        it ends, and a transition that ends by starting another (a provider going ACTIVE
        wakes its dependents) does so before the count is read again.
        """
        while self._in_flight:
            if self._quiet is None:
                self._quiet = asyncio.get_running_loop().create_future()
            await asyncio.shield(self._quiet)

    async def idle(self) -> None:
        """Wait until no fiber owns background work, then re-raise the first failure in it.

        The asyncio analogue of "the process exits when the event loop has nothing pending":
        a bootstrap mounts the composition, awaits idle(), and unwinds. Work that failed
        reaches the bootstrap here rather than vanishing into a never-retrieved exception,
        whether it failed before this call or during it.
        """
        await self.settle()
        while self._work and self._failure is None:
            await asyncio.wait(list(self._work), return_when=asyncio.FIRST_COMPLETED)
            await self.settle()
        if (error := self._failure) is not None:
            self._failure = None
            raise error

    async def shutdown(self, grace: float = 1.0) -> None:
        """Retire every child of the root; the cascade unwinds the tree, children first.

        A step already running cannot be interrupted, only awaited, so a component blocked
        inside its setup would hold the program open. Shutdown must end: after `grace`
        seconds the lifecycle tasks are cancelled, which unwinds each fiber's undos through
        the ordinary exception path.
        """
        try:
            async with asyncio.timeout(grace):
                for fiber in [f for f in self.registry if f.parent is self.root]:
                    await fiber.retire()
                await self.settle()
                return
        except TimeoutError:
            pass
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.registry = [f for f in self.registry if f is self.root_fiber]
        await self.settle()


async def _no_apply(**_: Any) -> Effects:
    return
    yield  # pragma: no cover - a component with no effects


@dataclass(frozen=True, slots=True, eq=False)
class _Seal:
    """A subtree that sees only `exposed` from outside (`use(..., expose=...)`). Every other key
    it reads or binds is its own: `(seal, key)` is the realm, so nothing leaks in or out.
    An exposed key resolves wherever the subtree was mounted from (`outer`)."""

    exposed: frozenset[Key]
    outer: Context


class Context:
    """A fiber's view of the runtime: its realm table and its identity.

    Effects receive it; components do not. It is an immutable record: built once when the
    fiber is mounted, read by the steps below, written by nothing.
    """

    __slots__ = ("_fiber", "_isolate", "_runtime", "_seal")

    def __init__(
        self,
        rt: Runtime,
        fiber: Fiber,
        isolate: frozendict[Key, object] = frozendict(),
        seal: _Seal | None = None,
    ) -> None:
        self._runtime = rt
        self._fiber = fiber
        self._isolate = isolate
        self._seal = seal

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    @property
    def fiber(self) -> Fiber:
        """The fiber this context belongs to; the root context's is the root fiber."""
        return self._fiber

    @property
    def isolate(self) -> frozendict[Key, object]:
        """Key -> realm symbol, for the keys this subtree keeps private."""
        return self._isolate

    def realm(self, key: Key) -> object:
        """The realm symbol for a key; the key itself is the default (global) realm.

        An isolated key is the subtree's own. In a sealed subtree an exposed key resolves
        where the subtree was mounted from, and any other key is the seal's own."""
        if key in self._isolate:
            return self._isolate[key]
        if self._seal is None:
            return key
        return self._seal.outer.realm(key) if key in self._seal.exposed else (self._seal, key)

    @property
    def seal(self) -> _Seal | None:
        """The allowlist this subtree was sealed with, if any (inherited by its children)."""
        return self._seal

    def get(self, key: Key) -> Any:
        """Raw store lookup in this context's realm. Never raises."""
        binding = self._runtime.store.get(self.realm(key))
        return None if binding is None else binding.value


def _mount(
    ctx: Context,
    what: Component | Callable[..., Any],
    *,
    config: Any = None,
    isolate: Iterable[Key] = (),
    id: str | None = None,
    expose: Iterable[Key] | None = None,
) -> Fiber:
    """Instantiate a component as a child of `ctx`; `use` is the effect that asks for it.

    `expose` seals the new subtree: it sees only those keys from outside (resolved in `ctx`),
    and every other key it reads or binds is private to it."""
    rt = ctx.runtime
    fiber = Fiber(derive(what), ctx, config, id=id, uid=next(rt._uids))
    new = {key: object() for key in isolate}
    if expose is not None:
        fiber.ctx = Context(rt, fiber, frozendict(new), _Seal(frozenset(expose), ctx))
    else:
        fiber.ctx = Context(rt, fiber, frozendict(ctx.isolate | new), ctx.seal)
    rt.registry.append(fiber)
    _refresh(fiber)
    return fiber


# -- the lifecycle ----------------------------------------------------------------------


async def _run_step[T](what: Effect[T], ctx: Context) -> Result[T]:
    """Run an effect's step against a fiber's context and check the shape of what it returns.

    The pair to `_run`, which invokes the undo a step returned.
    """
    out = what.step(ctx, *what.args, **what.kwargs)
    if inspect.isawaitable(out):
        out = await out
    if not (isinstance(out, tuple) and len(out) == 2):
        raise TypeError(
            f"effect {what.name} returned {type(out).__name__}; a step returns (result, undo), "
            f"where undo is None when the step changes nothing reversible"
        )
    result, undo = out
    if undo is not None and not callable(undo):
        raise TypeError(f"effect {what.name} returned a {type(undo).__name__} as its undo")
    return result, undo


async def _run(undo: Undo) -> None:
    """Invoke an undo that may be sync or async; a sync one may return anything."""
    if inspect.isawaitable(r := undo()):
        await r


def _check_contracts(fiber: Fiber) -> None:
    """Every dependency this component annotated with a class must be bound to a value satisfying it."""
    committed = fiber.committed if fiber.committed is not None else frozendict()
    for name, contract in fiber.component.contracts:
        check_contract(fiber.name, name, committed[name], contract)


def _instantiate(fiber: Fiber) -> Effects:
    """Call the component's function with this fiber's committed dependencies and its config."""
    return fiber.component.fn(**arguments(fiber.component, fiber.committed or frozendict(), fiber.config))


async def _perform_all(fiber: Fiber, gen: Effects, guard: Callable[[], bool]) -> None:
    """The effect iterator: drive the generator, perform, record the undo, send the result back.

    Stops at the next step boundary once the guard trips. On an exception the undos already
    recorded stay on the fiber's stack for the caller to unwind.
    """
    async with aclosing(gen):
        send: Any = None
        while guard():
            try:
                item = await gen.asend(send)
            except StopAsyncIteration:
                break
            if not isinstance(item, Effect):
                raise TypeError(
                    f"{fiber.name} yielded a {type(item).__name__}; a component yields effects "
                    f"(did you mean `yield bind(key, value)`?)"
                )
            result, undo = await _run_step(item, fiber.ctx)
            if undo is not None:
                fiber.stack.push_async_callback(_run, undo)
            fiber.performed.append(item)
            send = result


def provider_of(fiber: Fiber) -> ProviderLookup:
    """Who binds a key as this fiber sees it: the store, read through the fiber's realms."""

    def lookup(key: Key) -> tuple[int, State] | None:
        b = fiber.ctx.runtime.store.get(fiber.ctx.realm(key))
        return None if b is None else (b.fiber.uid, b.fiber.state)

    return lookup


def _target_of(fiber: Fiber) -> Target:
    return resolve_target(fiber.component.inject, fiber.retired, provider_of(fiber))


def _notify(ctx: Context, keys: Iterable[Key]) -> list[Fiber]:
    """Recompute every fiber that depends on `keys` in `ctx`'s realm; returns them for a drain."""
    changed = {(k, ctx.realm(k)) for k in keys}
    if not changed:
        return []
    candidates = [(f, {(k, f.ctx.realm(k)) for k in f.component.inject}) for f in ctx.runtime.registry]
    dependents = affected(candidates, changed)
    for fiber in dependents:
        _refresh(fiber)
    return dependents


def _refresh(fiber: Fiber) -> None:
    """Recompute the target from ACTIVE providers and act on it."""
    _apply_target(fiber, _target_of(fiber))


def _apply_target(fiber: Fiber, new: Target) -> None:
    decision = decide(fiber.state, fiber.target, new)
    if fiber.state is not State.FAILED:
        fiber.target = new
    match decision:
        case Next.STAY:
            return
        case Next.START:
            _begin_transition(fiber, State.LOADING)
            fiber.ctx.runtime.spawn(_live(fiber))
        case Next.DEACTIVATE:
            # Mark UNLOADING here, before the task wakes, so a provider draining its
            # dependents already sees this one as in transition (paper: L-Leave).
            _begin_transition(fiber, State.UNLOADING)
            fiber.deactivate.set()


def _begin_transition(fiber: Fiber, state: State) -> None:
    fiber.state = state
    if fiber.inertia is None:
        fiber.inertia = asyncio.get_running_loop().create_future()
        fiber.ctx.runtime._in_flight += 1


def _end_transition(fiber: Fiber, state: State) -> None:
    fiber.state = state
    if fiber.inertia is not None:
        fiber.inertia.set_result(None)
        fiber.inertia = None
        rt = fiber.ctx.runtime
        rt._in_flight -= 1
        if rt._in_flight == 0 and rt._quiet is not None:
            rt._quiet.set_result(None)
            rt._quiet = None


async def _live(fiber: Fiber) -> None:
    """The fiber's whole loaded lifetime, as one task."""
    try:
        await _lifetime(fiber)
    except asyncio.CancelledError:
        # The event loop is shutting down under us. What must not happen is a waiter on this
        # fiber's inertia hanging forever, which would stall a parent unwinding its stack.
        fiber.stack = AsyncExitStack()
        fiber.committed = None
        fiber.retired = True
        _end_transition(fiber, State.INACTIVE)
        fiber.ctx.runtime.emit("cancelled", fiber)
        raise


async def _lifetime(fiber: Fiber) -> None:
    rt = fiber.ctx.runtime
    while True:
        # Lazy scheduling (paper footnote 2): the target may have become unsatisfied between
        # the START decision and this task first running, so re-read it.
        if fiber.target is Unsatisfied:
            _end_transition(fiber, State.INACTIVE)
            rt.emit("inactive", fiber)
            return
        target0 = fiber.target

        def unchanged(t0: Target = target0) -> bool:
            return fiber.target == t0

        failed = False
        fiber.committed = frozendict({k: fiber.ctx.get(k) for k in fiber.component.inject})
        fiber.performed = []
        fiber.error = None  # a fresh setup starts clean; a stale error from a prior ACTIVE
        # period (background work that died) must not outlive the reload that moved past it
        rt.emit("reload", fiber)
        try:
            async with AsyncExitStack() as stack:
                fiber.stack = stack
                try:
                    _check_contracts(fiber)
                    await _perform_all(fiber, _instantiate(fiber), unchanged)
                    if unchanged():  # only check when setup is about to ACTIVATE; a target
                        # that moved mid-setup goes to UNLOAD and retries, not a failure here
                        check_provided(fiber.name, fiber.component.provides, fiber.bound)
                except Exception as exc:
                    failed, fiber.error, fiber.target = True, exc, Unsatisfied
                    rt.emit("failed", fiber, error=repr(exc))
                if after_setup(failed, fiber.target, target0) is AfterSetup.ACTIVATE:
                    _end_transition(fiber, State.ACTIVE)
                    rt.emit("active", fiber)
                    _notify(fiber.ctx, list(fiber.bound))
                    await fiber.deactivate.wait()  # the ACTIVE period
                    fiber.deactivate.clear()
                fiber.state = State.UNLOADING
                rt.emit("unloading", fiber)
                await _drain(fiber)
        except Exception as exc:
            # An undo raised. The stack has already run the others; the lifecycle must still
            # complete, or every waiter on this fiber hangs.
            fiber.error = exc
            rt.emit("teardown-error", fiber, error=repr(exc))
        fiber.stack = AsyncExitStack()  # detached: effects on a dead fiber go nowhere
        fiber.committed = None
        match after_unload(failed, fiber.target):
            case AfterUnload.FAILED:
                _end_transition(fiber, State.FAILED)
                rt.emit("failed-inactive", fiber)
                return
            case AfterUnload.INACTIVE:
                _end_transition(fiber, State.INACTIVE)
                rt.emit("inactive", fiber)
                return
            case AfterUnload.CHAIN:
                fiber.state = State.LOADING  # reinstall against the new providers


async def _drain(fiber: Fiber) -> None:
    """The guard on unload: dependents recompute against this fiber as gone, and we wait."""
    dependents = _notify(fiber.ctx, list(fiber.bound))
    async with asyncio.TaskGroup() as tg:
        for d in dependents:
            if d is not fiber:
                tg.create_task(d.settled())


# -- the framework's own effects ---------------------------------------------------
# Each is written exactly as a plugin author would write one: a step function of the
# context returning (result, undo), plus a constructor that defers it.


def bind_step(ctx: Context, key: Key, value: object) -> Result[None]:
    """Put a value under a name in this fiber's realm; the undo removes it.

    Anything goes under a name: the check is the consumer's, against the class it annotated
    the dependency with, when the value is committed to it (`_check_contracts`).
    """
    rt, realm, fiber = ctx.runtime, ctx.realm(key), ctx.fiber
    if fiber is rt.root_fiber:
        raise RuntimeError("the root context binds nothing; mount a component")
    if realm in rt.store:
        owner = rt.store[realm].fiber
        raise AlreadyBound(
            f"{fiber.name} cannot bind {key_name(key)}: {owner.name}#{owner.uid} already binds it "
            f"in this realm; retire that one first, or mount this subtree with isolate"
        )
    rt.store[realm] = _Binding(value, fiber)
    fiber.bound.add(key)
    rt.emit("bind", fiber, key=key)
    _notify(ctx, [key])

    def undo() -> None:
        del rt.store[realm]
        fiber.bound.discard(key)
        rt.emit("unbind", fiber, key=key)
        _notify(ctx, [key])

    return None, undo


def bind(key: Key, value: object) -> Effect[None]:
    """Provide `value` under `key` for components that depend on it; undone by unbinding it,
    which unloads them first. Yield it: `yield bind("net", client)`."""
    return effect(bind_step, key, value)


async def enter_step[T](ctx: Context, cm: AbstractAsyncContextManager[T]) -> Result[T]:
    """Enter an async context manager; its __aexit__ is the undo."""
    if not hasattr(cm, "__aenter__"):
        raise TypeError(
            f"enter expects an async context manager, got {type(cm).__name__}; "
            f"for a plain resource write a step that returns (resource, close)"
        )
    value = await cm.__aenter__()

    async def undo() -> None:
        await cm.__aexit__(None, None, None)

    return value, undo


def enter[T](cm: AbstractAsyncContextManager[T]) -> Effect[T]:
    """Enter an async context manager and hold it while the component lives; its exit is the
    undo. Yields back what entering gave: `client = yield enter(NetClient(port))`."""
    return effect(enter_step, cm)


def use_step(
    ctx: Context,
    what: Component | Callable[..., Any],
    config: Any = None,
    isolate: Iterable[Key] = (),
    id: str | None = None,
    expose: Iterable[Key] | None = None,
) -> Result[Fiber]:
    """Mount a child component; the undo retires it, draining its own children first."""
    fiber = _mount(ctx, what, config=config, isolate=isolate, id=id, expose=expose)
    return fiber, fiber.retire


def use(
    what: Component | Callable[..., Any],
    *,
    config: Any = None,
    isolate: Iterable[Key] = (),
    id: str | None = None,
    expose: Iterable[Key] | None = None,
) -> Effect[Fiber]:
    """Mount a child. `isolate` keeps some keys private to its subtree; `expose` seals the
    subtree instead, so it sees only those keys from outside and keeps every other one."""
    return effect(use_step, what, config, isolate, id, expose)


def background_step(ctx: Context, coro: Awaitable[None]) -> Result[asyncio.Task[None]]:
    """Run work this fiber owns: counted by Runtime.idle(), cancelled by the undo.

    A failure is kept on the fiber and on the runtime rather than discarded, so it is
    visible in `explain()` and re-raised by `idle()` even if nobody was waiting then.
    """
    rt, fiber = ctx.runtime, ctx.fiber
    task = rt.spawn(coro)
    rt._work.add(task)

    def finished(done: asyncio.Task[None]) -> None:
        rt._work.discard(done)
        if done.cancelled() or (error := done.exception()) is None:
            return
        if isinstance(error, Exception):
            fiber.error = error
            rt.emit("work-failed", fiber, error=repr(error))
        if rt._failure is None:
            rt._failure = error

    task.add_done_callback(finished)

    async def undo() -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    return task, undo


def background(coro: Awaitable[None]) -> Effect[asyncio.Task[None]]:
    """Run `coro` as work this component owns, cancelled when it leaves; a failure is kept on
    the component (`explain()` shows it). Yields back the task: `yield background(poll())`."""
    return effect(background_step, coro)


async def acquire_step(ctx: Context, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Result[None]:
    """Call a function whose return value is its own undo: a registration that returns its remover.

    The paper's revertible effect in its purest form, an operation that hands back its
    inverse. `None` means there is nothing to reverse.
    """
    undo = fn(*args, **kwargs)
    if inspect.isawaitable(undo):
        undo = await undo
    if undo is not None and not callable(undo):
        raise TypeError(
            f"acquire({getattr(fn, '__name__', fn)}) returned a {type(undo).__name__}; the return "
            f"value is the undo, so it must be callable (or None when there is nothing to reverse)"
        )
    return None, undo


def acquire(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Effect[None]:
    """Call `fn(*args, **kwargs)`, whose return value is its own undo (a registration that
    returns its remover, called when the component leaves): `yield acquire(commands.register,
    spec, run)`. `fn` may be async; it may return None when there is nothing to undo."""
    return effect(acquire_step, fn, *args, **kwargs)


def observe_step(ctx: Context, fn: Callable[[Event], None]) -> Result[None]:
    """Hear every lifecycle event from now on (the `--trace` stream); the undo stops hearing.

    A listener is called in the middle of a transition, so one that raises must not break
    it: it is taken off, its error is kept on the fiber that asked (as `explain()` shows a
    background failure), and an `observe-failed` event says so.
    """
    rt, fiber = ctx.runtime, ctx.fiber

    def listener(event: Event) -> None:
        try:
            fn(event)
        except Exception as error:
            _stop_hearing(rt, listener)
            fiber.error = error
            rt.emit("observe-failed", fiber, error=repr(error))

    rt.listeners.append(listener)

    def undo() -> None:
        _stop_hearing(rt, listener)

    return None, undo


def _stop_hearing(rt: Runtime, listener: Callable[[Event], None]) -> None:
    if listener in rt.listeners:
        rt.listeners.remove(listener)


def observe(fn: Callable[[Event], None]) -> Effect[None]:
    """Hear every lifecycle event (a component loading, active, failed, ...) while the component
    lives; `fn` is called with each `Event`."""
    return effect(observe_step, fn)


class Performer:
    """Performs further effects on a fiber after its setup has finished.

    Setup is the only place a component can yield, but composition is not always known
    then: a loader swaps one row when a file changes, a session mounts what a model wrote
    this turn. A performer is that ability, scoped to the fiber that asked for it. The
    undos it collects are the fiber's, so unloading the fiber still unwinds everything,
    and it stops working the moment its fiber leaves.

    Prefer `enter` during setup for anything task-affine (timeouts, cancel scopes): a
    later perform runs in the caller's task, not the fiber's.
    """

    __slots__ = ("_fiber",)

    def __init__(self, fiber: Fiber) -> None:
        self._fiber = fiber

    async def perform[T](self, what: Effect[T]) -> T:
        """Perform one effect now, recording its undo on this performer's fiber."""
        return await self._fiber.perform(what)

    def __repr__(self) -> str:
        return f"Performer({self._fiber.name}#{self._fiber.uid})"


def performer_step(ctx: Context) -> Result[Performer]:
    """Hand the component a performer for its own fiber. Nothing to undo."""
    if ctx.fiber is ctx.runtime.root_fiber:
        raise RuntimeError("performer() needs a mounted fiber; the root context has none")
    return Performer(ctx.fiber), None


def performer() -> Effect[Performer]:
    """Get a `Performer` for this component's own fiber, to perform effects after setup (from
    background work); each one's undo runs when the component leaves."""
    return effect(performer_step)
