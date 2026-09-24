"""Effects: a deferred step and its undo.

An effect is the only way a component changes the world, and the runtime is the only thing
that performs one. The paper's revertible effect is `e : Gamma -> Gamma x (Gamma -> Gamma)`:
a step that produces a new state and the function that reverses it. Here a step is an
ordinary function of the fiber's context returning `(result, undo)`, and `Effect` is that
step with its arguments, not yet performed.

    def subscribe_step(ctx: Context, feed: Feed) -> tuple[Sub, Undo | None]:
        sub = feed.subscribe()
        return sub, sub.unsubscribe

    def subscribe(feed: Feed) -> Effect[Sub]:
        return effect(subscribe_step, feed)

A step that changes nothing reversible returns `(result, None)`. This module is the bottom
of cordis: it imports nothing from the rest of it and performs nothing, so a step is an
ordinary function that can be written and tested without a runtime. The five steps the
framework itself ships live in `cordis.runtime`, because they are what touches the runtime.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

type Key = str
type Undo = Callable[[], Awaitable[None] | object]
type Result[T] = tuple[T, Undo | None]
type Step[T] = Callable[..., Result[T] | Awaitable[Result[T]]]


@dataclass(frozen=True, slots=True)
class Effect[T]:
    """A step and its arguments, not yet performed.

    Components yield these; the runtime performs them, records the undo on the fiber, and
    sends the result back into the generator.
    """

    step: Step[T]
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """The step's name without the `_step` suffix: `bind`, `enter`, `subscribe`."""
        return getattr(self.step, "__name__", type(self.step).__name__).removesuffix("_step")

    def __str__(self) -> str:
        shown = [_short(a) for a in self.args] + [f"{k}={_short(v)}" for k, v in self.kwargs.items()]
        return f"{self.name}({', '.join(shown)})"


type Effects = AsyncGenerator[Effect[Any], Any]
"""What a component's generator yields and receives: effects out, their results back in."""


def effect[T](step: Step[T], *args: Any, **kwargs: Any) -> Effect[T]:
    """Defer a step: `effect(subscribe_step, feed)` is the effect, not the subscription."""
    return Effect(step, args, kwargs)


def key_name(key: Key) -> str:
    """A key as it reads in a message."""
    return key


def sort_key(key: Key) -> str:
    """A stable order over keys."""
    return key


def _short(value: object) -> str:
    text = getattr(value, "__name__", None) or str(value)
    return text if len(text) <= 40 else f"{text[:37]}..."
