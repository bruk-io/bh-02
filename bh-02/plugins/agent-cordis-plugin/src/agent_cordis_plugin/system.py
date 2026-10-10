"""The `system` value: the system prompt the loop sends, read fresh each time.

Organised as Claude Code's is: who the model is and what bh-02 is first (bh-02's own, naming no
tool: the tools are the rows' that register them), then where it is working (the directory and
the git branch), then the sections rows add: the memory row's instructions (CLAUDE.md and the
rest), how to extend bh-02, an extension's own, what a tool's row tells of it (`python`).
`describe` is the whole prompt as a function of what was found; `SystemPrompt.text` finds it
every time it is asked. The date is not in it: the prompt would read differently every
midnight, so the loop tells the date with the person's message instead.

It is a broker (paper 6.2): a row with something to tell the model `acquire`s a named section
(`add`), read with the rest each time, and its remover takes it out again when the row leaves.
Sections are told sorted by name (two of one name by their text), never in the order rows added
them: a row that adds its section again after a restart (`memory:auto` on every `/clear`) keeps
its place, so the prompt does not read as changed.

`agent:loop` calls `text()` on its `executor`, in a thread off the event loop, one call at a
time; so a section function runs there too and must not need the event loop.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from cordis_helpers import Hooks
from host_paths import Link, read_beneath

__all__ = ["SystemConfig", "SystemPrompt", "branch_of", "describe"]

_INTRO = (
    "You are the model in bh-02, a coding harness: a terminal app in which a person works with "
    "you on a project on their machine. Read before you change anything, change as little as the "
    "task needs, and say plainly what you did and what you could not do."
)
_HARNESS = (
    "bh-02 is a cordis composition: every part of it is a row, named in a layer file, that can be "
    "added, replaced or removed while it runs. You (the model row), the loop that sends you the "
    "conversation and runs your tool calls, each tool and where it runs, and the terminal app "
    "are each one. The person reshapes it with slash commands (/rows, /model NAME, /clear), "
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
        self._sections: Hooks[tuple[str, Callable[[], str]]] = Hooks()

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]:
        """Add `section` to the prompt under `name`, read each time the prompt is; returns its
        remover. A row `acquire`s one, so it leaves the prompt with the row. Where it goes is by
        `name`, not by when it was added."""
        return self._sections.add((name, section))

    def text(self) -> str:
        root = Path(self._config.root).resolve()
        try:
            branch = branch_of(_head(root))
        except OSError:  # no repository here (or a worktree's, whose .git is a file), or a link
            branch = None
        # the sections rows have added now: a snapshot, as the event loop may add or remove one
        # while this runs in the loop's worker thread
        read = sorted((name, section()) for name, section in self._sections)
        return describe(str(root), branch, [text for _, text in read])


def _head(root: Path) -> str:
    """The project's `.git/HEAD`, walked to from its root through no link and read only when it
    is a regular file with one name (`host_paths.read_beneath`): the model can write it, and a
    link there could lead to a file it may not read. Raises OSError when it is not."""
    found = read_beneath(root, (".git", "HEAD"), cap=_HEAD_LIMIT)
    if isinstance(found, Link):
        raise OSError(f"{root / '.git' / 'HEAD'} is a link")
    return found.decode("utf-8", errors="replace")
