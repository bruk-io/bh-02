"""The decorator, and finding what it marked.

    @component
    async def price_feed(*, feed: Feed) -> Effects:
        sub: Sub = yield subscribe(feed)
        yield bind("recent_prices", ...)

`@component` attaches and returns the function unchanged (venusian's discipline), so
importing a plugin has no side effects, the decorated object is the plain async generator
function a test can drive by hand, and a scan is what turns a package into components by
name. The component itself is derived in `cordis.component`; this module is discovery.
"""

from collections.abc import Callable, Iterable, Mapping
from types import ModuleType
from typing import Any, overload

import venusian

from cordis.component import Component, derive
from cordis.effects import Effects

_CATEGORY = "cordis"


@overload
def component[F: Callable[..., Effects]](fn: F) -> F: ...


@overload
def component[F: Callable[..., Effects]](
    *, name: str | None = ..., provides: Iterable[str] = ...
) -> Callable[[F], F]: ...


def component(fn: Any = None, *, name: str | None = None, provides: Iterable[str] = ()) -> Any:
    """Mark an async generator function as a component. Attaches; returns it unchanged.

    The decorated object is the plain function: same signature, same type, directly callable
    in a test. Nothing is registered until a scan finds it. Deriving the component here
    rather than at scan time means a malformed one fails loudly at import.

    `provides` is the keys this component's author claims it binds: checked against what it
    actually binds at activation (see `cordis.decisions.check_provided`), not a contract on
    the value.
    """

    def deco(f: Any, depth: int = 1) -> Any:
        derive(f, name=name, provides=provides)  # derive now, so a malformed component fails at import

        def callback(scanner: venusian.Scanner, found: str, obj: Any) -> None:
            made = derive(obj, name=name, provides=provides)
            scanner.found[made.name] = made

        # depth counts the frames between the decorated module and this call: `@component`
        # goes through component() and deco(), `@component(...)` only through deco().
        venusian.attach(f, callback, category=_CATEGORY, depth=depth)
        return f

    return deco(fn, depth=2) if fn is not None else deco


def scan(package: ModuleType, categories: Iterable[str] = (_CATEGORY,)) -> dict[str, Component]:
    """Walk a package and collect its components by name. Importing registers nothing; this does.

    A scan matches a component to the module it was defined in, so a module assembled at
    runtime (model-written source, say) must be in `sys.modules` under its own name first.
    """
    found: dict[str, Component] = {}
    venusian.Scanner(found=found).scan(package, categories=tuple(categories))
    return found


def lookup(found: Mapping[str, Component], name: str) -> Component:
    """One component out of a scan, or a LookupError that says what the package does have."""
    try:
        return found[name]
    except KeyError:
        known = ", ".join(sorted(found)) or "nothing"
        raise LookupError(f"no component named {name!r}; this package has {known}") from None
