"""Paths on the person's machine, as every package that reads their files must agree on them:
where their configuration lives (`config_home`), and every place reading a file goes through
(`walked`), which a caller holds against where another party may write.

No cordis in them, and no domain: a package that decides whether to trust a file by where it is
and how it is reached needs one answer, the same as every other package's, and the packages of
a family may import nothing of each other's.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

__all__ = ["MOST_LINKS", "config_home", "walked"]

MOST_LINKS: Final = 40  # links one walk follows at most (Linux's own limit), so a loop of links ends


def config_home(environ: Mapping[str, str], home: Path) -> Path:
    """Where the person's configuration lives: `$XDG_CONFIG_HOME` as `environ` has it, else
    `home`'s `.config` (when the variable is unset or empty). As given: a relative value stays
    relative, for the caller to place."""
    return Path(environ.get("XDG_CONFIG_HOME") or home / ".config")


def walked(path: Path) -> list[Path]:
    """Every place reading the absolute `path` goes through, from the top: each directory and
    link on the way (a link where it sits, then what it points to, followed), then where it
    ends. A `..` goes up from where the links before it led, as the kernel's lookup does. At
    most `MOST_LINKS` links are followed; one past that, or one that can't be read (gone since,
    not permitted), is a place like any other, and reading the file will say what is wrong.

    Whoever may write any of these chooses what reading `path` reads: a link they could repoint,
    a directory they could swap for a link."""
    at, pending, links, out = Path(path.anchor), list(path.parts[1:]), 0, list[Path]()
    while pending:
        part = pending.pop(0)
        if part == "..":  # after the links before it are followed, as the kernel does
            at = at.parent
            continue
        step = at / part
        out.append(step)
        try:
            target = Path(os.readlink(step)) if links < MOST_LINKS and step.is_symlink() else None
        except OSError:  # gone since, or can't be read: reading the file will say what is wrong
            target = None
        if target is None:
            at = step
            continue
        links += 1
        at = Path(target.anchor) if target.is_absolute() else at
        pending[:0] = target.parts[1:] if target.is_absolute() else target.parts
    return [*out, at]
