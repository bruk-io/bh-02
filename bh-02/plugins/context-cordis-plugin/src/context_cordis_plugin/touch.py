"""The `memory` function of the context files: what their `on_touch` sections say about the
files an input opened (`system.touched`), told with that input's result. Claude Code's on-demand
loading, where a path-scoped rule or a subdirectory's CLAUDE.md arrives when the model first
works on a file it covers, with the files an input opened (`kernel.touched()`) standing in for
Claude Code's Read, Write and Edit.

The context files are the `system` value's own (`ProjectContext.touched`), so a layer's `files`,
`root` and `home` on the `system` row reach the prompt and this alike, and each file is read and
searched once. What this keeps is what it told this conversation; what the conversation was told
before it began (a resumed session's) is in the `transcript`, after the results there.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = ["Memory", "OnTouch", "System", "Transcript"]

_MAX_CHARS = 20_000  # what one input's result is told at most, as the prompt's sections by default


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
    it."""

    @property
    def messages(self) -> Sequence[Mapping[str, Any]]: ...


def _results(messages: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """What each input in `messages` (a transcript's) was answered with: its result, then the
    notes told with it, each after a blank line (the loop's `tool` entries)."""
    return tuple(str(m.get("content") or "") for m in messages if m.get("role") == "tool")


def _told_in(results: Sequence[str], text: str) -> bool:
    """Whether `text` was told after a result in `results` (`_results`): its exact text, after a
    blank line, with another blank line or the entry's end after it. Not when a result begins
    with it, nor when it was cut short there (a note over `_MAX_CHARS`)."""
    note = f"\n\n{text}"
    return any(result.endswith(note) or f"{note}\n\n" in result for result in results)


class OnTouch:
    """A `memory` function over what `system`'s context files' `on_touch` sections say: given an
    input (`touched`, ...), what they say about the files it opened that this conversation has
    not been told (a file whose text changed since is told again); '' for nothing. At most
    `_MAX_CHARS` of it.

    What the conversation was told before this began (a resumed session's, or this one's before
    the row reloaded) is in its `transcript`: read at the first input that opens a file, and
    each text checked against it once, the first time `system` says it."""

    def __init__(self, system: System, transcript: Transcript) -> None:
        self._system = system
        self._transcript = transcript
        # (file, what was said), told this conversation or checked against what was told before
        # this began. Called in the loop's worker thread, one input's at a time, so it takes no
        # lock.
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
        said = self._system.touched([str(t) for t in touched])
        unseen = [item for item in dict.fromkeys(said) if item not in self._told]
        self._told.update(unseen)
        new = [text for _, text in unseen if not _told_in(before, text)]
        text = "\n\n".join(new)
        more = len(text) - _MAX_CHARS
        return text if more <= 0 else f"{text[:_MAX_CHARS]}\n... [{more} more chars of guidance]"
