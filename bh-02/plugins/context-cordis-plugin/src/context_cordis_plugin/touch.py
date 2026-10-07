"""The `memory` function of the context files: what their `on_touch` sections say about the
files an input opened (`ContextFiles.touched`), told with that input's result. Claude Code's
on-demand loading, where a path-scoped rule or a subdirectory's CLAUDE.md arrives when the model
first works on a file it covers, with the files an input opened (`kernel.touched()`) standing
in for Claude Code's Read, Write and Edit.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from context_cordis_plugin.context_file import ContextFiles
from context_cordis_plugin.project import ContextConfig

__all__ = ["Memory", "OnTouch"]


@runtime_checkable
class Memory(Protocol):
    """What the on-touch row needs of the `memory` value (CONTRACTS.md: memory): a function
    added, and its remover back."""

    def add(self, fn: Callable[[Mapping[str, Any]], str]) -> Callable[[], None]: ...


class OnTouch:
    """A `memory` function over the context files `config` names: given an input (`touched`,
    ...), what their `on_touch` sections say about the files it opened that this conversation
    has not been told (a file whose text changed since is told again); '' for nothing. At most
    `max_chars` of it."""

    def __init__(self, config: ContextConfig) -> None:
        self._config = config
        self._files = ContextFiles(config.files, config.max_chars)
        # (file, what was said), told this conversation. Called in the loop's worker thread, one
        # input's at a time, so it and the files' caches take no lock.
        self._told: set[tuple[str, str]] = set()

    def __call__(self, input: Mapping[str, Any]) -> str:
        touched = input.get("touched") or ()
        if not touched:
            return ""
        root = Path(self._config.root).resolve()
        home = Path(self._config.home or Path.home()).resolve()
        said = self._files.touched([Path(str(t)) for t in touched], root, home)
        new = [item for item in dict.fromkeys(said) if item not in self._told]
        self._told.update(new)
        text = "\n\n".join(text for _, text in new)
        cap = self._config.max_chars
        return text if len(text) <= cap else f"{text[:cap]}\n... [{len(text) - cap} more chars of guidance]"
