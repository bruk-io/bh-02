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
    Rule,
    Runner,
    System,
    Tools,
)

__all__ = ["extensions"]


@runtime_checkable
class _Runs(Runner, Protocol):
    """The `runner` value as the extensions row uses it: a start, whether it is released, and
    the worker's stop asked on `/release` (CONTRACTS.md: runner)."""

    def on_release(self, stop: Callable[[], Awaitable[str]]) -> Callable[[], None]: ...


@component
async def extensions(
    *,
    runner: _Runs,
    commands: Commands,
    frame: Frame,
    system: System,
    tools: Tools,
    approval: Rule,
    output: Confirm,
    config: ExtensionsConfig,
) -> Effects:
    """Fills an `extensions` row: `use = "extensions:extensions"`. Watches the project's
    extensions directory and loads what the model writes there into a worker the runner starts,
    each at once when the `approval` rule says it runs unasked (a runner that confines it), else
    on the person's yes (`output.confirm`); tells the model how (a `system` section). On
    `/release` it stops its own worker (`runner.on_release`). Binds nothing: what the extensions
    add goes into `commands`, `frame`, `system` and `tools` (a tool's calls run in the worker,
    each decided by the `approval` rule as an input is), each entry with its remover, so the row
    leaving takes every one of them back."""
    running = yield enter(Extensions(runner, commands, frame, system, tools, approval, output, config))
    yield acquire(runner.on_release, running.stopped)
    yield acquire(system.add, "extensions", running.section)
