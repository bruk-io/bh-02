"""The `transcript` values: the conversation in memory, or in a JSONL file a session can be resumed from.

A row of its own, so it outlives the loop: replace the model and the conversation
carries on. With a file, it also outlives bh-02: each message is appended as it happens, and a
new transcript over the same file starts with everything already there. `append` commits the
message in memory and queues its line to `host_paths.Appender`, which writes it on a thread, in
order, at 0600, so the event loop the TUI shares never waits on a disk. The file may therefore
be a few entries behind the memory for a moment: the loop flushes it at the end of every reply
(`flush`), so whatever reads the file between replies (`/clear`, `/compact`, a resume) finds every
entry. A line that can't be written is not lost silently: the next `append` and `flush` raise it.
`/compact` replaces the file whole (`rewrite`, keeping the old one beside it, both at 0600) and
restarts the row, which then starts with the new conversation.

If that restart fails, the transcript is still the old conversation's, over a file that is now
the new one's. It writes nothing more to it: the writer refuses a file replaced under it
(`host_paths.Replaced`), and `append`, `flush` and leaving raise `TranscriptReplaced` instead, a
recoverable failure (`kind` and `message`, CONTRACTS.md: errors) whose message tells the person
`/restart transcript` begins the new conversation. As with any failed write, the entry whose
write found the file replaced stays in memory and the ones after it are refused before they are
kept; nothing of the old conversation reaches the new file, and none is written to the old inode,
where no one would read it.
"""

import contextlib
import itertools
import json
import os
import shutil
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, Self

from host_paths import Appender, Replaced

__all__ = ["FileTranscript", "MemoryTranscript", "TranscriptReplaced", "rewrite"]

# What the person is told when the transcript's file was replaced under it. `unrestarted` (the
# conversation row) says the same of a restart that failed; this is what they meet when they type.
_REPLACED = (
    "the conversation's file {path} was replaced since this conversation began (by a /clear or "
    "/compact whose restart failed, or by hand), so nothing more is written to it: the file holds "
    "another conversation now. /restart transcript begins that one"
)


class TranscriptReplaced(OSError):
    """The transcript's file is no longer the one it writes to: a recoverable failure (CONTRACTS.md:
    errors), its `kind` `transcript_replaced`, its `message` for the person, naming the command
    that begins the conversation the file holds. An `OSError`, as every failed write is."""

    def __init__(self, path: Path) -> None:
        self.kind = "transcript_replaced"
        self.message = _REPLACED.format(path=path)
        super().__init__(self.message)


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
    `TranscriptReplaced`, by `append`, `flush` and leaving.
    """

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = Path(path)
        self._appender = Appender(path)  # opens the file at the first write, not before
        if self._path.is_file():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    super().append(json.loads(line))

    def append(self, message: Mapping[str, Any]) -> None:
        """Keep `message`: in memory now, in the file as soon as the thread gets to it (`flush`
        waits for that).

        Raises:
            TranscriptReplaced: the file was replaced under the transcript; nothing is kept.
            OSError: an earlier line could not be written; nothing after it is.
        """
        with self._refusing():
            self._appender.append(f"{json.dumps(message)}\n".encode())
        super().append(message)

    async def flush(self) -> None:
        """Return once every message appended so far is in the file.

        Raises:
            TranscriptReplaced: the file was replaced under the transcript.
            OSError: a line could not be written.
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
        """Say a file replaced under the appender as the person is told it."""
        try:
            yield
        except Replaced as replaced:
            raise TranscriptReplaced(self._path) from replaced


# A transcript is the person's, and not for the model's code to read or write: what `rewrite` makes
# is readable by its owner alone, made so in the one call that opens it. `O_NOFOLLOW`: never through
# a link left at the name.
_MADE = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOCTTY
_PRIVATE = 0o600


def _backup(file: Path, n: int) -> Path:
    """The `n`th backup of `file` (from 1): `file.bak`, then `file.bak.2`, and so on."""
    return file.with_name(f"{file.name}.bak" if n == 1 else f"{file.name}.bak.{n}")


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
    backup = next(b for n in itertools.count(1) if not (b := _backup(file, n)).exists())
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
