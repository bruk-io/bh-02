"""`/memory`: the memory files, where they are and how each loads, as text for the person. Pure:
`Memory.listed()` finds them, this says them.

Claude Code's `/memory` lists the same files and opens one in an editor; bh-02's app owns the
terminal, so this names them, and the person opens one in their own editor: a change reaches the
model's next message.
"""

from collections.abc import Sequence
from pathlib import Path

from memory_cordis_plugin.memory import Entry, label, where

__all__ = ["SPEC", "listing"]

SPEC = {
    "name": "memory",
    "help": "the memory files the model is told (CLAUDE.md, AGENTS.md, rules) and how each loads",
    "usage": "",
}
_MARKS = {"loaded": "✓", "on demand": "…", "missing": "·", "excluded": "✗", "skipped": "–", "not read": "✗"}


def listing(entries: Sequence[Entry], root: Path, home: Path, instruction_files: str) -> str:
    """What `/memory` answers: one line per memory file, marked by how it loads, then how the rest
    load and where to change them."""
    lines = [f"Memory, as Claude Code reads it (instruction files: {instruction_files}):"]
    for entry in entries:
        if entry.state == "missing" and entry.source.kind == "managed":
            continue  # no managed policy on this machine: nothing to say
        named = where(entry.source.path, root, home)
        line = f"  {_MARKS[entry.state]} {named}: {label(entry.source, root, home)}"
        match entry.state:
            case "on demand":
                line += f" for {entry.why}, told when an input first opens one"
            case "missing":
                line += " (not there)"
            case "excluded":
                line += " (excluded)"
            case "skipped":
                line += f" (not read: a CLAUDE.md is there, and instruction files is {instruction_files})"
            case "not read":
                line += f" (not read: {entry.why})"
        lines.append(line)
    lines += [
        "",
        "✓ loaded at the start   … loaded on demand   · not there   ✗ excluded or not read",
        "A subdirectory's CLAUDE.md, and a rule for some files, load when an input first opens a "
        "file they cover. Edit any of these in your editor: a change reaches the model's next message.",
    ]
    return "\n".join(lines)
