"""The real `bh-02` console script in a pseudo-terminal: the app draws, keys go in, it exits.

`run_test()` takes a different path through Textual than a real launch (a stylesheet token
that only a real launch parses, a terminal left in raw mode, a child process painting over
the screen), so these start the installed script the way a person does. The model is a fake
from `bh_02.testing`, so no credential is needed: a `loop` fake, named by a `--patch` layer,
replaces the whole loop; a fake model (`fake`, `slow`, `inputs`, a models file's entries naming
a `bh_02.testing` provider) is chosen with `--model` under the shipped loop and model row, so
`/model` switches between them as it would between Claude and an OpenAI model. The kernel runs
unjailed so the tests don't depend on the platform. Deselect with `-m "not real_launch"`.
"""

import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from models_cordis_plugin.openai.testing import StubServer
from tui_cordis_plugin import bh01_theme
from tui_cordis_plugin.widgets import GRACE

pytestmark = pytest.mark.real_launch

_SCRIPT = Path(sys.executable).parent / "bh-02"
_ROWS, _COLS = 36, 120
# CSI (with private markers such as `?` and `<`), OSC, and two-byte escapes.
_ESCAPES = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
_READY = "Ctrl-Q, /exit or /quit leaves"


class Launched:
    """The script on a pty of its own: what it has written so far, as text, and a way in."""

    def __init__(
        self,
        args: list[str],
        cwd: Path,
        state: Path,
        *,
        cols: int = _COLS,
        truecolor: bool = False,
        config: Path | None = None,
    ) -> None:
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", _ROWS, cols, 0, 0))
        env = {**os.environ, "TERM": "xterm-256color", "XDG_STATE_HOME": str(state)}
        # a models file of the test's own, never the person's ~/.config/bh-02/models.toml
        env["XDG_CONFIG_HOME"] = str(config or state.parent / "config")
        env.pop("COLORTERM", None)
        if truecolor:  # Textual then writes the theme's own colours, not the nearest of 256
            env["COLORTERM"] = "truecolor"
        self.process = subprocess.Popen(
            [str(_SCRIPT), *args],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        os.close(slave)
        self._master = master
        self._written = b""

    def written(self) -> bytes:
        """Everything written so far, escapes included."""
        return self._written

    def text(self) -> str:
        """Everything written so far, escapes removed (so a styled run of text reads plain)."""
        return _ESCAPES.sub(b"", self._written).decode(errors="replace")

    def wait_for(self, token: str, timeout: float = 30.0, *, after: int = 0) -> int:
        """Wait until `token` is written (at or past offset `after`); return where it ends."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._pump(0.1)
            found = self.text().find(token, after)
            if found >= 0:
                return found + len(token)
            if self.process.poll() is not None:
                self._pump(0.2)
                break
        found = self.text().find(token, after)
        assert found >= 0, f"{token!r} never appeared; the screen said:\n{self.text()[-3000:]}"
        return found + len(token)

    def type(self, text: str) -> None:
        """Type `text` and press Enter."""
        self.press(text.encode())
        self._pump(0.2)
        self.press(b"\r")

    def press(self, keys: bytes) -> None:
        os.write(self._master, keys)

    def answer(self, key: bytes) -> None:
        """Answer the question just put up: once it takes answers (it drops keys for a moment
        after it is shown, so ones typed ahead answer nothing), press `key`."""
        self.settle(GRACE + 0.3)
        self.press(key)

    def settle(self, seconds: float = 0.3) -> None:
        """Keep reading for `seconds`, so the app has drawn what the last key changed."""
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            self._pump(left)  # returns as soon as anything is written

    def exit_code(self, timeout: float = 20.0) -> int:
        deadline = time.monotonic() + timeout
        while self.process.poll() is None and time.monotonic() < deadline:
            self._pump(0.1)
        self._pump(0.3)
        assert self.process.returncode is not None, f"still running; the screen said:\n{self.text()[-3000:]}"
        return self.process.returncode

    def resize(self, cols: int) -> None:
        """Make the terminal `cols` wide, as dragging its window's edge does. The script runs in
        a session of its own, so the terminal is not its controlling one and the kernel signals
        nobody: SIGWINCH is sent here, and the app reads the new size from the terminal."""
        fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", _ROWS, cols, 0, 0))
        os.kill(self.process.pid, signal.SIGWINCH)

    def hang_up(self) -> None:
        """Close the terminal, as closing its window does."""
        os.close(self._master)
        self._master = -1

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        if self._master >= 0:
            os.close(self._master)

    def _pump(self, wait: float) -> None:
        if self._master < 0:
            time.sleep(wait)
            return
        ready, _, _ = select.select([self._master], [], [], wait)
        while ready:
            try:
                chunk = os.read(self._master, 65536)
            except OSError:  # the other end closed
                return
            if not chunk:
                return
            self._written += chunk
            ready, _, _ = select.select([self._master], [], [], 0)


type Launch = Callable[..., Launched]


def _sgr(layer: str, token: str) -> bytes:
    """The truecolor escape for a dark-theme token as the generated theme has it now (`38`
    foreground, `48` background), so a new bh-01 palette changes this test with the theme."""
    rgb = bh01_theme.DARK_VARIABLES[token].removeprefix("#")
    red, green, blue = (int(rgb[n : n + 2], 16) for n in (0, 2, 4))
    return f"{layer};2;{red};{green};{blue}".encode()


# The fake models every launch can name (`--model`, `/model`), in the test's own models file.
_MODELS = {
    "fake": "echo_provider",
    "fake-2": "echo_provider",
    "slow": "slow_provider",
    "slow-2": "slow_provider",
    "inputs": "repl_provider",
}


def _models_file(config: Path, more: str = "") -> None:
    """The test's models file: every fake model, and `more` (a stub server's model)."""
    tables = [
        f'[{name}]\nprovider = "bh_02.testing:{provider}"\nid = "{name}"\n'
        for name, provider in _MODELS.items()
    ]
    (config / "bh-02").mkdir(parents=True, exist_ok=True)
    (config / "bh-02" / "models.toml").write_text("\n".join([*tables, more]))


@pytest.fixture
def launch(tmp_path: Path) -> Iterator[Launch]:
    """Launch `bh-02 --no-jail`, in a temporary project, state and config dir, on a fake: a
    fake model by name (`fake`, `slow`, `inputs`: `--model NAME`), or a `loop` fake from
    `bh_02.testing` (`echo`, `showcase`, ...: `--patch`, over the `fake` model)."""
    work, state, config = tmp_path / "work", tmp_path / "state", tmp_path / "config"
    work.mkdir()
    _models_file(config)
    started: list[Launched] = []

    def start(model: str, *args: str, cols: int = _COLS, truecolor: bool = False) -> Launched:
        chosen = ["--model", model if model in _MODELS else "fake"]
        if model not in _MODELS:
            patch = tmp_path / f"{model}.toml"
            patch.write_text(f'[[plugin]]\nid = "loop"\nuse = "bh_02.testing:{model}"\n')
            chosen += ["--patch", str(patch)]
        jail = [] if "--resume" in args else ["--no-jail"]  # a resumed session keeps its own
        app = Launched([*jail, *chosen, *args], work, state, cols=cols, truecolor=truecolor, config=config)
        started.append(app)
        return app

    yield start
    for app in started:
        app.close()


def test_a_message_gets_its_reply_ctrl_c_only_explains_and_ctrl_q_leaves(launch: Launch) -> None:
    app = launch("echo")
    ready = app.wait_for(_READY, 60)
    app.wait_for("jail: unjailed", after=0)  # the status row pushed into the status bar
    app.type("hello there")
    replied = app.wait_for("echo: HELLO THERE", after=ready)
    app.press(b"\x03")  # Ctrl-C with no turn running: a note, not an exit
    app.wait_for("Nothing is running.", after=replied)
    assert app.process.poll() is None
    app.press(b"\x11")  # Ctrl-Q
    assert app.exit_code() == 0
    assert "(uv run bh-02 --resume to continue it)" in app.text()


def test_the_transcript_draws_every_kind_of_event_and_a_long_reply(launch: Launch) -> None:
    app = launch("showcase")
    ready = app.wait_for(_READY, 60)
    app.type("tour")
    stopped = app.wait_for("stopped: max_tokens", after=ready)
    # each is drawn by the frame after it arrives, which may come after the stop's
    for part in (
        "A tour",
        "print(n)",
        "⏺ python",
        "+    return 'hello'",
        "NameError: x",
        "1,234 in · 56 out",
    ):
        stopped = max(stopped, app.wait_for(part, 10, after=ready))
    app.wait_for("thinking · 2 lines", after=ready)  # folded away once the reply moved on
    started = time.monotonic()
    app.type("lines 2000")
    app.wait_for("line 1999 of the long reply", 60, after=stopped)
    app.type("/exit")  # and it still answers the keyboard
    assert app.exit_code() == 0
    assert time.monotonic() - started < 60


def test_a_resumed_session_shows_what_was_said(launch: Launch) -> None:
    first = launch("echo")
    ready = first.wait_for(_READY, 60)
    first.type("hello there")
    first.wait_for("echo: HELLO THERE", after=ready)
    first.press(b"\x11")
    assert first.exit_code() == 0
    again = launch("echo", "--resume")
    ready = again.wait_for(_READY, 60)
    before = again.text()[:ready]  # drawn before the app said how to leave: the history
    assert "hello there" in before and "echo: HELLO THERE" in before
    assert "the session so far" in before
    again.type("/exit")
    assert again.exit_code() == 0


def _children(pid: int) -> list[int]:
    listed = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False)
    return [int(line) for line in listed.stdout.split()]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _ends_and_takes_its_children(app: Launched, children: list[int]) -> int:
    """Wait for bh-02 to leave on its own (not killed by a signal) and its kernel to be gone."""
    deadline = time.monotonic() + 10
    while (app.process.poll() is None or any(map(_alive, children))) and time.monotonic() < deadline:
        app.settle(0.1)
    code = app.process.returncode
    assert code is not None and code >= 0, f"still running, or killed ({code}):\n{app.text()[-2000:]}"
    assert not [pid for pid in children if _alive(pid)], "the kernel outlived bh-02"
    return code


def test_the_terminal_going_away_leaves_and_ends_the_kernel(launch: Launch) -> None:
    """A pty with no controlling terminal: no SIGHUP, only stdin at end of file (which Textual's
    input thread would otherwise read again and again, at 100% CPU, for ever)."""
    app = launch("echo")
    app.wait_for(_READY, 60)
    children = _children(app.process.pid)
    assert children  # the kernel
    app.hang_up()
    # 120: Python could not flush its output at exit, to a terminal that is gone
    assert _ends_and_takes_its_children(app, children) in (0, 120)


def test_a_hangup_signal_leaves_and_ends_the_kernel(launch: Launch) -> None:
    app = launch("echo")
    app.wait_for(_READY, 60)
    children = _children(app.process.pid)
    assert children  # the kernel
    app.process.send_signal(signal.SIGHUP)
    assert _ends_and_takes_its_children(app, children) == 0


def test_exit_in_the_composer_leaves_cleanly(launch: Launch) -> None:
    app = launch("echo")
    app.wait_for(_READY, 60)
    app.type("/exit")
    assert app.exit_code() == 0


def test_a_crash_in_the_app_is_reported_after_the_terminal_is_restored(launch: Launch) -> None:
    app = launch("bomb")
    ready = app.wait_for(_READY, 60)
    app.type("boom")
    assert app.exit_code() == 1
    after = app.text()[ready:]
    assert "RuntimeError" in after and "cannot be drawn" in after  # Textual's traceback
    assert "error: the app crashed (exit code 1)" in after  # and bh-02's one line, after it


def test_an_input_asks_in_a_modal_and_its_output_comes_back(launch: Launch) -> None:
    app = launch("inputs")
    ready = app.wait_for(_READY, 60)
    app.type("print(6 * 7)")
    asked = app.wait_for("Run this python code (1 line)?", after=ready)
    app.answer(b"y")
    answered = app.wait_for("the input said: 42", after=asked)
    app.type("import time; time.sleep(30)")
    asked = app.wait_for("Run this python code (1 line)?", after=answered)
    app.answer(b"y")
    app.wait_for("⏺ python", after=asked)
    app.press(b"\x03")  # Ctrl-C while the input runs: the turn stops, the app stays
    app.wait_for("stopped: interrupted", 10, after=asked)
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_an_unjailed_input_runs_on_a_yes_and_not_at_all_on_a_no(launch: Launch, tmp_path: Path) -> None:
    """`--no-jail`: every input is put to the person with its code and the keys drawn; a yes runs
    it (it writes a file in the project with plain Python), a no runs nothing."""
    app = launch("inputs")
    ready = app.wait_for(_READY, 60)
    app.type("open('y.txt', 'w').write('yes')")
    asked = app.wait_for("Run this python code (1 line)?", 10, after=ready)
    app.wait_for("y  allow     n / Esc  decline", 10, after=asked)
    app.answer(b"y")
    answered = app.wait_for("the input said: 3", 10, after=asked)
    app.type("open('n.txt', 'w').write('no')")
    asked = app.wait_for("Run this python code (1 line)?", 10, after=answered)
    app.wait_for("y  allow     n / Esc  decline", 10, after=asked)
    app.answer(b"n")
    app.wait_for("the input said: denied: the person said no to this input", 10, after=asked)
    work = tmp_path / "work"
    assert (work / "y.txt").read_text() == "yes" and not (work / "n.txt").exists()
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_keys_typed_as_the_modal_comes_up_do_not_answer_it(launch: Launch, tmp_path: Path) -> None:
    """A person still typing when an input is put to them ("Run n..."): the `n` must not decline
    it, and none of it lands in the composer; the modal answers once it has been up a moment."""
    app = launch("inputs")
    ready = app.wait_for(_READY, 60)
    app.type("open('ahead.txt', 'w').write('ran')")
    asked = app.wait_for("Run this python code (1 line)?", 10, after=ready)
    app.press(b"Run n")  # at once: the modal is on screen, but has only just come up
    app.press(b"\x1b")  # Escape, too
    app.settle(GRACE + 0.5)
    assert "denied" not in app.text()[asked:]  # nothing answered it
    app.press(b"y")
    app.wait_for("the input said: 3", 10, after=asked)
    assert (tmp_path / "work" / "ahead.txt").read_text() == "ran"
    answered = len(app.text())
    app.type("print('next')")  # the composer is empty: this is the whole of the next message
    app.wait_for("Run this python code (1 line)?", 10, after=answered)
    assert "Run nprint" not in app.text()[answered:]
    app.answer(b"y")
    app.wait_for("the input said: next", 10, after=answered)
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_a_layer_that_cannot_be_reloaded_is_reported_after_the_app_exits(
    launch: Launch, tmp_path: Path
) -> None:
    """The report would paint over the app: it goes to the trace file now, and to the
    terminal once the app has given it back."""
    trace = tmp_path / "trace.log"
    app = launch("echo", "--trace", str(trace))
    app.wait_for(_READY, 60)
    (tmp_path / "echo.toml").write_text("[[plugin]\n")  # the patch the fixture wrote, broken
    deadline = time.monotonic() + 10
    while "report: reload failed" not in trace.read_text() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert "report: reload failed: TOMLDecodeError" in trace.read_text()
    app.press(b"\x11")
    assert app.exit_code() == 0
    assert "error: reload failed: TOMLDecodeError" in app.text()
    # everything the terminal was sent: the report shows once, and that is after the app left
    assert app.text().count("reload failed") == 1, app.text()[-2000:]


def test_the_screen_is_drawn_in_bh_01_s_dark_theme(launch: Launch) -> None:
    """The generated theme survives a real launch's stylesheet parse and is what is drawn."""
    app = launch("echo", truecolor=True)
    app.wait_for(_READY, 60)
    app.wait_for("jail: unjailed")
    written = app.written()
    assert _sgr("48", "bh-bg") in written  # behind everything
    assert _sgr("38", "bh-ring") in written  # mandarin: the focused composer's border
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_the_palette_runs_a_command_and_the_status_bar_follows_the_model(launch: Launch) -> None:
    """Ctrl-P lists the commands broker's commands on the real screen; choosing one runs it
    through the input, and it offers `/model NAME` for each model. The status bar's model field
    reads the session's layer, and a `/model` (which rewrites that layer and reloads the model
    row) shows the new one."""
    app = launch("fake")
    ready = app.wait_for(_READY, 60)
    app.wait_for("model: fake", after=0)
    app.press(b"\x10")  # Ctrl-P
    opened = app.wait_for("/restart", after=ready)  # an operator command, offered in the palette
    app.type("rows")  # the palette's search, then Enter on the hit
    ran = app.wait_for("tui:palette", after=opened)  # /rows's table names the palette's own row
    app.press(b"\x10")  # Ctrl-P again: a model by name is an entry of its own
    offered = app.wait_for("/model fake-2", after=ran)
    app.type("fake-2")  # the palette's search: the one entry that runs it
    app.wait_for("model: fake-2", 20, after=offered)
    app.type("hello")
    app.wait_for("[fake-2] echo: HELLO", 20, after=offered)
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_a_patch_that_cannot_be_read_is_one_line_not_a_traceback(launch: Launch, tmp_path: Path) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("[[plugin]\n")
    app = launch("echo", "--patch", str(broken))
    assert app.exit_code() == 1
    assert f"error: {broken}: Expected ']]'" in app.text() and "fix the file or drop it" in app.text()
    assert "Traceback" not in app.text()


