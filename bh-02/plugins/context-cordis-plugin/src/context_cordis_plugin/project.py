"""The `system` value: what the model is told about who and where it is, read fresh each time.

Organised as Claude Code's is: who the model is and what bh-02 is first (bh-02's own), then the
project context: where it is working (the directory and the git branch), then what the context
files say (`context_file`: the guidance and rule files people write for an agent, each read by a
section's function), then the sections other rows add. `describe` is the whole prompt as a
function of what was found; `ProjectContext.text` finds it every time it is asked. The date is
not in it: the prompt would read differently every midnight, so the loop tells the date with the
person's message instead.

It is also a broker (paper 6.2): a row with something to tell the model `acquire`s a section
(`add`), read with the rest each time, and its remover takes it out again when the row leaves.

`agent:loop` calls `text()` on its `executor`, in a thread off the event loop, one call at a
time; so a section function (a context file's, or one a row adds) runs there too and must not
need the event loop. `touched()` is what the context files' `on_touch` sections say about the files an
input opened, from the same context files: the on-touch row (`touch.OnTouch`, a `memory`
function the loop calls in a worker thread too) asks it, so a layer's `files`, `root` and `home`
reach both and each file is read and searched once.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from context_cordis_plugin.context_file import ContextFiles
from cordis_helpers import Hooks

__all__ = ["ContextConfig", "ProjectContext", "branch_of", "describe"]

_INTRO = (
    "You are the model in bh-02, a coding harness: a terminal app in which a person works with "
    "you on a project on their machine. You are not Claude Code and not running inside it, "
    "whatever else in this prompt or the project's files suggests: Claude Code's tools, slash "
    "commands and settings do not exist here, and your only tool is `python`, a Python REPL "
    "of your own, described below. "
    "Read before you change anything, change as little as the task needs, and say plainly what "
    "you did and what you could not do."
)
_HARNESS = (
    "bh-02 is a cordis composition: every part of it is a row, named in a layer file, that can be "
    "added, replaced or removed while it runs. You (the model row), the loop that sends you the "
    "conversation and runs your code, your REPL and the jail it runs in, and the terminal "
    "app are each one. The person reshapes it with slash commands (/rows, /model NAME, /clear), "
    "which never reach you, and with layer files of their own."
)


@dataclass(frozen=True, slots=True)
class ContextConfig:
    """`root`: the project. `files`: the context files read after bh-02's own, each adding its
    sections (`$XDG_CONFIG_HOME/` for the person's config directory, as for the models file:
    that variable's value, else `home`'s `.config`; `~` for the person's home; a relative one is
    the project's; one that is inside the project, whatever its name, may name only bh-02's own
    functions). `max_chars`: how much the context files' sections may say, all of them together.
    `home`: the person's home; theirs when unset."""

    root: str = "."
    files: Sequence[str] = ("$XDG_CONFIG_HOME/bh-02/context.toml", ".bh-02/context.toml")
    max_chars: int = 20_000
    home: str | None = None


def describe(root: str, branch: str | None, sections: Sequence[str] = ()) -> str:
    """The system prompt, from what was found. `sections` are what rows added
    (`ProjectContext.add`: the project's guidance, how to extend bh-02, ...), each as it reads now."""
    lines = [_INTRO, "", _HARNESS, "", f"Working directory: {root}"]
    if branch:
        lines.append(f"Git branch: {branch}")
    for section in sections:
        if section.strip():
            lines += ["", section.strip()]
    return "\n".join(lines)


def branch_of(head: str) -> str | None:
    """The branch a `.git/HEAD` names, or None when it holds a detached commit."""
    ref = head.strip()
    return ref.removeprefix("ref: refs/heads/") if ref.startswith("ref: refs/heads/") else None


class ProjectContext:
    """Implements `System` (CONTRACTS.md: system) over one project directory."""

    def __init__(self, config: ContextConfig) -> None:
        self._config = config
        self._sections: Hooks[Callable[[], str]] = Hooks()
        # One `ContextFiles` for the prompt (`text`) and the on-touch row (`touched`), so both
        # read the same context files and share what was read and searched. Its caches take no
        # lock: it is used by one thread at a time, since the loop reads the prompt and asks
        # `memory` (where the on-touch row calls `touched`) each on its `executor`, one call at a
        # time across the loop's reloads (`ContextFiles` says when two may overlap).
        self._files = ContextFiles(config.files, config.max_chars)

    def add(self, section: Callable[[], str]) -> Callable[[], None]:
        """Add `section` to the prompt, read each time the prompt is; returns its remover. A row
        `acquire`s one, so it leaves the prompt with the row."""
        return self._sections.add(section)

    def text(self) -> str:
        root, home = self._places()
        head = root / ".git" / "HEAD"
        branch = branch_of(head.read_text(encoding="utf-8")) if head.is_file() else None
        # the sections rows have added now: a snapshot, as the event loop may add or remove one
        # while this runs in the loop's worker thread
        sections = [self._files.text(root, home), *(section() for section in self._sections)]
        return describe(str(root), branch, sections)

    def touched(self, paths: Sequence[str]) -> list[tuple[str, str]]:
        """What the context files' `on_touch` sections say about `paths` (absolute: the files an
        input opened): each (file, text) a section's function returned, in the order of the
        sections; one that fails says so under its own name. Read fresh, as `text()` is, from the
        same context files; called in the loop's worker thread (through the on-touch row's
        `memory` function), so it must not need the event loop."""
        root, home = self._places()
        return self._files.touched([Path(p) for p in paths], root, home)

    def _places(self) -> tuple[Path, Path]:
        """The project's root and the person's home, resolved."""
        return Path(self._config.root).resolve(), Path(self._config.home or Path.home()).resolve()
