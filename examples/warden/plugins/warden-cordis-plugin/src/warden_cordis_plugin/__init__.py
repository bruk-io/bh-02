"""A process supervisor: a registry every managed process registers into, one row each."""

from warden_cordis_plugin.process import Process, ProcessConfig, managed_process
from warden_cordis_plugin.registry import Processes
from warden_cordis_plugin.wiring import registry, supervised

__all__ = ["Process", "ProcessConfig", "Processes", "managed_process", "registry", "supervised"]