def test_ctrl_c_with_the_modal_up_declines_and_stops_the_turn(launch: Launch, tmp_path: Path) -> None:
    """Ctrl-C while an input waits for approval: the modal comes down as a no, the turn stops, the
    transcript tells the model the input never ran, and the next turn runs as usual. (The Ctrl-C
    held between a line and its turn is a race a pty cannot aim at; the bridge's and Pilot tests
    pin it.)"""
    app = launch("inputs")
    ready = app.wait_for(_READY, 60)
    app.type("import time; time.sleep(30)")
    asked = app.wait_for("Ctrl-C  stop the turn", 10, after=ready)
    app.press(b"\x03")
    stopped = app.wait_for("stopped: interrupted", 10, after=asked)
    assert "Nothing is running." not in app.text()[ready:]
    app.type("print(6 * 7)")
    app.wait_for("Run this python code (1 line)?", 10, after=stopped)
    app.answer(b"y")
    app.wait_for("the input said: 42", 10, after=stopped)
    app.press(b"\x11")
    assert app.exit_code() == 0
    (transcript,) = (tmp_path / "state").glob("bh-02/sessions/*/transcript.jsonl")
    results = [
        m["content"] for m in map(json.loads, transcript.read_text().splitlines()) if m["role"] == "tool"
    ]
    assert results[0].startswith("not run: the person stopped the turn before this call started")
    assert results[1] == "42"


