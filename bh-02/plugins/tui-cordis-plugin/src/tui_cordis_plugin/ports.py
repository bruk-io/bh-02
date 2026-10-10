"""The app's ports: `input` and `output` (CONTRACTS.md), and `frame`, where rows push status.

`Bridge` is what the app and the ports share: lines the person typed, Ctrl-C, pending
questions, and whether the app has ended. Ctrl-C is never dropped while bh-02 is busy with a
line: between a line being handed out and the turn it starts listening for Ctrl-C (or while a
command runs: a slash command, a `!` one), one interrupt is held for the next `interrupted()`,
and the next `read()` drops it (a command is not interrupted, and a held Ctrl-C must not kill
the next turn); the app says so when a held one is still unheard a moment later
(`interrupt_held`: a command is running, not a turn starting).

A line typed while nobody reads (the chat row is down because a row it depends on is coming
back up: `/model` restarts the model, `/clear` the loop and its transcript, each of which
may take a moment) waits
in the bridge for the next `read()`. The bridge hears which rows are coming up (the output's
lifecycle), so the app can say the line is waiting and for what (`waiting_on`).

A command that restarts rows queues the restart in `jobs`, and the chat row reads its next line
only once that is done (CONTRACTS.md: jobs), so a line typed right after `/model` waits in the
bridge for the new model rather than going to the old one. The command says which rows in its
answer (a `restarting` event), which the output hands the bridge (`announce`) only so a line
kept meanwhile can say what it waits for; it holds nothing back, and is forgotten at the next
read.

Whatever ends the app (Ctrl-Q, `/exit`, a crash) ends the bridge, and that settles everything
waiting on it: a pending `read()` returns None (or raises `AppCrashed` after a crash, so the
failure reaches the command line through the chat row's `done`), `interrupted()` and `closed()`
waiters return (a command running is cancelled on `closed()`, so bh-02 leaves at once), and a
pending question is answered no.

The ports never touch a widget: they post a message (`messages.py`) and the app draws it.
"""

import asyncio
import functools
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol

from textual.message import Message

from tui_cordis_plugin import frame, render
from tui_cordis_plugin.messages import (
    Asked,
    FrameChanged,
    Noted,
    Shown,
    TurnEnded,
    TurnStarted,
)

__all__ = ["AppCrashed", "Bridge", "Frame", "TuiInput", "TuiOutput"]

type Post = Callable[[Message], bool]
type Remover = Callable[[], None]


