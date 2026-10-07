"""The two helpers on their own, and once as rows on a runtime with `acquire`."""

import pytest

from cordis import Effects, Runtime, State, acquire, bind, component
from cordis_helpers import Hooks, Registry


def test_each_registration_is_its_own_entry_and_its_remover_takes_only_that() -> None:
    registry: Registry[int] = Registry("number")
    remove_one = registry.register("one", 1)
    remove_two = registry.register("two", 2)
    assert registry.names == ["one", "two"] and registry.values == [1, 2]
    assert list(registry) == [("one", 1), ("two", 2)] and len(registry) == 2
    remove_one()
    assert registry.names == ["two"] and "one" not in registry
    remove_one()  # idempotent
    remove_two()
    assert len(registry) == 0 and registry.get("two") is None


def test_two_entries_cannot_share_a_name_and_the_message_says_what_they_are() -> None:
    registry: Registry[int] = Registry("tool")
    registry.register("x", 1)
    with pytest.raises(ValueError, match="a tool named 'x' is already registered"):
        registry.register("x", 2)


def test_a_remover_does_not_take_a_later_entry_under_the_same_name() -> None:
    registry: Registry[int] = Registry()
    remove_first = registry.register("x", 1)
    remove_first()
    registry.register("x", 2)
    remove_first()  # the name is taken by another entry now; leave it
    assert registry.get("x") == 2


def test_hooks_are_a_set_with_per_hook_removal_and_a_snapshot_on_iteration() -> None:
    hooks: Hooks[str] = Hooks()
    remove_a = hooks.add("a")
    hooks.add("b")
    assert list(hooks) == ["a", "b"]
    for h in hooks:
        if h == "a":
            remove_a()  # removing while iterating is safe: iteration is over a snapshot
    assert list(hooks) == ["b"] and len(hooks) == 1


def test_the_same_hook_added_twice_is_two_registrations() -> None:
    """Definition 44: each registration is its own entry, even of one function."""
    hooks: Hooks[str] = Hooks()
    remove_one, remove_two = hooks.add("same"), hooks.add("same")
    remove_one()
    assert list(hooks) == ["same"]
    remove_one()  # idempotent: the other registration stays
    assert list(hooks) == ["same"]
    remove_two()
    assert list(hooks) == []


async def test_contributors_come_and_go_without_reloading_the_broker_or_each_other() -> None:
    @component
    async def broker() -> Effects:
        yield bind("things", Registry[str]("thing"))

    def contributor(name: str) -> object:
        @component
        async def row(*, things: Registry[str]) -> Effects:
            yield acquire(things.register, name, name.upper())

        return row

    rt = Runtime()
    b = rt.mount(broker, id="things")
    a, c = rt.mount(contributor("a"), id="a"), rt.mount(contributor("c"), id="c")
    await rt.settle()
    registry: Registry[str] = rt.root.get("things")
    assert registry.names == ["a", "c"]
    await a.retire()
    assert registry.names == ["c"] and c.state is State.ACTIVE and b.state is State.ACTIVE
    await rt.shutdown()
