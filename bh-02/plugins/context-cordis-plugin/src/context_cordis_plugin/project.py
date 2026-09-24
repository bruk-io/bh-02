"""The `system` value: what the model is told about where it is working, read fresh each time.

`describe` is the whole prompt as a function of what was found; `ProjectContext.text` finds
it (the directory, the git branch, the project's instructions file) every time it is asked,
so an edit to CLAUDE.md reaches the next request without reloading anything.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ContextConfig", "ProjectContext", "branch_of", "describe"]

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


def describe(root: str, branch: str | None, today: str, guidance: tuple[str, str] | None) -> str:
    """The system prompt, from what was found. `guidance` is (file name, its text)."""
    lines = [_INTRO, "", f"Working directory: {root}"]
    if branch:
        lines.append(f"Git branch: {branch}")
    lines.append(f"Today: {today}")
    if guidance is not None:
        name, text = guidance
        lines += ["", f"The project's own instructions ({name}):", "", text.strip()]
    return "\n".join(lines)


def branch_of(head: str) -> str | None:
    """The branch a `.git/HEAD` names, or None when it holds a detached commit."""
    ref = head.strip()
    return ref.removeprefix("ref: refs/heads/") if ref.startswith("ref: refs/heads/") else None


class ProjectContext:
    """Implements `System` (CONTRACTS.md: system) over one project directory."""

    def __init__(self, config: ContextConfig) -> None:
        self._config = config

    def text(self) -> str:
        root = Path(self._config.root).resolve()
        head = root / ".git" / "HEAD"
        branch = branch_of(head.read_text(encoding="utf-8")) if head.is_file() else None
        return describe(str(root), branch, datetime.date.today().isoformat(), self._guidance(root))

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
