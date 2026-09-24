"""The `model` value for a row's config: the named model, on its provider.

`resolved` is which model the config names (the built-ins, the models file, the row's own
`extra`), or why none can be used. `opened` is its provider's value, entered for as long as the
row is up: Claude Code (`claude-code`), an OpenAI-compatible endpoint (`openai`), or a factory
a model names as `module:attribute`. A model that can't be used still binds, as `Unusable`,
whose every step raises what is wrong, so a typo in the models file is a message in the
conversation (and `/model` another model fixes it), not a composition that won't start.
"""

import contextlib
import importlib
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
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
    models_file,
    parsed,
    read_models,
)
from models_cordis_plugin.openai import OpenAIModel

__all__ = ["Unusable", "known", "opened", "resolved"]

type Json = Mapping[str, Any]


class Unusable:
    """The `model` value when the named model can't be used: each step says why, and what to do."""

    def __init__(self, error: ModelsError) -> None:
        self.error = error

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        raise ModelsError(self.error.kind, self.error.message)
        yield {}  # an async generator, as every provider's `complete` is


def known(config: ModelConfig) -> tuple[list[Named], str]:
    """Every model the config can name, and the models file they were read from."""
    path = models_file(config.models, environ())
    return combined(parsed(read_models(path), str(path)), str(path), config.extra), str(path)


def resolved(config: ModelConfig) -> Named:
    """The model `config.default` names, or a `ModelsError` saying what to do."""
    models, source = known(config)
    return chosen(config.default, models, source)


def _provided(named: Named, config: ModelConfig) -> Any:
    """The provider's value for `named`: not entered yet."""
    if named.provider == CLAUDE_CODE:
        return ClaudeCodeModel(
            ClaudeCodeConfig(model=named.id, state=config.state, env_file=config.env_file, cwd=config.cwd)
        )
    if named.provider == OPENAI:
        return OpenAIModel(named, config.env_file)
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
async def opened(config: ModelConfig) -> AsyncIterator[Any]:
    """The `model` value, for as long as the row is up: the named model's provider, entered
    when it is a context manager (Claude Code's process, an HTTP client), else `Unusable`."""
    try:
        value = _provided(resolved(config), config)
    except ModelsError as error:
        value = Unusable(error)
    if isinstance(value, AbstractAsyncContextManager):
        async with value as entered:
            yield entered
    else:
        yield value
