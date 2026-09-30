"""The `models` value: the models there are, which one the model row names now, and whether
a name can be switched to (CONTRACTS.md: models).

It reads the model row's config from the loader's entries each time it is asked (the layers
as they compose now, `/model`'s edit included) and the models file with it, so it never holds
anything that goes stale and never has to reload: `/model` and the status bar depend on it,
not on `model`, which a switch replaces.
"""

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol, runtime_checkable

from models_cordis_plugin.named import OPENAI, ModelConfig, ModelsError, Named, problem
from models_cordis_plugin.openai import missing_key
from models_cordis_plugin.providers import known

__all__ = ["Catalog", "Entries"]

_MODELS: Final = "models:model"  # the component whose config this reads
_FIELDS: Final = frozenset(f.name for f in dataclasses.fields(ModelConfig))


@runtime_checkable
class Entries(Protocol):
    """What the catalog needs of the `loader` value: the rows as the layers compose them now."""

    def entries(self) -> Sequence[Any]: ...


class Catalog:
    """The `models` value over one loader and the model row's id (module docstring); `searched`
    is where `local.env` is looked for (the `layers` value's `credentials`)."""

    def __init__(self, loader: Entries, row: str = "model", searched: Sequence[str] = ()) -> None:
        self._loader = loader
        self._row = row
        self._searched = tuple(searched)

    def _entry(self) -> Any:
        return next((e for e in self._loader.entries() if getattr(e, "id", None) == self._row), None)

    def _config(self) -> ModelConfig | None:
        """The model row's config, when the row is `models:model` (None for another component,
        such as a fake a `--patch` names)."""
        entry = self._entry()
        if entry is None or (entry.use is not None and entry.use != _MODELS):
            return None
        raw: Mapping[str, Any] = entry.config or {}
        return ModelConfig(**{k: v for k, v in raw.items() if k in _FIELDS})

    @property
    def path(self) -> str:
        """The models file the model row reads (whether or not it exists)."""
        return known(self._config() or ModelConfig())[1]

    def listed(self) -> list[dict[str, Any]]:
        """Every model, in order (the built-ins, the file's, the row's `extra`): `name`,
        `provider`, `id`, `current` (the one the model row names), `where` (an openai model's
        base_url), and `problem` or `shadows` when there is one. A models file that can't be
        read raises its `ModelsError`."""
        config = self._config() or ModelConfig()
        models, _ = known(config)
        current = self.current()["name"]
        return [_listed(named, named.name == current) for named in models]

    def current(self) -> dict[str, str]:
        """The model the row names now: `name` and `provider` (empty when it names no model
        there is, or the row is another component: then `name` is that component)."""
        entry = self._entry()
        config = self._config()
        if config is None:
            return {"name": str(getattr(entry, "use", "") or "none"), "provider": ""}
        try:
            models, _ = known(config)
        except ModelsError:
            return {"name": str(config.default), "provider": ""}
        found = next((n for n in models if n.name == config.default), None)
        return {
            "name": str(config.default),
            "provider": found.provider if found and not problem(found) else "",
        }

    def check(self, name: str) -> str | None:
        """Why the model row can't switch to `name`, said so the person can fix it; None when
        it can. A model whose key names a line local.env doesn't have is refused here, not at
        its first message (the line is only looked for, never read out)."""
        config = self._config()
        if config is None:
            entry = self._entry()
            return (
                f"the {self._row!r} row is {getattr(entry, 'use', None) or 'not in the composition'}, not "
                f"{_MODELS}, so it has no models to switch between"
            )
        try:
            models, source = known(config)
        except ModelsError as error:
            return error.message
        found = next((n for n in models if n.name == name), None)
        if found is None:
            names = ", ".join(n.name for n in models)
            return (
                f"no model named {name!r}; the models are {names}. To add one, give it a table in the "
                f'models file {source}: [{name}] provider = "openai", id = "...", base_url = "https://.../v1"'
            )
        if (why := problem(found)) is not None:
            return why
        return missing_key(found, config.env_file, self._searched) if found.provider == OPENAI else None


def _listed(named: Named, current: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"name": named.name, "provider": named.provider, "id": named.id, "current": current}
    if isinstance(url := named.table.get("base_url"), str):
        out["where"] = url
    if (why := problem(named)) is not None:
        out["problem"] = why
    if named.shadows:
        out["shadows"] = f"shadows the built-in {named.name!r} ({named.source})"
    return out
