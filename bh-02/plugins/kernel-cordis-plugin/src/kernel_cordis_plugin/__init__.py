"""A persistent Python kernel in a process of its own, started by the composition's `jail`,
and the model's one tool, `python(code)`, which runs an input in it; and the shell hints it
adds to `memory`."""

from kernel_cordis_plugin.client import Jail, Jailed, Kernel, KernelConfig, is_confined, worker_argv
from kernel_cordis_plugin.python import (
    PYTHON,
    Memory,
    ShellHints,
    instructions_for,
    programs,
    shell_note,
    shelled,
)
from kernel_cordis_plugin.unjailed import UNENFORCED, Unjailed
from kernel_cordis_plugin.wiring import kernel, shell_hints, unjailed

__all__ = [
    "PYTHON",
    "UNENFORCED",
    "Jail",
    "Jailed",
    "Kernel",
    "KernelConfig",
    "Memory",
    "ShellHints",
    "Unjailed",
    "instructions_for",
    "is_confined",
    "kernel",
    "programs",
    "shell_hints",
    "shell_note",
    "shelled",
    "unjailed",
    "worker_argv",
]
