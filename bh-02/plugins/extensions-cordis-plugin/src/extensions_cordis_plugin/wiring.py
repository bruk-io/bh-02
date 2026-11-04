"""The row: the model's own extensions, loaded while bh-02 runs."""

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from cordis import Effects, acquire, component, enter
from extensions_cordis_plugin.host import (
    Commands,
    Confirm,
    Extensions,
    ExtensionsConfig,
    Frame,
    Granting,
    Rule,
    Runner,
    System,
    Tools,
)

__all__ = ["process"]


@runtime_checkable
class _Runs(Runner, Protocol):
    """The `runner` value as the extensions row uses it: a start, whether it is released, and
    the worker's stop asked on `/release` (CONTRACTS.md: runner)."""

    def on_release(self, stop: Callable[[], Awaitable[str]]) -> Callable[[], None]: ...


@component
async def process(
    *,
    runner: _Runs,
    commands: Commands,
    frame: Frame,
    system: System,
    tools: Tools,
    approval: Rule,
    output: Confirm,
    grants: Granting,
    config: ExtensionsConfig,
) -> Effects:
    """Fills an `extensions` row: `use = "extensions:process"`. Watches the project's
    extensions directory and loads what the model writes there into a worker the runner starts,
    each at once when the `approval` rule says it runs unasked (a runner that confines it), else
    on the person's yes (`output.confirm`); tells the model how (a `system` section). On
    `/release` it stops its own worker (`runner.on_release`). Binds nothing: what the extensions
    add goes into `commands`, `frame`, `system` and `tools` (a tool's calls run in the worker,
    each decided by the `approval` rule as an input is), each entry with its remover, so the row
    leaving takes every one of them back. An extension may also ask the person for a grant
    (`grants.ask(...)` in its code), put through the `grants` broker as that extension's; and when a
    path or variable grant changes (`grants.generation()`, followed through `grants.on_change`) its
    worker is replaced at once, every extension loading again. Depends on the broker's binding, which
    never reloads, so a grant never reloads the row."""
    running = yield enter(
        Extensions(runner, commands, frame, system, tools, approval, output, config, grants)
    )
    yield acquire(grants.on_change, running.regranted)
    yield acquire(runner.on_release, running.stopped)
    yield acquire(system.add, "extensions", running.section)
