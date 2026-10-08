"""The `system` value: the system prompt the loop sends, read fresh each time.

Organised as Claude Code's is: who the model is and what bh-02 is first (bh-02's own), then
where it is working (the directory and the git branch), then the sections rows add: the
memory row's instructions (CLAUDE.md and the rest), how to extend bh-02, an extension's own.
`describe` is the whole prompt as a function of what was found; `SystemPrompt.text` finds it
every time it is asked. The date is not in it: the prompt would read differently every
midnight, so the loop tells the date with the person's message instead.

It is a broker (paper 6.2): a row with something to tell the model `acquire`s a section
(`add`), read with the rest each time, and its remover takes it out again when the row leaves.

`agent:loop` calls `text()` on its `executor`, in a thread off the event loop, one call at a
time; so a section function runs there too and must not need the event loop.
"""

import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from cordis_helpers import Hooks

__all__ = ["SystemConfig", "SystemPrompt", "branch_of", "describe"]

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
_HEAD_LIMIT = 4096  # a `.git/HEAD` names a branch or a commit: no more is read


@dataclass(frozen=True, slots=True)
class SystemConfig:
    """`root`: the project, whose directory and branch the prompt names."""

    root: str = "."


def describe(root: str, branch: str | None, sections: Sequence[str] = ()) -> str:
    """The system prompt, from what was found. `sections` are what rows added
    (`SystemPrompt.add`: the memory row's instructions, how to extend bh-02, ...), each as it
    reads now."""
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


class SystemPrompt:
    """Implements `system` (CONTRACTS.md: system) over one project directory."""

    def __init__(self, config: SystemConfig) -> None:
        self._config = config
        self._sections: Hooks[Callable[[], str]] = Hooks()

    def add(self, section: Callable[[], str]) -> Callable[[], None]:
        """Add `section` to the prompt, read each time the prompt is; returns its remover. A row
        `acquire`s one, so it leaves the prompt with the row."""
        return self._sections.add(section)

    def text(self) -> str:
        root = Path(self._config.root).resolve()
        try:
            branch = branch_of(_head(root))
        except OSError:  # no repository here (or a worktree's, whose .git is a file), or a link
            branch = None
        # the sections rows have added now: a snapshot, as the event loop may add or remove one
        # while this runs in the loop's worker thread
        return describe(str(root), branch, [section() for section in self._sections])


def _head(root: Path) -> str:
    """The project's `.git/HEAD`, walked to from its root through no link (`O_NOFOLLOW` on
    each part) and read only when it is a regular file with one name: the model can write it,
    and a link there could lead to a file it may not read. Raises OSError when it is not."""
    here = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        git = os.open(".git", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=here)
    finally:
        os.close(here)
    try:
        opened = os.open("HEAD", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=git)
    finally:
        os.close(git)
    with os.fdopen(opened, "rb") as file:
        found = os.fstat(file.fileno())
        if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            raise OSError(f"{root / '.git' / 'HEAD'} is not a regular file with one name")
        return file.read(_HEAD_LIMIT).decode("utf-8", errors="replace")
