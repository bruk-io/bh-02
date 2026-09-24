"""warden: a process supervisor built on cordis, composed the way bh-02 is.

This package is the command line, the bootstrap and one shipped layer file; the capability
lives in `warden-cordis-plugin`, named by the layer. It imports `cordis` and nothing else in
the workspace.
"""

from warden.bootstrap import CompositionError, layers, run
from warden.cli import main

__all__ = ["CompositionError", "layers", "main", "run"]
