"""What a chat does: converse until the input runs out.

`converse` is a plain function of the values this plugin declares its own contracts for
(CONTRACTS.md: loop, input, output, and commands if it has them). Nothing here touches a
terminal or cordis.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Commands",
    "Event",
    "Input",
    "Loop",
    "Output",
    "Recoverable",
    "converse",
    "is_command",
]

type Event = Mapping[str, Any]
"""One thing that happened in a turn (CONTRACTS.md: event). The chat row passes them through unread."""


@runtime_checkable
class Loop(Protocol):
    """What the chat row needs of the `loop` value."""

    def reply(self, message: str) -> AsyncIterator[Event]: ...


@runtime_checkable
class Input(Protocol):
    """Lines from the person, and their asking to stop the turn that is running."""

    async def read(self) -> str | None: ...
    async def interrupted(self) -> None: ...


@runtime_checkable
class Output(Protocol):
    async def show(self, events: AsyncIterator[Event]) -> None: ...
    async def notice(self, message: str) -> None: ...


@runtime_checkable
class Commands(Protocol):
    """What the session needs of the `commands` value: run a slash command, get what to show
    (text, or events: CONTRACTS.md, commands)."""

    async def run(self, line: str) -> str | Sequence[Event]: ...


def _answered(answer: str | Sequence[Event]) -> list[Event]:
    """A command's answer as the events to show: text is one note; events are shown as they are."""
    return [{"type": "note", "text": answer}] if isinstance(answer, str) else list(answer)


def is_command(line: str) -> bool:
    """Whether a line is for the harness rather than the model: `/name`, then whitespace or the end.
    A pasted `/tmp/app.py is broken` is not."""
    head = line.strip().split(maxsplit=1)[0] if line.strip() else ""
    return (
        len(head) > 1
        and head[0] == "/"
        and head[1].isalpha()
        and all(c.isalpha() or c == "-" for c in head[1:])
    )


@runtime_checkable
class Recoverable(Protocol):
    """A `loop` failure the person should see and can recover from: any exception shaped like this."""

    kind: str
    message: str


async def converse(loop: Loop, input: Input, output: Output, commands: Commands | None = None) -> None:
    """Read a message, show the streamed reply, repeat until there is no more input.

    A `/command` line goes to `commands` and never to the model; what it returns is shown
    (`_answered`: text as a note, events as they are).

    A recoverable failure is shown and the chat carries on; anything else leaves, and the
    bootstrap re-raises it. Returning is how the program ends: nothing is left running, so
    the runtime is idle.
    """
    while (message := await input.read()) is not None:
        if not message.strip():
            continue
        if commands is not None and is_command(message):
            await output.show(_each(_answered(await commands.run(message))))
            continue
        try:
            await _interruptible(_show(loop.reply(message), output), input, output)
        except Exception as error:
            if not isinstance(error, Recoverable):
                raise
            await output.notice(error.message)


async def _interruptible(turn: Awaitable[None], input: Input, output: Output) -> None:
    """Run a turn until it ends or the person interrupts it; an interrupted turn is cancelled
    (its reply closed, so a provider can stop its own work) and shown as stopped."""
    work = asyncio.ensure_future(turn)
    stop = asyncio.ensure_future(input.interrupted())
    try:
        await asyncio.wait({work, stop}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stop.cancel()
        if not work.done():
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
            await output.show(_once({"type": "stop", "reason": "interrupted"}))
    if not work.cancelled():
        work.result()


async def _once(event: Event) -> AsyncIterator[Event]:
    yield event


async def _each(events: Iterable[Event]) -> AsyncIterator[Event]:
    for event in events:
        yield event


async def _show(chunks: AsyncIterator[Event], output: Output) -> None:
    """Show a reply, and close it if the output stops reading early.

    A provider's cleanup (`agent:loop` closes its model step, and the Claude Code one interrupts
    Claude Code) runs when its generator is closed, which only happens on exhaustion or
    `aclose()`; an output that raises mid-stream does neither.
    """
    try:
        await output.show(chunks)
    finally:
        if isinstance(chunks, AsyncGenerator):
            await chunks.aclose()
