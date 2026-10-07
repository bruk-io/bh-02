"""The paper's service broker (section 6.2) with the domain stripped out.

A registry is a value one row binds and many rows contribute to. Each contribution returns
the function that withdraws it, so a contributor yields `acquire(registry.register, ...)` and
cordis keeps the remover as the undo. Consumers depend on the registry, never on a
contributor: adding or removing one reloads nobody.

Both classes keep the paper's commutativity condition (Definition 44): every registration is
its own entry, so any subset can be withdrawn in any order. That is what makes a set of
contributors safe to compose from a layer file, where order carries no meaning.
"""

from collections.abc import Callable, Iterator

__all__ = ["Hooks", "Registry"]


class Registry[T]:
    """Entries by name. Two entries cannot share a name; a name is one entry."""

    def __init__(self, what: str = "entry") -> None:
        self._what = what  # what an entry is called in messages: "tool", "command"
        self._entries: dict[str, T] = {}

    def register(self, name: str, entry: T) -> Callable[[], None]:
        """Add an entry; returns the remover, which takes only this entry and is idempotent."""
        if name in self._entries:
            raise ValueError(
                f"a {self._what} named {name!r} is already registered; a name is one entry, so "
                f"retire the row that registered it first"
            )
        self._entries[name] = entry

        def remove() -> None:
            if self._entries.get(name) is entry:
                del self._entries[name]

        return remove

    def get(self, name: str) -> T | None:
        return self._entries.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[tuple[str, T]]:
        return iter(list(self._entries.items()))

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def names(self) -> list[str]:
        return list(self._entries)

    @property
    def values(self) -> list[T]:
        return list(self._entries.values())


class Hooks[F]:
    """A set of callables whose order must not matter: guards, listeners, policies."""

    def __init__(self) -> None:
        self._hooks: list[tuple[object, F]] = []

    def add(self, fn: F) -> Callable[[], None]:
        """Add a hook; returns the remover, which takes only this registration and is
        idempotent. Two rows adding the same function hold two registrations, so either can
        leave without taking the other's."""
        mine = object()
        self._hooks.append((mine, fn))

        def remove() -> None:
            self._hooks[:] = [entry for entry in self._hooks if entry[0] is not mine]

        return remove

    def __iter__(self) -> Iterator[F]:
        # a snapshot, the list copied in one step: a hook may add or remove hooks, and one
        # iterating in a worker thread must not see the list shift under it while the event loop
        # adds or removes one (it would skip a hook, or see one twice)
        return iter([fn for _, fn in list(self._hooks)])

    def __len__(self) -> int:
        return len(self._hooks)
