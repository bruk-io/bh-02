"""The app's widgets, one module each, named as bh-01 names them."""

from tui_cordis_plugin.widgets.approval import GRACE, ApprovalScreen
from tui_cordis_plugin.widgets.completions import Completions
from tui_cordis_plugin.widgets.composer import Composer
from tui_cordis_plugin.widgets.palette import CommandsProvider
from tui_cordis_plugin.widgets.status_bar import StatusBar
from tui_cordis_plugin.widgets.transcript import Clipped, Stream, Transcript
from tui_cordis_plugin.widgets.working import WORKING_EVERY, Working

__all__ = [
    "GRACE",
    "WORKING_EVERY",
    "ApprovalScreen",
    "Clipped",
    "CommandsProvider",
    "Completions",
    "Composer",
    "StatusBar",
    "Stream",
    "Transcript",
    "Working",
]
