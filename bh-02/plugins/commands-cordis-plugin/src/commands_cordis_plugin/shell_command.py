"""`!COMMAND`: a line the person starts with a prefix runs as a shell command, as them, and what
it printed waits for the model.

The person typed it, so it runs as them: not in the jail, in the project (`cwd`), through their
shell (`$SHELL -c`, else `/bin/sh -c`), in bh-02's own environment less what is the host's alone
(`ANTHROPIC_*` and `CLAUDE*`: a Claude credential the person exported, what a launching Claude
Code left), as `runner:unconfined` drops them, since what it prints goes to the model. Nothing here
reads `local.env`.

The app owns the terminal, so the command gets none of it: no input, its output (stdout and
stderr as one stream, as a terminal shows them) captured, and a session of its own, so the
terminal's Ctrl-C never reaches it and a program that opens /dev/tty fails rather than drawing
over the app. A command is not a turn, and Ctrl-C does not stop it (CONTRACTS.md: input), so it
has a `timeout`, at which its process group is ended; so is a program it left running in the
background that still holds its output, once it has exited, since nobody would read what that
prints, and so is the command when it is cancelled (the person left bh-02). What it printed is
kept to its start and its end, however much there was, and shown as plain text: nothing in it
reaches the terminal that a terminal acts on (an escape, a control character).

Its answer (CONTRACTS.md: commands) is a `note` for the person, what it printed and how it
ended, and a `for_model` event, the same framed for the model, which the `commands` value
holds and `chat:converse` puts in front of the person's next message: the model reads it with
that, never during a turn.
"""

import asyncio
import contextlib
import os
import re
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["Ran", "ShellCommandConfig", "answer", "environment", "run_command", "run_line"]

_MAX_OUTPUT = 20_000  # bytes of what a command printed that are kept, as an input's output is cut
_HEAD = 6_000  # of those, how many are its start; the rest are its end (a test run's summary)
_CHUNK = 1 << 16
_LEFT_OPEN_S = 0.5  # after the shell exits, how long a program it left running may hold the output
_STOP_GRACE_S = 2.0  # between SIGTERM and SIGKILL
_EXITED_POLL_S = 0.05  # how often whether the shell has exited is looked at
_GONE = (ProcessLookupError, PermissionError)  # a group already ended (darwin: only zombies left)
_HOST_ONLY = ("ANTHROPIC_", "CLAUDE")
# What a program writes for a terminal though it has none (colour, `tput sgr0`'s `ESC ( B`)
_ESCAPES = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI (private markers too): colour, the cursor
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: a title, a link
    r"|\x1b[PX^_][^\x1b]*\x1b\\"  # DCS, SOS, PM, APC: a string for the terminal
    r"|\x1b[ -/]*[0-~]"  # the rest: a character set (`ESC ( 0`), `ESC 7`, `ESC c` (a reset)
)
# an escape the text ends in the middle of (where the start kept of a long output was cut)
_UNFINISHED = re.compile(r"\x1b(?:\[[0-?]*[ -/]*|\][^\x07\x1b]*|[PX^_][^\x1b]*|[ -/]*)?\Z")
# what is left that a terminal acts on: a stray ESC, C0 controls but tab and newline, DEL, C1
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


@dataclass(frozen=True, slots=True)
class ShellCommandConfig:
    """`prefix`: the character a line starts with to run as a shell command (`!`); `cwd`: where
    it runs (`.`: the project, where bh-02 runs); `timeout`: the seconds it may take before it
    is stopped (120); `shell`: the program run with `-c` (empty: the person's `$SHELL`, else
    `/bin/sh`)."""

    prefix: str = "!"
    cwd: str = "."
    timeout: float = 120.0
    shell: str = ""


@dataclass(frozen=True, slots=True)
class Ran:
    """A command that ran: what was typed; what it printed (stdout and stderr together, its start
    and end when it was long, as plain text: `_plain`); and how it ended: its exit status
    (negative: the signal that ended it), or None when it was stopped at its timeout."""

    command: str
    output: str
    status: int | None


def environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The command's environment: bh-02's, less what is the host's alone (`ANTHROPIC_*`,
    `CLAUDE*`), since what the command prints goes to the model."""
    return {name: value for name, value in environ.items() if not name.startswith(_HOST_ONLY)}


def _plain(text: str) -> str:
    """`text` as a terminal would leave it to read, with nothing left in it that a terminal acts
    on: escapes taken out (one it ends in the middle of too); a line a program wrote over
    (`\\r`, a progress bar) as it ended up; any other control character but tab and newline
    gone."""
    lines = _ESCAPES.sub("", _UNFINISHED.sub("", text)).replace("\r\n", "\n").split("\n")
    return _CONTROLS.sub("", "\n".join(line.rstrip("\r").rpartition("\r")[2] for line in lines))


def _whole(head: bytes, tail: bytes) -> tuple[bytes, bytes]:
    """The start and end kept of what was printed, cut where a character begins: a UTF-8
    character the cut split is left out of both."""
    for back in range(1, min(4, len(head)) + 1):
        if head[-back] < 0x80:  # ASCII: the start ends on a whole character
            break
        if head[-back] >= 0xC0:  # where the last character began: whole, or left out
            needs = 2 if head[-back] < 0xE0 else 3 if head[-back] < 0xF0 else 4
            head = head if back >= needs else head[:-back]
            break
    skip = next((n for n in range(min(3, len(tail))) if not 0x80 <= tail[n] < 0xC0), min(3, len(tail)))
    return head, tail[skip:]


def _printed(head: bytes, tail: bytes, total: int) -> str:
    """What a command printed, as text (`_plain`): all of it, or, when it printed more than was
    kept, its start and its end, each cut on a whole character, with how much was cut between."""
    if total <= len(head) + len(tail):
        return _plain((head + tail).decode(errors="replace"))
    head, tail = _whole(head, tail)
    cut = total - len(head) - len(tail)
    start, end = (_plain(part.decode(errors="replace")) for part in (head, tail))
    return f"{start}\n... [{cut} bytes cut here] ...\n{end}"


class _Output:
    """What a command prints, as it is read: its first `_HEAD` bytes, its last ones (up to
    `_MAX_OUTPUT` in all), and how many there were, so a flood never fills memory."""

    def __init__(self) -> None:
        self._head = bytearray()
        self._tail = bytearray()
        self._total = 0

    async def read(self, stream: asyncio.StreamReader | None) -> None:
        while stream is not None and (chunk := await stream.read(_CHUNK)):
            self._total += len(chunk)
            room = max(0, _HEAD - len(self._head))
            self._head += chunk[:room]
            self._tail += chunk[room:]
            del self._tail[: max(0, len(self._tail) - (_MAX_OUTPUT - _HEAD))]

    def text(self) -> str:
        return _printed(bytes(self._head), bytes(self._tail), self._total)


async def run_command(command: str, config: ShellCommandConfig) -> Ran:
    """Run `command` as the person (the module's docstring says how) and wait for it to end, at
    most `config.timeout` seconds. Raises OSError when it can't start (no such shell or `cwd`)."""
    process = await asyncio.create_subprocess_exec(
        config.shell or os.environ.get("SHELL") or "/bin/sh",
        "-c",
        command,
        cwd=config.cwd,
        env=environment(os.environ),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    output = _Output()
    reading = asyncio.ensure_future(output.read(process.stdout))
    stopped = False
    try:
        async with asyncio.timeout(config.timeout):
            await _exited(process)
            await asyncio.wait({reading}, timeout=_LEFT_OPEN_S)
    except TimeoutError:
        stopped = process.returncode is None
    finally:
        # stopped at its timeout (its output closed or not), cancelled (the person left bh-02:
        # the chat row cancels a command once its input closes), or a program it left running
        # still holds its output: it ends with the command, since nobody would read what it prints
        if process.returncode is None or not reading.done():
            await _end(process)
            await asyncio.wait({reading}, timeout=_STOP_GRACE_S)
        reading.cancel()
        await asyncio.gather(reading, return_exceptions=True)
    return Ran(command, output.text(), None if stopped else process.returncode)


async def _exited(process: asyncio.subprocess.Process) -> None:
    """Return once the shell itself has exited. Not `process.wait()`: that also waits for the
    shell's pipes to close (CPython 3.15 does), which a program the command left running holds
    open, so it would wait for that program too."""
    while process.returncode is None:
        await asyncio.sleep(_EXITED_POLL_S)


async def _end(process: asyncio.subprocess.Process) -> None:
    """End the command's process group: SIGTERM, a moment for the shell to go, then SIGKILL for
    whatever of the group is left."""
    with contextlib.suppress(*_GONE):
        os.killpg(process.pid, signal.SIGTERM)
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(_STOP_GRACE_S):
            await _exited(process)
    with contextlib.suppress(*_GONE):
        os.killpg(process.pid, signal.SIGKILL)
    await _exited(process)


def _ended(status: int | None, timeout: float) -> str:
    """How a command ended, in a few words."""
    if status is None:
        return f"stopped at its timeout, {timeout:g} s"
    if status < 0:
        try:
            return f"ended by {signal.Signals(-status).name}"
        except ValueError:
            return f"ended by signal {-status}"
    return f"exit status {status}"


def answer(ran: Ran, timeout: float) -> list[dict[str, Any]]:
    """A command's answer (CONTRACTS.md: commands): a note for the person, what it printed and
    how it ended, and the same for the model, which the chat row holds for the person's next
    message (`for_model`)."""
    ended = _ended(ran.status, timeout)
    printed = ran.output.rstrip("\n")
    how = f"{ended} (the shell-command row's `timeout` sets it)" if ran.status is None else ended
    note = f"{printed or '(it printed nothing)'}\n{how}; the model reads this with your next message"
    told = "\n".join(
        [
            "(Before this message the person ran a shell command themselves, in bh-02, not in your REPL:)",
            f"$ {ran.command}",
            *([printed] if printed else []),
            f"(End of what it printed; {ended}.)",
        ]
    )
    return [{"type": "note", "text": note}, {"type": "for_model", "text": told}]


async def run_line(command: str, *, config: ShellCommandConfig) -> str | list[dict[str, Any]]:
    """What the prefix runs, given the rest of the line: the command, then its answer. An empty
    command, or one that can't start, is said, and nothing is held for the model."""
    if not command:
        return f"type a shell command after {config.prefix}, such as {config.prefix}git status"
    try:
        ran = await run_command(command, config)
    except OSError as error:
        shell = config.shell or "empty: your $SHELL, else /bin/sh"
        return (
            f"couldn't run {command!r}: {error}. The shell-command row runs it with its `shell` "
            f"({shell}) in its `cwd` ({config.cwd}): give that row a shell and a directory that "
            "exist, in a layer"
        )
    return answer(ran, config.timeout)