def test_a_narrow_screen_keeps_every_jail_grade_named(launch: Launch) -> None:
    app = launch("echo", cols=90)
    app.wait_for(_READY, 60)
    app.wait_for("jail: unjailed fs_write ✗ network ✗ fs_read ✗ env ✗")  # every grade, named
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_ctrl_c_stops_a_reply_mid_stream_whether_it_comes_paced_or_all_at_once(launch: Launch) -> None:
    """A paced reply stops at once; a burst (every event at once, a reply that never waits)
    stops too, instead of the key waiting behind the whole reply being drawn."""
    app = launch("showcase")
    ready = app.wait_for(_READY, 60)
    app.type("slow 400")
    begun = app.wait_for("slow 3", 10, after=ready)
    app.press(b"\x03")
    stopped = app.wait_for("stopped: interrupted", 5, after=begun)
    assert "slow 399" not in app.text()
    app.type("lines 100000")
    begun = app.wait_for("of the long reply", 20, after=stopped)  # which line is up to the frame
    app.press(b"\x03")
    stopped = app.wait_for("stopped: interrupted", 10, after=begun)
    assert "line 99999 of the" not in app.text()
    assert "Nothing is running." not in app.text()[ready:]
    app.type("tour")  # and the next turn streams as usual
    app.wait_for("stopped: max_tokens", 10, after=stopped)
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_at_80_columns_the_status_bar_shows_session_model_jail_and_usage(launch: Launch) -> None:
    app = launch("showcase", cols=80)
    ready = app.wait_for(_READY, 60)
    app.type("tour")
    app.wait_for("stopped: max_tokens", 10, after=ready)
    app.wait_for("usage: 1.2k/56 $0.01", 10, after=ready)
    screen = app.text()
    last = screen[screen.rfind("session: ") :]
    assert "model: fake" in last and "jail: unjailed w✗n✗r✗e✗" in last  # a short model: room for the axes
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_a_resumed_session_s_usage_adds_to_what_it_had(launch: Launch) -> None:
    first = launch("showcase")
    ready = first.wait_for(_READY, 60)
    first.type("tour")
    first.wait_for("stopped: max_tokens", 10, after=ready)
    first.press(b"\x11")
    assert first.exit_code() == 0
    again = launch("showcase", "--resume")
    ready = again.wait_for(_READY, 60)
    again.wait_for("usage: 1.2k/56 $0.01", 10)  # the session's so far, before any turn
    again.type("tour")
    again.wait_for("usage: 2.5k/112 $0.02", 10, after=ready)
    screen = again.text()
    last = screen[screen.rfind("session: ") :]
    assert " ↻ │ model: fake" in last  # at 120 columns: resumed, and the grades keep their axes
    assert "jail: unjailed fs_write ✗ network ✗ fs_read ✗ env ✗ │ usage" in last
    again.press(b"\x11")
    assert again.exit_code() == 0


