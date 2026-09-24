"""The paper's metatheory as runtime invariants, checked under random operation histories.

Def 53 / Thm 70   an ACTIVE fiber's dependencies resolve to ACTIVE providers, and its
                  target names exactly those providers
Def 76            an ACTIVE fiber's bindings are installed and owned by it
Progress          no INACTIVE fiber is left with every dependency provided
Corollary 69      a departed fiber has left nothing: bindings, resources
Thm 80            the quiescent state depends only on the final set of components

Run this after any change to runtime.py: it has caught bugs the unit tests missed.
"""

import random
from typing import Any

import pytest

from cordis import Component, Context, Effects, Fiber, Runtime, State, Undo, bind, effect
from cordis.decisions import Resolved, Unsatisfied

KEYS = ("a", "b", "c")


class Ledger:
    """Counts resources acquired and released per component name."""

    def __init__(self) -> None:
        self.open: dict[str, int] = {}

    def acquire(self, name: str) -> Undo:
        self.open[name] = self.open.get(name, 0) + 1
        return lambda: self.open.__setitem__(name, self.open[name] - 1)


def acquire_step(ctx: Context, ledger: Ledger, name: str) -> tuple[None, Undo]:
    return None, ledger.acquire(name)


def make(name: str, inject: frozenset[str], provide: frozenset[str], ledger: Ledger) -> Component:
    async def apply(**deps: Any) -> Effects:
        assert set(deps) == set(inject)  # every dependency is readable while loading
        yield effect(acquire_step, ledger, name)  # one "resource" per activation
        for key in sorted(provide):
            yield bind(key, f"{name}:{key}")

    return Component(
        name=name,
        inject=frozenset(inject),
        params=tuple((key, key) for key in sorted(inject)),
        wants_config=False,
        config_type=None,
        fn=apply,
    )


def catalogue(ledger: Ledger) -> dict[str, Component]:
    """Providers, consumers, and chains (depend on one key, bind another)."""
    cs = {f"p_{k}": make(f"p_{k}", frozenset(), frozenset({k}), ledger) for k in KEYS}
    cs["c_a"] = make("c_a", frozenset({"a"}), frozenset(), ledger)
    cs["c_ab"] = make("c_ab", frozenset({"a", "b"}), frozenset(), ledger)
    cs["c_bc"] = make("c_bc", frozenset({"b", "c"}), frozenset(), ledger)
    cs["x_a_d"] = make("x_a_d", frozenset({"a"}), frozenset({"d"}), ledger)  # chain a -> d
    cs["c_d"] = make("c_d", frozenset({"d"}), frozenset(), ledger)
    cs["c_cd"] = make("c_cd", frozenset({"c", "d"}), frozenset(), ledger)
    return cs


def check(rt: Runtime, ledger: Ledger) -> None:
    live = [f for f in rt.registry if f is not rt.root_fiber]
    assert all(f.state in (State.ACTIVE, State.INACTIVE, State.FAILED) for f in live), "settled"
    for f in live:
        if f.state is State.ACTIVE:
            # Def 53 / Thm 70: dependencies resolve to ACTIVE providers; the target names them
            assert isinstance(f.target, Resolved)
            for key, uid in f.target.providers:
                b = rt.store[f.ctx.realm(key)]
                assert b.fiber.uid == uid and b.fiber.state is State.ACTIVE, (f.name, key)
            assert {k for k, _ in f.target.providers} == f.component.inject
            # Def 76: every key it bound is installed and owned by it
            for key in f.bound:
                assert rt.store[f.ctx.realm(key)].fiber is f, (f.name, key)
        else:
            # Corollary 69: a fiber that is not ACTIVE holds nothing
            assert all(b.fiber is not f for b in rt.store.values()), f.name
            assert not f.bound, f.name
            if f.state is State.INACTIVE:
                # Progress: it is INACTIVE only because something it needs is missing
                assert f.target is Unsatisfied
                missing = [
                    k
                    for k in f.component.inject
                    if (b := rt.store.get(f.ctx.realm(k))) is None or b.fiber.state is not State.ACTIVE
                ]
                assert missing, f"{f.name} is INACTIVE with every dependency provided"
    # the ledger: open resources == activations still standing
    active = {f.name for f in live if f.state is State.ACTIVE}
    for name, n in ledger.open.items():
        assert n == (1 if name in active else 0), (name, n)


async def run_history(seed: int, steps: int) -> tuple[Runtime, Ledger, dict[str, Fiber]]:
    rng = random.Random(seed)
    ledger = Ledger()
    cs = catalogue(ledger)
    rt = Runtime()
    loaded: dict[str, Fiber] = {}
    for _ in range(steps):
        name = rng.choice(list(cs))
        match rng.random(), name in loaded:
            case (r, True) if r < 0.4:
                await loaded.pop(name).retire()  # unload
            case (_, True):
                await loaded.pop(name).retire()  # swap: retire, then mount again
                loaded[name] = rt.mount(cs[name])
            case (_, False):
                loaded[name] = rt.mount(cs[name])
        await rt.settle()
        check(rt, ledger)
    return rt, ledger, loaded


@pytest.mark.parametrize("seed", range(40))
async def test_invariants_hold_along_random_histories(seed: int) -> None:
    rt, ledger, loaded = await run_history(seed, steps=25)
    # Corollary 69, globally: retire everything and nothing is left
    for f in loaded.values():
        await f.retire()
    await rt.settle()
    assert rt.store == {} and rt.registry == []
    assert all(n == 0 for n in ledger.open.values()), ledger.open


@pytest.mark.parametrize("seed", range(20))
async def test_quiescent_state_depends_only_on_the_final_components(seed: int) -> None:
    """Thm 80: whatever the history, what ends up ACTIVE is a function of what is mounted."""
    rt, _, loaded = await run_history(seed, steps=25)
    observed = {f.name: f.state for f in loaded.values()}

    rng = random.Random(seed + 1000)  # the same final set, mounted fresh in another order
    order = sorted(loaded)
    rng.shuffle(order)
    rt2, ledger2 = Runtime(), Ledger()
    cs2 = catalogue(ledger2)
    fresh = {n: rt2.mount(cs2[n]) for n in order}
    await rt2.settle()
    check(rt2, ledger2)
    assert observed == {n: f.state for n, f in fresh.items()}
    assert set(rt.store) == set(rt2.store)


@pytest.mark.parametrize("seed", range(300))
async def test_invariants_hold_when_operations_interleave(seed: int) -> None:
    """Several orchestration actions in flight at once, settled together (confluence)."""
    rng = random.Random(seed)
    ledger = Ledger()
    cs = catalogue(ledger)
    rt = Runtime()
    loaded: dict[str, Fiber] = {}
    for _ in range(60):
        pending = []
        for name in rng.sample(list(cs), k=rng.randint(1, 4)):
            if name in loaded:
                pending.append(loaded.pop(name).retire())
                if rng.random() < 0.5:
                    loaded[name] = rt.mount(cs[name])  # swap while the retire is in flight
            else:
                loaded[name] = rt.mount(cs[name])
        for r in pending:
            await r
        await rt.settle()
        check(rt, ledger)
    for f in loaded.values():
        await f.retire()
    await rt.settle()
    assert rt.store == {} and rt.registry == [] and not any(ledger.open.values())
