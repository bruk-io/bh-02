"""Auto memory, as Claude Code has it: notes the model keeps for itself, across conversations,
in a directory of the project's own outside the repository (`$XDG_STATE_HOME/bh-02/projects/
<project>/memory`, the `layers` value's `memory`), which the jail lets an input write. A
`MEMORY.md` index, one line per memory, and a topic file for each; the index's first 200 lines
or 25KB are told at the start of every conversation, the topic files read when they are needed.

The model writes them with whatever tools the composition gives it, as it writes any file:
this plugin adds none, and says nothing of any (a tool that can write there says so itself, as
the python tool names the directories its jail lets it write). What it is told (`auto_section`)
is what is worth keeping, of which kind, and where. The index
is read once a conversation (`AutoMemory`, a section of the system prompt whose row lives as long
as the conversation does), as Claude Code reads it at the start of one: a write to it during the
conversation is the model's own, and telling it back as a change in its instructions would only
repeat it. The model can write the directory, so the index is read from it through no link
(`reading.read`, the directory its root).
"""

import os
from pathlib import Path

from memory_cordis_plugin.reading import read

__all__ = ["INDEX", "AutoMemory", "auto_section", "indexed"]

INDEX = "MEMORY.md"
_LINES = 200  # the index's lines told, at most, as Claude Code's
_BYTES = 25 * 1024  # and its bytes


def indexed(text: str) -> tuple[str, bool]:
    """The index as it is told: its first 200 lines or 25KB, whichever ends first, ending at a
    whole line; and whether there was more."""
    lines = text.splitlines(keepends=True)
    kept, size = [], 0
    for line in lines[:_LINES]:
        size += len(line.encode())
        if size > _BYTES:
            break
        kept.append(line)
    return "".join(kept).rstrip("\n"), len(kept) < len(lines)


def auto_section(directory: str, index: str | None, cut: bool) -> str:
    """What the model is told about its auto memory: how to keep it, in `directory`, then the
    index (None: there is none yet), with a word when it was `cut`."""
    how = (
        f"Auto memory: {directory} is a directory of your own, kept across conversations for "
        "this project (on this machine; never in the repository). Save there what would help a "
        "later conversation and that the code, its history and the memory files above don't "
        "already say: the person's role, expertise and preferences (type "
        "`user`), corrections they gave you and approaches they confirmed (`feedback`), ongoing "
        "work, deadlines and decisions (`project`), and where to find things outside the project "
        "(`reference`). One topic file per memory, opening with frontmatter (`name`, "
        "`description`, `type`), and one line for it in MEMORY.md, the index: its first 200 "
        "lines or 25KB are told to you at the start of every conversation, so keep each entry to "
        "a line and the detail in its topic file, which you read when you need it. When the "
        "person asks you to remember something, save it here; when they ask you to add it to "
        "CLAUDE.md, edit that instead. Change or remove a memory that turns out to be wrong."
    )
    if index is None:
        return f"{how}\n\nMEMORY.md is not there yet."
    if not index.strip():
        return f"{how}\n\nMEMORY.md is empty."
    more = (
        "\n\n(MEMORY.md is longer than this: what is past its first 200 lines or 25KB is not "
        "told, so shorten it: one line per memory, the detail in topic files.)"
        if cut
        else ""
    )
    return f"{how}\n\nContents of {directory}/MEMORY.md (your auto memory index):\n\n{index}{more}"


class AutoMemory:
    """The auto memory section of one conversation's system prompt: `auto_section` over the
    index as it read when the prompt was first read, kept for the rest of the conversation.
    Called in the loop's worker thread, one call at a time, so it takes no lock."""

    def __init__(self, directory: Path, named: str) -> None:
        self._directory = directory
        self._named = named
        self._said: str | None = None

    def __call__(self) -> str:
        if self._said is None:
            index, cut = self._index()
            self._said = auto_section(self._named, index, cut)
        return self._said

    def _index(self) -> tuple[str | None, bool]:
        """The index as it is told, or None when there is none; a line saying why when it can't
        be read (a link the model made, a second name)."""
        path = self._directory / INDEX
        if not os.path.lexists(path):
            return None, False
        try:
            return indexed(read(path, [path], self._directory))
        except OSError as error:
            return f"(bh-02 did not read MEMORY.md: {error})", False