def test_clear_clears_the_screen_and_model_does_not(launch: Launch) -> None:
    """`/clear` answers `cleared` (CONTRACTS.md: event): the old turns leave the screen and one
    note says why. `/model` keeps them. What was written stays in the pty's stream, so each
    check reads what follows a resize of the terminal, which makes the app draw the transcript
    again at its new width: only what the transcript holds then."""
    app = launch("fake")
    ready = app.wait_for(_READY, 60)
    app.type("hello there")
    replied = app.wait_for("echo: HELLO THERE (message 1)", after=ready)
    app.type("/model fake-2")
    app.wait_for("↻ chat reloaded", 20, after=replied)
    app.settle(1.0)
    narrowed = len(app.text())
    app.resize(_COLS - 20)
    app.wait_for("echo: HELLO THERE", 10, after=narrowed)  # /model: the conversation is still shown
    app.type("/clear")
    cleared = app.wait_for(
        "the conversation was cleared; starting afresh: loop, transcript, kernel", 10, after=narrowed
    )
    app.wait_for("↻ status reloaded", 20, after=cleared)  # the last row /clear restarts
    app.settle(1.0)
    app.type("again")  # the model's transcript was forgotten too: this is its first message
    app.wait_for("echo: AGAIN (message 1)", 20, after=cleared)
    # the kernel's restart reloads status: the jail field keeps its text meanwhile
    bars = re.findall(r"session: [^\n]*", app.text()[narrowed:])  # every status bar drawn since
    assert bars and all("jail: unjailed" in bar for bar in bars)
    widened = len(app.text())
    app.resize(_COLS)  # drawn again
    top = app.wait_for("the conversation was cleared", 10, after=widened)  # its first block now
    app.wait_for("↻ status reloaded", 10, after=top)  # to its last: the whole transcript
    app.settle()
    assert "HELLO THERE" not in app.text()[cleared:]
    app.press(b"\x11")
    assert app.exit_code() == 0
    again = launch("fake", "--resume")  # a resume draws from the clear on
    ready = again.wait_for(_READY, 60)
    screen = again.text()
    # (the `cleared` note itself is above the fold by now, under the restarts' notes)
    assert "echo: AGAIN (message 1)" in screen and "HELLO THERE" not in screen, screen[-4000:]
    again.type("more")  # and sends the model its transcript since the clear: `again`, then this
    again.wait_for("echo: MORE (message 2)", 20, after=ready)
    again.press(b"\x11")
    assert again.exit_code() == 0


