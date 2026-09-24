"""What the model is told about where it is working: a `system` value read fresh per request."""

from context_cordis_plugin.project import ContextConfig, ProjectContext, branch_of, describe
from context_cordis_plugin.wiring import project

__all__ = ["ContextConfig", "ProjectContext", "branch_of", "describe", "project"]
