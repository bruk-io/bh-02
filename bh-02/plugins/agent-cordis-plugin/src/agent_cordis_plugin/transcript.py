"""The `transcript` values: the conversation in memory, or in a JSONL file a session can be resumed from.

A row of its own, so it outlives the loop: replace the model and the conversation
carries on. With a file, it also outlives bh-02: each message is appended as it happens, and a
new transcript over the same file starts with everything already there. `append` commits the
message in memory and queues its line to `host_paths.Appender`, which writes it on a thread, in
order, at 0600, so the event loop the TUI shares never waits on a disk. The file may therefore
be a few entries behind the memory for a moment: the loop flushes it at the end of every reply
(`flush`), so whatever reads the file between replies (`/clear`, `/compact`, a resume) finds every
entry. A line that can't be written is not lost silently: the next `append` and `flush` raise it, as
`TranscriptWriteFailed`, a recoverable failure (`kind` and `message`, CONTRACTS.md: errors), so a full
disk is shown to the person like any other failure of a reply and the chat carries on, not ends
with a traceback. Its message names the file, what failed, and what to do: free space, then
`/restart transcript`, which begins again from what the file holds. The writer's rule stands: the
entry whose write failed stays in memory, nothing after it is written, and the ones after it are
refused before they are kept.
`/compact` replaces the file whole (`rewrite`, keeping the old one beside it, both at 0600) and
restarts the row, which then starts with the new conversation.

A process killed mid-write leaves the file's last line unfinished: no newline, and not JSON. That
is an entry that was never made, so a transcript over such a file drops it: the bytes are kept
beside the file first (`path.torn`, then `path.torn.2`, ... the first name not taken, at 0600, through
no link, as `rewrite` keeps `.bak`), then the file is cut to its last whole line, before the
appender's first write, so the next entry is not glued onto them. A last line that is whole but
for its newline is read, and given one. A line that is not JSON anywhere else, including a last
line that ends in a newline, is damage and not a write cut short: the transcript stops (`ValueError`
naming the file and the line) and the file is left as it is, for the person to repair.

If that restart fails, the transcript is still the old conversation's, over a file that is now
the new one's. It writes nothing more to it: the writer refuses a file replaced under it
(`host_paths.Replaced`), and `append`, `flush` and leaving raise `TranscriptReplaced` instead, a
recoverable failure (`kind` and `message`, CONTRACTS.md: errors) whose message tells the person
`/restart transcript` begins the new conversation. As with any failed write, the entry whose
write found the file replaced stays in memory and the ones after it are refused before they are
kept; nothing of the old conversation reaches the new file, and none is written to the old inode,
where no one would read it. The writer looks at the file only before a write, so a reply asks it to
look first (`check`), before it appends anything: the refusal then comes before the model is asked,
not at the step's entry after it. The look is the writing thread's one stat, which the reply waits
for with the event loop free; it writes nothing, and it waits behind no write at a reply's start,
since the reply before flushed.
"""

import contextlib
import itertools
import json
import os
import shutil
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from host_paths import Appender, Replaced, write_beneath

__all__ = ["FileTranscript", "MemoryTranscript", "TranscriptReplaced", "TranscriptWriteFailed", "rewrite"]

# What the person is told when the transcript's file was replaced under it. `unrestarted` (the
# conversation row) says the same of a restart that failed; this is what they meet when they type.
_REPLACED = (
    "the conversation's file {path} was replaced since this conversation began (by a /clear or "
    "/compact whose restart failed, or by hand), so nothing more is written to it: the file holds "
    "another conversation now. /restart transcript begins that one"
)

# What the person is told when the transcript's writer could not write its file (the disk is full, the
# directory is gone, the file is a directory). The writer writes nothing after a failed write, so
# nothing is until the transcript is started again over the file.
_UNWRITTEN = (
    "writing the conversation's file {path} failed ({error}), so the entry that failed and every one "
    "after it are not in the file, and nothing more is written to it. If the disk is full, free some "
    "space (otherwise put right what the error says), then /restart transcript to carry on from what "
    "the file holds: what was not written is lost"
)

# What the person is told when a line before the last is not JSON. Only the last line can be a write
# cut short, so this one is damage (a hand edit, a disk): the file is left as it is.
_DAMAGED = (
    "{path} line {number} is not JSON ({error}), so the conversation in it can't be read: it is "
    "not a write cut short (only an unfinished last line is), so nothing was changed. Repair or "
    "remove that line in an editor (one JSON message per line), or leave this session and start a "
    "new one without --resume"
)


