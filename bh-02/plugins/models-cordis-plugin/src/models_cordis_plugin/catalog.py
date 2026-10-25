"""The `models` value: the models there are, which one the model row names now, whether a
name can be switched to, and why the models file is not read (CONTRACTS.md: models).

It reads the model row's config from the loader's entries each time it is asked (the layers
as they compose now, `/model`'s edit included) and the models file with it, so it never holds
anything that goes stale and never has to reload: `/model` and the status bar depend on it,
not on `model`, which a switch replaces.

The one thing it keeps is what the models file's discovering endpoints (`discover = true`) listed
(`openai.Discovery`). `refresh` fills it, awaited by `/model` when it lists and by nothing else,
so `listed` (which `/model`'s choices and the composer's completion call, on the event loop, once
per key) and `current` (the status bar's) read it and never ask a server.
"""

import asyncio
import dataclasses
import time
from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import Any, Final, Protocol, runtime_checkable

from models_cordis_plugin.named import (
    OPENAI,
    Intended,
    ModelConfig,
    ModelsError,
    Named,
    chosen,
    derived,
    find,
    from_file,
    key_spec,
    named_models,
    not_a_model,
    problem,
    said_names,
)
from models_cordis_plugin.openai import (
    SHOWN,
    Ask,
    Discovery,
    Get,
    Listed,
    ListingKey,
    Unlisted,
    headers_for,
    httpx_get,
    matching,
    missing_key,
    models_url,
    notes,
)
from models_cordis_plugin.providers import known, resolution

__all__ = ["Catalog", "Entries"]

_MODELS: Final = "models:model"  # the component whose config this reads
_FIELDS: Final = frozenset(f.name for f in dataclasses.fields(ModelConfig))


@runtime_checkable
class Entries(Protocol):
    """What the catalog needs of the `loader` value: the rows as the layers compose them now."""

    def entries(self) -> Sequence[Any]: ...


