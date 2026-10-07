"""The `transcript` values: history in memory, or in a JSONL file a session can be resumed from.

A row of its own, so it outlives the loop: replace the model and the conversation
carries on. With a file, it also outlives bh-02: each message is appended as it happens (the
log is written before anything reads it back), and a new transcript over the same file
starts with everything already there. `/compact` replaces the file whole (`rewrite`, keeping
the old one beside it) and restarts the row, which then starts with the new conversation.
"""

import contextlib
import itertools
import json
import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

__all__ = ["FileTranscript", "MemoryTranscript", "rewrite"]


class MemoryTranscript:
    def __init__(self) -> None:
        self._messages: list[Mapping[str, Any]] = []

    @property
    def messages(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._messages)

    def append(self, message: Mapping[str, Any]) -> None:
        self._messages.append(message)


class FileTranscript(MemoryTranscript):
    """A transcript kept in `path`, one JSON message per line, read back when it starts."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = Path(path)
        if self._path.is_file():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    super().append(json.loads(line))

    def append(self, message: Mapping[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(message) + "\n")
        super().append(message)


def _backup(file: Path, n: int) -> Path:
    """The `n`th backup of `file` (from 1): `file.bak`, then `file.bak.2`, and so on."""
    return file.with_name(f"{file.name}.bak" if n == 1 else f"{file.name}.bak.{n}")


def rewrite(path: str, messages: Iterable[Mapping[str, Any]]) -> str:
    """Replace the transcript file `path` with `messages`, in one step: they are written whole
    beside it, then renamed over it, so whatever reads it (a resume, the restarted row) finds
    the old conversation or the new one, never part of either. The old file is kept beside it
    under the first backup name not taken (`path.bak`, then `path.bak.2`, ...), so an earlier
    backup is never replaced, and its path returned. When any of this fails (`OSError`), the
    transcript is as it was and no backup is left."""
    file = Path(path)
    temporary = file.with_name(f"{file.name}.new")
    backup = next(b for n in itertools.count(1) if not (b := _backup(file, n)).exists())
    made = [temporary]
    try:
        with temporary.open("w", encoding="utf-8") as out:
            out.writelines(json.dumps(message) + "\n" for message in messages)
        with file.open("rb") as old, backup.open("xb") as kept:  # "x": never another's backup
            made.append(backup)
            shutil.copyfileobj(old, kept)
        os.replace(temporary, file)
    except BaseException:
        for left in made:
            with contextlib.suppress(OSError):
                left.unlink()
        raise
    return str(backup)
