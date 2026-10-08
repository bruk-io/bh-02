"""The rows: the kernel, bound under `kernel`; `/release` over it; whether the model's code may
run, under `approval`; and a jail that confines nothing, under `jail`."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component, enter
from kernel_cordis_plugin.approval import Approval, Asks, Graded
from kernel_cordis_plugin.client import Jail, Kernel, KernelConfig
from kernel_cordis_plugin.unjailed import Unjailed

__all__ = ["approval", "kernel", "release", "unjailed"]


@runtime_checkable
class _Releasing(Protocol):
    """What `/release` needs of the `kernel` value (CONTRACTS.md: kernel)."""

    async def release(self) -> str: ...


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value (CONTRACTS.md: commands)."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@component(provides=("kernel",))
async def kernel(*, jail: Jail, config: KernelConfig) -> Effects:
    """Fills a `kernel` row: `use = "kernel:kernel"`. The kernel is also the model's one tool,
    `python(code)`; the loop asks `approval` about each input before it runs.

    Depends on the jail and nothing else, so swapping the model or the ui keeps the
    namespace; swapping the jail starts a new process, which is the honest thing for a new jail
    to mean."""
    started = yield enter(Kernel(jail, config))
    yield bind("kernel", started)


@component(provides=("approval",))
async def approval(*, jail: Graded, output: Asks) -> Effects:
    """Fills an `approval` row: `use = "kernel:approval"`. Whether the model's code may run (an
    input, an extension to load): at once when the jail confines it, else on the person's yes
    through `output.confirm`.

    Depends on the jail and the output, not the kernel, so `/clear` (a new kernel) leaves it and
    what depends on it up. It runs in bh-02's own process: only a layer replaces it."""
    yield bind("approval", Approval(jail, output))


@component
async def release(*, kernel: _Releasing, commands: _Registrar) -> Effects:
    """Fills a `release` row: `use = "kernel:release"`. `/release` ends the kernel's worker now,
    and its jail with it, and releases the jail (on Linux it stops the extensions' worker too),
    which frees the paths the jail holds on the host (where bh-02 looks for its credential) until
    the next input starts a new one: the way to add a credential mid-session. A row of its own,
    so the kernel depends on its jail alone."""

    async def run(args: str) -> str:
        return await kernel.release()

    spec = {
        "name": "release",
        "help": "stop the kernel until the next input (to add your credential)",
        "usage": "",
    }
    yield acquire(commands.register, spec, run)


@component(provides=("jail",))
async def unjailed() -> Effects:
    """Fills a `jail` row with no confinement: `use = "kernel:unjailed"`. Every input then asks."""
    yield bind("jail", Unjailed())
