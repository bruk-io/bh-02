"""The rows: the model itself, bound under `model`, and the models there are, under `models`."""

from dataclasses import dataclass

from cordis import Effects, bind, component, enter
from models_cordis_plugin.catalog import Catalog, Entries
from models_cordis_plugin.named import ModelConfig
from models_cordis_plugin.providers import opened

__all__ = ["CatalogConfig", "catalog", "model"]


@component(provides=("model",))
async def model(*, config: ModelConfig) -> Effects:
    """Fills a `model` row: `use = "models:model"`. The model `config.default` names, on its
    provider, entered for as long as the row is up (`/model` changes `default`, which reloads
    this row alone and whatever depends on `model`).

    Nothing starts until the first step (Claude Code needs the request's system prompt and
    tools; a key is read per request), so a composition without a credential comes up, and
    each step says what is missing. A model that can't be used (an unknown name, a table
    with a problem) binds too, and each step says what is wrong with it.
    """
    value = yield enter(opened(config))
    yield bind("model", value)


@dataclass(frozen=True, slots=True)
class CatalogConfig:
    """`model_row`: the row whose config names the model (`model`)."""

    model_row: str = "model"


@component(provides=("models",))
async def catalog(*, loader: Entries, config: CatalogConfig) -> Effects:
    """Fills a `models` row: `use = "models:catalog"`. The models there are and which one the
    model row names, read fresh from the layers and the models file each time; it depends on
    the loader alone, so a `/model` never reloads it, nor `/model` itself, nor the status bar."""
    yield bind("models", Catalog(loader, config.model_row))