class TranscriptReplaced(OSError):
    """The transcript's file is no longer the one it writes to: a recoverable failure (CONTRACTS.md:
    errors), its `kind` `transcript_replaced`, its `message` for the person, naming the command
    that begins the conversation the file holds. An `OSError`, as every failed write is."""

    def __init__(self, path: Path) -> None:
        self.kind = "transcript_replaced"
        self.message = _REPLACED.format(path=path)
        super().__init__(self.message)


class TranscriptWriteFailed(OSError):
    """The transcript's file could not be written (a full disk, a directory gone): a recoverable
    failure (CONTRACTS.md: errors), its `kind` `transcript_write_failed`, its `message` for the
    person, naming the file, what failed, and the command that begins again from the file. An
    `OSError`, as every failed write is; the writer's own error is its `__cause__`."""

    def __init__(self, path: Path, error: OSError) -> None:
        self.kind = "transcript_write_failed"
        self.message = _UNWRITTEN.format(path=path, error=error)
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class _Reading:
    """What a transcript file holds: its `messages`; `whole`, the bytes up to and including its last
    newline; `torn`, an unfinished last line (no newline, not JSON: empty when there is none); and
    `unended`, whether the last line is a whole entry with no newline after it."""

    messages: tuple[Mapping[str, Any], ...]
    whole: int
    torn: bytes
    unended: bool


def _message(line: bytes) -> Mapping[str, Any]:
    """The entry on `line`.

    Raises:
        ValueError: `line` is not JSON, or not UTF-8.
    """
    message: Mapping[str, Any] = json.loads(line.decode("utf-8"))
    return message


def _read(data: bytes, path: Path) -> _Reading:
    """Read the transcript file `data` (the bytes of `path`, which only names it in an error): every
    line is an entry or blank, but for an unfinished last line, which is set apart.

    Raises:
        ValueError: a line is not JSON and is not the last line without a newline (a write cut
            short); the message names `path` and the line number.
    """
    *lines, last = data.split(b"\n")
    messages = []
    for number, line in enumerate(lines, 1):
        if line.strip():
            try:
                messages.append(_message(line))
            except ValueError as error:
                raise ValueError(_DAMAGED.format(path=path, number=number, error=error)) from error
    whole = len(data) - len(last)
    if not last.strip():
        return _Reading(tuple(messages), whole, b"", False)
    try:
        messages.append(_message(last))
    except ValueError:
        return _Reading(tuple(messages), whole, last, False)
    return _Reading(tuple(messages), whole, b"", True)


class MemoryTranscript:
    def __init__(self) -> None:
        self._messages: list[Mapping[str, Any]] = []

    @property
    def messages(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._messages)

    def append(self, message: Mapping[str, Any]) -> None:
        self._messages.append(message)


