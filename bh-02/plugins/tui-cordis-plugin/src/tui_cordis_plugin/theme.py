"""The app's themes: bh-01's dark (the default) and light, generated into `bh01_theme`.

Every colour lives in `bh01_theme` (written by `scripts/sync-tokens` from bh-01's token CSS);
a widget's stylesheet names Textual's own tokens (`$primary`, `$surface`, ...) or bh-01's roles
(`$bh-text-muted`, `$bh-border`, `$bh-primary-glow`, ...), never a colour. Two rules keep a real
launch from dying on a token `run_test()` never notices: the themes are registered in
`App.__init__` (before any stylesheet is parsed), and every `$bh-*` a stylesheet names has a
default in `VARIABLES`, which the app returns from `get_theme_variable_defaults`.
"""

from collections.abc import Mapping

from textual.theme import Theme

from tui_cordis_plugin import bh01_theme

__all__ = ["NAME", "VARIABLES", "themes"]

NAME = bh01_theme.DARK

# The defaults for every custom token: the dark theme's (both themes define the same names).
VARIABLES: Mapping[str, str] = bh01_theme.DARK_VARIABLES


def themes() -> tuple[Theme, ...]:
    """Return every theme the app registers, the default first."""
    return (bh01_theme.dark(), bh01_theme.light())
