"""The rows: the kernel, bound under `kernel`; and a jail that confines nothing, under `jail`."""

from cordis import Effects, bind, component, enter
from kernel_cordis_plugin.client import Jail, Kernel, KernelConfig
from kernel_cordis_plugin.unjailed import Unjailed

__all__ = ["kernel", "unjailed"]


@component(provides=("kernel",))
async def kernel(*, jail: Jail, config: KernelConfig) -> Effects:
    """Fills a `kernel` row: `use = "kernel:kernel"`. The kernel is also the model's one tool,
    `python(code)`; the loop asks the person about each input when the kernel is not `confined`.

    Depends on the jail and nothing else, so swapping the model or the ui keeps the
    namespace; swapping the jail starts a new process, which is the honest thing for a new jail
    to mean."""
    started = yield enter(Kernel(jail, config))
    yield bind("kernel", started)


@component(provides=("jail",))
async def unjailed() -> Effects:
    """Fills a `jail` row with no confinement: `use = "kernel:unjailed"`. Every input then asks."""
    yield bind("jail", Unjailed())
