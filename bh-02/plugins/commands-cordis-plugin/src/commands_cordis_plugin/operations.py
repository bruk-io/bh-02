"""Commands over the running composition: see it, explain a row, restart one, clear.

They act through the loader's handle (cordis's operator API) and never through the runtime.
A restart replaces a row the chat session depends on, which restarts the session itself: so
restarts are queued for work the operator row owns (`jobs`, run by cordis-helpers' `perform`),
never run in the session's own task, which they would cancel half-way. `/clear` answers with a
`cleared` event (CONTRACTS.md: event), so a ui drops the old conversation from its screen, and
ends with a `restarting` event naming the rows it restarts, so a ui holds a line typed
meanwhile for them instead of handing it to the old loop. (`/model` is the models plugin's,
beside the catalog it reads.)
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from commands_cordis_plugin.registry import Answer, CommandSpec, Run
from cordis_helpers import Job

__all__ = ["Loader", "Operator", "OperatorConfig", "rows_table", "unfinished"]


@runtime_checkable
class Loader(Protocol):
    """What the operator needs of the `loader` value (cordis.loader.Loader)."""

    def status(self) -> dict[str, str]: ...
    def explain(self, rid: str) -> str: ...
    async def restart(self, *rids: str) -> None: ...
    def entries(self) -> Sequence[Any]: ...


@dataclass(frozen=True, slots=True)
class OperatorConfig:
    """`clear`: the rows `/clear` starts afresh, together; `forget`: the files it empties first
    (the loop's transcript), or the restarted rows would just read the old conversation back."""

    clear: Sequence[str] = ("loop", "transcript", "kernel")
    forget: Sequence[str] = ()


def _spec(name: str, help: str, usage: str = "") -> CommandSpec:
    return {"name": name, "help": help, "usage": usage}


def _restarting(rows: Sequence[str], running: Mapping[str, str]) -> list[Mapping[str, Any]]:
    """The `restarting` event for the rows among `rows` that are running, or none if none are."""
    named = [rid for rid in rows if rid in running]
    return [{"type": "restarting", "rows": named}] if named else []


def unfinished(why: str) -> str:
    """What the person is told when a restart a command queued (/clear, /restart) failed
    (`why`): the command answered before its restart ran, so what it said may not hold (after
    /clear the loop may still hold the old conversation, and write it to the emptied file)."""
    return (
        f"a command's restart failed ({why}), so the rows may not be as it said (after /clear the "
        "loop may still hold the old conversation); /rows shows what is running, and /restart ROW "
        "tries again"
    )


def rows_table(status: Mapping[str, str], uses: Mapping[str, str]) -> str:
    """Every row, what fills it, and its state, aligned."""
    width = max((len(rid) for rid in status), default=0)
    used = max((len(uses.get(rid, "")) for rid in status), default=0)
    return "\n".join(
        f"{rid.ljust(width)}  {uses.get(rid, '').ljust(used)}  {state}"
        for rid, state in sorted(status.items())
    )


@dataclass
class Operator:
    """The commands, as `(spec, run)` pairs a row registers, over one loader and one job queue."""

    loader: Loader
    config: OperatorConfig
    jobs: asyncio.Queue[Job]
    specs: list[tuple[CommandSpec, Run]] = field(init=False)

    def __post_init__(self) -> None:
        self.specs = [
            (_spec("rows", "the running composition: each row, its plugin, its state"), self.rows),
            (_spec("explain", "what cordis knows about a row", "ROW"), self.explain),
            (_spec("restart", "start a row afresh (its dependents reload)", "ROW"), self.restart),
            (_spec("clear", "a new conversation and an empty kernel"), self.clear),
        ]

    async def rows(self, args: str) -> str:
        uses = {str(e.id): str(e.use) for e in self.loader.entries()}
        return rows_table(self.loader.status(), uses)

    async def explain(self, args: str) -> str:
        return self.loader.explain(args) if args else "which row? /rows lists them"

    async def restart(self, args: str) -> str:
        if args not in self.loader.status():
            return f"no row {args!r}; /rows lists them"
        await self.jobs.put(lambda: self.loader.restart(args))
        return f"restarting {args}"

    async def clear(self, args: str) -> Answer:
        """Start a new conversation: forget, restart the rows, and tell the ui the conversation
        starts afresh (`cleared`), then say so in a note a ui that doesn't know `cleared` shows,
        then which rows are restarting (`restarting`), last: the restart may stop the session
        showing this answer, and the note is what must not be lost."""
        running = self.loader.status()
        chosen = [rid for rid in self.config.clear if rid in running]

        async def job() -> None:
            for path in self.config.forget:
                if Path(path).is_file():
                    Path(path).write_text("")
            # together: a row depending on several of them (the chat row, on `loop`) reloads once
            await self.loader.restart(*chosen)

        await self.jobs.put(job)
        return [
            {"type": "cleared"},
            {"type": "note", "text": f"the conversation was cleared; starting afresh: {', '.join(chosen)}"},
            *_restarting(chosen, running),
        ]
