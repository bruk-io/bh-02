"""The rows: the model itself, bound under `model`; the models there are, under `models`; and
`/model`, which lists them and switches by name."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, Row, acquire, bind, component, enter
from cordis.composition import format_layer
from cordis.loader import Loader as _Mounting
from cordis.loader import read_layer
from models_cordis_plugin.catalog import Catalog, Entries
from models_cordis_plugin.local_env import Credentials
from models_cordis_plugin.named import ModelConfig
from models_cordis_plugin.providers import opened
from models_cordis_plugin.switch import Models, Queue, Reloads, Switch, SwitchConfig

__all__ = ["CatalogConfig", "catalog", "model", "set_model", "shadowing", "switch"]


@runtime_checkable
class _Registrar(Protocol):
    """What `/model` needs of the `commands` value: a registration and its remover."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@component(provides=("model",))
async def model(*, config: ModelConfig, layers: Credentials) -> Effects:
    """Fills a `model` row: `use = "models:model"`. The model `config.default` names, on its
    provider, entered for as long as the row is up (`/model` changes `default`, which reloads
    this row alone and whatever depends on `model`).

    Nothing starts until the first step (Claude Code needs the request's system prompt and
    tools; a key is read per request), so a composition without a credential comes up, and
    each step says what is missing. A model that can't be used (an unknown name, a table
    with a problem) binds too, and each step says what is wrong with it.

    The credential file is looked for where `layers` says (`credentials`, nearest first,
    every one a secret the jail keeps from an input), unless the config names an `env_file`.
    """
    value = yield enter(opened(config, layers.credentials))
    yield bind("model", value)


@dataclass(frozen=True, slots=True)
class CatalogConfig:
    """`model_row`: the row whose config names the model (`model`)."""

    model_row: str = "model"


@component(provides=("models",))
async def catalog(*, loader: Entries, layers: Credentials, config: CatalogConfig) -> Effects:
    """Fills a `models` row: `use = "models:catalog"`. The models there are and which one the
    model row names, read fresh from the layers and the models file each time; it depends on
    the loader and `layers` (where a key's `local.env` is looked for), neither of which a
    `/model` replaces, so a switch never reloads it, nor `/model` itself, nor the status bar."""
    yield bind("models", Catalog(loader, config.model_row, layers.credentials))


@component
async def switch(
    *, commands: _Registrar, loader: Reloads, models: Models, jobs: Queue, config: SwitchConfig
) -> Effects:
    """Fills a `switch` row: `use = "models:switch"`. `/model` lists the models (`models`), the
    current one marked, and `/model NAME` names NAME as the model row's `default` in the
    session's layer (`layer`, on the row `model_row`) and reloads the layers. The reload is
    queued in `jobs`, run after the command has answered, and one that fails is told to the
    person there. It depends on `models`, not `model`, so a switch never reloads it."""
    files = [str(path) for path in loader.config.layers] if isinstance(loader, _Mounting) else []
    chosen = Switch(loader, models, config, jobs, set_model, lambda layer, rid: shadowing(files, layer, rid))
    yield acquire(commands.register, chosen.spec(), chosen.run)


def set_model(layer: str, rid: str, model: str) -> None:
    """Name `model` as row `rid`'s `default` in the layer file `layer`, keeping the rest of its
    config (the model row's `default` is the model's name)."""
    rows = read_layer(layer)
    current = next((r for r in rows if r.id == rid), Row(rid))
    kept = [r for r in rows if r.id != rid]
    chosen = Row(rid, current.use, {**(current.config or {}), "default": model}, current.disabled)
    Path(layer).write_text(format_layer([*kept, chosen], "This session's own layer; /model edits it."))


def shadowing(files: Sequence[str], layer: str, rid: str) -> str | None:
    """The first of the layer `files` composed after `layer` that sets row `rid`'s config, which
    replaces the config `layer` gives it whole (a `--patch` naming the model row, over the
    session's layer that /model edits); None when none does. A file that can't be read is
    skipped: the loader reports it."""
    mine = Path(layer).resolve()
    at = next((n for n, path in enumerate(files) if Path(path).resolve() == mine), None)
    for path in files[at + 1 :] if at is not None else []:
        try:
            rows = read_layer(path)
        except OSError, ValueError:
            continue
        if any(row.id == rid and row.config is not None for row in rows):
            return path
    return None