def test_while_the_model_restarts_the_status_bar_says_so_and_a_message_waits_visibly(
    launch: Launch,
) -> None:
    """`/model` restarts the model row, which may take a while to come up (`slow-2` takes 3 s):
    the model field says it is starting until the row is active, and a message
    typed meanwhile says it is waiting, then gets its reply. `/clear` restarts the loop, its
    transcript and the kernel, and a message typed meanwhile waits for whichever of them are
    still coming up, the same way."""
    app = launch("slow")
    ready = app.wait_for(_READY, 60)
    app.type("first")
    up = app.wait_for("echo: FIRST", 20, after=ready)
    app.type("/model slow-2")
    starting = app.wait_for("model: slow-2…", 10, after=up)  # the narrow form: a factory's name is long
    app.type("hello")
    waiting = app.wait_for(
        "⧗ waiting for model to start; this message is sent once it is up", 5, after=starting
    )
    replied = app.wait_for("echo: HELLO", 20, after=waiting)
    status = app.text()[app.text().rfind("model: slow-2") :]
    assert status.startswith("model: slow-2 "), status[:80]  # active again
    app.type("/clear")  # the loop, its transcript and the kernel restart; the model stays up
    app.type("again")
    # `Loader.restart` retires the rows together, then mounts them, so which of them are still
    # coming up when `again` arrives is timing: the note names some of them, never the model.
    noted = app.wait_for("⧗ waiting for ", 5, after=replied)
    waiting = app.wait_for("to start; this message is sent once", 5, after=noted)
    rows = app.text()[noted:waiting].removesuffix(" to start; this message is sent once")
    assert rows and set(rows.split(", ")) <= {"kernel", "loop", "transcript"}, rows
    app.wait_for("echo: AGAIN", 20, after=waiting)
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_a_message_typed_the_moment_after_model_waits_for_the_new_model(launch: Launch) -> None:
    """The restart begins a moment after `/model` answers, while the chat row still reads: a
    message typed straight after it (both lines in one burst of keys) waits for the new model
    and says so, rather than going to the old one or being stopped by the restart."""
    app = launch("slow")
    ready = app.wait_for(_READY, 60)
    app.type("first")
    up = app.wait_for("echo: FIRST", 20, after=ready)
    app.press(b"/model slow-2\rhello\r")
    switching = app.wait_for("switching to slow-2", 10, after=up)
    waiting = app.wait_for("⧗ waiting for model to start; this message is sent once it is up", 5, after=up)
    replied = app.wait_for("echo: HELLO", 20, after=max(switching, waiting))
    shown = app.text()
    assert "stopped: interrupted" not in shown[up:], shown[up:][-2000:]
    starting = shown.find("model: slow-2…", up)
    assert 0 <= starting < replied  # it was answered once the new model had started
    status = shown[shown.rfind("model: slow-2") :]
    assert status.startswith("model: slow-2 "), status[:80]  # up again
    app.press(b"/clear\ragain\r")  # the same for /clear, which restarts the kernel too
    waiting = app.wait_for("⧗ waiting for kernel, loop, transcript to start", 10, after=replied)
    again = app.wait_for("echo: AGAIN", 20, after=waiting)
    assert "stopped: interrupted" not in app.text()[replied:again]
    app.press(b"\x11")
    assert app.exit_code() == 0


