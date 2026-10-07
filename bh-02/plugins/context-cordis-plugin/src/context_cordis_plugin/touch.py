"""The `memory` function of the context files: what their `on_touch` sections say about the
files an input opened (`system.touched`), told with that input's result. Claude Code's on-demand
loading, where a path-scoped rule or a subdirectory's CLAUDE.md arrives when the model first
works on a file it covers, with the files an input opened (`kernel.touched()`) standing in for
Claude Code's Read, Write and Edit.

The context files are the `system` value's own (`ProjectContext.touched`), so a layer's `files`,
`root` and `home` on the `system` row reach the prompt and this alike, and each file is read and
searched once. What this keeps is what it told this conversation.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = ["Memory", "OnTouch", "System"]

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


class OnTouch:
    """A `memory` function over what `system`'s context files' `on_touch` sections say: given an
    input (`touched`, ...), what they say about the files it opened that this conversation has
    not been told (a file whose text changed since is told again); '' for nothing. At most
    `_MAX_CHARS` of it."""

    def __init__(self, system: System) -> None:
        self._system = system
        # (file, what was said), told this conversation. Called in the loop's worker thread, one
        # input's at a time, so it takes no lock.
        self._told: set[tuple[str, str]] = set()

    def __call__(self, input: Mapping[str, Any]) -> str:
        touched = input.get("touched") or ()
        if not touched:
            return ""
        said = self._system.touched([str(t) for t in touched])
        new = [item for item in dict.fromkeys(said) if item not in self._told]
        self._told.update(new)
        text = "\n\n".join(text for _, text in new)
        more = len(text) - _MAX_CHARS
        return text if more <= 0 else f"{text[:_MAX_CHARS]}\n... [{more} more chars of guidance]"
