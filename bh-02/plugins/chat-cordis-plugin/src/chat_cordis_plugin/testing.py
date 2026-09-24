"""Fakes for the four values the chat row consumes, shaped as CONTRACTS.md says. For tests, no terminal."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

__all__ = ["Angry", "Echo", "Noted", "Screen", "Typed"]


class Echo:
    """A `loop` that echoes each word, and remembers everything it was asked."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        self.seen.append(message)
        for word in message.split():
            yield {"type": "text", "text": f"{word} "}


class _Slow(Exception):
    """A recoverable failure: any exception with `kind` and `message`."""

    def __init__(self) -> None:
        super().__init__("slow down")
        self.kind, self.message = "rate_limit", "slow down"


class Angry:
    """A `loop` whose every reply is a recoverable failure."""

    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        raise _Slow()
        yield  # pragma: no cover


class Typed:
    """An `input` fed by the test."""

    def __init__(self, *lines: str) -> None:
        self.lines: asyncio.Queue[str | None] = asyncio.Queue()
        for line in lines:
            self.lines.put_nowait(line)

        self._interrupt = asyncio.Event()

    def type(self, line: str | None) -> None:
        self.lines.put_nowait(line)

    def interrupt(self) -> None:
        """Ctrl-C: stop the turn that is running."""
        self._interrupt.set()

    async def read(self) -> str | None:
        return await self.lines.get()

    async def interrupted(self) -> None:
        await self._interrupt.wait()
        self._interrupt.clear()


class Screen:
    """An `output` that collects what it was shown: each reply's text, and every event."""

    def __init__(self) -> None:
        self.shown: list[str] = []
        self.events: list[Mapping[str, Any]] = []
        self.notices: list[str] = []

    async def show(self, events: AsyncIterator[Mapping[str, Any]]) -> None:
        """Record as the events arrive, so a reply cut off part-way shows what it got to."""
        self.shown.append("")
        async for event in events:
            self.events.append(event)
            if event.get("type") == "text":
                self.shown[-1] += str(event["text"])

    async def notice(self, message: str) -> None:
        self.notices.append(message)


class Noted:
    """A `commands` value that answers every command with what it was asked, except `/clear`,
    which answers with events (CONTRACTS.md: commands), as the operator's does."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    async def run(self, line: str) -> str | list[Mapping[str, Any]]:
        self.ran.append(line)
        if line.strip() == "/clear":
            return [{"type": "cleared"}, {"type": "note", "text": "cleared"}]
        return f"ran {line}"
