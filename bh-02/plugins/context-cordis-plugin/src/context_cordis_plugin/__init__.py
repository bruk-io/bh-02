"""What the model is told about who and where it is: a `system` value that rows add sections to,
with the project context the context files describe; and what those files say about the files
an input opens, through `memory`."""

from context_cordis_plugin.context_file import ContextFiles, Section, parse, read
from context_cordis_plugin.project import ContextConfig, ProjectContext, branch_of, describe
from context_cordis_plugin.sections import (
    Rule,
    frontmatter,
    named,
    place,
    place_touched,
    rule,
    rules,
    rules_touched,
    whole,
)
from context_cordis_plugin.touch import Memory, OnTouch, System, Transcript
from context_cordis_plugin.wiring import on_touch, project

__all__ = [
    "ContextConfig",
    "ContextFiles",
    "Memory",
    "OnTouch",
    "ProjectContext",
    "Rule",
    "Section",
    "System",
    "Transcript",
    "branch_of",
    "describe",
    "frontmatter",
    "named",
    "on_touch",
    "parse",
    "place",
    "place_touched",
    "project",
    "read",
    "rule",
    "rules",
    "rules_touched",
    "whole",
]
