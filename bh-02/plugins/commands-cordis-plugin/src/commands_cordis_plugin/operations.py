"""Commands over the running composition: see it, explain a row, restart one.

They act through the loader's handle (cordis's operator API) and never through the runtime.
A restart replaces a row the chat session depends on, which restarts the session itself: so
restarts are queued in `jobs` (CONTRACTS.md: jobs), never run in the session's own task, which
they would cancel half-way, and `/restart` answers with a `restarting` event naming the row.
A row `jobs` depends on, directly or through others (the ui, which binds `output`), is refused: its
restart would reload `jobs` and cancel itself.
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


type Declare = Callable[[str], tuple[frozenset[str], frozenset[str]] | None]
"""A row's `use` -> the keys its component injects and provides, or None when it does not resolve."""


def _spec(name: str, help: str, usage: str = "") -> CommandSpec:
    return {"name": name, "help": help, "usage": usage}


def _unfinished(why: str) -> str:
    """What the person is told when a restart `/restart` queued failed (`why`): the command
    answered before its restart ran, so what it said may not hold."""
    return f"a command's restart failed ({why}); /rows shows what is running, and /restart ROW tries again"


def _jobs_needs(entries: Sequence[Any], declare: Declare) -> dict[str, str]:
    """The rows the `jobs` row depends on, directly or through other rows, each with the key it is
    reached by. A restart reloads the rows depending on the one restarted, and a restart run by
    `jobs` that reloads `jobs` is cancelled half-way. A row whose component `declare` does not know
    is left out."""
    declared: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for entry in entries:
        if getattr(entry, "disabled", False):
            continue
        if (keys := declare(str(entry.use))) is not None:
            declared[str(entry.id)] = keys
    needs: dict[str, str] = {}
    pending = [rid for rid, (_, provides) in declared.items() if "jobs" in provides]
    for rid in pending:
        needs[rid] = "jobs"
    while pending:
        inject = declared[pending.pop()][0]
        for key in sorted(inject):
            for rid, (_, provides) in declared.items():
                if key in provides and rid not in needs:
                    needs[rid] = key
                    pending.append(rid)
    return needs


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
    declare: Declare = lambda use: None
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
        if (key := _jobs_needs(self.loader.entries(), self.declare).get(args)) is not None:
            why = (
                "it is the row that runs restarts"
                if key == "jobs"
                else f"the jobs row depends on it ({key}), so it reloads with it"
            )
            return (
                f"/restart {args} is refused: {why}, which would cancel the restart half-way; "
                "quit and start bh-02 again"
            )
        self.jobs.put(lambda: self.loader.restart(args), _unfinished)
        return [{"type": "note", "text": f"restarting {args}"}, {"type": "restarting", "rows": [args]}]
