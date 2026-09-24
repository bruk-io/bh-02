"""The runtime's decisions, tested as the functions they are: no tasks, no store, no clock.

Each decision has an imperative half in cordis.runtime that acts on it (`decide` ->
`_apply_target`, `after_setup` and `after_unload` -> `_lifetime`, `affected` -> `_notify`,
`resolve_target` -> `_refresh`, `check_contract` -> `_lifetime`). The lifecycle tests cover
the halves together; these pin the rules on their own.
"""

from typing import Protocol, runtime_checkable

import pytest

from cordis import State
from cordis.decisions import (
    AfterSetup,
    AfterUnload,
    ContractViolation,
    Declared,
    Next,
    Resolved,
    Target,
    UnboundProvide,
    Unsatisfied,
    affected,
    after_setup,
    after_unload,
    check_contract,
    check_provided,
    decide,
    resolve_target,
    unsatisfiable,
)

A = Resolved((("k", 1),))
B = Resolved((("k", 2),))


@pytest.mark.parametrize(
    ("state", "old", "new", "expected"),
    [
        (State.INACTIVE, Unsatisfied, A, Next.START),
        (State.INACTIVE, Unsatisfied, Unsatisfied, Next.STAY),
        (State.ACTIVE, A, Unsatisfied, Next.DEACTIVATE),
        (State.ACTIVE, A, B, Next.DEACTIVATE),  # a different provider set is a reload
        (State.ACTIVE, A, A, Next.STAY),
        (State.FAILED, Unsatisfied, A, Next.STAY),  # never retried as this fiber (paper 4.4)
        (State.LOADING, A, Unsatisfied, Next.STAY),  # the live task re-reads at its boundary
        (State.UNLOADING, Unsatisfied, A, Next.STAY),
    ],
)
def test_decide(state: State, old: Target, new: Target, expected: Next) -> None:
    assert decide(state, old, new) is expected


def test_a_setup_activates_only_against_the_providers_it_started_with() -> None:
    assert after_setup(False, A, A) is AfterSetup.ACTIVATE
    assert after_setup(False, B, A) is AfterSetup.UNLOAD  # a provider changed mid-setup
    assert after_setup(False, Unsatisfied, A) is AfterSetup.UNLOAD
    assert after_setup(True, Unsatisfied, A) is AfterSetup.FAIL


def test_an_unwound_fiber_rests_or_chains() -> None:
    assert after_unload(True, Unsatisfied) is AfterUnload.FAILED
    assert after_unload(True, A) is AfterUnload.FAILED  # failure wins over a new target
    assert after_unload(False, Unsatisfied) is AfterUnload.INACTIVE
    assert after_unload(False, A) is AfterUnload.CHAIN


def test_affected_matches_on_key_and_realm() -> None:
    root, inner = object(), object()  # two realms for the key "k"
    shared = ("shared", {("k", root)})
    isolated = ("isolated", {("k", inner)})
    unrelated = ("unrelated", {("other", root)})
    fibers = [shared, isolated, unrelated]

    assert affected(fibers, {("k", root)}) == ["shared"]  # a bind at the root
    assert affected(fibers, {("k", inner)}) == ["isolated"]  # a bind inside the realm
    assert affected(fibers, {("other", root)}) == ["unrelated"]
    assert affected(fibers, {("nobody", root)}) == []
    assert affected(fibers, {("k", root), ("other", root)}) == ["shared", "unrelated"]


def test_resolve_target_needs_every_provider_active() -> None:
    providers: dict[object, tuple[int, State]] = {"a": (1, State.ACTIVE), "b": (2, State.ACTIVE)}
    assert resolve_target(["b", "a"], False, providers.get) == Resolved((("a", 1), ("b", 2)))
    assert resolve_target([], False, providers.get) == Resolved(())
    assert resolve_target(["a", "c"], False, providers.get) is Unsatisfied  # no provider
    providers["b"] = (2, State.LOADING)
    assert resolve_target(["a", "b"], False, providers.get) is Unsatisfied  # not ACTIVE yet
    assert resolve_target(["a"], True, providers.get) is Unsatisfied  # retired: never resolves


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...


class Sundial:
    def now(self) -> float:
        return 0.0


def test_a_contract_is_the_consumer_s_and_is_checked_structurally() -> None:
    check_contract("p", "clock", Sundial(), Clock)  # no inheritance needed
    with pytest.raises(ContractViolation, match=r"p: clock is bound to a str, which is missing now"):
        check_contract("p", "clock", "noon", Clock)
    with pytest.raises(ContractViolation, match=r"not an instance of int"):
        check_contract("p", "n", "1", int)  # a concrete class has no member list to name


def test_a_protocol_that_is_not_runtime_checkable_cannot_be_a_contract() -> None:
    class Plain(Protocol):
        def now(self) -> float: ...

    with pytest.raises(ContractViolation, match="Decorate the Protocol with @runtime_checkable"):
        check_contract("p", "clock", Sundial(), Plain)


def test_check_provided_passes_when_every_declared_key_was_bound() -> None:
    check_provided("m", frozenset({"a", "b"}), {"a", "b", "c"})  # extra binds are fine


def test_check_provided_fails_a_fiber_that_declared_a_key_it_never_bound() -> None:
    with pytest.raises(UnboundProvide, match=r"m: declared provides \['a'\].*never bound it"):
        check_provided("m", frozenset({"a"}), set())


def test_check_provided_names_every_key_it_never_bound() -> None:
    with pytest.raises(UnboundProvide, match=r"declared provides \['a', 'b'\].*never bound them"):
        check_provided("m", frozenset({"a", "b"}), set())


def test_unsatisfiable_is_empty_when_every_inject_is_declared_by_some_provides() -> None:
    consumer = Declared("mode", frozenset({"llm"}), frozenset())
    provider = Declared("model", frozenset(), frozenset({"llm"}))
    assert unsatisfiable([consumer, provider]) == {}


def test_unsatisfiable_names_a_row_and_the_keys_nothing_declares() -> None:
    consumer = Declared("mode", frozenset({"llm", "tools"}), frozenset())
    provider = Declared("model", frozenset(), frozenset({"llm"}))
    assert unsatisfiable([consumer, provider]) == {"mode": frozenset({"tools"})}


def test_unsatisfiable_never_lets_a_row_satisfy_its_own_inject() -> None:
    # a fiber can only go ACTIVE once its dependencies are bound, so a row that injects a
    # key it also declares providing can never satisfy itself: this is always a deadlock
    self_only = Declared("m", frozenset({"a"}), frozenset({"a"}))
    assert unsatisfiable([self_only]) == {"m": frozenset({"a"})}


def test_unsatisfiable_lets_a_different_row_satisfy_a_key_a_row_also_provides() -> None:
    # two rows may both declare "a": one injects it and is satisfied by the other providing it
    consumer = Declared("mode", frozenset({"a"}), frozenset({"a"}))
    provider = Declared("model", frozenset(), frozenset({"a"}))
    assert unsatisfiable([consumer, provider]) == {}
