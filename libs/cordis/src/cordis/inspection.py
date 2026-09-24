"""The runtime's read-only view: what anything outside cordis reads it through.

`Inspection(rt)` is the observation surface: a harness that reads through it never depends
on how the store or the registry happen to be laid out.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cordis.decisions import Resolved, State
from cordis.effects import Key, key_name, sort_key
from cordis.runtime import Event, Fiber, Runtime, provider_of


@dataclass(frozen=True, slots=True)
class Held:
    """One binding, as seen from outside."""

    key: Key
    value: Any
    owner: str
    uid: int

    def __str__(self) -> str:
        return f"{key_name(self.key)} <- {self.owner}#{self.uid}"


class Inspection:
    """A view over one runtime. Its properties are computed on access, so a held Inspection
    keeps reading live state."""

    __slots__ = ("_rt",)

    def __init__(self, rt: Runtime) -> None:
        self._rt = rt

    @property
    def fibers(self) -> list[Fiber]:
        return [f for f in self._rt.registry if f is not self._rt.root_fiber]

    @property
    def bindings(self) -> dict[Key, Held]:
        out: dict[Key, Held] = {}
        for fiber in self.fibers:
            for key in fiber.bound:
                out[key] = Held(key, fiber.ctx.get(key), fiber.name, fiber.uid)
        return out

    @property
    def events(self) -> Sequence[Event]:
        return tuple(self._rt.events)

    def fiber(self, name: str) -> Fiber | None:
        return next((f for f in self.fibers if f.name == name), None)

    def waiting_on(self, fiber: Fiber) -> list[Key]:
        """Which of a fiber's dependencies have no ACTIVE provider right now."""
        lookup = provider_of(fiber)
        return [
            key
            for key in sorted(fiber.component.inject, key=sort_key)
            if (found := lookup(key)) is None or found[1] is not State.ACTIVE
        ]

    def explain(self, name: str) -> str:
        """A fiber's state, what it binds, what it did, what it waits on, and its recent events."""
        fiber = self.fiber(name)
        if fiber is None:
            return f"{name}: not mounted"
        status = fiber.state.value
        if fiber.state is State.ACTIVE and fiber.error is not None:
            status += ", work failed"  # the error itself is still the `error:` line below
        lines = [f"{fiber.name}#{fiber.uid}: {status}"]
        if fiber.bound:
            lines.append(f"  binds: {', '.join(sorted(key_name(k) for k in fiber.bound))}")
        if fiber.performed:
            lines.append(f"  performed: {', '.join(str(e) for e in fiber.performed)}")
        if waiting := self.waiting_on(fiber):
            lines.append(f"  waiting on: {', '.join(key_name(k) for k in waiting)}")
        elif isinstance(fiber.target, Resolved) and fiber.target.providers:
            lines.append("  uses: " + ", ".join(f"{key_name(k)}#{uid}" for k, uid in fiber.target.providers))
        if fiber.error is not None:
            lines.append(f"  error: {fiber.error!r}")
        lines.extend(f"  {e}" for e in [str(e) for e in self._rt.events if e.uid == fiber.uid][-4:])
        return "\n".join(lines)

    def __str__(self) -> str:
        return "\n".join(f"{f.name}#{f.uid}: {f.state.value}" for f in self.fibers)
