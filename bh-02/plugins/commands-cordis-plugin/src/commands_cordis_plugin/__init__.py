"""Slash commands: a broker rows register commands into (and claim line prefixes in), commands
over the composition, and `!`, a shell command the person runs."""

from commands_cordis_plugin.operations import Loader, Operator, rows_table
from commands_cordis_plugin.registry import Choice, Commands, CommandSpec, Run, parse
from commands_cordis_plugin.shell_command import (
    Ran,
    ShellCommandConfig,
    answer,
    environment,
    run_command,
    run_line,
)
from commands_cordis_plugin.wiring import operator, registry, shell_command

__all__ = [
    "Choice",
    "CommandSpec",
    "Commands",
    "Loader",
    "Operator",
    "Ran",
    "Run",
    "ShellCommandConfig",
    "answer",
    "environment",
    "operator",
    "parse",
    "registry",
    "rows_table",
    "run_command",
    "run_line",
    "shell_command",
]
