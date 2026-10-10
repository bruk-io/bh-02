"""What a chat does: converse until the input runs out.

`converse` is a plain function of the values this plugin declares its own contracts for
(CONTRACTS.md: loop, input, output, and commands if it has them). Nothing here touches a
terminal or cordis. Which lines are commands is the `commands` value's to say (`claims`): a
slash command, or a line starting with a prefix a row claimed (`!`, a shell command). What a
command leaves for the model (`!`'s output) the `commands` value holds, not this row, so a
restart of this row (`/model` reloads the loop, and this row with it) keeps it.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Commands",
    "Event",
    "Input",
    "Jobs",
    "Loop",
    "Output",
    "Recoverable",
    "converse",
]

type Event = Mapping[str, Any]
"""One thing that happened in a turn (CONTRACTS.md: event). The chat row passes them through unread."""


@runtime_checkable
class Loop(Protocol):
    """What the chat row needs of the `loop` value."""

    def reply(self, message: str) -> AsyncIterator[Event]: ...


@runtime_checkable
class Input(Protocol):
    """Lines from the person; their asking to stop the turn that is running (`interrupted`);
    and their having left (`closed`: no more lines will come)."""

    async def read(self) -> str | None: ...
    async def interrupted(self) -> None: ...
    async def closed(self) -> None: ...


@runtime_checkable
class Output(Protocol):
    async def show(self, events: AsyncIterator[Event]) -> None: ...
    async def notice(self, message: str) -> None: ...


@runtime_checkable
class Commands(Protocol):
    """What the session needs of the `commands` value: whether a line is the harness's rather
    than the model's; to run one, getting what to show (text, or events: CONTRACTS.md,
    commands); and to take what commands left for the model's next message (`!`'s output)."""

    def claims(self, line: str) -> bool: ...
    async def run(self, line: str) -> str | Sequence[Event]: ...
    def take_for_model(self) -> Sequence[str]: ...


@runtime_checkable
class Jobs(Protocol):
    """What the session needs of the `jobs` value: to wait until no restart a command queued is
    pending, so the next line reaches the rows as they are after it."""

    async def settled(self) -> None: ...


def _answered(answer: str | Sequence[Event]) -> list[Event]:
    """A command's answer as the events to show: text is one note; events are shown as they are."""
    return [{"type": "note", "text": answer}] if isinstance(answer, str) else list(answer)


def _told(held: Sequence[str], message: str) -> str:
    """The message the loop is given: what commands held for the model, in the order they ran,
    then the person's own, each a paragraph of its own."""
    return "\n\n".join([*held, message])


@runtime_checkable
class Recoverable(Protocol):
    """A `loop` failure the person should see and can recover from: any exception shaped like this."""

    kind: str
    message: str


async def converse(
    loop: Loop, input: Input, output: Output, commands: Commands | None = None, jobs: Jobs | None = None
) -> None:
    """Read a message, show the streamed reply, repeat until there is no more input.

    A line `commands` claims (a `/command`, or one starting with a claimed prefix, `!`) goes to
    it and never to the model, and what it answers is shown (`_answered`: text as a note,
    events as they are). It runs until it answers or the input closes (the person left: a
    `!` command may run for minutes, and nobody is left to read its answer), which cancels it.
    What commands left for the model (`for_model`: `!`'s output, which `commands` holds) is
    taken and put in front of the person's next message (`_told`), so the model reads it with
    that and never during a turn. The loop's contract is unchanged: it is given one message.

    Before each read it waits until no restart a command queued is pending (`jobs.settled`): a
    restart of the loop (`/clear`, `/compact`, `/model NAME`, `/restart loop`) reloads this row,
    which is then waiting, not holding a line, so a line typed meanwhile stays with the input
    and the new row reads it and sends it to the new loop, never the old one.

    A recoverable failure is shown and the chat carries on; anything else leaves, and the
    bootstrap re-raises it. Returning is how the program ends: nothing is left running, so
    the runtime is idle.
    """
    while True:
        if jobs is not None:
            await jobs.settled()
        if (message := await input.read()) is None:
            return
        if not message.strip():
            continue
        if commands is not None and commands.claims(message):
            answer = await _unless_closed(commands.run(message), input)
            if answer is not None:
                await output.show(_each(_answered(answer)))
            continue
        told = _told(commands.take_for_model() if commands is not None else (), message)
        try:
            await _interruptible(_show(loop.reply(told), output), input, output)
        except Exception as error:
            if not isinstance(error, Recoverable):
                raise
            await output.notice(error.message)


async def _unless_closed[T](work: Awaitable[T], input: Input) -> T | None:
    """Run a command until it answers (its answer), or until the input closes (None): then it
    is cancelled, and its own cleanup (a `!` command's process group ended) runs first. Ctrl-C
    is a turn's (`interrupted`), so it does not stop a command."""
    run = asyncio.ensure_future(work)
    gone = asyncio.ensure_future(input.closed())
    try:
        await asyncio.wait({run, gone}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        gone.cancel()
        if not run.done():
            run.cancel()
            await asyncio.gather(run, return_exceptions=True)
    return None if run.cancelled() else run.result()


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
