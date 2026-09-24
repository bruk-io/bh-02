"""The Textual app, and `running`, which runs it on the event loop already running cordis.

Layout, in bh-01's words: an ActivityBar on the left, a SidebarPanel, the conversation
(Transcript over Composer) and a StatusBar along the bottom. The app owns the screen: its
input, output and frame post it messages (`messages.py`) and it draws them.

Below 100 columns the SidebarPanel is hidden (the screen's `-narrow` breakpoint); Ctrl-B shows
or hides it at any width, and the person's choice then holds. Showing it focuses its list;
hiding it puts focus back in the composer. The sessions it lists are read on a thread (reading
scans the state directory), never on the loop, which is cordis's too.

Leaving: Ctrl-Q, or `/exit` or `/quit` in the composer. The terminal going away (its window
closed: SIGHUP, or, with no controlling terminal, stdin at end of file) leaves the same way, so
the composition unwinds rather than the process dying where it stands or spinning on a dead
fd. Ctrl-C interrupts the running turn and never quits; with no turn running it says how to
leave. Ctrl-P (or the activity bar's `≡`) opens the command palette.

Questions (`output.confirm`) are shown one at a time, the rest queued: an interrupted turn
withdraws its own (shown or queued), and Ctrl-C with one up answers every open question no.

A session's history is drawn again when the app starts (`replay`, what `history.replayable`
chose from the file), and everything the transcript shows after that is appended to `history`,
so a resumed session shows what was said.
"""

import asyncio
import contextlib
import fcntl
import functools
import select
import signal
import struct
import sys
import termios
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer

from tui_cordis_plugin import frame, render, theme
from tui_cordis_plugin.frame import PaletteEntry
from tui_cordis_plugin.history import History, Replay, merged
from tui_cordis_plugin.messages import (
    Asked,
    FrameChanged,
    Noted,
    RowsUp,
    Shown,
    TurnEnded,
    TurnStarted,
    Withdrawn,
)
from tui_cordis_plugin.ports import AppCrashed, Bridge, Frame
from tui_cordis_plugin.sessions import resume_note
from tui_cordis_plugin.widgets import (
    GRACE,
    ActivityBar,
    ApprovalScreen,
    CommandsProvider,
    Composer,
    SidebarPanel,
    StatusBar,
    Transcript,
)

__all__ = ["BhApp", "running"]

EXIT_COMMANDS = frozenset({"/exit", "/quit"})
_WIDE = 100  # columns from which the sidebar shows by itself
_HOW_TO_LEAVE = "Ctrl-Q, /exit or /quit leaves; Ctrl-C only stops a running turn; Ctrl-P lists commands."

type _Question = tuple[Mapping[str, Any], asyncio.Future[bool]]

# How long an interrupted turn has to withdraw its own questions before they are answered no.
_WITHDRAW_GRACE = 0.5
# How long every row must stay up before a status field kept while they came up goes: a
# restart's old fiber ends a moment before its new one starts (`/clear`'s kernel), and the
# row showing the field (`status`) comes up after what it depends on.
_RELEASE_GRACE = 1.0
# How often the terminal is checked for having gone away, and how many checks in a row must
# say so: a key arriving between one check's two reads looks like a hangup once, never twice.
_HANGUP_EVERY = 0.5
_HANGUP_CHECKS = 2


