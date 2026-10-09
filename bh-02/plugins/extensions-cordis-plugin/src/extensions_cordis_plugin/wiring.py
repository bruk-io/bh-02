"""The row: the model's own extensions, loaded while bh-02 runs."""

from cordis import Effects, acquire, component, enter
from extensions_cordis_plugin.host import (
    Approval,
    Commands,
    Extensions,
    ExtensionsConfig,
    Frame,
    Jail,
    System,
)

__all__ = ["extensions"]


@component
async def extensions(
    *,
    jail: Jail,
    commands: Commands,
    frame: Frame,
    system: System,
    approval: Approval,
    config: ExtensionsConfig,
) -> Effects:
    """Fills an `extensions` row: `use = "extensions:extensions"`. Watches the project's
    extensions directory and loads what the model writes there into a worker the `jail` row
    starts, each on `approval`'s yes (at once when the jail confines it); tells the model how (a
    `system` section). Binds nothing: what the extensions add goes
    into `commands`, `frame` and `system`, each entry with its remover, so the row leaving takes
    every one of them back."""
    running = yield enter(Extensions(jail, commands, frame, system, approval, config))
    yield acquire(system.add, "extensions", running.section)
