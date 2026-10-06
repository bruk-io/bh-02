"""The app's widgets, one module each, named as bh-01 names them."""

from tui_cordis_plugin.widgets.approval import GRACE, ApprovalScreen
from tui_cordis_plugin.widgets.composer import Composer
from tui_cordis_plugin.widgets.palette import CommandsProvider
from tui_cordis_plugin.widgets.status_bar import StatusBar
from tui_cordis_plugin.widgets.transcript import Stream, Transcript

__all__ = [
    "GRACE",
    "ApprovalScreen",
    "CommandsProvider",
    "Composer",
    "StatusBar",
    "Stream",
    "Transcript",
]
