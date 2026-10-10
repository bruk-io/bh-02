"""The model's own plugins: cordis components it writes and bh-02 loads while it runs, jailed."""

from extensions_cordis_plugin.host import Extensions, ExtensionsConfig, worker_argv
from extensions_cordis_plugin.offered import offered_tool, shown_tool_call
from extensions_cordis_plugin.watch import Status, changes, extension_name, instructions
from extensions_cordis_plugin.wiring import extensions

__all__ = [
    "Extensions",
    "ExtensionsConfig",
    "Status",
    "changes",
    "extension_name",
    "extensions",
    "instructions",
    "offered_tool",
    "shown_tool_call",
    "worker_argv",
]
