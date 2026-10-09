"""Paths as bh-02's own process must judge them when the model can write some of them: where the
person's directories are (`config_home`, `state_home`), and every place reading a path goes
through (`walked`), held against the roots the model may write (`roots`, `passes`)."""

from host_paths.paths import MOST_LINKS, config_home, passes, roots, state_home, walked

__all__ = ["MOST_LINKS", "config_home", "passes", "roots", "state_home", "walked"]
