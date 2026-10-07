"""The `transcript` values: history in memory, or in a JSONL file a session can be resumed from.

A row of its own, so it outlives the loop: replace the model and the conversation
carries on. With a file, it also outlives bh-02: each message is appended as it happens (the
log is written before anything reads it back), and a new transcript over the same file
starts with everything already there. `/compact` replaces the file whole (`rewrite`) and
restarts the row, which then starts with the new conversation.
"""

import contextlib
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


def rewrite(path: str, messages: Iterable[Mapping[str, Any]]) -> str:
    """Replace the transcript file `path` with `messages`, in one step: they are written whole
    beside it, then renamed over it, so whatever reads it (a resume, the restarted row) finds
    the old conversation or the new one, never part of either. The old file is kept beside it
    as `path.bak` (an earlier one replaced), and its path returned. When any of this fails
    (`OSError`), the transcript is as it was."""
    file = Path(path)
    temporary, backup = file.with_name(f"{file.name}.new"), file.with_name(f"{file.name}.bak")
    try:
        with temporary.open("w", encoding="utf-8") as out:
            out.writelines(json.dumps(message) + "\n" for message in messages)
        shutil.copyfile(file, backup)
        os.replace(temporary, file)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise
    return str(backup)
