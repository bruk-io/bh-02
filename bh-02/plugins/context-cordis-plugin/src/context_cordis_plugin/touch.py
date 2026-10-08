"""The `memory` function of the context files: what their `on_touch` sections say about the
files an input opened (`system.touched`), told with that input's result. Claude Code's on-demand
loading, where a path-scoped rule or a subdirectory's CLAUDE.md arrives when the model first
works on a file it covers, with the files an input opened (`kernel.touched()`) standing in for
Claude Code's Read, Write and Edit.

The context files are the `system` value's own (`ProjectContext.touched`), so a layer's `files`,
`root` and `home` on the `system` row reach the prompt and this alike, and each file is read and
searched once. What this keeps is what it told this conversation; what the conversation was told
before it began (a resumed session's) is in the `transcript`'s `tool` entries, each the notes told
with a result (`notes`).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import accumulate
from typing import Any, Protocol, runtime_checkable

__all__ = ["Memory", "OnTouch", "System", "Transcript"]

_MAX_CHARS = 20_000  # what one input's result is told at most, as the prompt's sections by default
_CUT = "\n... ["  # the mark of a note cut short (`_cut`'s)
# How a text begins in a note of this row's, so where the one before it ends: bh-02's own on-touch
# functions' with a first line `From FILE, guidance for work under ...` or `From FILE, a rule for
# ...` (`sections.place_touched`, `sections.rules_touched`); a section that failed with
# `_FAILED` (`ContextFiles.touched`). Another function's text, whatever it begins with, is not
# taken for more of the one before it, which is then told again after a resume: told twice
# rather than never.
_FROM, _HEADS = "From ", (", guidance for work under ", ", a rule for ")
_FAILED = "(bh-02 could not make the section "
# What may follow a text told whole in a `tool` entry from before the loop kept `notes`, where its
# note ends (the entry's end aside): the mark of a note cut short, or another note: bh-02's begin
# with "(" (a shell hint, a function that failed, a change in the instructions), the context
# files' with "From ".
_ENDS = (_CUT, "\n\n(", "\n\nFrom ")


@runtime_checkable
class Memory(Protocol):
    """What the on-touch row needs of the `memory` value (CONTRACTS.md: memory): a function
    added, and its remover back."""

    def add(self, fn: Callable[[Mapping[str, Any]], str]) -> Callable[[], None]: ...


@runtime_checkable
class System(Protocol):
    """What the on-touch row needs of the `system` value (CONTRACTS.md: system): what the
    context files' `on_touch` sections say about the files an input opened (absolute), each
    (file, text), called in the loop's worker thread."""

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
        if (at == 0 or (at >= 2 and note[at - 2 : at] == "\n\n")) and (
            end == len(note)
            or note.startswith(_CUT, end)
            or (note.startswith("\n\n", end) and _begins(note, end + 2))
        ):
            return True
        at = note.find(text, at + 1)
    return False


def _begins(note: str, at: int) -> bool:
    """Whether a text begins at `at` in `note`: one of bh-02's own on-touch functions' (`From
    FILE, ...` with one of `_HEADS` in its first line), or a section's that failed (`_FAILED`)."""
    if note.startswith(_FAILED, at):
        return True
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
    return f"{text[:_MAX_CHARS]}\n... [{more} more chars of guidance]", max(whole, 1)


class OnTouch:
    """A `memory` function over what `system`'s context files' `on_touch` sections say: given an
    input (`touched`, ...), what they say about the files it opened that this conversation has
    not been told (a file whose text changed since is told again); '' for nothing. At most
    `_MAX_CHARS` of it (`_cut`): a text told only in part, cut by that or left out, is not told
    yet, so the next input that opens a file it covers tells it whole; one longer than that by
    itself is told once, cut.

    What the conversation was told before this began (a resumed session's, or this one's before
    the row reloaded) is in its `transcript`, the notes the loop kept on each `tool` entry: read
    at the first input that opens a file, and each text checked against them until it is told."""

    def __init__(self, system: System, transcript: Transcript) -> None:
        self._system = system
        self._transcript = transcript
        # (file, what was said), told this conversation (whole, or as much as a note holds) or
        # before this began. Called on the loop's `executor`, one call at a time, so it takes no lock.
        self._told: set[tuple[str, str]] = set()
        # what the inputs before this began were told (`_before`): None until the first input
        # that opens a file reads it
        self._before: tuple[tuple[str, ...], tuple[str, ...]] | None = None

    def __call__(self, input: Mapping[str, Any]) -> str:
        touched = input.get("touched") or ()
        if not touched:
            return ""
        if self._before is None:
            self._before = _before(self._transcript.messages)
        notes, texts = self._before
        said = self._system.touched([str(t) for t in touched])
        unseen = [item for item in dict.fromkeys(said) if item not in self._told]
        self._told.update(
            item
            for item in unseen
            if any(_holds(note, item[1]) for note in notes) or _told_in(texts, item[1])
        )
        new = [item for item in unseen if item not in self._told]
        note, told = _cut([text for _, text in new])
        self._told.update(new[:told])
        return note