class BhApp(App[None]):
    """bh-02's screen. `bridge` is what its input, output and frame share with it; `frame` is
    what rows push into; `replay` is drawn when it starts; `history`, when given, is appended
    to as the transcript draws; `grace` is how long a question just put up ignores y, n and
    Escape (keys typed ahead)."""

    TITLE = "bh-02"
    COMMANDS = {CommandsProvider}  # the commands rows offer, not Textual's system commands
    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", priority=True, show=False),
        Binding("ctrl+q", "quit", "Quit", priority=True, show=False),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=False),
    ]
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (_WIDE, "-wide")]
    # No `Screen { background: ... }` here: app CSS outranks every DEFAULT_CSS, and `Screen`
    # matches the approval modal too, which would lose its translucent background.
    CSS = """
    #main {
        height: 1fr;
    }
    #conversation {
        width: 1fr;
    }
    Screen.-narrow #sidebar {
        display: none;
    }
    """

    def __init__(
        self, *, history: History | None = None, replay: Replay | None = None, grace: float = GRACE
    ) -> None:
        super().__init__()
        self.history = history
        self.replay = replay
        self.grace = grace  # how long a question just shown ignores its keys (`ApprovalScreen`)
        # Registered before anything mounts: a stylesheet parsed at startup must find its tokens.
        for each in theme.themes():
            self.register_theme(each)
        self.theme = theme.NAME
        self.bridge = Bridge()
        self.frame = Frame(self.post_message, lambda: self.bridge.settling)
        self.ready = asyncio.Event()
        self._asking: tuple[ApprovalScreen, asyncio.Future[bool]] | None = None
        self._queued: deque[_Question] = deque()
        self._broken_noted: set[str] = set()  # broken session records the transcript has named
        self._releasing: Timer | None = None  # the grace before kept status fields go
        self._replying = 0  # replies streaming now (started, not yet ended)
        self._typed: list[str] = []  # lines typed while one streams, drawn once it ends
        self._hangups = 0  # checks in a row that found the terminal gone

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return dict(theme.VARIABLES)

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            yield ActivityBar(id="activity-bar")
            yield SidebarPanel(id="sidebar")
            with Vertical(id="conversation"):
                yield Transcript(id="transcript")
                yield Composer(id="composer")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        # The breakpoint classes come with the first Resize, after the first frame is drawn;
        # set them now so a narrow terminal never shows the sidebar for a frame.
        self.screen.set_class(self.size.width < _WIDE, "-narrow")
        self.screen.set_class(self.size.width >= _WIDE, "-wide")
        self.query_one(Composer).focus()
        if self.replay is not None:
            self.query_one(Transcript).replay(self.replay)
        self._check_history()  # a history that couldn't be read says so
        if self.history is not None and self.history.warning is not None:
            self.query_one(Transcript).note(self.history.warning, "failure")  # nor trimmed
        self.query_one(Transcript).note(_HOW_TO_LEAVE)
        self.query_one(SidebarPanel).show_sessions([])
        stdin = sys.__stdin__
        if not self.is_headless and stdin is not None and stdin.isatty():
            self.set_interval(_HANGUP_EVERY, functools.partial(self._watch_terminal, stdin.fileno()))

    def _watch_terminal(self, fd: int) -> None:
        """Leave once the terminal has gone (`_terminal_gone`) for `_HANGUP_CHECKS` checks in a row.
        Textual's input thread, on macOS, reads its end of file again and again and never exits."""
        self._hangups = self._hangups + 1 if _terminal_gone(fd) else 0
        if self._hangups >= _HANGUP_CHECKS:
            self.exit()

    def on_unmount(self) -> None:
        self.frame.release()  # nothing is coming back to an app that has ended
        if self.history is not None:
            self.history.close()

    def on_ready(self) -> None:
        self.ready.set()

    @property
    def asking(self) -> bool:
        """Whether a question is up."""
        return self._asking is not None

    def send(self, line: str) -> None:
        """Send a line as if typed: `/exit` and `/quit` leave; anything else goes to the input.
        A line typed while a reply streams goes to the input at once (it is read once the reply
        ends) but is drawn when the reply ends, so it never splits the reply's text or its
        usage line. A line nobody can read yet, because rows are coming back up (`/model`, `/clear`),
        says it is waiting and for what: it is read once they are up, never dropped."""
        if line.strip() in EXIT_COMMANDS:
            self.exit()
            return
        if self._replying:
            self._typed.append(line)  # drawn under the reply once it ends, not inside it
        else:
            self._draw_typed(line)
        waiting = self.bridge.waiting_on
        if not self.bridge.submit(line) and waiting:
            self.post_message(Noted(render.waiting_line(waiting)))

    def on_composer_submitted(self, message: Composer.Submitted) -> None:
        self.send(message.text)

    def palette_entries(self) -> Sequence[PaletteEntry]:
        """What the command palette lists: the commands rows offer now, `/help`, `/exit`."""
        return frame.palette_entries(self.frame.offered_commands())

    def choose(self, entry: PaletteEntry) -> None:
        """Run a palette entry; one that takes arguments goes in the composer to finish."""
        if not entry.takes_arguments:
            self.send(entry.call)
            return
        composer = self.query_one(Composer)
        composer.text = f"{entry.call} "
        composer.move_cursor(composer.document.end)
        composer.focus()

    def action_command_palette(self) -> None:
        """Ctrl-P: the palette, except while a question waits for its answer."""
        if self._asking is None:
            super().action_command_palette()

    def on_shown(self, message: Shown) -> None:
        """Draw a batch of a turn's events (each run of streamed text joined first, so it is
        drawn and kept once), then say it is drawn, so the output sends the next. A `cleared`
        drops the conversation so far, but not a line typed after `/clear` and not read yet:
        it is drawn again, since it is sent in the new conversation (one typed during this
        reply is drawn once it ends, as always)."""
        try:
            transcript = self.query_one(Transcript)
            for event in merged(message.events):
                transcript.event(event)
                self._record(event)
                if event.get("type") == "cleared":
                    # the newest kept lines are the ones held for this reply's end: drawn then
                    kept = self.bridge.kept
                    for line in kept[: max(0, len(kept) - len(self._typed))]:
                        self._draw_typed(line)
        finally:
            if message.drawn is not None and not message.drawn.done():
                message.drawn.set_result(None)

    def _draw_typed(self, line: str) -> None:
        self.query_one(Transcript).user(line)
        self._record({"type": "user", "text": line})

    def on_turn_started(self, message: TurnStarted) -> None:
        self._replying += 1

    def on_turn_ended(self, message: TurnEnded) -> None:
        self.query_one(Transcript).end_turn()
        self._record({"type": "turn_end"})
        self._replying = max(0, self._replying - 1)
        if not self._replying:
            typed, self._typed = self._typed, []
            for line in typed:
                self._draw_typed(line)

    def on_noted(self, message: Noted) -> None:
        self.query_one(Transcript).note(message.text, message.kind)
        self._record({"type": "noted", "text": message.text, "kind": message.kind})

    def _record(self, entry: Mapping[str, Any]) -> None:
        """Keep what was just drawn in the history; if that fails, say so once and go on."""
        if self.history is None:
            return
        self.history.record(entry)
        self._check_history()

    def _check_history(self) -> None:
        """A history that failed says why, once, and is not used again."""
        if self.history is not None and self.history.failed is not None:
            self.query_one(Transcript).note(self.history.failed, "failure")
            self.history = None

    def on_frame_changed(self, message: FrameChanged) -> None:
        """Redraw what the changed kind of entry shows: the status bar, or the sessions (read
        from disk, so not for a status change, which comes twice per usage event)."""
        if message.what == "status":
            self.query_one(StatusBar).show_fields(self.frame.forms())
        elif message.what == "sessions":
            self._list_sessions()

    def on_rows_up(self, message: RowsUp) -> None:
        """Rows that came back up: drop the status fields kept meanwhile, once they have all
        stayed up for a moment (`_RELEASE_GRACE`) since the last time they came up."""
        if self._releasing is not None:
            self._releasing.stop()
        self._releasing = self.set_timer(_RELEASE_GRACE, self._release_kept)

    def _release_kept(self) -> None:
        self._releasing = None
        if not self.bridge.settling:
            self.frame.release()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """The sidebar's list, focused: read the sessions again (one may have started since)."""
        sidebar = self.query_one(SidebarPanel)
        if sidebar in event.widget.ancestors_with_self:
            self._list_sessions()

    @work(exclusive=True, group="sessions")
    async def _list_sessions(self) -> None:
        """List the sessions as the rows' readers say now, read on a thread: they scan the
        state directory, which must not stall the loop (cordis's too). A newer listing
        cancels one still reading. A broken record is named in the transcript too, once (the
        sidebar is folded on a narrow screen)."""
        listed = await asyncio.to_thread(self.frame.session_listing())
        self.query_one(SidebarPanel).show_sessions(listed)
        for item in listed:
            if item.get("broken") and str(item.get("id")) not in self._broken_noted:
                self._broken_noted.add(str(item.get("id")))
                self.query_one(Transcript).note(resume_note(item), "failure")

    def on_asked(self, message: Asked) -> None:
        """Queue a question; the answer resolves the asker's future. An asker that stops
        waiting (its turn was interrupted) withdraws it."""
        answer = message.answer
        if answer.done():
            return

        def withdrawn(_: object) -> None:
            if answer.cancelled():
                self.post_message(Withdrawn(answer))

        answer.add_done_callback(withdrawn)
        self._queued.append((message.request, answer))
        self._ask_next()

    def _ask_next(self) -> None:
        """Put the oldest question still waiting in a modal, unless one is up."""
        while self._asking is None and self._queued:
            request, answer = self._queued.popleft()
            if answer.done():
                continue
            screen = ApprovalScreen(request, grace=self.grace)
            self._asking = (screen, answer)
            self.push_screen(screen, self._answerer(answer))

    def _answerer(self, answer: asyncio.Future[bool]) -> Any:
        """The callback a question's modal calls with its answer (None when taken down)."""

        def answered(allowed: bool | None) -> None:
            if not answer.done():
                answer.set_result(bool(allowed))
            if self._asking is not None and self._asking[1] is answer:
                self._asking = None
            self._ask_next()

        return answered

    def on_withdrawn(self, message: Withdrawn) -> None:
        """Take a withdrawn question down, wherever it is: queued, or up (under the palette, say)."""
        self._queued = deque(q for q in self._queued if q[1] is not message.answer)
        if self._asking is not None and self._asking[1] is message.answer:
            self._take_down(self._asking[0])

    def _take_down(self, screen: ApprovalScreen) -> None:
        """Dismiss a question's modal, first popping anything shown over it."""
        if screen not in self.screen_stack:
            return
        if screen is not self.screen:
            screen.pop_until_active()
        screen.dismiss(False)

    def action_toggle_sidebar(self) -> None:
        """Ctrl-B: show the sidebar if it is hidden (a narrow screen hides it) and focus its
        list, else hide it and focus the composer. Over a modal, focus stays where it is."""
        sidebar = self.query_one(SidebarPanel)
        sidebar.display = not sidebar.display
        self._list_sessions()
        if len(self.screen_stack) > 1:
            return
        if sidebar.display:
            sidebar.focus_list()
        else:
            self.query_one(Composer).focus()

    def action_interrupt(self) -> None:
        """Ctrl-C: stop the running turn and take its questions down as a no; with nothing
        running, say how to leave.

        A turn that hears Ctrl-C is cancelled, which cancels the questions it is waiting on,
        and those come down as withdrawn: answering them no first would let the turn carry on
        with the answer before it hears the interrupt. Any question still open a moment later
        (asked from outside a turn) is answered no; one with no turn to stop, at once.
        """
        questions = self._open_questions()
        stopped = self.bridge.interrupt()
        if stopped and questions:
            self.set_timer(_WITHDRAW_GRACE, functools.partial(self._decline, questions))
        elif questions:
            self._decline(questions)
        elif not stopped:
            self.query_one(Transcript).note(f"Nothing is running. {_HOW_TO_LEAVE}")

    def _open_questions(self) -> list[asyncio.Future[bool]]:
        """Every question not yet answered: the one up, then the queued ones."""
        shown = [self._asking[1]] if self._asking is not None else []
        return [answer for answer in [*shown, *(a for _, a in self._queued)] if not answer.done()]

    def _decline(self, answers: Sequence[asyncio.Future[bool]]) -> None:
        """Answer each of `answers` still open no, and take the one up down if it is among them."""
        for answer in answers:
            if not answer.done():
                answer.set_result(False)
        if self._asking is not None and any(a is self._asking[1] for a in answers):
            self._take_down(self._asking[0])


