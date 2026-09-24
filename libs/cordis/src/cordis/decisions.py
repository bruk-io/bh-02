"""What the runtime should do next, computed from values it is handed.

Nothing here touches the store, a task or a generator, and the boundaries rule proves it:
this module imports only `cordis.effects`. Each decision has an imperative half in
`cordis.runtime` that acts on it: `resolve_target` -> `_refresh`, `affected` -> `_notify`,
`decide` -> `_apply_target`, `after_setup` and `after_unload` -> `_lifetime`,
`check_contract` -> `_lifetime`, where a dependency is committed, and `check_provided` ->
`_lifetime`, where a fiber goes ACTIVE. `unsatisfiable` -> `boot`, before it mounts the
loader (the first effect a bootstrap performs). The rules are tested on their own in
`tests/test_decisions.py`.
"""

import enum
from collections.abc import Callable, Iterable, Set
from dataclasses import dataclass
from typing import Any

from cordis.effects import Key, sort_key


class State(enum.StrEnum):
    INACTIVE = enum.auto()
    LOADING = enum.auto()
    ACTIVE = enum.auto()
    UNLOADING = enum.auto()
    FAILED = enum.auto()


@dataclass(frozen=True, slots=True)
class Resolved:
    """Target digest: (key, provider uid) per dependency. Identity by uid, not by value."""

    providers: tuple[tuple[Key, int], ...]


Unsatisfied = sentinel("Unsatisfied")
"""Some dependency has no ACTIVE provider."""


type Target = Resolved | Unsatisfied

type ProviderLookup = Callable[[Key], tuple[int, State] | None]
"""Who binds a key as seen from one fiber: the provider's uid and state, or None."""


def resolve_target(inject: Iterable[Key], retired: bool, provider: ProviderLookup) -> Target:
    """(key, provider uid) per dependency; only ACTIVE providers count, and a retired fiber has none."""
    if retired:
        return Unsatisfied
    out = []
    for key in sorted(inject, key=sort_key):
        found = provider(key)
        if found is None or found[1] is not State.ACTIVE:
            return Unsatisfied
        out.append((key, found[0]))
    return Resolved(tuple(out))


def affected[T](
    candidates: Iterable[tuple[T, Set[tuple[Key, object]]]], changed: Set[tuple[Key, object]]
) -> list[T]:
    """Which candidates depend on any of the `(key, realm)` pairs that changed, in input order.

    A dependency is a key in a realm, so a binding in one realm is invisible to a dependent
    in another: a bind at the root does not wake a fiber inside an isolated subtree, and
    the reverse.
    """
    return [candidate for candidate, depends_on in candidates if depends_on & changed]


class Next(enum.StrEnum):
    STAY = enum.auto()
    START = enum.auto()
    DEACTIVATE = enum.auto()


def decide(state: State, old: Target, new: Target) -> Next:
    """What a target change should do. The imperative part is `_apply_target`."""
    if state is State.FAILED or old == new:
        return Next.STAY  # FAILED is never retried as this fiber (paper 4.4)
    if state is State.INACTIVE:
        return Next.START if isinstance(new, Resolved) else Next.STAY
    if state is State.ACTIVE:
        return Next.DEACTIVATE  # to Unsatisfied, or to a different provider set
    return Next.STAY  # LOADING or UNLOADING: the live task re-reads target at its next boundary


class AfterSetup(enum.StrEnum):
    FAIL = enum.auto()  # setup raised: unwind, then FAILED
    ACTIVATE = enum.auto()  # setup finished against the providers it started with
    UNLOAD = enum.auto()  # the providers changed while setting up: unwind without going ACTIVE


def after_setup(failed: bool, target: Target, target0: Target) -> AfterSetup:
    """What a finished setup means. `target0` is the target the setup was started against."""
    if failed:
        return AfterSetup.FAIL
    return AfterSetup.ACTIVATE if target == target0 else AfterSetup.UNLOAD


class AfterUnload(enum.StrEnum):
    FAILED = enum.auto()  # rests as FAILED; never retried as this fiber
    INACTIVE = enum.auto()  # rests as INACTIVE; a new target starts a new lifecycle task
    CHAIN = enum.auto()  # the target is satisfied again: reinstall in the same task


