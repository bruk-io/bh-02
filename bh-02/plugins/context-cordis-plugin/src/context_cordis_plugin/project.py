"""The `system` value: what the model is told about where it is working, read fresh each time.

`describe` is the whole prompt as a function of what was found; `ProjectContext.text` finds
it (the directory, the git branch, the project's instructions file) every time it is asked,
so an edit to CLAUDE.md reaches the model with its next message without reloading anything
(the loop tells it as a change, keeping the prompt the conversation began with).

It is also a broker (paper 6.2): a row with something to tell the model `acquire`s a section
(`add`), read with the rest each time, and its remover takes it out again when the row leaves.
"""

import datetime
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

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
    """`root` is the project; `instructions` are the files, in order, whose first found is its
    own guidance to an agent; `max_chars` caps how much of it is sent."""

    root: str = "."
    instructions: Sequence[str] = ("CLAUDE.md", "AGENTS.md")
    max_chars: int = 20_000


def describe(
    root: str,
    branch: str | None,
    today: str,
    guidance: tuple[str, str] | None,
    sections: Sequence[str] = (),
) -> str:
    """The system prompt, from what was found. `guidance` is (file name, its text); `sections`
    are what rows added (`ProjectContext.add`), each as it reads now."""
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

    def add(self, section: Callable[[], str]) -> Callable[[], None]:
        """Add `section` to the prompt, read each time the prompt is; returns its remover. A row
        `acquire`s one, so it leaves the prompt with the row."""
        return self._sections.add(section)

    def text(self) -> str:
        root = Path(self._config.root).resolve()
        head = root / ".git" / "HEAD"
        branch = branch_of(head.read_text(encoding="utf-8")) if head.is_file() else None
        today = datetime.date.today().isoformat()
        sections = [section() for section in self._sections]
        return describe(str(root), branch, today, self._guidance(root), sections)

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