@contextlib.asynccontextmanager
async def running(app: BhApp, *, headless: bool = False) -> AsyncIterator[BhApp]:
    """Run `app` on the running loop; enter once it is on screen, and leave once it has exited.

    Whatever ends the app (Ctrl-Q, `/exit`, a crash, this context leaving) ends its bridge,
    which settles every input, output or frame call waiting on it. An app that never became
    ready raises here, and an enter cancelled before the app is ready takes the app down before
    it re-raises. Textual makes its loop's tasks eager while it starts; the loop's own task
    factory is put back once the app is up, since the loop is cordis's too.
    """
    loop = asyncio.get_running_loop()
    factory = loop.get_task_factory()
    with contextlib.ExitStack() as hangup:
        if not headless:
            # the terminal closed: leave as Ctrl-Q does, rather than die on Python's default
            loop.add_signal_handler(signal.SIGHUP, app.exit)
            hangup.callback(loop.remove_signal_handler, signal.SIGHUP)
        task = asyncio.ensure_future(_until_ended(app, headless))
        ready = asyncio.ensure_future(app.ready.wait())
        try:
            await asyncio.wait({task, ready}, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            loop.set_task_factory(factory)
            ready.cancel()
        if not app.ready.is_set():
            await asyncio.gather(task, return_exceptions=True)
            raise app.bridge.crash or AppCrashed("the app exited before it was ready")
        try:
            yield app
        finally:
            if not task.done():
                app.exit()
            await task


async def _until_ended(app: BhApp, headless: bool) -> None:
    """Run the app; whatever ends it, end its bridge with why (a crash, or None)."""
    outcome: BaseException | None = None
    try:
        await app.run_async(headless=headless)
    except BaseException as error:
        outcome = error
        raise
    finally:
        app.bridge.end(_crash(outcome, app.return_code))


def _terminal_gone(fd: int) -> bool:
    """Whether the terminal on `fd` has hung up: it reads as ready with nothing waiting in it,
    which is a pty's end of file (a key waiting shows as bytes to read)."""
    ready, _, _ = select.select([fd], [], [], 0)
    if not ready:
        return False
    waiting = struct.unpack("i", fcntl.ioctl(fd, termios.FIONREAD, b"\0\0\0\0"))[0]
    return bool(waiting == 0)


def _crash(outcome: BaseException | None, return_code: int | None) -> AppCrashed | None:
    """Why the app ended, if it was not asked to: cancelled, an error, or a non-zero exit code."""
    if isinstance(outcome, asyncio.CancelledError):
        return AppCrashed("the app was cancelled")
    if outcome is not None:
        return AppCrashed(f"the app failed: {type(outcome).__name__}: {outcome}")
    if return_code not in (None, 0):
        return AppCrashed(f"the app crashed (exit code {return_code}); its traceback is above")
    return None