def after_unload(failed: bool, target: Target) -> AfterUnload:
    """What an unwound fiber rests as, or whether it goes straight back into setup."""
    if failed:
        return AfterUnload.FAILED
    return AfterUnload.INACTIVE if target is Unsatisfied else AfterUnload.CHAIN


class ContractViolation(TypeError):
    """A dependency's value does not satisfy the class its consumer annotated it with.

    The paper's key-collision problem (6.6): nominal linking accepts anything under a name.
    Here the name is the key and the consumer's annotation is its contract, checked where the
    value is committed to it, so a mismatch fails that consumer at load time with a message
    rather than surfacing as a call-time surprise. The provider never sees the contract;
    two consumers may hold one provider to different ones.
    """


def check_contract(owner: str, key: Key, value: object, contract: type) -> None:
    """Refuse a value committed under `key` that does not satisfy `owner`'s `contract` for it."""
    try:
        satisfied = isinstance(value, contract)
    except TypeError as e:  # a Protocol that is not runtime_checkable
        raise ContractViolation(
            f"{owner}: {contract.__name__} cannot be the contract for {key}: {e}. Decorate the "
            f"Protocol with @runtime_checkable, or use a concrete class."
        ) from e
    if not satisfied:
        raise ContractViolation(
            f"{owner}: {key} is bound to a {type(value).__name__}, which is {_missing(value, contract)}"
        )


class UnboundProvide(TypeError):
    """A component declared it provides a key it did not bind, once activated.

    The README's "what it provides is what it binds" (a component's inject is static, what
    it binds was previously known only after it ran): declaring `provides` makes that
    property checked at activation rather than diagnosed after the fact by `explain`.
    """


def check_provided(owner: str, declared: Set[Key], bound: Set[Key]) -> None:
    """Refuse a fiber that declared keys it did not bind by the time it went ACTIVE."""
    if missing := declared - bound:
        raise UnboundProvide(
            f"{owner}: declared provides {sorted(missing)} but never bound "
            f"{'it' if len(missing) == 1 else 'them'}; bind every declared key, or drop it "
            f"from `provides`"
        )


@dataclass(frozen=True, slots=True)
class Declared:
    """What a row's component declares, statically, before any effect runs.

    Just the two static shapes `unsatisfiable` needs (a row's diagnostic name, its inject,
    its provides), not the `Component` itself, which is cordis's imperative half.
    """

    name: str
    inject: frozenset[Key]
    provides: frozenset[Key]


def unsatisfiable(components: Iterable[Declared]) -> dict[str, frozenset[Key]]:
    """Which rows' injects no *other* row in the composition declares `provides` for.

    A row whose `use` did not resolve, or that declares no `provides`, contributes nothing
    to the union but is still checked against it: a component's own binds (what `bind_step`
    later records) are not visible here, only what it *declared*, because this runs before
    any effect does. Row id is a diagnostic name, never a role, so this compares declared
    provides against declared inject, not against ids.

    A row's own `provides` never counts toward its own `inject`: a fiber can only go ACTIVE
    once its dependencies are already bound, so a component that injects a key it also
    declares providing can never satisfy itself, whatever else is in the composition.
    """
    declared = list(components)
    return {
        c.name: missing
        for c in declared
        if (missing := frozenset(k for k in c.inject if not _provided_by_another(k, c, declared)))
    }


def _provided_by_another(key: Key, mine: Declared, components: Iterable[Declared]) -> bool:
    return any(key in c.provides for c in components if c is not mine)


def _missing(value: Any, iface: type) -> str:
    """Which members of the contract the value lacks, for the error message."""
    wanted = [n for n in getattr(iface, "__protocol_attrs__", ()) if not n.startswith("_")]
    if not wanted:
        return f"not an instance of {iface.__name__}"
    absent = [n for n in wanted if not hasattr(value, n)]
    return f"missing {', '.join(sorted(absent))}" if absent else "the wrong shape"
