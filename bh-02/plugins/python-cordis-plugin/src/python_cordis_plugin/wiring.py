"""The rows: the kernel, bound under `kernel`, which registers the `python` tool with `tools` and
what the model is told about it with `system`; `/release` over it; whether a call may run, under
`approval`; and a jail that confines nothing, under `jail`."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component, enter
from kernel_cordis_plugin.approval import Approval, Asks, Graded
from kernel_cordis_plugin.client import Access, Jail, Kernel, KernelConfig
from kernel_cordis_plugin.python import PYTHON, shown_call
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


@runtime_checkable
class _Tools(Protocol):
    """What the kernel row needs of the `tools` value (CONTRACTS.md: tools): a tool registered,
    and its remover back."""

    def register(
        self,
        spec: Mapping[str, Any],
        run: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
        *,
        runs: str = ...,
        show: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = ...,
    ) -> Callable[[], None]: ...


@runtime_checkable
class _Sections(Protocol):
    """What the kernel row needs of the `system` value (CONTRACTS.md: system): a named section
    added, and its remover back."""

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]: ...


@component(provides=("kernel",))
async def kernel(
    *, jail: Jail, tools: _Tools, system: _Sections, access: Access, config: KernelConfig
) -> Effects:
    """Fills a `kernel` row: `use = "kernel:kernel"`. The kernel registers the `python(code)`
    tool with `tools` (each call runs in the jail; the loop asks `approval` about it first, shown
    as its code), and adds what the model is told about it, its REPL and its jail, as the `system`
    section `python`, read each time the prompt is. Before an input's own Python opens a file in
    the project, the worker asks `access` about it, when a row is asking about that kind of
    opening (read, write), and a refusal stops the open.

    Depends on the jail and the three brokers, which never reload, so swapping the model or the
    ui keeps the namespace, and so does a reload of the loop; swapping the jail starts a new
    process, which is the honest thing for a new jail to mean. A restart (`/clear`) registers
    the same tool again, so the loop reloads with nothing."""
    started = yield enter(Kernel(jail, config, access))
    yield bind("kernel", started)
    yield acquire(tools.register, PYTHON, started.call, show=shown_call)
    yield acquire(system.add, "python", started.instructions)


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
