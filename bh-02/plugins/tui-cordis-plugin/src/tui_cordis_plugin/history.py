"""What the transcript showed, kept in a file so a resumed session shows it again.

One JSON object per line, in the order shown: a turn's events as they came (CONTRACTS.md:
event), and three entries of the ui's own: `{"type": "user", "text"}` (a message the person
sent), `{"type": "turn_end"}` (a reply's stream ended), `{"type": "noted", "text", "kind"}`
(bh-02 speaking outside a turn: a failure, a reload). The file is the ui's alone; nothing
else reads it, and a line it can't read is skipped rather than failing the resume.

`replayable` is pure (what to draw again, bounded), and so is `compacted` (what the file keeps
once it grows: a `carried` entry, the ui's fourth, holding how many entries were trimmed and
the usage they added up to, then the latest entries); `History` reads, trims and appends the
file. The ui row enters a `History` (an async context manager): entering reads what was
recorded (`recorded`), leaving closes the file.

`/clear` reaches the ui as a `cleared` event (CONTRACTS.md: event), recorded like any other:
the file keeps what came before it (so a resume's usage totals are the ones shown live, the
session's running totals) and a replay starts after the last one. A session made before
`cleared` existed also lists this file in `commands:operator`'s `forget`, which empties it
underneath the app; the next write notices and puts a `carried` entry first, holding what the
forgotten entries counted and added up to.
"""

import contextlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from tui_cordis_plugin import frame

__all__ = ["History", "Replay", "compacted", "merged", "replayable"]

type Entry = Mapping[str, Any]

_STREAMED = frozenset({"text", "thinking"})
_CARRIED = "carried"
_CLEARED = "cleared"


@dataclass(frozen=True, slots=True)
class Replay:
    """What to draw again (`entries`), and how many entries before them were left out."""

    entries: tuple[Entry, ...]
    skipped: int


def merged(entries: Iterable[Entry]) -> list[Entry]:
    """`entries` with each run of streamed text or thinking joined into one entry (a reply
    streamed a word at a time is one entry, not thousands); the rest as they are."""
    joined: list[Entry] = []
    for entry in entries:
        kind = entry.get("type")
        last = joined[-1] if joined else None
        if kind in _STREAMED and last is not None and last.get("type") == kind:
            joined[-1] = {**last, "text": f"{last.get('text', '')}{entry.get('text', '')}"}
        else:
            joined.append(entry)
    return joined


def replayable(entries: Iterable[Entry], limit: int) -> Replay:
    """The last `limit` entries to draw again, each streamed run merged into one entry first
    (`merged`). The cut moves forward to a message the person sent, when there is one, so a
    turn is shown whole. Entries the file no longer holds (`carried`) count as left out.

    Only the conversation since the last `/clear` is drawn (what follows the last `cleared`
    entry); what came before it is not counted as left out, since it was cleared, not trimmed."""
    joined = _since_cleared(merged(entries))
    shown = [e for e in joined if e.get("type") != _CARRIED]
    start = _cut(shown, limit)
    return Replay(tuple(shown[start:]), start + _carried_count(joined))


def _since_cleared(joined: Sequence[Entry]) -> Sequence[Entry]:
    """The entries after the last `cleared` one (all of them when there is none)."""
    last = max((n for n, e in enumerate(joined) if e.get("type") == _CLEARED), default=-1)
    return joined[last + 1 :]


def _cut(joined: Sequence[Entry], limit: int) -> int:
    """Where the last `limit` entries start, moved forward to a message the person sent."""
    start = max(0, len(joined) - limit)
    if start > 0:
        start = next((n for n in range(start, len(joined)) if joined[n].get("type") == "user"), start)
    return start


def _carried_count(entries: Iterable[Entry]) -> int:
    return sum(int(e.get("entries") or 0) for e in entries if e.get("type") == _CARRIED)


def compacted(entries: Iterable[Entry], keep: int) -> list[Entry] | None:
    """What the file should hold once it has grown past twice `keep` entries (streamed runs
    merged): a `carried` entry, then the last `keep` (cut as `replayable` cuts). `carried`
    says how many entries were trimmed and what their usage added up to, so the session's
    usage totals (`frame.total_usage`) survive the trim. None while the file is small enough."""
    joined = merged(entries)
    shown = [e for e in joined if e.get("type") != _CARRIED]
    if len(shown) <= 2 * keep:
        return None
    start = _cut(shown, keep)
    carried_before = [e for e in joined if e.get("type") == _CARRIED]
    used = frame.total_usage([*carried_before, *shown[:start]])
    return [_carried_entry(_carried_count(carried_before) + start, used), *shown[start:]]


