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
    "You are the model in bh-02, a coding harness: a terminal app in which a person works with "
    "you on a project on their machine. You are not Claude Code and not running inside it, "
    "whatever else in this prompt or the project's files suggests: Claude Code's tools, slash "
    "commands and settings do not exist here, and your only tool is the one described below. "
    "Read before you change anything, change as little as the task needs, and say plainly what "
    "you did and what you could not do."
)
_HARNESS = (
    "bh-02 is a cordis composition: every part of it is a row, named in a layer file, that can be "
    "added, replaced or removed while it runs. You (the model row), the loop that sends you the "
    "conversation and runs your code, the kernel and jail your code runs in, and the terminal "
    "app are each one. The person reshapes it with slash commands (/rows, /model NAME, /clear), "
    "which never reach you, and with layer files of their own."
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
    lines = [_INTRO, "", _HARNESS, "", f"Working directory: {root}"]
    if branch:
        lines.append(f"Git branch: {branch}")
    lines.append(f"Today: {today}")
    if guidance is not None:
        name, text = guidance
        lines += [
            "",
            f"The project's own instructions ({name}), written for whichever agent works here: "
            "where they name Claude Code or another agent, they mean you, and where they name its "
            "tools, do the same in Python.",
            "",
            text.strip(),
        ]
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
