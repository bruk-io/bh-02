"""bh-02: the shell around a cordis composition of plugins, in a Textual app.

This package is the command line, the bootstrap, sessions, the shipped layer files and
`testing` (rows a `--patch` layer can name for a real launch with no login). Every
capability is a `*-cordis-plugin` workspace member the layers name by string; it imports
`cordis` and nothing else in the workspace. The shapes it relies on are in CONTRACTS.md.
"""

from bh_02.bootstrap import CompositionError, Recoverable, layers, run
from bh_02.cli import main

__all__ = ["CompositionError", "Recoverable", "layers", "main", "run"]
