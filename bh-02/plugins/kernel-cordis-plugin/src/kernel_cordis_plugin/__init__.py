"""A persistent Python kernel in a process of its own, started by the composition's `jail`,
and the model's one tool, `python(code)`, which runs an input in it; `approval`: whether the
model's code may run, by the jail's confinement or the person's yes; and `/release`, which
stops the kernel until the next input."""

from kernel_cordis_plugin.approval import Approval, is_confined
from kernel_cordis_plugin.client import Jail, Jailed, Kernel, KernelConfig, worker_argv
from kernel_cordis_plugin.python import PYTHON, instructions_for
from kernel_cordis_plugin.unjailed import UNENFORCED, Unjailed
from kernel_cordis_plugin.wiring import approval, kernel, release, unjailed

__all__ = [
    "PYTHON",
    "UNENFORCED",
    "Approval",
    "Jail",
    "Jailed",
    "Kernel",
    "KernelConfig",
    "Unjailed",
    "approval",
    "instructions_for",
    "is_confined",
    "kernel",
    "release",
    "unjailed",
    "worker_argv",
]