def test_model_switches_by_name_between_a_fake_and_an_openai_model_on_a_stub_server(
    launch: Launch, tmp_path: Path
) -> None:
    """`/model` lists the models, the current one marked; `/model stub` moves the conversation
    to an OpenAI-compatible model (a stand-in server on a real socket, streaming SSE), whose
    python call runs as an input like any model's (the model row, up before the app heard it,
    notes its first reload); `/model fake` moves it back, the transcript
    carried across both providers. `fake` (a factory model) stands in for claude-code, which
    needs the real CLI here; Claude's own turns reaching an openai model are the models
    plugin's `test_claude_code_to_openai.py` (the real provider over its fake session)."""
    with StubServer() as stub:
        stub_model = f'[stub]\nprovider = "openai"\nid = "stub-1"\nbase_url = "{stub.base_url}"\n'
        _models_file(tmp_path / "config", stub_model)
        app = launch("fake")
        ready = app.wait_for(_READY, 60)
        app.type("hello")
        said = app.wait_for("[fake] echo: HELLO (message 1)", 20, after=ready)
        app.type("/model")
        listed = app.wait_for("/model NAME switches", 10, after=said)
        shown = app.text()[said:listed]
        assert "● fake" in shown and "stub    openai" in shown and f"at {stub.base_url}" in shown, shown
        app.type("/model stub")
        switched = app.wait_for("model: stub (openai)", 20, after=listed)
        app.wait_for("↻ model reloaded", 20, after=listed)  # the first switch says so too
        app.type("hi stub")
        heard = app.wait_for("[stub-1] heard: hi stub", 20, after=switched)
        app.type("call print(6 * 7)")
        app.wait_for("Run this python code", 10, after=heard)  # the input, put to the person (unjailed)
        app.answer(b"y")
        ran = app.wait_for("the input said: 42", 20, after=heard)
        app.type("/model fake")
        back = app.wait_for("model: fake", 20, after=ran)  # its provider too, when the bar has room
        app.type("again")
        app.wait_for("[fake] echo: AGAIN (message 4)", 20, after=back)  # one conversation throughout
        app.press(b"\x11")
        assert app.exit_code() == 0
    first, *_ = [r["body"]["messages"] for r in stub.requests]
    assert [m["role"] for m in first] == ["system", "user", "assistant", "user"]  # the fake's turn, carried
    assert first[2]["content"].startswith("[fake] echo: HELLO")
    assert all(r["authorization"] is None for r in stub.requests)  # no key named, none sent


