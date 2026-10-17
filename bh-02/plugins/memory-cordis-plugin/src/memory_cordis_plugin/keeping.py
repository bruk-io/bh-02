"""The `memory` tool, as pure functions: what a call asks (`understood`), how a memory is written
(`topic_text`, `index_line`) and how MEMORY.md's lines for it are kept (`with_line`).

A memory is a topic file `NAME.md` opening with `name`, `description` and `type` frontmatter, and
one line for it in MEMORY.md, the index. A call is refused, with what to fix, when its `name` is
not a slug, its `type` is not one of the four kinds, its `description` is not one line or its
`body` is empty. `directory.py` does the writing.

The index is partly the person's, so the tool keeps only its own lines: those that open with a
link to a memory's file (`- [title](NAME.md): ...`). It replaces or removes the lines for the
memory it is asked about, one per topic file, and leaves every other line as it is, to the byte.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MEMORY",
    "Delete",
    "Read",
    "Save",
    "index_line",
    "topic_file",
    "topic_text",
    "understood",
    "with_line",
]

type Json = Mapping[str, Any]

_KINDS = ("user", "feedback", "project", "reference")
_ACTIONS = ("save", "read", "delete")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_LONGEST = 64  # characters in a name: the file's name, and its line in the index
# `memory.md` and MEMORY.md are one file on a disk that ignores case (macOS's)
_TAKEN = "memory"

MEMORY: Json = {
    "name": "memory",
    "description": "Keep your auto memory: save, read or delete one memory by name.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(_ACTIONS), "description": "What to do."},
            "name": {
                "type": "string",
                "description": (
                    "The memory's name, a slug: lowercase letters and digits joined by hyphens "
                    "('prefers-tabs'). Saving under a name that exists updates that memory."
                ),
            },
            "type": {
                "type": "string",
                "enum": list(_KINDS),
                "description": "save: what kind of memory it is.",
            },
            "description": {
                "type": "string",
                "description": (
                    "save: one specific line saying what the memory is; it is the memory's line in MEMORY.md."
                ),
            },
            "body": {"type": "string", "description": "save: the memory itself."},
        },
        "required": ["action", "name"],
    },
}


@dataclass(frozen=True, slots=True)
class Save:
    """A memory to write: its `name`, its `kind` (the frontmatter's `type`), its one-line
    `description` and its `body`."""

    name: str
    kind: str
    description: str
    body: str


@dataclass(frozen=True, slots=True)
class Read:
    """A memory to read, by `name`."""

    name: str


@dataclass(frozen=True, slots=True)
class Delete:
    """A memory to delete, by `name`."""

    name: str


type Request = Save | Read | Delete


def understood(input: Json) -> Request | str:
    """What a call asks, or why it is refused: the text the model reads, `error: ` and what to
    fix. Nothing is looked up or written here."""
    action = input.get("action")
    if action not in _ACTIONS:
        return f"error: `action` is save, read or delete; got {action!r}"
    name = input.get("name")
    if not isinstance(name, str) or not _SLUG.fullmatch(name) or len(name) > _LONGEST:
        return (
            f"error: `name` is a slug, lowercase letters and digits joined by single hyphens, "
            f"{_LONGEST} characters at most ('prefers-tabs'); got {name!r}"
        )
    if name == _TAKEN:
        return f"error: `name` {_TAKEN!r} is MEMORY.md's own name on a disk that ignores case; choose another"
    match action:
        case "read":
            return Read(name)
        case "delete":
            return Delete(name)
        case _:
            return _saved(input, name)


def _saved(input: Json, name: str) -> Save | str:
    """The save `input` asks for under `name`, or why it is refused."""
    kind = input.get("type")
    if not isinstance(kind, str) or kind not in _KINDS:
        return f"error: save needs a `type`, one of user, feedback, project or reference; got {kind!r}"
    description = input.get("description")
    if not isinstance(description, str) or not description.strip():
        return (
            "error: save needs a `description`: one specific line saying what the memory is, "
            "which is its line in MEMORY.md"
        )
    lines = len(description.strip().splitlines())
    if lines != 1:
        return (
            f"error: `description` is {lines} lines; make it one specific line, which is the "
            "memory's line in MEMORY.md, and put the rest in `body`"
        )
    body = input.get("body")
    if not isinstance(body, str) or not body.strip():
        return "error: save needs a `body`: the memory itself"
    return Save(name, kind, description.strip(), body.strip())


def topic_file(name: str) -> str:
    """The name of the topic file of the memory `name`."""
    return f"{name}.md"


def topic_text(save: Save) -> str:
    """The topic file of `save`: the frontmatter, then the body."""
    return f"---\nname: {save.name}\ndescription: {save.description}\ntype: {save.kind}\n---\n\n{save.body}\n"


def index_line(save: Save) -> str:
    """The line of `save` in MEMORY.md, without its line end."""
    return f"- [{save.name}]({topic_file(save.name)}): {save.description}"


def with_line(index: str, name: str, line: str | None) -> str:
    """`index` with the lines for the memory `name` (those that open with a link to its file)
    replaced by `line`, the first where it stands and the others dropped, or `line` added at the
    end when there is none; with no `line`, those lines removed. Every other line is kept as it
    is, whatever its line end."""
    own = re.compile(rf"\s*(?:[-*+]\s+)?\[[^\]\n]*\]\({re.escape(topic_file(name))}\)")
    kept: list[str] = []
    placed = line is None
    for each in re.findall(r"[^\n]*\n|[^\n]+", index):
        if own.match(each) is None:
            kept.append(each)
        elif not placed and line is not None:
            kept.append(f"{line}\n")
            placed = True
    if not placed and line is not None:
        if kept and not kept[-1].endswith("\n"):
            kept[-1] += "\n"
        kept.append(f"{line}\n")
    return "".join(kept)
