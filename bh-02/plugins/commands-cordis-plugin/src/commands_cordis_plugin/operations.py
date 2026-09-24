"""Commands over the running composition: see it, explain a row, restart one, clear, switch model.

They act through the loader's handle (cordis's operator API) and never through the runtime.
A restart replaces a row the chat session depends on, which restarts the session itself: so
restarts are queued for work the operator row owns (`jobs`), never run in the session's own
task, which they would cancel half-way. `/clear` answers with a `cleared` event
(CONTRACTS.md: event), so a ui drops the old conversation from its screen. `/model` edits
the session's own layer file and queues a reload of the layers (the loader's watcher would
notice the edit too, half a second later): the layer files stay the only way the program's
shape changes, and a resumed session keeps the choice. Both end their answer with a
`restarting` event naming the rows they restart, so a ui holds a line typed meanwhile for
them instead of handing it to the old model.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from commands_cordis_plugin.registry import Answer, CommandSpec, Run

__all__ = ["Loader", "Models", "Operator", "OperatorConfig", "model_list", "perform", "rows_table"]

type Job = Callable[[], Awaitable[None]]


@runtime_checkable
class Loader(Protocol):
    """What the operator needs of the `loader` value (cordis.loader.Loader)."""

    def status(self) -> dict[str, str]: ...
    def explain(self, rid: str) -> str: ...
    async def restart(self, *rids: str) -> None: ...
    async def reload(self) -> None: ...
    def entries(self) -> Sequence[Any]: ...


@runtime_checkable
class Models(Protocol):
    """What the operator needs of the `models` value (CONTRACTS.md: models): the models there
    are, the one the model row names now, why a name can't be switched to, and the models file."""

    @property
    def path(self) -> str: ...
    def listed(self) -> Sequence[Mapping[str, Any]]: ...
    def current(self) -> Mapping[str, str]: ...
    def check(self, name: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class OperatorConfig:
    """`layer`: the session's layer file `/model` edits (none outside a session). `model_row`:
    the row that chooses the model there (`model`: its config's `default`). `clear`: the
    rows `/clear` starts afresh, together; `forget`: the files it empties first (the loop's
    transcript), or the restarted rows would just read the old conversation back."""

    layer: str | None = None
    model_row: str = "model"
    clear: Sequence[str] = ("loop", "transcript", "kernel")
    forget: Sequence[str] = ()


def _spec(name: str, help: str, usage: str = "") -> CommandSpec:
    return {"name": name, "help": help, "usage": usage}


def _restarting(rows: Sequence[str], running: Mapping[str, str]) -> list[Mapping[str, Any]]:
    """The `restarting` event for the rows among `rows` that are running, or none if none are."""
    named = [rid for rid in rows if rid in running]
    return [{"type": "restarting", "rows": named}] if named else []


def rows_table(status: Mapping[str, str], uses: Mapping[str, str]) -> str:
    """Every row, what fills it, and its state, aligned."""
    width = max((len(rid) for rid in status), default=0)
    used = max((len(uses.get(rid, "")) for rid in status), default=0)
    return "\n".join(
        f"{rid.ljust(width)}  {uses.get(rid, '').ljust(used)}  {state}"
        for rid, state in sorted(status.items())
    )


def model_list(models: Sequence[Mapping[str, Any]], path: str) -> str:
    """`/model`'s answer: every model, the current one marked, aligned, with where to add more."""
    width = max((len(str(m["name"])) for m in models), default=0)
    kinds = max((len(str(m["provider"])) for m in models), default=0)
    lines = []
    for m in models:
        mark = "●" if m.get("current") else " "
        where = f"  at {m['where']}" if m.get("where") else ""
        line = f"{mark} {str(m['name']).ljust(width)}  {str(m['provider']).ljust(kinds)}  {m['id']}{where}"
        notes = [str(m[k]) for k in ("shadows", "problem") if m.get(k)]
        lines.append(line.rstrip() + "".join(f"\n    {note}" for note in notes))
    return "\n".join([*lines, f"/model NAME switches; add models in {path}"])


@dataclass
class Operator:
    """The commands, as `(spec, run)` pairs a row registers, over one loader and one job queue."""

    loader: Loader
    models: Models
    config: OperatorConfig
    jobs: asyncio.Queue[Job]
    set_model: Callable[[str, str, str], None]  # (layer file, row, model name): edit a layer
    # (layer file, row): a later layer file that sets the row's config, and so replaces the one
    # `set_model` edits whole (a `--patch` naming the model row); None when none does
    shadowed: Callable[[str, str], str | None] = lambda layer, row: None
    specs: list[tuple[CommandSpec, Run]] = field(init=False)

    def __post_init__(self) -> None:
        self.specs = [
            (_spec("rows", "the running composition: each row, its plugin, its state"), self.rows),
            (_spec("explain", "what cordis knows about a row", "ROW"), self.explain),
            (_spec("restart", "start a row afresh (its dependents reload)", "ROW"), self.restart),
            (_spec("clear", "a new conversation and an empty kernel"), self.clear),
            (self._model_spec(), self.model),
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

    def _model_spec(self) -> CommandSpec:
        """`/model`'s spec, with a choice for each model, which the palette offers as its own
        entry (`/model haiku`), read each time the palette opens."""
        spec = _spec("model", "list the models, or switch to NAME for this session", "[NAME]")
        spec["choices"] = self._model_choices
        return spec

    def _model_choices(self) -> list[Mapping[str, str]]:
        try:
            listed = self.models.listed()
        except Exception:  # a models file that can't be read: /model says what is wrong
            return []
        return [
            {
                "args": str(m["name"]),
                "help": f"the model now ({m['provider']}: {m['id']})"
                if m.get("current")
                else f"switch to {m['name']} ({m['provider']}: {m['id']})",
            }
            for m in listed
            if not m.get("problem")
        ]

    async def model(self, args: str) -> Answer:
        """List the models, the current one marked; or record NAME in the session's layer and
        reload it now. A name the row already has changes nothing, so nothing restarts; a name
        that isn't a usable model says why and changes nothing either."""
        row = self.config.model_row
        if not args:
            return model_list(self.models.listed(), self.models.path)
        if args.startswith("/") or len(args.split()) != 1:
            return f"not a model name: {args!r}; type /model and one name, e.g. /model sonnet"
        if self.config.layer is None:
            return "no session layer to record the model in; start bh-02 with --model instead"
        if args == self.models.current()["name"]:
            return f"model: {args} already; nothing to switch"
        if (why := self.models.check(args)) is not None:
            return f"not switched: {why}"
        if (patch := self.shadowed(self.config.layer, row)) is not None:
            return (
                f"not switched: {patch} sets the {row!r} row's config, which replaces the session's "
                "(where /model records the model) whole, so the model that file names stays. Set "
                f'`default = "{args}"` in that file\'s {row!r} row, or run without it'
            )
        self.set_model(self.config.layer, row, args)
        await self.jobs.put(self.loader.reload)
        note = f"switching to {args} (the session's layer is reloaded; the conversation carries on)"
        return [{"type": "note", "text": note}, *_restarting([row], self.loader.status())]


async def perform(jobs: asyncio.Queue[Job], failed: Callable[[str], None]) -> None:
    """The operator's own work: run queued jobs one at a time, for as long as the row is up. A
    job that fails is reported and the next one still runs."""
    while True:
        job = await jobs.get()
        try:
            await job()
        except Exception as error:
            failed(f"{type(error).__name__}: {error}")
