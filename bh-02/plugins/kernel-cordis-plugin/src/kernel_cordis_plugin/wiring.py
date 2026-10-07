"""The rows: the kernel, bound under `kernel`; whether the model's code may run, under
`approval`; a jail that confines nothing, under `jail`; and the shell hints, added to `memory`."""

from typing import Any

from cordis import Effects, acquire, bind, component, enter
from kernel_cordis_plugin.approval import Approval, Asks, Graded
from kernel_cordis_plugin.client import Jail, Kernel, KernelConfig
from kernel_cordis_plugin.python import Memory, ShellHints
from kernel_cordis_plugin.unjailed import Unjailed

__all__ = ["approval", "kernel", "shell_hints", "unjailed"]


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


@component(provides=("jail",))
async def unjailed() -> Effects:
    """Fills a `jail` row with no confinement: `use = "kernel:unjailed"`. Every input then asks."""
    yield bind("jail", Unjailed())


@component
async def shell_hints(*, memory: Memory, transcript: Any) -> Effects:
    """Fills a `shell-hints` row: `use = "kernel:shell_hints"`. The first input of a conversation
    that runs `cat`, `sed`, `ls` or the like through a shell is told, with its result, how Python
    does that kind of work here (`ShellHints`). It depends on `transcript` only to share its
    lifetime: a new conversation (`/clear`) starts a new row, which tells each kind again."""
    yield acquire(memory.add, ShellHints())
