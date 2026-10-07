"""The `commands` value: slash commands by name, registered by whichever rows offer them.

The broker pattern (paper 6.2): one row binds the registry, rows `acquire` a registration whose
return value is its remover, so a row that leaves takes its commands with it and nothing else
notices. A line is a command only when it looks like one (`/name` then whitespace or the end),
so a pasted `/tmp/app.py is broken` still reaches the model.
"""

import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, NotRequired, TypedDict

from cordis_helpers import Registry

__all__ = ["Answer", "Choice", "CommandSpec", "Commands", "Run", "parse"]

_COMMAND = re.compile(r"/([a-z][a-z-]*)(?:\s+(.*))?", re.S)


class Choice(TypedDict):
    """One way to call a command the palette offers as its own entry: `/NAME ARGS`."""

    args: str
    help: str


class CommandSpec(TypedDict):
    """What `/help` shows: the name (no slash), what it does, and how to call it; `choices`,
    if any, the arguments the palette offers as entries of their own, read each time it opens
    (`/model`'s models)."""

    name: str
    help: str
    usage: str
    choices: NotRequired[Callable[[], Sequence[Mapping[str, str]]]]


type Answer = str | Sequence[Mapping[str, Any]] | AsyncIterator[Mapping[str, Any]]
"""What a command answers (CONTRACTS.md: commands): text, shown as one note, or events shown
as they are (`/clear`'s `cleared`, then a note saying so), or, from a command that takes a
while (`/compact`), events as they come, which a chat shows and stops as it does a reply."""

type Run = Callable[[str], Awaitable[Answer]]
"""A command: its argument text in, what to show the person out."""


def parse(line: str) -> tuple[str, str] | None:
    """`(name, arguments)` when `line` is a command, else None."""
    match = _COMMAND.fullmatch(line.strip())
    return (match.group(1), (match.group(2) or "").strip()) if match else None


class Commands:
    """The broker: bound once, registered into by many; `/help` is its own."""

    def __init__(self) -> None:
        self._commands: Registry[tuple[CommandSpec, Run]] = Registry("command")

    def register(self, spec: CommandSpec, run: Run) -> Callable[[], None]:
        return self._commands.register(spec["name"], (spec, run))

    def specs(self) -> list[CommandSpec]:
        return [spec for spec, _ in self._commands.values]

    async def run(self, line: str) -> Answer:
        """Run the command `line` names; an unknown one says so, and never reaches the model."""
        parsed = parse(line)
        if parsed is None:
            return f"{line.strip()!r} is not a command; /help lists them"
        name, args = parsed
        if name == "help":
            return self._help()
        entry = self._commands.get(name)
        if entry is None:
            return f"unknown command /{name}; /help lists them"
        try:
            answer = await entry[1](args)
        except Exception as error:
            return f"/{name} failed: {error}"
        return _guarded(name, answer) if isinstance(answer, AsyncIterator) else answer

    def _help(self) -> str:
        rows = [("/help", "list the commands")]
        rows += [
            (f"/{s['name']}" + (f" {s['usage']}" if s["usage"] else ""), s["help"]) for s in self.specs()
        ]
        # no key to leave by: that is each ui's own (the app's Ctrl-Q; another ui would name its
        # own), and each ui says it; Ctrl-C stops a reply in every ui (CONTRACTS.md: input.interrupted)
        rows += [("/exit", "leave; Ctrl-C stops a reply, or a command still at work")]
        width = max(len(call) for call, _ in rows)
        return "\n".join(f"{call.ljust(width)}  {what}" for call, what in sorted(rows))


async def _guarded(name: str, events: AsyncIterator[Mapping[str, Any]]) -> AsyncIterator[Mapping[str, Any]]:
    """A streamed answer's events as they come; one that fails part-way ends with a note saying
    so, as a command that fails before answering does. Closed early (Ctrl-C), it closes the
    command's own stream, so the command stops what it runs."""
    try:
        async for event in events:
            yield event
    except Exception as error:
        yield {"type": "note", "text": f"/{name} failed: {error}"}
    finally:
        if isinstance(events, AsyncGenerator):
            await events.aclose()