class Catalog:
    """The `models` value over one loader and the model row's id (module docstring)."""

    def __init__(
        self,
        loader: Entries,
        row: str = "model",
        get: Get = httpx_get,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loader = loader
        self._row = row
        self._discovery = Discovery(get, clock)
        self._refreshing = asyncio.Lock()  # one refresh at a time: a second finds the first's listing

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
        return known(self._config() or ModelConfig()).source

    @property
    def problem(self) -> str | None:
        """Why the models file is not read, said so the person can fix it: it is in the project,
        which the model's code can write, or it can't be read or is not TOML (the row's `extra` is
        still listed, and can be switched to). None when it is read, there or not."""
        return known(self._config() or ModelConfig()).why

    @property
    def default_problem(self) -> str | None:
        """Why the models file's `default` can't be used, said as the model row says it (what to
        write): it is no name, names no model, or its model's table has a problem. None when it can
        be used, there is none, or the file is not read (`problem` says why not)."""
        config = self._config()
        if config is None:
            return None
        found = known(config)
        if found.unread is not None or not from_file(found.standing):
            return None
        try:
            chosen(found.standing.name, found.models, found.source, found.why, found.standing.origin)
        except ModelsError as error:
            return error.message
        return None

    def listed(self) -> list[dict[str, Any]]:
        """Every model, in order (each endpoint's of the file, then of the row's `extra`): `name`,
        `provider`, `id`, `current` (the one the model row names), `default` (on the model a new
        session starts on when no layer names one: where that came from, `the models file`),
        `where` (a model's base_url, when it has one), and `problem` when there is one. An endpoint's
        models are the ones its `models` names, in order, then what its last `refresh` found, in its
        `include`, and the model row's and the default when they are of it, so the marks are always
        there; this never asks a server. A models file that can't be read, is not TOML, or is in the
        project is not read, and lists none (`problem` says why); it never raises."""
        config = self._config() or ModelConfig()
        found = known(config)
        current = self.current()["name"]
        standing = None if found.unread is not None else found.standing  # an unread default is unknown
        return self._served(found.models, current, standing)

    def _served(
        self, models: Sequence[Named], current: str, standing: Intended | None
    ) -> list[dict[str, Any]]:
        """The models each endpoint of `models` serves: the ones its `models` names, in order, then,
        sorted by id, those its server listed when `refresh` last asked (`discover`: those its
        `include` lets through, at most `SHOWN`, and none a named model already has) and the model
        row's and the default, when they are of it and named by id."""
        out: list[dict[str, Any]] = []
        for host in models:
            if not host.endpoint or problem(host) is not None:
                continue
            named = named_models(host)
            found = self._discovery.found(_key(host)) if host.table.get("discover") is True else None
            ids = matching(found.ids, host.table.get("include", ())) if isinstance(found, Listed) else ()
            prefix = f"{host.name}/"
            given = {model.name.removeprefix(prefix) for model in named}
            pinned = (
                name.removeprefix(prefix)
                for name in (current, standing.name if standing else None)
                if isinstance(name, str) and name.startswith(prefix)
            )
            listed = {model_id for model_id in ids[:SHOWN] if model_id not in {model.id for model in named}}
            unnamed = sorted({*listed, *filter(None, pinned)} - given)
            for model in [*named, *(derived(host, model_id) for model_id in unnamed)]:
                out.append(_listed(model, model.name == current, _default(model, standing)))
        return out

    def endpoints(self) -> list[dict[str, Any]]:
        """Each endpoint with something to say besides its models: `name`, `where` (its base_url)
        and `notes`, one line each: its table's problem (it serves no model then), or, for one that
        discovers, why its server listed none (the server isn't there, refused the key, has no
        /models, a key's line is missing) or what its list leaves out. Read from what `refresh` kept;
        this never asks a server."""
        found = known(self._config() or ModelConfig())
        out: list[dict[str, Any]] = []
        for host in found.models:
            if not host.endpoint:
                continue
            url = str(host.table.get("base_url") or "")
            if (why := problem(host)) is not None:
                lines: tuple[str, ...] = (why,)
            elif host.table.get("discover") is True:
                lines = notes(
                    models_url(url), self._discovery.found(_key(host)), host.table.get("include", ())
                )
            else:
                continue
            out.append({"name": host.name, "where": url, "notes": list(lines)})
        return out

    async def refresh(self) -> None:
        """Ask each discovering endpoint of the models file for its models, all at once, and keep what they
        say for `listed` and `endpoints` (`openai.Discovery.refresh`: one that was listed a moment ago
        is not asked again). `/model` awaits this when it lists; nothing else does. It never
        raises for a server: an endpoint that can't be asked is said by `endpoints`. A models
        file that can't be read is `listed`'s to say."""
        config = self._config()
        if config is None:
            return
        try:
            models = known(config).models
        except ModelsError:
            return
        wanted = {
            _key(host): partial(_ask, host)
            for host in models
            if host.endpoint and host.table.get("discover") is True and problem(host) is None
        }
        async with self._refreshing:
            await self._discovery.refresh(wanted)

    def current(self) -> dict[str, str]:
        """The model the row names now: `name` and `provider` (empty when it names no model
        there is, or the row is another component: then `name` is that component), and `unusable`,
        why it can't be used, when it can't (the status bar says so; `name` is the default's own text
        when it is a name, `none` when nothing names a model, else `default`, so it is never blank).
        Never raises."""
        entry = self._entry()
        config = self._config()
        if config is None:
            return {"name": str(getattr(entry, "use", "") or "none"), "provider": ""}
        try:
            name, outcome = resolution(config)
        except ModelsError as error:  # the row's own config is wrong: a layer's default is still its name
            return {"name": _shown(config.default), "provider": "", "unusable": error.message}
        if isinstance(outcome, ModelsError):
            unchosen = name is None and known(config).unread is None  # no default, not an unread one
            return {"name": "none" if unchosen else _shown(name), "provider": "", "unusable": outcome.message}
        return {"name": outcome.name, "provider": outcome.provider}

    def check(self, name: str) -> str | None:
        """Why the model row can't switch to `name`, said so the person can fix it; None when
        it can. A model whose key reads a variable bh-02's environment doesn't have is refused here,
        not at its first message (the variable is only looked for, never read out)."""
        config = self._config()
        if config is None:
            entry = self._entry()
            return (
                f"the {self._row!r} row is {getattr(entry, 'use', None) or 'not in the composition'}, not "
                f"{_MODELS}, so it has no models to switch between"
            )
        try:
            models, source, why, _, _ = known(config)
        except ModelsError as error:
            return error.message
        found = find(name, models)
        if found is None:
            names = said_names(models)
            if why is not None:  # its models may be there, but are not read
                return f"no model named {name!r}; the models are {names}; {why}"
            return (
                f"no model named {name!r}; the models are {names}. To add one, give it an endpoint in the "
                f'models file {source}: [ENDPOINT] provider = "openai", base_url = "https://.../v1", then '
                '[ENDPOINT.models.MODEL] id = "...", and /model ENDPOINT/MODEL'
            )
        if (why := not_a_model(found)) is not None:
            return why
        return missing_key(found) if found.provider == OPENAI else None


def _listed(named: Named, current: bool, default: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"name": named.name, "provider": named.provider, "id": named.id, "current": current}
    if default is not None:
        out["default"] = default
    if isinstance(url := named.table.get("base_url"), str):
        out["where"] = url
    if (why := problem(named)) is not None:
        out["problem"] = why
    return out


def _shown(name: object) -> str:
    """A model's name as the status bar shows it: its own text when it is a name, else `default`
    (the models file's, which is no name or can't be read)."""
    return name if isinstance(name, str) and name else "default"


def _default(named: Named, standing: Intended | None) -> str | None:
    """Where the default model came from (`the models file`) when `named` is it; None
    for no default known (`standing` None: the models file can't be read)."""
    return standing.origin if standing is not None and named.name == standing.name else None


def _key(host: Named) -> ListingKey:
    """What an endpoint's listing is kept under: its base_url and where its key comes from."""
    spec = key_spec(host.table.get("key"))
    return str(host.table.get("base_url")), None if spec is None else spec.label


async def _ask(host: Named) -> Ask | Unlisted:
    """The request for an endpoint's models: where, and the headers with its key, read from the
    environment or printed by its command now (`openai.headers_for`: header only). A key that can't
    be had is no request: it is the endpoint's answer, said so the person can fix it."""
    if (why := missing_key(host)) is not None:
        return Unlisted(why)
    try:
        headers = await headers_for(host)
    except ModelsError as error:
        return Unlisted(error.message)
    headers["Accept"] = "application/json"
    return Ask(models_url(str(host.table["base_url"])), headers)
