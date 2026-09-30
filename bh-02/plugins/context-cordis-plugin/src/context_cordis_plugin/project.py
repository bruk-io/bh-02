"""The `system` value: what the model is told about where it is working, read fresh each time.

`describe` is the whole prompt as a function of what was found; `ProjectContext.text` finds
it (the directory, the git branch, the project's instructions file, what the kernel's jail can
read) every time it is asked, so an edit to CLAUDE.md reaches the next request without
reloading anything.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["ContextConfig", "ProjectContext", "Reads", "branch_of", "describe"]

_INTRO = (
    "You are a coding agent working in a repository on the person's machine. Read before you "
    "change anything, change as little as the task needs, and say plainly what you did and "
    "what you could not do."
)


@dataclass(frozen=True, slots=True)
class ContextConfig:
    """`root` is the project; `instructions` are the files, in order, whose first found is its
    own guidance to an agent; `max_chars` caps how much of it is sent."""

    root: str = "."
    instructions: Sequence[str] = ("CLAUDE.md", "AGENTS.md")
    max_chars: int = 20_000


@runtime_checkable
class Reads(Protocol):
    """What the context needs of the `kernel` value (CONTRACTS.md: kernel): the trees its jail
    lets a cell read, when that is all a cell can read (a Linux jail); empty otherwise."""

    def reads(self) -> tuple[str, ...]: ...


def describe(
    root: str,
    branch: str | None,
    today: str,
    guidance: tuple[str, str] | None,
    reads: Sequence[str] = (),
) -> str:
    """The system prompt, from what was found. `guidance` is (file name, its text); `reads`, the
    trees the kernel's jail reads when it reads by allowlist (a Linux jail), is said plainly,
    so the model spends no steps on reads that can't succeed."""
    lines = [_INTRO, "", f"Working directory: {root}"]
    if branch:
        lines.append(f"Git branch: {branch}")
    lines.append(f"Today: {today}")
    if reads:
        lines += [
            "",
            f"The jail your code runs in reads only these trees: {', '.join(reads)}. Nothing else "
            "exists in it, the person's home directory included (at most the path to an "
            "interpreter installed under it): no ~/.gitconfig, ~/.ssh, dotfiles or caches, so don't "
            "look for files outside these. git commits carry the person's name and email when git "
            "on their machine knows them.",
        ]
    if guidance is not None:
        name, text = guidance
        lines += ["", f"The project's own instructions ({name}):", "", text.strip()]
    return "\n".join(lines)


def branch_of(head: str) -> str | None:
    """The branch a `.git/HEAD` names, or None when it holds a detached commit."""
    ref = head.strip()
    return ref.removeprefix("ref: refs/heads/") if ref.startswith("ref: refs/heads/") else None


class ProjectContext:
    """Implements `System` (CONTRACTS.md: system) over one project directory, and what the
    kernel's jail can read."""

    def __init__(self, config: ContextConfig, kernel: Reads) -> None:
        self._config = config
        self._kernel = kernel

    def text(self) -> str:
        root = Path(self._config.root).resolve()
        head = root / ".git" / "HEAD"
        branch = branch_of(head.read_text(encoding="utf-8")) if head.is_file() else None
        today = datetime.date.today().isoformat()
        return describe(str(root), branch, today, self._guidance(root), self._kernel.reads())

    def _guidance(self, root: Path) -> tuple[str, str] | None:
        for name in self._config.instructions:
            path = root / name
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                cap = self._config.max_chars
                return name, text if len(text) <= cap else text[
                    :cap
                ] + f"\n... [{len(text) - cap} more chars]"
        return None
