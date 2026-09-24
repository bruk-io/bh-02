"""The rows: the registry every managed process registers into, and one contributor per process."""

from cordis import Effects, acquire, bind, component, enter
from warden_cordis_plugin.process import Process, ProcessConfig, managed_process
from warden_cordis_plugin.registry import Processes

__all__ = ["registry", "supervised"]


@component(provides=("processes",))
async def registry() -> Effects:
    """Fills the `processes` row: `use = "warden:registry"`. Everything else registers into it."""
    yield bind("processes", Processes())


@component
async def supervised(*, config: ProcessConfig, processes: Processes) -> Effects:
    """A managed process, registered under `config.name`: `use = "warden:supervised"`.

    Depends on the registry, not on any other managed process row: adding, removing or
    reconfiguring one process never reloads another.
    """
    process: Process = yield enter(managed_process(config.command))
    yield acquire(processes.register, config.name, process)
