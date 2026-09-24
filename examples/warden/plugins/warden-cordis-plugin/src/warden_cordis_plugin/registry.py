"""The registry value: managed processes by name.

The generic half is `cordis_helpers.Registry`; what is here is what makes it a *process*
registry: entries are `Process`, and the name is what a contributor picked, not a row id.
"""

from collections.abc import Callable

from cordis_helpers import Registry
from warden_cordis_plugin.process import Process

__all__ = ["Processes"]


class Processes:
    """The broker: bound once under `processes`, registered into by one row per managed process."""

    def __init__(self) -> None:
        self._processes: Registry[Process] = Registry("process")

    def register(self, name: str, process: Process) -> Callable[[], None]:
        """Register a running process under `name`; returns the remover. A name is one process."""
        return self._processes.register(name, process)

    def get(self, name: str) -> Process | None:
        return self._processes.get(name)

    @property
    def names(self) -> list[str]:
        return self._processes.names
