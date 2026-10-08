"""Claude Code's memory in bh-02: the CLAUDE.md and AGENTS.md files, the files they import and the
rules, found where Claude Code finds them, told as a section of the system prompt; the ones for
a subdirectory or some files told with the result of the first input that opens a file they
cover; and `/memory`, which lists them."""

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
from memory_cordis_plugin.reading import LIMIT, read, roots, secret, under, way, writable
from memory_cordis_plugin.rules import Rule, frontmatter, matches, rule
from memory_cordis_plugin.touch import Notes, OnTouch, Transcript
from memory_cordis_plugin.wiring import memory, on_touch

__all__ = [
    "INSTRUCTION_FILES",
    "LIMIT",
    "SPEC",
    "Entry",
    "Memory",
    "MemoryConfig",
    "Notes",
    "OnTouch",
    "Rule",
    "Source",
    "Transcript",
    "described",
    "frontmatter",
    "imports",
    "label",
    "listing",
    "matches",
    "memory",
    "on_touch",
    "read",
    "roots",
    "rule",
    "secret",
    "uncommented",
    "under",
    "way",
    "where",
    "without_trailing",
    "writable",
]
