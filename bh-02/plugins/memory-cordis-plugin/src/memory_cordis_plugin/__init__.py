"""Claude Code's memory in bh-02: the CLAUDE.md and AGENTS.md files, the files they import and the
rules, found where Claude Code finds them, told as a section of the system prompt; the ones for
a subdirectory or some files told beside the result of the first input that opens a file they
cover; auto memory, the memories the model keeps for itself, with the `memory` tool that saves,
reads and deletes them; and `/memory`, which lists them."""

from memory_cordis_plugin.auto import INDEX, AutoMemory, auto_section, indexed
from memory_cordis_plugin.directory import call, keep
from memory_cordis_plugin.keeping import MEMORY, Delete, Read, Save, topic_text, understood, with_line
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
from memory_cordis_plugin.touch import Asides, OnTouch, Transcript
from memory_cordis_plugin.wiring import auto, files, on_touch

__all__ = [
    "INDEX",
    "INSTRUCTION_FILES",
    "LIMIT",
    "MEMORY",
    "SPEC",
    "Asides",
    "AutoMemory",
    "Delete",
    "Entry",
    "Memory",
    "MemoryConfig",
    "OnTouch",
    "Read",
    "Rule",
    "Save",
    "Source",
    "Transcript",
    "auto",
    "auto_section",
    "call",
    "described",
    "frontmatter",
    "imports",
    "indexed",
    "keep",
    "label",
    "listing",
    "matches",
    "files",
    "on_touch",
    "read",
    "rule",
    "secret",
    "topic_text",
    "uncommented",
    "under",
    "understood",
    "where",
    "with_line",
    "without_trailing",
]
