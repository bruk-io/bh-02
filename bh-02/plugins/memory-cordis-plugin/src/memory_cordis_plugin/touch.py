"""The `notes` function of memory: what loads on demand for the files a call opened
(`memory.touched`), told with that call's result. Claude Code's on-demand loading, where a
path-scoped rule or a subdirectory's CLAUDE.md arrives when the model first works on a file it
covers, with the files a call opened (its tool's `touched`: the python tool's inputs, heard in
its REPL) standing in for Claude Code's Read, Write and Edit. A memory file the model opened
itself is in the conversation already, so it is not told after that, as Claude Code does not
load one its own tools read.

The memory files are the `memory` value's (`Memory.touched`), so the memory row's `root`, `home`,
`instruction_files` and `excludes` reach the prompt and this alike. What this keeps is what it
told this conversation; what the conversation was told before it began (a resumed session's) is
in the `transcript`'s `tool` entries, each the notes told with a result (`notes`).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import accumulate
from typing import Any, Protocol, runtime_checkable

__all__ = ["Memory", "Notes", "OnTouch", "Transcript"]

_MAX_CHARS = 20_000  # what one input's result is told at most, as the prompt's sections by default
_CUT = "\n... ["  # the mark of a note cut short (`_cut`'s)
# How a text begins in a note of this row's, so where the one before it ends: a first line `From
# FILE, instructions ...` or `From FILE, a rule for ...` (`Memory.touched`). A file a text imports
# follows within that text (`From FILE, imported by ...`, `(bh-02 did not import ...)`), so it
# begins nothing: a text whose imports changed since reads as changed, and is told again.
_FROM, _HEADS = "From ", (", instructions ", ", a rule for ")
# What may follow a text told whole in a `tool` entry from before the loop kept `notes`, where its
# note ends (the entry's end aside): the mark of a note cut short, or another note: bh-02's begin
# with "(" (a shell hint, a function that failed, a change in the instructions), memory's with
# "From ".
_ENDS = (_CUT, "\n\n(", "\n\nFrom ")


@runtime_checkable
class Notes(Protocol):
    """What the on-touch row needs of the `notes` value (CONTRACTS.md: notes): a function added,
    and its remover back."""

    def add(self, fn: Callable[[Mapping[str, Any]], str]) -> Callable[[], None]: ...


@runtime_checkable
class Memory(Protocol):
    """What the on-touch row needs of the `memory` value (CONTRACTS.md: memory): what loads on
    demand for the files an input opened (absolute), each (file, text), called in the loop's
    worker thread."""

    def touched(self, paths: Sequence[str]) -> Sequence[tuple[str, str]]: ...


@runtime_checkable
class Transcript(Protocol):
    """What the on-touch row needs of the `transcript` value (CONTRACTS.md: transcript): the
    conversation so far, whose `tool` entries carry each input's result and the notes told with
    it (`notes`)."""

    @property
    def messages(self) -> Sequence[Mapping[str, Any]]: ...


def _before(messages: Iterable[Mapping[str, Any]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What the inputs in `messages` (a transcript's) were told: the notes the loop kept on each
    `tool` entry (`notes`), and the text of each entry from before it kept them (the input's
    result, then the notes told with it, each after a blank line), which is searched instead."""
    notes: list[str] = []
    texts: list[str] = []
    for m in messages:
        if m.get("role") != "tool":
            continue
        kept = m.get("notes")
        if isinstance(kept, list | tuple):
            notes += [note for note in kept if isinstance(note, str)]
        else:
            texts.append(str(m.get("content") or ""))
    return tuple(notes), tuple(texts)


def _holds(note: str, text: str) -> bool:
    """Whether `note`, a note told with a result, tells `text` whole: as one of the texts this
    row's notes join with a blank line (`_cut`), at the note's start or after a blank line, and
    ending where the note does, where it was cut short, or where the next text begins (`_begins`):
    not followed by more of itself (a file cut back since: the paragraphs now gone follow it)."""
    at = note.find(text)
    while at != -1:
        end = at + len(text)
        if (at == 0 or note[at - 2 : at] == "\n\n") and (
            end == len(note)
            or note.startswith(_CUT, end)
            or (note.startswith("\n\n", end) and _begins(note, end + 2))
        ):
            return True
        at = note.find(text, at + 1)
    return False


def _begins(note: str, at: int) -> bool:
    """Whether a text of this row's begins at `at` in `note`: `From FILE, ...` with one of
    `_HEADS` in its first line."""
    if not note.startswith(_FROM, at):
        return False
    ends = note.find("\n", at)
    line = note[at:] if ends == -1 else note[at:ends]
    return any(head in line for head in _HEADS)