class FileTranscript(MemoryTranscript):
    """A transcript kept in `path`, one JSON message per line, read back when it starts.

    Entered as an async context manager (the transcript row does), it waits for the last write
    and closes the file when it leaves, so a restart or a retired sub-agent holds no descriptor.
    A file replaced under it (`/clear` or `/compact`, whose restart failed) is refused:
    `TranscriptReplaced`, by `check`, `append`, `flush` and leaving. A write that failed (a full
    disk) is refused the same way, once and for good: `TranscriptWriteFailed`.
    """

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = Path(path)
        self._appender = Appender(path)  # opens the file at the first write, not before
        if self._path.is_file():
            reading = _read(self._path.read_bytes(), self._path)
            self._mend(reading)
            for message in reading.messages:
                super().append(message)

    def _mend(self, reading: _Reading) -> None:
        """Make the file end where an entry does, so the appender's first write starts a line of
        its own: set an unfinished last line aside and cut the file after the line before it, or
        end a whole last line that has no newline. The bytes are kept before they are cut: if
        they can't be, nothing is.

        Raises:
            OSError: the bytes could not be kept, or the file could not be cut or ended (a link
                stands at the name, no room, no permission); the file is as it was.
        """
        if reading.torn:
            kept = next(k for n in itertools.count(1) if not (k := _beside(self._path, "torn", n)).exists())
            try:
                write_beneath(self._path.parent, [kept.name], reading.torn)
            except OSError as error:
                error.add_note(
                    f"the last line of {self._path} is unfinished (a write cut short) and could not "
                    f"be kept as {kept}, so it was not cut off and the file is as it was"
                )
                raise
        if reading.torn or reading.unended:
            try:
                with os.fdopen(os.open(self._path, _MENDED), "ab") as file:
                    if reading.torn:
                        file.truncate(reading.whole)
                    else:
                        file.write(b"\n")
            except OSError as error:
                error.add_note(f"the end of {self._path} could not be mended, so the file is as it was")
                raise

    def append(self, message: Mapping[str, Any]) -> None:
        """Keep `message`: in memory now, in the file as soon as the thread gets to it (`flush`
        waits for that).

        Raises:
            TranscriptReplaced: the file was replaced under the transcript; nothing is kept.
            TranscriptWriteFailed: an earlier line could not be written; nothing after it is,
                and nothing is kept.
        """
        with self._refusing():
            self._appender.append(f"{json.dumps(message)}\n".encode())
        super().append(message)

    async def check(self) -> None:
        """Return once the writer has looked at the file and found it the one this transcript
        writes to, which the loop awaits before a reply appends anything, so a file replaced
        under the transcript is refused before the model is asked. Nothing is written: the look is
        one stat, on the writing thread, queued behind the writes before it (none, at a reply's
        start).

        Raises:
            TranscriptReplaced: the file was replaced under the transcript.
            TranscriptWriteFailed: a line could not be written, or the file could not be looked at.
        """
        with self._refusing():
            await self._appender.check()

    async def flush(self) -> None:
        """Return once every message appended so far is in the file.

        Raises:
            TranscriptReplaced: the file was replaced under the transcript.
            TranscriptWriteFailed: a line could not be written.
        """
        with self._refusing():
            await self._appender.flush()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        with self._refusing():
            await self._appender.close()

    @contextlib.contextmanager
    def _refusing(self) -> Iterator[None]:
        """Say the appender's failure as the person is told it: a file replaced under it as
        `TranscriptReplaced`, any other failed write as `TranscriptWriteFailed`."""
        try:
            yield
        except Replaced as replaced:
            raise TranscriptReplaced(self._path) from replaced
        except OSError as error:
            raise TranscriptWriteFailed(self._path, error) from error


# A transcript is the person's, and not for the model's code to read or write: what `rewrite` makes
# is readable by its owner alone, made so in the one call that opens it. `O_NOFOLLOW`: never through
# a link left at the name.
_MADE = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOCTTY
_PRIVATE = 0o600
# Mending a transcript's end in place: never through a link left at the name; the file is there.
_MENDED = os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOCTTY


def _beside(file: Path, kind: str, n: int) -> Path:
    """The `n`th file of `kind` kept beside `file` (from 1): `file.bak`, then `file.bak.2`, and so on."""
    return file.with_name(f"{file.name}.{kind}" if n == 1 else f"{file.name}.{kind}.{n}")


def rewrite(path: str, messages: Iterable[Mapping[str, Any]]) -> str:
    """Replace the transcript file `path` with `messages`, in one step: they are written whole
    beside it, then renamed over it, so whatever reads it (a resume, the restarted row) finds
    the old conversation or the new one, never part of either. The old file is kept beside it
    under the first backup name not taken (`path.bak`, then `path.bak.2`, ...), so an earlier
    backup is never replaced, and its path returned. When any of this fails (`OSError`), the
    transcript is as it was and no backup is left. The new file and the backup are readable by
    their owner alone (0600), the new one even where a `.new` left by a crashed rewrite was wider."""
    file = Path(path)
    temporary = file.with_name(f"{file.name}.new")
    backup = next(b for n in itertools.count(1) if not (b := _beside(file, "bak", n)).exists())
    made = [temporary]
    try:
        with os.fdopen(os.open(temporary, _MADE | os.O_TRUNC, _PRIVATE), "w", encoding="utf-8") as out:
            os.fchmod(out.fileno(), _PRIVATE)  # a `.new` that was already there keeps the mode it had
            out.writelines(json.dumps(message) + "\n" for message in messages)
        with (
            file.open("rb") as old,
            os.fdopen(os.open(backup, _MADE | os.O_EXCL, _PRIVATE), "wb") as kept,  # never another's backup
        ):
            made.append(backup)
            shutil.copyfileobj(old, kept)
        os.replace(temporary, file)
    except BaseException:
        for left in made:
            with contextlib.suppress(OSError):
                left.unlink()
        raise
    return str(backup)
