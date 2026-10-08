"""The `notes` function of memory: what loads on demand for the files an input opened
(`memory.touched`), told with that input's result. Claude Code's on-demand loading, where a
path-scoped rule or a subdirectory's CLAUDE.md arrives when the model first works on a file it
covers, with the files an input opened (`kernel.touched()`) standing in for Claude Code's Read,
Write and Edit. A memory file the model opened itself is in the conversation already, so it is
not told after that, as Claude Code does not load one its own tools read.

The memory files are the `memory` value's (`Memory.touched`), so the memory row's `root`, `home`,
`instruction_files` and `excludes` reach the prompt and this alike. What this keeps is what it
told this conversation; what the conversation was told before it began (a resumed session's) is
in the `transcript`'s `tool` entries, with the results.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import accumulate
from typing import Any, Protocol, runtime_checkable

__all__ = ["Memory", "Notes", "OnTouch", "Transcript"]

_MAX_CHARS = 20_000  # what one input's result is told at most, as the prompt's sections by default
# What may follow a text told whole in a `tool` entry, where its note ends (the entry's end aside):
# the mark of a note cut short (`OnTouch`'s), or another note: bh-02's begin with "(" (a shell
# hint, a function that failed, a change in the instructions), memory's with "From ".
_ENDS = ("\n... [", "\n\n(", "\n\nFrom ")


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
    it."""

    @property
    def messages(self) -> Sequence[Mapping[str, Any]]: ...


def _results(messages: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """What each input in `messages` (a transcript's) was answered with: its result, then the
    notes told with it, each after a blank line (the loop's `tool` entries)."""
    return tuple(str(m.get("content") or "") for m in messages if m.get("role") == "tool")


def _told_in(results: Sequence[str], text: str) -> bool:
    """Whether `text` was told in `results` (`_results`): its exact text, after a blank line,
    where a note ends (the entry's end, or `_ENDS`). Not at an entry's start, nor cut short (a note
    over `_MAX_CHARS`), nor followed by more of itself (a file cut back since: the paragraphs now
    gone follow it). Where the result ends is not marked, so a text an input printed after a blank
    line counts too."""
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
    """A `notes` function over what `memory` loads on demand: given an input (`touched`, ...),
    what loads for the files it opened that this conversation has not been told (a file whose
    text changed since is told again, one the model opened itself never); '' for nothing. At most
    `_MAX_CHARS` of it (`_cut`): a text told only in part, cut by that or left out, is not told
    yet, so the next input that opens a file it covers tells it whole; one longer than that by
    itself is told once, cut.

    What the conversation was told before this began (a resumed session's, or this one's before
    the row reloaded) is in its `transcript`: read at the first input that opens a file, and
    each text checked against it until it is told."""

    def __init__(self, memory: Memory, transcript: Transcript) -> None:
        self._memory = memory
        self._transcript = transcript
        # the files the conversation's inputs opened: a memory file among them was read whole by
        # the model, so it is not told after that
        self._opened: set[str] = set()
        # (file, what was said), told this conversation (whole, or as much as a note holds) or
        # before this began. Called on the loop's `executor`, one call at a time, so it takes no lock.
        self._told: set[tuple[str, str]] = set()
        # what the inputs before this began were answered with: None until the first input that
        # opens a file reads them
        self._before: tuple[str, ...] | None = None

    def __call__(self, input: Mapping[str, Any]) -> str:
        touched = input.get("touched") or ()
        if not touched:
            return ""
        if self._before is None:
            self._before = _results(self._transcript.messages)
        before = self._before
        self._opened.update(str(t) for t in touched)
        said = self._memory.touched([str(t) for t in touched])
        unseen = [
            item for item in dict.fromkeys(said) if item not in self._told and item[0] not in self._opened
        ]
        self._told.update(item for item in unseen if _told_in(before, item[1]))
        new = [item for item in unseen if item not in self._told]
        note, told = _cut([text for _, text in new])
        self._told.update(new[:told])
        return note