def _told_in(results: Sequence[str], text: str) -> bool:
    """Whether `text` was told in `results`, the text of `tool` entries from before the loop kept
    `notes` (`_before`): its exact text, after a blank line, where a note ends (the entry's end, or
    `_ENDS`). Not at an entry's start, nor cut short (a note over `_MAX_CHARS`), nor followed by
    more of itself (a file cut back since: the paragraphs now gone follow it). Where the result
    ends is not marked, so a text an input printed after a blank line counts too."""
    note = f"\n\n{text}"
    for result in results:
        at = result.find(note)
        while at != -1:
            end = at + len(note)
            if end == len(result) or result.startswith(_ENDS, end):
                return True
            at = result.find(note, at + 1)
    return False


def _cut(texts: Sequence[str]) -> tuple[str, int]:
    """The note telling `texts`, each after a blank line: at most `_MAX_CHARS` of it, the rest
    counted after it. And how many of them it tells: each it holds whole, so one the cap cuts, or
    leaves out, is told by a later note; and the first even when cut, since it alone is longer
    than any note holds."""
    text = "\n\n".join(texts)
    more = len(text) - _MAX_CHARS
    if more <= 0:
        return text, len(texts)
    whole = sum(1 for end in accumulate(len(t) + 2 for t in texts) if end - 2 <= _MAX_CHARS)
    return f"{text[:_MAX_CHARS]}\n... [{more} more chars of memory]", max(whole, 1)


class OnTouch:
    """A `notes` function over what `memory` loads on demand: given a call (`name`, `input`,
    `result`, `touched`), what loads for the files it opened that this conversation has not been
    told (a file whose text changed since is told again, one the model opened itself never); ''
    for nothing. At most `_MAX_CHARS` of it (`_cut`): a text told only in part, cut by that or
    left out, is not told yet, so the next call that opens a file it covers tells it whole; one
    longer than that by itself is told once, cut.

    What the conversation was told before this began (a resumed session's, or this one's before
    the row reloaded) is in its `transcript`, the notes the loop kept on each `tool` entry: read
    at the first input that opens a file, and each text checked against them until it is told.

    It also answers `access` before a write (`before_write`): a file covered by what this
    conversation has not been told is not written until it has been, so the instructions arrive
    before the file changes, as Claude Code's do (its Edit and Write refuse a file not Read
    first). The refused file is among what the call touched, so they follow as its note."""

    def __init__(self, memory: Memory, transcript: Transcript) -> None:
        self._memory = memory
        self._transcript = transcript
        # the files the conversation's inputs opened: a memory file among them was read whole by
        # the model, so it is not told after that
        self._opened: set[str] = set()
        # (file, what was said), told this conversation (whole, or as much as a note holds) or
        # before this began. Called one call at a time, before a write while an input runs and as a
        # note on the loop's `executor` after it, never both at once, so it takes no lock.
        self._told: set[tuple[str, str]] = set()
        # what the inputs before this began were told (`_before`): None until the first input
        # that opens a file reads it
        self._before: tuple[tuple[str, ...], tuple[str, ...]] | None = None

    def __call__(self, input: Mapping[str, Any]) -> str:
        touched = input.get("touched") or ()
        if not touched:
            return ""
        self._opened.update(str(t) for t in touched)
        new = self._unseen([str(t) for t in touched])
        note, told = _cut([text for _, text in new])
        self._told.update(new[:told])
        return note

    def before_write(self, path: str) -> str | None:
        """An `access` function (CONTRACTS.md: access): why `path` may not be written yet, while
        what loads on demand for it holds a text this conversation has not been told; None once it
        has been, and for a memory file itself (its own text is what the model is changing)."""
        files = [file for file, _ in self._unseen([path]) if file != path]
        if not files:
            return None
        return (
            f"instructions that apply to it ({', '.join(dict.fromkeys(files))}) have not been told in "
            "this conversation; they come with this input's result, and nothing was written to it: "
            "read them, then write it again"
        )

    def _unseen(self, paths: Sequence[str]) -> list[tuple[str, str]]:
        """What loads on demand for `paths` that this conversation has not been told, as (file,
        text): none the model opened itself, and none the transcript says was told before this
        began (read once, at the first call that asks), which are marked told here."""
        if self._before is None:
            self._before = _before(self._transcript.messages)
        notes, texts = self._before
        said = self._memory.touched(list(paths))
        unseen = [
            item for item in dict.fromkeys(said) if item not in self._told and item[0] not in self._opened
        ]
        self._told.update(
            item
            for item in unseen
            if any(_holds(note, item[1]) for note in notes) or _told_in(texts, item[1])
        )
        return [item for item in unseen if item not in self._told]
