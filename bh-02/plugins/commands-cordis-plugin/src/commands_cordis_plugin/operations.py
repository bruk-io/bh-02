"""Commands over the running composition: see it, explain a row, restart one.

They act through the loader's handle (cordis's operator API) and never through the runtime.
A restart replaces a row the chat session depends on, which restarts the session itself: so
restarts are queued in `jobs` (CONTRACTS.md: jobs), never run in the session's own task, which
they would cancel half-way, and `/restart` answers with a `restarting` event naming the row.
(`/model` is the models plugin's, beside the catalog it reads; `/clear` and `/compact` the agent
plugin's conversation row's, beside the transcript they rewrite.)
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from commands_cordis_plugin.registry import Answer, CommandSpec, Run
from cordis_helpers import Job

__all__ = ["Loader", "Operator", "Queue", "rows_table"]


@runtime_checkable
class Loader(Protocol):
    """What the operator needs of the `loader` value (cordis.loader.Loader)."""

    def status(self) -> dict[str, str]: ...
    def explain(self, rid: str) -> str: ...
    async def restart(self, *rids: str) -> None: ...
    def entries(self) -> Sequence[Any]: ...


@runtime_checkable
class Queue(Protocol):
    """What a command that restarts rows needs of the `jobs` value: a restart queued, and what
    the person is told if it fails."""

    def put(self, job: Job, failed: Callable[[str], str]) -> None: ...


def _spec(name: str, help: str, usage: str = "") -> CommandSpec:
    return {"name": name, "help": help, "usage": usage}


def _unfinished(why: str) -> str:
    """What the person is told when a restart `/restart` queued failed (`why`): the command
    answered before its restart ran, so what it said may not hold."""
    return f"a command's restart failed ({why}); /rows shows what is running, and /restart ROW tries again"


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
    jobs: Queue
    specs: list[tuple[CommandSpec, Run]] = field(init=False)

    def __post_init__(self) -> None:
        self.specs = [
            (_spec("rows", "the running composition: each row, its plugin, its state"), self.rows),
            (_spec("explain", "what cordis knows about a row", "ROW"), self.explain),
            (_spec("restart", "start a row afresh (its dependents reload)", "ROW"), self.restart),
        ]

    async def rows(self, args: str) -> str:
        uses = {str(e.id): str(e.use) for e in self.loader.entries()}
        return rows_table(self.loader.status(), uses)

    async def explain(self, args: str) -> str:
        return self.loader.explain(args) if args else "which row? /rows lists them"

    async def restart(self, args: str) -> Answer:
        if args not in self.loader.status():
            return f"no row {args!r}; /rows lists them"
        self.jobs.put(lambda: self.loader.restart(args), _unfinished)
        return [{"type": "note", "text": f"restarting {args}"}, {"type": "restarting", "rows": [args]}]
