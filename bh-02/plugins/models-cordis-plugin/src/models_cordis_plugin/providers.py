"""The `model` value for a row's config: the named model, on its provider.

`resolved` is which model the config names (the models file's endpoints unless it is in the
project or can't be read, and the row's own `extra`), or why none can be used. `opened` is its
provider's value, entered for as long as the row is up: Claude Code (`claude-code`), an
OpenAI-compatible endpoint (`openai`), or a factory a model names as `module:attribute`. A
model that can't be used still binds, as `Unusable`, whose every step raises what is wrong,
so a typo in the models file is a message in the conversation (and `/model` another model
fixes it), not a composition that won't start.
"""

import contextlib
import importlib
import os
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, NamedTuple, cast

from models_cordis_plugin.claude_code import ClaudeCodeConfig, ClaudeCodeModel, Gateway
from models_cordis_plugin.named import (
    CLAUDE_CODE,
    OPENAI,
    Intended,
    ModelConfig,
    ModelsError,
    Named,
    chosen,
    combined,
    environ,
    in_project,
    intended,
    key_spec,
    models_file,
    parsed,
    read_models,
    standing,
)
from models_cordis_plugin.openai import OpenAIModel

__all__ = ["Unusable", "known", "opened", "resolution", "resolved"]

type Json = Mapping[str, Any]


class Unusable:
    """The `model` value when the named model can't be used: each step says why, and what to do."""

    def __init__(self, error: ModelsError) -> None:
        self.error = error

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        raise ModelsError(self.error.kind, self.error.message)
        yield {}  # an async generator, as every provider's `complete` is


def _refused(config: ModelConfig) -> str | None:
    """Why the config's models file is not read (`in_project`), or None when it is outside the
    project: the working directory, where the jail lets the model's code write (the Python process's
    root), and the row's `cwd` when a layer names another."""
    if not isinstance(config.cwd, str | None):  # cordis does not type-check a row's config
        raise ModelsError(
            "model_config",
            f"the model row's cwd is {config.cwd!r}, not a directory; give it the project's path, "
            "or remove it (the working directory is the project then)",
        )
    path = models_file(config.models, environ())
    roots = dict.fromkeys(root for root in (config.cwd, os.getcwd()) if root)
    return next((why for root in roots if (why := in_project(path, Path(root))) is not None), None)


class _Known(NamedTuple):
    """What a config can name: `models`, the models file they were read from (`source`), why that
    file is not read (`why`: it is in the project, or it can't be read or parsed (`unread`);
    then only the row's `extra` is named), `standing`, the default below any layer
    (the file's `default`, read only with the file), and `unread`, the error that file gave, if any
    (its `default` is unknown, so a row no layer names a model for has no model: `resolution`)."""

    models: list[Named]
    source: str
    why: str | None
    standing: Intended
    unread: ModelsError | None


def known(config: ModelConfig) -> _Known:
    """Every model the config can name, with where they came from (`_Known`). A models file that
    can't be read or is not TOML (or holds a key that is no table) is not an error here: the row's
    `extra` stays named, as behind a file refused in the project, and `why` says what is wrong.

    Raises:
        ModelsError: the config's own `cwd` is not a directory's name.
    """
    path = models_file(config.models, environ())
    why = _refused(config)
    unread: ModelsError | None = None
    try:
        file = parsed(None if why is not None else read_models(path), str(path))
    except ModelsError as error:
        unread, file = error, parsed(None, str(path))
        why = f"only the model row's `extra` is offered until the models file is fixed: {error.message}"
    return _Known(
        combined(file.endpoints, str(path), config.extra), str(path), why, standing(file.default), unread
    )


def resolution(config: ModelConfig) -> tuple[object, Named | ModelsError]:
    """The name the config chooses (as written; None when it is the models file's `default`, which
    can't be read) and the model it means, or why none can be used: the config's `default`, else
    the models file's, else none (`intended`; `chosen` says what to write). A models file that can't
    be read gives no default, so a row no layer names a model for has the file's problem to say,
    with what to write.

    Raises:
        ModelsError: the config's own `cwd` is not a directory's name (`known`).
    """
    found = known(config)
    if config.default is None and found.unread is not None:
        return None, found.unread
    wanted = intended(config.default, found.standing)
    try:
        return wanted.name, chosen(wanted.name, found.models, found.source, found.why, wanted.origin)
    except ModelsError as error:
        return wanted.name, error


def resolved(config: ModelConfig) -> Named:
    """The model the config names (`resolution`), or a `ModelsError` saying what to do.

    Raises:
        ModelsError: no model can be used, and why.
    """
    _, outcome = resolution(config)
    if isinstance(outcome, ModelsError):
        raise outcome
    return outcome


def _provided(named: Named, config: ModelConfig, searched: Sequence[str]) -> Any:
    """The provider's value for `named`: not entered yet. `searched`: where the claude-code
    provider looks for `local.env` when the config names no `env_file` (the `host` value's `credentials`)."""
    if named.provider == CLAUDE_CODE:
        return ClaudeCodeModel(
            ClaudeCodeConfig(
                model=named.id,
                name=named.name,
                state=config.state,
                env_file=config.env_file,
                cwd=config.cwd,
                searched=tuple(searched),
                gateway=_gateway(named.table),
            )
        )
    if named.provider == OPENAI:
        return OpenAIModel(named)
    module, _, attribute = named.provider.partition(":")
    try:
        factory = cast(
            Callable[[Mapping[str, Any]], Any], getattr(importlib.import_module(module), attribute)
        )
    except (ImportError, AttributeError) as error:
        raise ModelsError(
            "model_config",
            f"model {named.name!r} ({named.source}) names the provider {named.provider!r}, which can't be "
            f'loaded ({type(error).__name__}: {error}); use "{CLAUDE_CODE}" or "{OPENAI}", or a '
            "module:attribute that is installed",
        ) from None
    try:
        return factory(named.table)
    except Exception as error:  # a factory's own code can raise anything: said, not fatal to the row
        raise ModelsError(
            "model_config",
            f"model {named.name!r} ({named.source}): its provider {named.provider!r} failed to make the "
            f"model ({type(error).__name__}: {error}); fix its table, or /model another model",
        ) from None


def _gateway(table: Mapping[str, Any]) -> Gateway | None:
    """The gateway a claude-code model's table names (`base_url` and a `key` of `cmd` or `op`, which
    `problem` has checked come together), or None: the subscription."""
    url, spec = table.get("base_url"), key_spec(table.get("key"))
    if not isinstance(url, str) or spec is None or (command := spec.command) is None:
        return None
    return Gateway(url, command, spec.ttl_ms, table.get("experimental_betas") is not False)


@contextlib.asynccontextmanager
async def opened(config: ModelConfig, searched: Sequence[str] = ()) -> AsyncIterator[Any]:
    """The `model` value, for as long as the row is up: the named model's provider, entered
    when it is a context manager (Claude Code's process, an HTTP client), else `Unusable`.
    `searched`: where the provider looks for `local.env` (the `host` value's `credentials`)."""
    try:
        value = _provided(resolved(config), config, searched)
    except ModelsError as error:
        value = Unusable(error)
    if isinstance(value, AbstractAsyncContextManager):
        async with value as entered:
            yield entered
    else:
        yield value
