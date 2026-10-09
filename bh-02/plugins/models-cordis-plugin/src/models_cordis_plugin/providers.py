"""The `model` value for a row's config: the named model, on its provider.

`resolved` is which model the config names (the built-ins, the models file unless it is in the
project, `refused`, and the row's own `extra`), or why none can be used. `opened` is its
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
from typing import Any, cast

from models_cordis_plugin.claude_code import ClaudeCodeConfig, ClaudeCodeModel
from models_cordis_plugin.named import (
    CLAUDE_CODE,
    OPENAI,
    ModelConfig,
    ModelsError,
    Named,
    chosen,
    combined,
    environ,
    in_project,
    models_file,
    parsed,
    read_models,
)
from models_cordis_plugin.openai import OpenAIModel

__all__ = ["Unusable", "known", "opened", "refused", "resolved"]

type Json = Mapping[str, Any]


class Unusable:
    """The `model` value when the named model can't be used: each step says why, and what to do."""

    def __init__(self, error: ModelsError) -> None:
        self.error = error

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        raise ModelsError(self.error.kind, self.error.message)
        yield {}  # an async generator, as every provider's `complete` is


def refused(config: ModelConfig) -> str | None:
    """Why the config's models file is not read (`in_project`), or None when it is outside the
    project: the working directory, where the jail lets the model's code write (the kernel's
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


def known(config: ModelConfig) -> tuple[list[Named], str, str | None]:
    """Every model the config can name, the models file they were read from, and why that file
    was not read (`refused`): then only the built-ins and the row's `extra` are named."""
    path = models_file(config.models, environ())
    why = refused(config)
    text = None if why is not None else read_models(path)
    return combined(parsed(text, str(path)), str(path), config.extra), str(path), why


def resolved(config: ModelConfig) -> Named:
    """The model `config.default` names, or a `ModelsError` saying what to do."""
    models, source, why = known(config)
    return chosen(config.default, models, source, why)


def _provided(named: Named, config: ModelConfig, searched: Sequence[str]) -> Any:
    """The provider's value for `named`: not entered yet. `searched`: where `local.env` is
    looked for when the config names no `env_file` (the `host` value's `credentials`)."""
    if named.provider == CLAUDE_CODE:
        return ClaudeCodeModel(
            ClaudeCodeConfig(
                model=named.id,
                state=config.state,
                env_file=config.env_file,
                cwd=config.cwd,
                searched=tuple(searched),
            )
        )
    if named.provider == OPENAI:
        return OpenAIModel(named, config.env_file, searched=searched)
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
