"""Slash commands: a broker rows register commands into, and commands over the composition."""

from commands_cordis_plugin.operations import (
    Loader,
    Models,
    Operator,
    OperatorConfig,
    model_list,
    perform,
    rows_table,
)
from commands_cordis_plugin.registry import Choice, Commands, CommandSpec, Run, parse
from commands_cordis_plugin.wiring import operator, registry, set_model, shadowing

__all__ = [
    "Choice",
    "CommandSpec",
    "Commands",
    "Loader",
    "Models",
    "Operator",
    "OperatorConfig",
    "Run",
    "model_list",
    "operator",
    "parse",
    "perform",
    "registry",
    "rows_table",
    "set_model",
    "shadowing",
]
