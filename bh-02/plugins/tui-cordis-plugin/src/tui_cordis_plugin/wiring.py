"""The rows: the app as `input`, `output` and `frame` (`output.confirm` asks in a modal); and
the rows that push into the app's frame: the status bar's fields and the palette's commands."""

from cordis import Effects, acquire, bind, component, enter, observe
from tui_cordis_plugin import frame, render
from tui_cordis_plugin.app import BhApp, running
from tui_cordis_plugin.history import History, Replay, replayable
from tui_cordis_plugin.ports import TuiInput, TuiOutput
from tui_cordis_plugin.status import (
    CommandSink,
    CommandSource,
    Confinement,
    Entries,
    ModelField,
    ModelSource,
    Notes,
    Running,
    StatusConfig,
    StatusSink,
    TuiConfig,
)

__all__ = ["palette", "status", "tui"]


@component(name="app", provides=("input", "output", "frame"))
async def tui(*, config: TuiConfig) -> Effects:
    """Fills a `ui` row: `use = "tui:app"`. Depends on nothing but its config, so no reload
    elsewhere ever restarts the app (and loses the transcript). Runs the app on cordis's loop
    for as long as the row is up, and notes the composition changing (a reload, a failure).
    With `history` configured, the app draws that file again (its last `replay` entries) and
    keeps what it shows there, and the status bar's `usage` starts from the usage it holds."""
    history: History | None = None
    replay: Replay | None = None
    used = frame.Usage()
    if config.history:
        history = yield enter(History(config.history, config.replay))
        replay = replayable(history.recorded, config.replay)
        used = frame.total_usage(history.recorded)  # the session's, not only this run's
    app = BhApp(history=history, replay=replay)
    shown = yield enter(running(app, headless=config.headless))
    output = TuiOutput(shown.post_message, shown.bridge, shown.frame.status, used)
    yield acquire(output.usage_field)
    yield observe(output.lifecycle)
    yield bind("input", TuiInput(shown.bridge))
    yield bind("output", output)
    yield bind("frame", shown.frame)


@component
async def status(
    *,
    kernel: Confinement,
    loader: Entries,
    models: ModelSource,
    sessions: Running,
    frame: StatusSink,
    output: Notes,
    config: StatusConfig,
) -> Effects:
    """The status bar's fields that rows report (`use = "tui:status"`): the running session's
    id (with its short form for a narrow bar), the model, and the kernel's jail grades. Usage
    is the output's own field, not this row's.

    A small row of its own, so a new kernel (a `/clear`, a new jail) reloads this and never the
    app; while it comes back up the bar keeps the fields' last text. The model field hears the
    composition change, so a `/model` (which reloads the model row, not this one) shows the new
    model, `starting…` until it is up: it asks `models` (which never reloads) which model and
    provider the model row names, never `model` itself, which a switch replaces.

    What the kernel's jail says the person should know (`kernel.notice()`: on Linux, the paths
    it holds with a mount the host can undo) is shown once as a note in the conversation, each
    time a kernel comes up: at the start of a session, and after a `/clear` or a new jail."""
    if notice := kernel.notice():
        await output.show(render.noted(notice))
    if sessions.current:
        shown = render.session_forms(sessions.current, resumed=sessions.resumed)
        yield acquire(frame.status, "session", *shown)
    yield acquire(frame.status, "jail", *render.jail_forms(kernel.confined, kernel.report()))
    field = ModelField(frame.status, loader, config.model_row, models.current)
    yield acquire(field.show)
    yield observe(field.lifecycle)


@component
async def palette(*, commands: CommandSource, frame: CommandSink) -> Effects:
    """Offers the commands broker's commands in the palette (Ctrl-P): `use = "tui:palette"`.

    It pushes `commands.specs` itself, which the palette reads each time it opens, so a
    command a row registers later is offered with no reload of this row.
    """
    yield acquire(frame.commands, commands.specs)
