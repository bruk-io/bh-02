"""The chat row. It is the loop as work its component owns, so it stops when its input or
output leaves and starts again against the replacement. It also binds that work's own task as `done`
(CONTRACTS.md), which is how the shell's bootstrap knows the chat row itself has finished without
waiting on every fiber's background work (Runtime.idle() is process-wide)."""

from chat_cordis_plugin import chat
from cordis import Effects, background, bind, component

__all__ = ["converse"]


@component(provides=("done",))
async def converse(
    *, loop: chat.Loop, input: chat.Input, output: chat.Output, commands: chat.Commands, jobs: chat.Jobs
) -> Effects:
    """An interactive chat: `use = "chat:converse"`. A line `commands` claims (a `/command`, or
    `!` and a shell command) goes to it; what `commands` holds for the model (`!`'s output) goes
    with the next message, and survives this row's restart, since `commands` holds it. It reads
    a line only once no restart a command queued in `jobs` is pending."""
    task = yield background(chat.converse(loop, input, output, commands, jobs))
    yield bind("done", task)
