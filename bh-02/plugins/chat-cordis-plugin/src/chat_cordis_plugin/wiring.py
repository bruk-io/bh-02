"""The chat row. It is the loop as work its component owns, so it stops when its input or
output leaves and starts again against the replacement. It also binds that work's own task as `done`
(CONTRACTS.md), which is how the shell's bootstrap knows the chat row itself has finished without
waiting on every fiber's background work (Runtime.idle() is process-wide)."""

from chat_cordis_plugin.chat import Commands, Input, Loop, Output, converse
from cordis import Effects, background, bind, component

__all__ = ["session"]


@component(provides=("done",))
async def session(*, loop: Loop, input: Input, output: Output, commands: Commands) -> Effects:
    """An interactive chat: `use = "chat:session"`. A line `commands` claims (a `/command`, or
    `!` and a shell command) goes to it; what it holds for the model goes with the next message."""
    task = yield background(converse(loop, input, output, commands))
    yield bind("done", task)
