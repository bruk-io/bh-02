"""Claude Code's memory in bh-02: the CLAUDE.md and AGENTS.md files, the files they import and the
rules, found where Claude Code finds them, told as a section of the system prompt; the ones for
a subdirectory or some files told with the result of the first input that opens a file they
cover; auto memory, the notes the model keeps for itself; and `/memory`, which lists them."""

from memory_cordis_plugin.auto import INDEX, AutoMemory, auto_section, indexed
from memory_cordis_plugin.listing import SPEC, listing
from memory_cordis_plugin.markdown import imports, uncommented, without_trailing
from memory_cordis_plugin.memory import (
    INSTRUCTION_FILES,
    Entry,
    Memory,
    MemoryConfig,
    Source,
    described,
    label,
    where,
)
from memory_cordis_plugin.reading import LIMIT, read, secret, under
from memory_cordis_plugin.rules import Rule, frontmatter, matches, rule
from memory_cordis_plugin.touch import Notes, OnTouch, Transcript
from memory_cordis_plugin.wiring import auto, memory, on_touch

__all__ = [
    "INDEX",
    "INSTRUCTION_FILES",
    "LIMIT",
    "SPEC",
    "AutoMemory",
    "Entry",
    "Memory",
    "MemoryConfig",
    "Notes",
    "OnTouch",
    "Rule",
    "Source",
    "Transcript",
    "auto",
    "auto_section",
    "described",
    "frontmatter",
    "imports",
    "indexed",
    "label",
    "listing",
    "matches",
    "memory",
    "on_touch",
    "read",
    "rule",
    "secret",
    "uncommented",
    "under",
    "where",
    "without_trailing",
]