def test_a_patch_that_sets_the_model_row_s_config_keeps_its_model_and_says_so(tmp_path: Path) -> None:
    """A `--patch` setting the model row's config replaces the session layer's whole, so the
    model it names is the one that runs: `--model` with it is refused before anything starts,
    and `/model` says it can't switch rather than announcing a switch that never happens."""
    work, state, config = tmp_path / "work", tmp_path / "state", tmp_path / "config"
    work.mkdir()
    _models_file(config)
    pin = tmp_path / "pin.toml"
    pin.write_text('[[plugin]]\nid = "model"\nconfig = { default = "fake-2" }\n')
    refused = Launched(["--no-jail", "--model", "fake", "--patch", str(pin)], work, state, config=config)
    app = Launched(["--no-jail", "--patch", str(pin)], work, state, config=config)
    try:
        assert refused.exit_code() == 1
        assert "--model fake would not take effect" in " ".join(refused.text().split())
        ready = app.wait_for(_READY, 60)
        app.wait_for("model: fake-2", after=0)
        app.type("/model fake")
        said = app.wait_for("not switched:", 10, after=ready)
        app.wait_for("row's config", 10, after=said)
        app.type("hello")
        app.wait_for("[fake-2] echo: HELLO", 20, after=said)  # still the patch's model
        app.press(b"\x11")
        assert app.exit_code() == 0
    finally:
        refused.close()
        app.close()


