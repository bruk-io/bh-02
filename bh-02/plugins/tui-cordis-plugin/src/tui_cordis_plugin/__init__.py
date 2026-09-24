"""A Textual app as the ui: `input`, `output` (whose `confirm` asks in a modal) and `frame`,
and rows that push status into the app's frame.

`app` is the Textual app and `running`; `ports` the values the ui binds (input, output,
frame); `wiring` the rows.
"""

from tui_cordis_plugin.app import BhApp, running
from tui_cordis_plugin.history import History, Replay, replayable
from tui_cordis_plugin.ports import AppCrashed, Bridge, Frame, TuiInput, TuiOutput
from tui_cordis_plugin.sessions import SessionSink, SessionSource, listing, marked, resume_note, session_label
from tui_cordis_plugin.status import (
    CommandSink,
    CommandSource,
    Confinement,
    Entries,
    ModelField,
    ModelSource,
    Running,
    StatusConfig,
    StatusSink,
    TuiConfig,
)
from tui_cordis_plugin.wiring import palette, session_list, status, tui

__all__ = [
    "AppCrashed",
    "BhApp",
    "Bridge",
    "Frame",
    "CommandSink",
    "CommandSource",
    "Confinement",
    "Entries",
    "ModelField",
    "ModelSource",
    "Running",
    "History",
    "Replay",
    "SessionSink",
    "SessionSource",
    "StatusConfig",
    "StatusSink",
    "TuiConfig",
    "TuiInput",
    "TuiOutput",
    "listing",
    "marked",
    "resume_note",
    "palette",
    "replayable",
    "running",
    "session_label",
    "session_list",
    "status",
    "tui",
]
