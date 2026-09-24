"""The `transcript` values: history in memory, or in a JSONL file a session can be resumed from.

A row of its own, so it outlives the loop: replace the model and the conversation
carries on. With a file, it also outlives bh-02: each message is appended as it happens (the
log is written before anything reads it back), and a new transcript over the same file
starts with everything already there.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["FileTranscript", "MemoryTranscript"]


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
