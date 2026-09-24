"""Drive a component by hand: no runtime, no fiber, just the effects it yields.

A component is an async generator, so a test can call it with fakes for its dependencies
and read the effects off it one by one. This module makes that a line:

    effects = await drive(git_tools(git=GitClient("git", FakeSubprocess())))
    assert [e.name for e in effects] == ["bind"]
    assert effects[0].args[0] == "git_status"

Nothing is performed. A step that a test does want to run is a plain function of a
context: call it (`subscribe_step(fake_ctx, feed)`) and check the `(result, undo)` it returns.
"""

from collections.abc import Iterable
from contextlib import aclosing
from typing import Any

from cordis.effects import Effect, Effects


async def drive(gen: Effects, replies: Iterable[Any] = ()) -> list[Effect[Any]]:
    """Run a component's generator to the end and return the effects it yielded, in order.

    Each yielded effect is answered with the next item of `replies` (what the runtime would
    have sent back as the effect's result), then `None` once the script runs out. The
    generator is closed afterwards even if it raises, so a component that holds a
    resource across yields sees the same exit it would under the runtime.
    """
    script = iter(replies)
    effects: list[Effect[Any]] = []
    async with aclosing(gen):
        send: Any = None
        while True:
            try:
                item = await gen.asend(send)
            except StopAsyncIteration:
                return effects
            if not isinstance(item, Effect):
                raise TypeError(f"the component yielded a {type(item).__name__}; a component yields effects")
            effects.append(item)
            send = next(script, None)
