"""The rows: the app as `input`, `output` and `frame` (`output.confirm` asks in a modal); and
the rows that push into the app's frame: the status bar's fields (the session and the model,
and the runner's grades) and the palette's commands."""

import asyncio

from cordis import Effects, acquire, background, bind, component, enter, observe
from tui_cordis_plugin import frame, render
from tui_cordis_plugin.app import BhApp, running
from tui_cordis_plugin.history import History, Replay, replayable
from tui_cordis_plugin.ports import TuiInput, TuiOutput
from tui_cordis_plugin.status import (
    CommandSink,
    CommandSource,
    Confinement,
    Entries,
    GradesField,
    ModelField,
    ModelSource,
    Notes,
    Running,
    Starts,
    StatusConfig,
    StatusSink,
    TuiConfig,
)

__all__ = ["grades", "palette", "status", "tui"]


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
    loader: Entries,
    models: ModelSource,
    sessions: Running,
    frame: StatusSink,
    config: StatusConfig,
) -> Effects:
    """The status bar's session and model fields (`use = "tui:status"`): the running session's
    id (with its short form for a narrow bar), and the model. Usage is the output's own field,
    the runner's grades the `grades` row's.

    It depends on nothing a restart replaces, so it never reloads with `/clear` or `/model`. The
    model field hears the composition change, so a `/model` (which reloads the model row, not
    this one) shows the new model, `starting…` until it is up: it asks `models` (which never
    reloads) which model and provider the model row names, never `model` itself, which a switch
    replaces."""
    if sessions.current:
        shown = render.session_forms(sessions.current, resumed=sessions.resumed)
        yield acquire(frame.status, "session", *shown)
    field = ModelField(frame.status, loader, config.model_row, models.current)
    yield acquire(field.show)
    yield observe(field.lifecycle)


@component
async def grades(*, runner: Starts, approval: Confinement, frame: StatusSink, output: Notes) -> Effects:
    """The status bar's `jail` field (`use = "tui:grades"`): the grades of the runner's last
    start, and whether the `approval` rule counts them as confined. A row of its own over the
    runner, which tells it each start: it never reloads with `/clear`, and follows a Python
    process started again in place. What a start says the person should know (on Linux, the
    paths its jail holds with a mount the host can undo) is shown once as a note."""
    notes: asyncio.Queue[str] = asyncio.Queue()

    async def tell() -> None:
        while True:
            await output.show(render.noted(await notes.get()))

    yield background(tell())
    field = GradesField(frame.status, approval, runner.report(), notes.put_nowait)
    yield acquire(field.show)
    yield acquire(runner.on_start, field.started)


@component
async def palette(*, commands: CommandSource, frame: CommandSink) -> Effects:
    """Offers the commands broker's commands in the palette (Ctrl-P): `use = "tui:palette"`.

    It pushes `commands.specs` itself, which the palette reads each time it opens, so a
    command a row registers later is offered with no reload of this row.
    """
    yield acquire(frame.commands, commands.specs)
