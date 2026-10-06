"""What the model is told about who and where it is: a `system` value that rows add sections to,
with the project context the context files describe."""

from context_cordis_plugin.context_file import ContextFiles, Section, parse
from context_cordis_plugin.project import ContextConfig, ProjectContext, branch_of, describe
from context_cordis_plugin.sections import Rule, frontmatter, named, place, rule, rules, whole
from context_cordis_plugin.wiring import project

__all__ = [
    "ContextConfig",
    "ContextFiles",
    "ProjectContext",
    "Rule",
    "Section",
    "branch_of",
    "describe",
    "frontmatter",
    "named",
    "parse",
    "place",
    "project",
    "rule",
    "rules",
    "whole",
]