def test_a_keyed_model_s_key_never_reaches_an_input_s_environment(tmp_path: Path) -> None:
    """A model's key goes only into its requests' Authorization header: an unjailed input (whose
    environment is scrubbed of Claude's names alone) finds neither its name nor its value."""
    work, state, config = tmp_path / "work", tmp_path / "state", tmp_path / "config"
    work.mkdir()
    env = tmp_path / "scratch.env"
    env.write_text("VERIFY_STUB_KEY=fake-verify-key\n")
    pin = tmp_path / "keyed.toml"  # the env file is the model row's config, so it names the model too
    pin.write_text(f'[[plugin]]\nid = "model"\nconfig = {{ default = "keyed", env_file = "{env}" }}\n')
    with StubServer(key="fake-verify-key") as stub:
        keyed = f'[keyed]\nprovider = "openai"\nid = "stub-1"\nbase_url = "{stub.base_url}"\n'
        keyed += 'key = "VERIFY_STUB_KEY"\n'
        _models_file(config, keyed)
        app = Launched(["--no-jail", "--patch", str(pin)], work, state, config=config)
        try:
            ready = app.wait_for(_READY, 60)
            app.wait_for("model: keyed", after=0)
            app.type(
                'call import os; print("VERIFY_STUB_KEY" in os.environ, "fake-verify-key" in str(os.environ))'
            )
            app.wait_for("Run this python code", 10, after=ready)
            app.answer(b"y")
            app.wait_for("the input said: False False", 20, after=ready)
            app.press(b"\x11")
            assert app.exit_code() == 0
        finally:
            app.close()
    assert {r["authorization"] for r in stub.requests} == {"Bearer fake-verify-key"}
