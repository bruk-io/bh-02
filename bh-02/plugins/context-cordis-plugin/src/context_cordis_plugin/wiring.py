"""The row: the project's context, bound under `system`."""

from context_cordis_plugin.project import ContextConfig, ProjectContext, Reads
from cordis import Effects, bind, component

__all__ = ["project"]


@component(provides=("system",))
async def project(*, config: ContextConfig, kernel: Reads) -> Effects:
    """Fills a `system` row: `use = "context:project"`. Depends on `kernel` for what its jail
    can read, so a new kernel (a new jail) reloads it, and nothing else does."""
    yield bind("system", ProjectContext(config, kernel))
