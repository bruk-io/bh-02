"""The Textual app, and `running`, which runs it on the event loop already running cordis.

Layout, in bh-01's words: the conversation (Transcript over Composer), the whole width, and a
StatusBar along the bottom. The app owns the screen: its input, output and frame post it
messages (`messages.py`) and it draws them.

Leaving: Ctrl-Q, or `/exit` or `/quit` in the composer. The terminal going away (its window
closed: SIGHUP, or, with no controlling terminal, stdin at end of file) leaves the same way, so
the composition unwinds rather than the process dying where it stands or spinning on a dead
fd. Ctrl-C interrupts the running turn and never quits; with no turn running it says how to
leave, and while a command runs (a `!` one may take minutes) that Ctrl-C doesn't stop it. Esc
stops a running reply as Ctrl-C does, once nothing nearer wants it: the composer's list of
commands (Esc closes it), a question (Esc declines it) and the palette (Esc closes it); with no
reply running it does nothing. Ctrl-P opens the command palette.

Copying goes to the terminal's clipboard through Textual (`copy_to_clipboard`, an OSC 52
sequence), and every way of copying says how much in one line: Ctrl-C with text selected (it
stops nothing then, and a second Ctrl-C stops the reply), Cmd-C (Textual's own `super+c`),
a mouse selection finished in the transcript (copied at once), and Ctrl-T for the newest reply.

Questions (`output.confirm`) are shown one at a time, the rest queued: an interrupted turn
withdraws its own (shown or queued), and Ctrl-C with one up answers no to every open question
but a sub-agent's: the reply it stops withdraws its foreground child's, and a background
child's stays queued.

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

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import OptionList, TextArea

from tui_cordis_plugin import frame, render, theme
from tui_cordis_plugin.frame import PaletteEntry
from tui_cordis_plugin.history import History, Replay, merged
from tui_cordis_plugin.messages import (
    Asked,
    FrameChanged,
    Noted,
    Shown,
    TurnEnded,
    TurnStarted,
    Withdrawn,
)
from tui_cordis_plugin.ports import AppCrashed, Bridge, Frame
from tui_cordis_plugin.widgets import (
    GRACE,
    ApprovalScreen,
    CommandsProvider,
    Completions,
    Composer,
    StatusBar,
    Transcript,
)

__all__ = ["BhApp", "running"]

EXIT_COMMANDS = frozenset({"/exit", "/quit"})
_HOW_TO_LEAVE = "Ctrl-Q, /exit or /quit leaves; Ctrl-C only stops a running turn; Ctrl-P lists commands."
_COMMAND_RUNS = (
    "A command is running, and Ctrl-C stops only a turn: a `!` command or /compact runs until it "
    "ends or its timeout stops it. Ctrl-Q, /exit or /quit leaves, and stops it too."
)

type _Question = tuple[Mapping[str, Any], asyncio.Future[bool]]

# How long the line saying what was copied stays on screen.
_TOLD_FOR = 3.0
_NOTHING_TO_COPY = "Nothing to copy: no reply yet"
# A selection of fewer characters than this is not copied when the mouse ends it.
_COPY_ON_SELECT = 2
# How long an interrupted turn has to withdraw its own questions before they are answered no.
_WITHDRAW_GRACE = 0.5
# How long a Ctrl-C held for the line being handled may go unheard before the app says a
# command is running: a turn that is starting hears it within a tick.
_UNHEARD_GRACE = 0.3
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
        # Not priority: the list of commands, the question and the palette take Esc first.
        Binding("escape", "stop_reply", "Stop the reply", show=False),
        # Free in the composer (TextArea binds no ctrl+t), the screen and the app, and no
        # terminal keeps it: Ctrl-O, Ctrl-R, Ctrl-G and Ctrl-N are what Claude Code and readline
        # use for other things.
        Binding("ctrl+t", "copy_reply", "Copy the newest reply", show=False),
    ]
    # No app `CSS`: each widget styles itself (its DEFAULT_CSS). App CSS outranks every
    # DEFAULT_CSS, and a `Screen { background: ... }` here would match the approval modal too,
    # which would lose its translucent background.

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
        self.frame = Frame(self.post_message)
        self.ready = asyncio.Event()
        self._asking: tuple[ApprovalScreen, asyncio.Future[bool]] | None = None
        self._queued: deque[_Question] = deque()
        self._replying = 0  # replies streaming now (started, not yet ended)
        self._typed: list[str] = []  # lines typed while one streams, drawn once it ends
        self._hangups = 0  # checks in a row that found the terminal gone

    def get_theme_variable_defaults(self) -> dict[str, str]:
        return dict(theme.VARIABLES)

    def compose(self) -> ComposeResult:
        yield Transcript(id="transcript")
        listed = Completions(id="completions")
        yield listed
        yield Composer(id="composer", completions=listed)
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        self.query_one(Composer).focus()
        if self.replay is not None:
            self.query_one(Transcript).replay(self.replay)
        self._check_history()  # a history that couldn't be read says so
        if self.history is not None and self.history.warning is not None:
            self.query_one(Transcript).note(self.history.warning, "failure")  # nor trimmed
        self.query_one(Transcript).note(_HOW_TO_LEAVE)
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

    def on_composer_paged(self, message: Composer.Paged) -> None:
        """PageUp or PageDown in the composer: the conversation scrolls a page, at once as the
        composer's own cursor does, and the focus stays where it is. Scrolling up releases the
        transcript's anchor, so it stops following new output; scrolling back to its end anchors
        it again: what the mouse wheel does, since both go through `scroll_to`."""
        self.query_one(Transcript).page(up=message.up)

    def palette_entries(self) -> Sequence[PaletteEntry]:
        """What the command palette lists: the commands rows offer now, `/help`, `/exit`."""
        return frame.palette_entries(self.frame.offered_commands())

    def on_text_area_changed(self, message: TextArea.Changed) -> None:
        """The composer's text changed: the list of commands follows it (opening with the
        entries read now, once, while no question is up)."""
        if isinstance(message.text_area, Composer):
            self._follow_composer()

    def _follow_composer(self) -> None:
        """The list follows the composer's text, but stays shut while a question is up and
        while the text is a line recalled from the history (Up and Down are then the history's)."""
        composer = self.query_one(Composer)
        self.query_one(Completions).update_for(
            composer.text, self.palette_entries, allowed=self._asking is None and not composer.recalled
        )

    def on_descendant_blur(self, event: events.DescendantBlur) -> None:
        """The composer lost focus (the palette, a question): the list closes."""
        if isinstance(event.widget, Composer):
            self.query_one(Completions).close()

    def on_composer_chose(self, message: Composer.Chose) -> None:
        """Enter took an entry of the list: it runs, or finishes its arguments in the composer."""
        self._take(message.entry)

    def on_option_list_option_selected(self, message: OptionList.OptionSelected) -> None:
        """A click on a row of the list takes it, as Enter on it would."""
        listed = message.option_list
        if isinstance(listed, Completions) and (entry := listed.entry_at(message.option_index)) is not None:
            self._take(entry)

    def _take(self, entry: PaletteEntry) -> None:
        """Choose an entry of the list: one that runs replaces the line it completed."""
        if not entry.takes_arguments:
            self.query_one(Composer).clear()
        self.choose(entry)

    def choose(self, entry: PaletteEntry) -> None:
        """Run a palette entry (it joins the lines Up recalls); one that takes arguments goes in
        the composer to finish."""
        composer = self.query_one(Composer)
        if not entry.takes_arguments:
            composer.remember(entry.call)
            self.send(entry.call)
            return
        composer.text = f"{entry.call} "
        composer.move_cursor(composer.document.end)
        composer.focus()

    def action_command_palette(self) -> None:
        """Ctrl-P: the palette, except while a question waits for its answer."""
        if self._asking is None:
            self.query_one(Completions).close()  # the palette is a screen of its own: no blur
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
        """Redraw the status bar when a status field changed; commands need no redraw (the
        palette reads them each time it opens, and the composer's list once per opening: a
        command registered or removed while it is open shows at the next, and choosing one that
        has gone is answered as an unknown command)."""
        if message.what == "status":
            self.query_one(StatusBar).show_fields(self.frame.forms())

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
            self.query_one(Completions).close()
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

    def action_interrupt(self) -> None:
        """Ctrl-C: copy the text that is selected, if any, and stop nothing (`_copy_selection`);
        otherwise stop the running turn (`_stop`)."""
        if not self._copy_selection():
            self._stop()

    def _copy_selection(self) -> bool:
        """Copy the text selected now, clear the selection (or a second Ctrl-C would copy it
        again and never stop anything), and say whether there was any. It is the composer's own
        selection when the composer has the focus and some, else the screen's (the transcript's,
        which Textual keeps). Never while a question is up: Ctrl-C then answers it no, as ever."""
        if self._asking is not None:
            return False
        composer = self.query_one(Composer)
        selected = composer.selected_text if self.focused is composer else ""
        if selected:
            composer.move_cursor(composer.cursor_location)  # the cursor alone: nothing selected
        elif selected := self.screen.get_selected_text() or "":
            self.screen.clear_selection()
        else:
            return False
        self.copy_to_clipboard(selected)
        return True

    def copy_to_clipboard(self, text: str) -> None:
        """Copy `text` to the terminal's clipboard (Textual writes OSC 52, which a terminal may
        ignore, and keeps its own record in `clipboard`) and say how much in one line. Every
        copy comes through here, Textual's own too (Cmd-C, a cut or a copy in the composer),
        so each says the same. A toast, not a line of the conversation: one there would split
        a reply that is still streaming."""
        super().copy_to_clipboard(text)
        self.notify(render.copied_line(text), timeout=_TOLD_FOR, markup=False)

    def on_text_selected(self, event: events.TextSelected) -> None:
        """A mouse selection ended (the screen says so at every mouse up, a click included):
        what is selected is copied at once. A click, or one character, copies nothing and says
        nothing. The selection stays shown."""
        if len(text := self.screen.get_selected_text() or "") >= _COPY_ON_SELECT:
            self.copy_to_clipboard(text)

    def action_copy_reply(self) -> None:
        """Ctrl-T: copy the newest reply's text whole (`Transcript.reply`), or say there is none."""
        if (text := self.query_one(Transcript).reply()) is None:
            self.notify(_NOTHING_TO_COPY, timeout=_TOLD_FOR, markup=False)
        else:
            self.copy_to_clipboard(text)

    def _stop(self) -> None:
        """Stop the running turn and take its questions down as a no; with nothing
        running, say how to leave; while a command runs, say that Ctrl-C doesn't stop it. A
        sub-agent's question is never answered here: the stopped reply withdraws its foreground
        child's, and a background child's stays queued (the reply it stops is not its own).

        A turn that hears Ctrl-C is cancelled, which cancels the questions it is waiting on,
        and those come down as withdrawn: answering them no first would let the turn carry on
        with the answer before it hears the interrupt. Any question still open a moment later
        (asked from outside a turn) is answered no; one with no turn to stop, at once. A Ctrl-C
        the bridge holds for the line being handled is a turn's that is starting, which hears it
        at once, or a command's, which never does: still held a moment later, it is the second.
        """
        questions = self._open_questions()
        stopped = self.bridge.interrupt()
        if stopped and questions:
            self.set_timer(_WITHDRAW_GRACE, functools.partial(self._decline, questions))
        elif questions:
            self._decline(questions)
        elif not stopped:
            self.query_one(Transcript).note(f"Nothing is running. {_HOW_TO_LEAVE}")
        elif self.bridge.interrupt_held:
            self.set_timer(_UNHEARD_GRACE, self._unheard)

    def action_stop_reply(self) -> None:
        """Esc: stop the running reply exactly as Ctrl-C does (`_stop`), though never to copy. With no
        reply running it does nothing, and says nothing: Esc is pressed out of habit, and the
        composer is not its business. It reaches here only when the list of commands, a question
        and the palette have passed on it."""
        if self.bridge.turn_running:
            self._stop()

    def _unheard(self) -> None:
        """A Ctrl-C held for the line being handled went unheard: a command is running (no turn
        took it), which Ctrl-C does not stop; say so, and how to leave."""
        if self.bridge.interrupt_held and not self.bridge.turn_running and not self.bridge.ended:
            self.query_one(Transcript).note(_COMMAND_RUNS)

    def _open_questions(self) -> list[asyncio.Future[bool]]:
        """Every question not yet answered that Ctrl-C answers no: the one up, then the queued
        ones, but a sub-agent's."""
        shown = [(self._asking[0].request, self._asking[1])] if self._asking is not None else []
        return [
            answer
            for request, answer in [*shown, *self._queued]
            if not answer.done() and not render.asked_by_a_sub_agent(request)
        ]

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
    which is a pty's end of file (a key waiting shows as bytes to read). On Linux, asking how
    much is waiting fails (EIO) once the terminal's other end has closed: that is hung up too."""
    ready, _, _ = select.select([fd], [], [], 0)
    if not ready:
        return False
    try:
        waiting = struct.unpack("i", fcntl.ioctl(fd, termios.FIONREAD, b"\0\0\0\0"))[0]
    except OSError:
        return True
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
