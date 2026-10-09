"""`/model`: the models there are, the current one marked, and a switch to one by name for this
session, beside the catalog it reads (`models`).

A switch edits the session's own layer file (the model row's `default`) and queues a reload of
the layers (the loader's watcher would notice the edit too, half a second later): the layer
files stay the only way the program's shape changes, and a resumed session keeps the choice.
The reload replaces the model row, which the chat session depends on and so restarts with it:
so it is queued in `jobs` (CONTRACTS.md: jobs), never run in the session's own task, which it
would cancel half-way; the chat row reads its next line only once the reload is done, so a line
typed meanwhile reaches the new model. The answer ends with a `restarting` event naming the
model row, which a ui names in what such a line says it waits for.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from cordis_helpers import Job

__all__ = ["Models", "Queue", "Reloads", "Switch", "SwitchConfig", "model_list"]

type Answer = str | Sequence[Mapping[str, Any]]


@runtime_checkable
class Reloads(Protocol):
    """What `/model` needs of the `loader` value (cordis.loader.Loader): which rows are running,
    and the layers read again now."""

    def status(self) -> dict[str, str]: ...
    async def reload(self) -> None: ...


@runtime_checkable
class Models(Protocol):
    """What `/model` needs of the `models` value (CONTRACTS.md: models): the models there are,
    the one the model row names now, why a name can't be switched to, the models file, and why
    that file is not read."""

    @property
    def path(self) -> str: ...
    @property
    def problem(self) -> str | None: ...
    def listed(self) -> Sequence[Mapping[str, Any]]: ...
    def current(self) -> Mapping[str, str]: ...
    def check(self, name: str) -> str | None: ...


@runtime_checkable
class Queue(Protocol):
    """What `/model` needs of the `jobs` value: the reload queued, and what the person is told if
    it fails."""

    def put(self, job: Job, failed: Callable[[str], str]) -> None: ...


@dataclass(frozen=True, slots=True)
class SwitchConfig:
    """`layer`: the session's layer file `/model` edits (none outside a session). `model_row`:
    the row that chooses the model there (`model`: its config's `default`)."""

    layer: str | None = None
    model_row: str = "model"


def model_list(models: Sequence[Mapping[str, Any]], path: str, problem: str | None = None) -> str:
    """`/model`'s answer: every model, the current one marked, aligned, with where to add more,
    or, when the models file is not read (`problem`), why and where it must be instead."""
    width = max((len(str(m["name"])) for m in models), default=0)
    kinds = max((len(str(m["provider"])) for m in models), default=0)
    lines = []
    for m in models:
        mark = "●" if m.get("current") else " "
        where = f"  at {m['where']}" if m.get("where") else ""
        line = f"{mark} {str(m['name']).ljust(width)}  {str(m['provider']).ljust(kinds)}  {m['id']}{where}"
        notes = [str(m[k]) for k in ("shadows", "problem") if m.get(k)]
        lines.append(line.rstrip() + "".join(f"\n    {note}" for note in notes))
    add = problem if problem is not None else f"add models in {path}"
    return "\n".join([*lines, f"/model NAME switches; {add}"])


def _unfinished(why: str) -> str:
    """What the person is told when the reload a `/model NAME` queued failed (`why`): it
    answered before the reload ran, so the model it named may not be the one running."""
    return (
        f"the model switch's reload failed ({why}), so the model may not be the one /model named; "
        "/rows shows what is running, and /restart ROW tries again"
    )


@dataclass
class Switch:
    """`/model` as a `(spec, run)` pair a row registers, over one loader, the `models` value and
    the `jobs` value."""

    loader: Reloads
    models: Models
    config: SwitchConfig
    jobs: Queue
    set_model: Callable[[str, str, str], None]  # (layer file, row, model name): edit a layer
    # (layer file, row): a later layer file that sets the row's config, and so replaces the one
    # `set_model` edits whole (a `--patch` naming the model row); None when none does
    shadowed: Callable[[str, str], str | None] = lambda layer, row: None

    def spec(self) -> dict[str, Any]:
        """`/model`'s spec, with a choice for each model, which the palette offers as its own
        entry (`/model haiku`), read each time the palette opens."""
        return {
            "name": "model",
            "help": "list the models, or switch to NAME for this session",
            "usage": "[NAME]",
            "choices": self._choices,
        }

    def _choices(self) -> list[Mapping[str, str]]:
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

    async def run(self, args: str) -> Answer:
        """List the models, the current one marked; or record NAME in the session's layer and
        reload it now. A name the row already has changes nothing, so nothing restarts; a name
        that isn't a usable model says why and changes nothing either."""
        row = self.config.model_row
        if not args:
            return model_list(self.models.listed(), self.models.path, self.models.problem)
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
        self.jobs.put(self.loader.reload, _unfinished)
        note = f"switching to {args} (the session's layer is reloaded; the conversation carries on)"
        restarting = [{"type": "restarting", "rows": [row]}] if row in self.loader.status() else []
        return [{"type": "note", "text": note}, *restarting]