class AppCrashed(Exception):
    """The app ended on an error. Shaped as a recoverable failure (`kind`, `message`), so the
    command line reports it in one line; Textual prints the traceback itself once the
    terminal is restored."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.kind = "ui_crashed"
        self.message = message


class Bridge:
    """The state the app and its ports share, on one event loop."""

    def __init__(self) -> None:
        self._lines: deque[str] = deque()
        self._readers: deque[asyncio.Future[str | None]] = deque()
        self._interrupts: set[asyncio.Future[None]] = set()
        self._questions: set[asyncio.Future[bool]] = set()
        self._ended = False
        self._closed = asyncio.Event()  # set with `_ended`, for those awaiting it (`closed()`)
        self._crash: AppCrashed | None = None
        self._draws: set[asyncio.Future[None]] = set()  # batches posted and not yet drawn
        self._busy = False  # a line was handed out and nobody has read since
        self._interrupt_held = False  # a Ctrl-C that came while busy with no turn listening yet
        self._starting: frozenset[str] = frozenset()  # rows coming (back) up, by lifecycle
        self._keyless = frame.Keyless()  # rows that bind no key: no line waits on them
        self._unnoted = False  # a line was kept while no row was coming up: it has not said it waits
        self._announced: frozenset[str] = frozenset()  # rows a command said it restarts, until a read

    @property
    def ended(self) -> bool:
        return self._ended

    @property
    def crash(self) -> AppCrashed | None:
        """Why the app ended, if it crashed."""
        return self._crash

    @property
    def interrupt_held(self) -> bool:
        """Whether a Ctrl-C is waiting for the turn a line is about to start."""
        return self._interrupt_held

    @property
    def turn_running(self) -> bool:
        """Whether a turn is waiting to hear about Ctrl-C (CONTRACTS.md: input.interrupted)."""
        return any(not w.done() for w in self._interrupts)

    @property
    def kept(self) -> tuple[str, ...]:
        """The lines typed that nobody has read yet, oldest first."""
        return tuple(self._lines)

    @property
    def waiting_on(self) -> frozenset[str]:
        """The rows a line kept for later waits on: those a command announced it restarts
        (the chat row reads again once they are: `jobs`); else, with nothing in hand (no turn
        running, no line being handled, such as a slash command), those coming (back) up, as
        the chat row is down with them, except a row that binds no key (a status-bar row such
        as `status`): the chat row depends on none of them. A line typed during a turn or a
        command waits for it, as it always has, and does not name a row reloading meanwhile
        that it does not wait on."""
        if self.turn_running:
            return frozenset()
        if self._announced:
            return self._announced
        return frozenset() if self._busy else self._starting - self._keyless.unwaited

    def row_changed(self, kind: str, row: str) -> frozenset[str]:
        """Hear one lifecycle event (cordis's `kind` of row `row`): which rows are coming up.

        Return the rows a kept line now waits on when it has not said so yet, else nothing: a
        line typed between a restarted row's old fiber going `inactive` and its new one's
        `reload` (`/clear`, `/restart`) was kept with no row coming up, and says it waits here.
        """
        self._starting = frame.starting_after(self._starting, kind, row)
        self._keyless = frame.keyless_after(self._keyless, kind, row)
        return self._to_note()

    def announce(self, rows: Iterable[str]) -> frozenset[str]:
        """A command is restarting `rows` (CONTRACTS.md: `restarting`): a line kept until the
        chat row reads again waits on them, and says so. Return the rows a line kept (while the
        command ran) now waits on, when it has not said so yet, else nothing."""
        if self._ended or not (rows := frozenset(rows) - self._announced):
            return frozenset()
        self._announced |= rows
        return self._to_note()

    def _to_note(self) -> frozenset[str]:
        """The rows a kept line that has not said it waits now waits on, or nothing (once)."""
        waiting = self.waiting_on
        if not (self._unnoted and self._lines and waiting):
            return frozenset()
        self._unnoted = False
        return waiting

    def submit(self, line: str) -> bool:
        """Hand a line to the oldest waiting reader, or keep it for the next read; say whether
        a reader took it."""
        while self._readers:
            reader = self._readers.popleft()
            if not reader.done():
                self._busy = True
                reader.set_result(line)
                return True
        self._lines.append(line)
        self._unnoted = self._unnoted or not self.waiting_on
        return False

    async def line(self) -> str | None:
        """Return the next line, None once the app has ended, or raise its crash.

        Reading is where the last line's work ended: a Ctrl-C still held is dropped, and the
        rows a command announced are up (the chat row reads only once its restarts are done).
        """
        self._interrupt_held = False
        self._announced = frozenset()
        if self._lines:
            kept = self._lines.popleft()
            self._busy = True
            self._unnoted = self._unnoted and bool(self._lines)
            return kept
        if self._ended:
            self._raise_crash()
            return None
        self._busy = False
        reader: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self._readers.append(reader)
        line = await reader
        if line is None:
            self._raise_crash()
        return line

    def interrupt(self) -> bool:
        """Ctrl-C: settle every turn waiting on it; say whether anything was running.

        A line handed out with no turn listening yet (its turn is starting, or it is a command:
        a slash command, a `!` one) is running too: the interrupt is held for the next
        `interrupted()`, and the next `read()` drops it.
        """
        waiting = [w for w in self._interrupts if not w.done()]
        for waiter in waiting:
            waiter.set_result(None)
        if waiting:
            return True
        if self._busy and not self._ended:
            self._interrupt_held = True
            return True
        return False

    async def interrupted(self) -> None:
        """Return at the next Ctrl-C (or at once for one held), or at once if the app has ended."""
        if self._ended or self._interrupt_held:
            self._interrupt_held = False
            return
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._interrupts.add(waiter)
        try:
            await waiter
        finally:
            self._interrupts.discard(waiter)

    async def closed(self) -> None:
        """Return once the app has ended (at once if it has): no more lines will come."""
        await self._closed.wait()

    def question(self) -> asyncio.Future[bool] | None:
        """A future for the answer to one question, or None when nobody is left to ask."""
        if self._ended:
            return None
        answer: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._questions.add(answer)
        answer.add_done_callback(self._questions.discard)
        return answer

    def draw(self) -> asyncio.Future[None]:
        """A future the app settles once it has drawn a batch of events: settled at once when
        the app has ended, and by `end` otherwise, so nobody waits on a screen that is gone."""
        drawn: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        if self._ended:
            drawn.set_result(None)
            return drawn
        self._draws.add(drawn)
        drawn.add_done_callback(self._draws.discard)
        return drawn

    def end(self, crash: AppCrashed | None = None) -> None:
        """The app has ended: settle every reader, turn and question waiting on it."""
        if self._ended:
            return
        self._ended, self._crash = True, crash
        self._closed.set()
        while self._readers:
            reader = self._readers.popleft()
            if not reader.done():
                reader.set_result(None)
        self.interrupt()
        for answer in list(self._questions):
            if not answer.done():
                answer.set_result(False)
        for drawn in list(self._draws):
            if not drawn.done():
                drawn.set_result(None)

    def _raise_crash(self) -> None:
        if self._crash is not None:
            raise self._crash


class _Lifecycle(Protocol):
    """What the output reads of one lifecycle event (cordis's `Event`, heard through `observe`)."""

    @property
    def kind(self) -> str: ...
    @property
    def fiber(self) -> str: ...
    @property
    def error(self) -> str | None: ...


class TuiInput:
    """Implements `input`: lines from the composer; Ctrl-C is `interrupted()`; the app ending
    (Ctrl-Q, `/exit`, a crash) is `closed()`."""

    def __init__(self, bridge: Bridge) -> None:
        self._bridge = bridge

    async def read(self) -> str | None:
        """Return the next line typed; None once the app has ended (`/exit`, Ctrl-Q)."""
        return await self._bridge.line()

    async def interrupted(self) -> None:
        """Return when the person asks to stop the turn that is running (Ctrl-C)."""
        await self._bridge.interrupted()

    async def closed(self) -> None:
        """Return once the app has ended (`/exit`, Ctrl-Q, a crash): no more lines will come."""
        await self._bridge.closed()


class _Status(Protocol):
    """Where the output pushes its `usage` field: the frame's `status`."""

    def __call__(self, field: str, text: str, /, *shorter: str) -> Remover: ...


_NOTHING_USED = frame.Usage()
# How many events gather while the app draws the last batch before reading waits for it.
_BATCH = 512


class TuiOutput:
    """Implements `output`: a turn's events, notices and questions, posted to the app.

    Usage events also add up, for the session, into the status bar's `usage` field (`status`
    is the frame's), replaced as each one streams in. `used` is where the totals start: what
    a resumed session's history already adds up to.
    """

    def __init__(
        self, post: Post, bridge: Bridge, status: _Status | None = None, used: frame.Usage = _NOTHING_USED
    ) -> None:
        self._post = post
        self._bridge = bridge
        self._status = status
        self._up: set[str] = set()  # rows seen up, so the next activation is a reload
        self._used = used
        self._usage_shown: Remover | None = None

    def usage_field(self) -> Remover:
        """Show the totals so far (if there are any) in the status bar; return what takes the
        field down, whichever push is current then. The ui row `acquire`s it."""
        if self._used != _NOTHING_USED:
            self._show_usage()
        return self._hide_usage

    def _hide_usage(self) -> None:
        if self._usage_shown is not None:
            self._usage_shown()
            self._usage_shown = None

    async def show(self, events: AsyncIterator[Mapping[str, Any]]) -> None:
        """Draw a turn as it streams in; stop reading once the app has ended.

        Events go to the app in batches, never faster than it draws them: while one batch is
        being drawn, the next gathers (and once it is large, reading waits for the app), and
        it is posted as soon as the app has drawn the last, whether or not another event comes
        (a reply that pauses mid-stream, thinking, still shows what it said so far). The
        loop is given a turn after every event, so a reply that never waits (every event at
        once) still leaves the app free to hear Ctrl-C, which cancels this mid-stream. Every
        event read is posted before the turn's end, even when the turn stops mid-stream; the
        turn's start and end are posted too (`TurnStarted`, `TurnEnded`). A
        `restarting` event (a command's answer) is handed to the bridge as it is read.
        """
        batch: list[Mapping[str, Any]] = []
        drawn: asyncio.Future[None] | None = None
        over = False
        partial = False  # whether the usage so far awaits its output count (CONTRACTS.md: usage)
        if not self._bridge.ended:
            self._post(TurnStarted())

        def flush() -> None:
            """Post what gathered, if anything, and follow the app's drawing of it."""
            nonlocal batch, drawn
            if batch and not over and not self._bridge.ended:
                drawn, batch = self._draw(batch), []
                drawn.add_done_callback(flushed)

        def flushed(future: asyncio.Future[None]) -> None:
            """The app drew a batch: post what gathered meanwhile (only for the latest batch)."""
            if future is drawn:
                flush()

        try:
            async for event in events:
                if self._bridge.ended:
                    return
                batch.append(event)
                if event.get("type") == "usage":
                    partial = bool(event.get("partial"))
                    self._add_usage(event)
                if drawn is not None and not drawn.done() and len(batch) >= _BATCH:
                    await drawn  # the app is behind: let it catch up
                if drawn is None or drawn.done():
                    flush()
                if event.get("type") == "restarting":
                    self._announce(event)
                await asyncio.sleep(0)
        finally:
            # whatever was read is drawn (and recorded), however the turn ends: finished,
            # stopped by Ctrl-C mid-stream, or a provider that raised; posting does not wait
            if batch and not self._bridge.ended:
                self._draw(batch)
            over, batch = True, []  # a draw still pending posts nothing after the turn's end
            if partial:  # stopped before its output was counted: the totals are lower bounds
                self._used = frame.output_uncounted(self._used)
                self._show_usage()
            self._post(TurnEnded())

    def _announce(self, event: Mapping[str, Any]) -> None:
        """A command is restarting rows (CONTRACTS.md: `restarting`): a line already kept says
        it waits for them."""
        rows = event.get("rows")
        if not isinstance(rows, Sequence) or isinstance(rows, str):
            return
        if waiting := self._bridge.announce(str(row) for row in rows):
            self._post(Noted(render.waiting_line(waiting)))

    def _draw(self, batch: Sequence[Mapping[str, Any]]) -> asyncio.Future[None]:
        """Post a batch of events to the app; return what it settles once they are drawn."""
        drawn = self._bridge.draw()
        self._post(Shown(*batch, drawn=drawn))
        return drawn

    def _add_usage(self, event: Mapping[str, Any]) -> None:
        """Add a usage event to the session's totals and show them."""
        self._used = frame.add_usage(self._used, event)
        self._show_usage()

    def _show_usage(self) -> None:
        """Push the totals as the `usage` field, replacing the last push."""
        if self._status is None:
            return
        shown = self._status("usage", *frame.usage_forms(self._used))
        if self._usage_shown is not None:
            self._usage_shown()
        self._usage_shown = shown

    async def notice(self, message: str) -> None:
        """Show a failure the person can recover from."""
        self._post(Noted(f"error: {message}", "failure"))

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        """Ask about a call in a modal; no once the app has ended."""
        answer = self._bridge.question()
        if answer is None:
            return False
        self._post(Asked(request, answer))
        return await answer

    def lifecycle(self, event: _Lifecycle) -> None:
        """Note a change to the running composition: a row reloaded, or one that failed; and
        tell the bridge which rows are coming up, for a line typed meanwhile."""
        if waiting := self._bridge.row_changed(event.kind, event.fiber):
            self._post(Noted(render.waiting_line(waiting)))
        line = render.lifecycle_line(event.kind, event.fiber, event.error, event.fiber in self._up)
        # A row seen active, or seen going down (it was up, perhaps before the app was there to
        # hear it: the model row depends on nothing and is up first), comes back as a reload.
        if event.kind in ("active", "unloading"):
            self._up.add(event.fiber)
        if line is not None:
            self._post(Noted(line, "failure" if line.startswith("✗") else "note"))


class Frame:
    """Implements `frame` (CONTRACTS.md): what rows push into the app's frame.

    Every push returns its remover, so a row `acquire`s it and its entry leaves with it. Two
    rows pushing the same status field: the later push shows until it is removed. A row that
    pushes a field reloads only with what it shows (the grades' row with the runner, never on
    `/clear`), so nothing here keeps a field across a reload.
    """

    def __init__(self, post: Post) -> None:
        self._post = post
        self._next = 0
        self._entries: dict[int, tuple[str, Any]] = {}  # token -> (what, value), in push order

    def status(self, field: str, text: str, *shorter: str) -> Remover:
        """Show `text` in the status bar under `field` until the remover is called.

        `shorter` are shorter forms of the same text, each shorter than the last, which the
        status bar shows instead when the line is too narrow for the fuller ones.
        """
        return self._push("status", (field, (text, *shorter)))

    def commands(self, specs: Callable[[], Sequence[Mapping[str, Any]]]) -> Remover:
        """Offer commands (`name`, `help`, `usage`) until the remover is called.

        `specs` is read each time the palette opens, so a command registered after the push
        (a row that came up later) is offered too, and no push has to be redone.
        """
        return self._push("commands", specs)

    def fields(self) -> dict[str, str]:
        """The status bar's fields as their full text, in the order first pushed; the latest
        push per field wins."""
        return {field: forms[0] for field, forms in self.forms().items()}

    def forms(self) -> dict[str, tuple[str, ...]]:
        """Each status field's forms, the full text first then any shorter ones; as `fields`."""
        shown: dict[str, tuple[str, ...]] = {}
        for field, forms in self._pushed("status"):
            shown[field] = forms
        return shown

    def offered_commands(self) -> list[Mapping[str, Any]]:
        """Every command spec offered now, in push order (each source read afresh)."""
        return [spec for specs in self._pushed("commands") for spec in specs()]

    def _pushed(self, what: str) -> list[Any]:
        return [value for kind, value in self._entries.values() if kind == what]

    def _push(self, what: str, value: Any) -> Remover:
        token, self._next = self._next, self._next + 1
        self._entries[token] = (what, value)
        self._post(FrameChanged(what))
        return functools.partial(self._remove, token)

    def _remove(self, token: int) -> None:
        """Drop an entry."""
        if (entry := self._entries.pop(token, None)) is None:
            return
        self._post(FrameChanged(entry[0]))
