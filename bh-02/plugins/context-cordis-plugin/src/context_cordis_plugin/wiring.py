"""The row: the project's context, bound under `system`."""

from context_cordis_plugin.project import ContextConfig, ProjectContext
from cordis import Effects, bind, component

__all__ = ["project"]


@component(provides=("system",))
async def project(*, config: ContextConfig) -> Effects:
    """Fills a `system` row: `use = "context:project"`."""
    yield bind("system", ProjectContext(config))