def _counted(entries: Iterable[Entry]) -> int:
    """How many entries `entries` stand for, as `replayable` counts them: each streamed run
    as one, and what each `carried` entry says it holds."""
    joined = merged(entries)
    return sum(1 for e in joined if e.get("type") != _CARRIED) + _carried_count(joined)


def _carried_entry(count: int, used: frame.Usage) -> Entry:
    """The entry that stands for `count` entries no longer in the file, and their usage."""
    entry: dict[str, Any] = {
        "type": _CARRIED,
        "entries": count,
        "input_tokens": used.input_tokens,
        "output_tokens": used.output_tokens,
    }
    if used.cost_usd is not None:
        entry["cost_usd"] = used.cost_usd
    if used.cached_tokens:
        entry["cache_read_input_tokens"] = used.cached_tokens
    if used.uncounted:
        entry["uncounted"] = used.uncounted
    return entry


class History:
    """The file a ui config names (`history`): appended to as the transcript draws, read once
    when the app starts. A write that fails turns recording off and says why, once, through
    `failed`, rather than taking the app down. A trim that fails leaves the file as it was
    and says so in `warning` (recording goes on)."""

    def __init__(self, path: str, keep: int = 400) -> None:
        self.path = path
        self.keep = keep
        self.failed: str | None = None
        self.warning: str | None = None
        self.recorded: tuple[Entry, ...] = ()
        self._file: IO[str] | None = None
        self._count = 0  # entries the file stands for, as `_counted` counts them
        self._used = frame.Usage()  # and the usage they add up to

    async def __aenter__(self) -> History:
        """Read what was recorded so far into `recorded`, as the ui row starts; a file grown
        past twice `keep` entries is trimmed to its last `keep` first (`compacted`), so it
        never grows without bound and a resume reads a file of about one run's size."""
        recorded = self.read()
        trimmed = compacted(recorded, self.keep)
        if trimmed is not None and self._rewrite(trimmed):
            recorded = trimmed
        self.recorded = tuple(recorded)
        self._count, self._used = _counted(recorded), frame.total_usage(recorded)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.close()

    def read(self) -> list[Entry]:
        """Every entry recorded so far (none if the file isn't there yet), unreadable lines
        skipped. A file that is there and can't be read is none too, and says why (`failed`)."""
        try:
            lines = Path(self.path).read_text(errors="replace").splitlines()
        except FileNotFoundError, NotADirectoryError:
            return []
        except OSError as error:
            self.failed = f"history can't be read ({self.path}): {error.strerror or error}"
            return []
        return [entry for line in lines if (entry := _entry(line)) is not None]

    def _rewrite(self, entries: Sequence[Entry]) -> bool:
        """Replace the file with `entries`, whole or not at all; say whether it was."""
        temporary = f"{self.path}.trim"
        try:
            with open(temporary, "w", encoding="utf-8") as file:
                file.writelines(json.dumps(entry, default=str) + "\n" for entry in entries)
            os.replace(temporary, self.path)
        except OSError as error:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            self.warning = (
                f"history can't be trimmed ({self.path}): {error.strerror or error}; it is kept "
                "whole and grows until it can be (check the directory's space and permissions)"
            )
            return False
        return True

    def record(self, entry: Entry) -> None:
        """Append one entry; a line at a time, so a crash loses at most the one being written.

        The file is opened for appending, so `/clear` emptying it underneath is fine: the next
        write lands at the new end, after a `carried` entry for what was forgotten. Anything
        JSON can't hold is written as its `str`."""
        if self.failed is not None:
            return
        try:
            if self._file is None:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                self._file = open(self.path, "a", buffering=1, encoding="utf-8")  # noqa: SIM115
            if self._count and os.fstat(self._file.fileno()).st_size == 0:  # emptied underneath
                self._file.write(json.dumps(_carried_entry(self._count, self._used)) + "\n")
            self._file.write(json.dumps(entry, default=str) + "\n")
        except OSError as error:
            self.failed = f"history is not being kept ({self.path}): {error.strerror or error}"
            return
        self._count += 1
        if entry.get("type") == "usage":
            self._used = frame.add_usage(self._used, entry)

    def close(self) -> None:
        """Close the file, if it was opened."""
        if self._file is not None:
            self._file.close()
            self._file = None


def _entry(line: str) -> Entry | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) and isinstance(value.get("type"), str) else None
