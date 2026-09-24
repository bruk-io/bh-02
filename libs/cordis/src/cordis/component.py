"""A component, read out of a function's signature.

    @component
    async def git(*, config: GitConfig, subprocess: Subprocess) -> Effects:
        client: GitClient = yield enter(GitClient(config.binary, subprocess))
        yield bind("git", client)

Keyword-only parameters are dependencies: the key is the parameter's annotation when it is
a class, else the parameter's name. A parameter named `config` is configuration, built from
its dataclass annotation. Nothing here runs a component; `cordis.runtime` instantiates one.

Pure but for one memo: `derive` records the component on the function it read it from.
That memo is how a name given to the decorator (`@component(name="x")`) reaches a later
`mount(fn)` or `resolve("m:fn")`, which derive with no name and get the recorded one back.
"""

import contextlib
import dataclasses
import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from cordis.effects import Effects, Key

_DERIVED = "__cordis_component__"
_CONFIG = "config"


@dataclass(frozen=True, slots=True)
class Component:
    """A recipe: dependencies, a name, and the generator that yields effects.

    Identity persists across versions and reloads: a component is what a row names, what a
    dependency resolves to, and what an author tests. A fiber is one mounting of it.
    """

    name: str
    inject: frozenset[Key]
    params: tuple[tuple[str, Key], ...]  # parameter name -> key (the name itself)
    wants_config: bool
    config_type: type | None
    fn: Callable[..., Effects]
    contracts: tuple[tuple[str, type], ...] = ()  # parameter name -> the class its value must satisfy
    provides: frozenset[Key] = frozenset()  # keys this component's author claims it binds


def derive(
    fn: Callable[..., Effects] | Component, *, name: str | None = None, provides: Iterable[Key] = ()
) -> Component:
    """The component for a function, recorded on it. A Component passes through.

    With no `name`, a recorded component wins, whatever name it was recorded under; with a
    `name`, the record is replaced unless it already carries that name. The decorator relies
    on this: it derives once with its name, and every later derivation sees that one.
    """
    if isinstance(fn, Component):
        return fn
    cached = getattr(fn, _DERIVED, None)
    if isinstance(cached, Component) and (name is None or cached.name == name):
        return cached
    made = _read(fn, name, provides)
    with contextlib.suppress(AttributeError, TypeError):
        setattr(fn, _DERIVED, made)  # a builtin or a slotted callable simply re-derives
    return made


def _read(fn: Callable[..., Effects], name: str | None, provides: Iterable[Key] = ()) -> Component:
    if not inspect.isasyncgenfunction(fn):
        raise TypeError(
            f"{getattr(fn, '__name__', fn)!r} is not a component: a component is an async "
            f"generator that yields effects (`async def ... -> Effects`, with at least one `yield`)"
        )
    hints = _annotations(fn)
    params: list[tuple[str, Key]] = []
    contracts: list[tuple[str, type]] = []
    positional: list[str] = []
    wants_config = False
    config_type: type | None = None
    for param in inspect.signature(fn).parameters.values():
        if param.kind is not param.KEYWORD_ONLY:
            positional.append(param.name)
        elif param.name == _CONFIG:
            wants_config, config_type = True, _as_class(hints.get(_CONFIG))
        else:
            params.append((param.name, param.name))
            if (contract := _as_class(hints.get(param.name))) is not None:
                contracts.append((param.name, contract))
    if positional:
        raise TypeError(
            f"{fn.__name__}: a component's parameters must be keyword-only (after `*`); got "
            f"positional {positional}. A function with positional parameters is a value, not a "
            f"component; bind it from one with `yield bind(name, partial(fn, **deps))`."
        )
    return Component(
        name=name or fn.__name__,
        inject=frozenset(key for _, key in params),
        params=tuple(params),
        wants_config=wants_config,
        config_type=config_type,
        fn=fn,
        contracts=tuple(contracts),
        provides=frozenset(provides),
    )


def _as_class(annotated: Any) -> type | None:
    """A parameter's annotation as a class, or None when it is not one.

    For a dependency that class is the contract its value must satisfy, checked when the
    dependency is committed; for `config` it is the schema. `Any` is a class in 3.11+, so
    `*, thing: Any` would otherwise read as a contract rather than as "a dependency named
    thing whose shape this component does not constrain".
    """
    return annotated if isinstance(annotated, type) and annotated is not Any else None


def _annotations(fn: Callable[..., Any]) -> dict[str, Any]:
    try:
        return inspect.get_annotations(fn, eval_str=True)
    except Exception:  # a forward reference this module cannot resolve is not an error here
        return {}


def configure(raw: Any, want: type | None, owner: str) -> Any:
    """Build a component's `config` argument from the row's payload.

    A dataclass annotation is the schema: a wrong or missing key is a TypeError naming the
    component, raised before any effect is performed, so a component never starts
    half-configured. Any other annotation is documentation, and the payload passes through.
    """
    if want is None or not dataclasses.is_dataclass(want):
        return raw
    if isinstance(raw, want):
        return raw
    if isinstance(raw, Mapping | None):
        try:
            return want(**(raw or {}))
        except TypeError as e:
            raise TypeError(f"{owner}: invalid config for {want.__name__}: {e}") from e
    raise TypeError(f"{owner}: config must be a {want.__name__}, got {type(raw).__name__}")


def arguments(component: Component, committed: Mapping[Key, Any], config: Any) -> dict[str, Any]:
    """The keyword arguments a component's function is called with: its dependencies and config."""
    kwargs: dict[str, Any] = {name: committed[key] for name, key in component.params}
    if component.wants_config:
        kwargs[_CONFIG] = configure(config, component.config_type, component.name)
    return kwargs
