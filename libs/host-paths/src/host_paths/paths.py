"""The one definition of these, for every package that decides whether to trust a file by where
it is and how it is reached. bh-02's plugins may import nothing of each other's, and a copy that
drifted would be a hole: the models file, the person's startup file and memory files outside the
project are each read on the host only when nothing the model can write chooses what is read.

No cordis here and no domain: no key, row or bh-02 path, only the XDG directories and links.
"""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

__all__ = ["MOST_LINKS", "config_home", "passes", "roots", "state_home", "walked"]

MOST_LINKS: Final = 40  # links one walk follows at most (Linux's own limit), so a loop of links ends


def config_home(environ: Mapping[str, str], home: Path) -> Path:
    """Where the person's configuration lives: `$XDG_CONFIG_HOME` as `environ` has it, else
    `home`'s `.config`. A relative value counts as unset, as the XDG spec says: it would name a
    different directory from wherever each reader happens to be."""
    return _xdg(environ.get("XDG_CONFIG_HOME"), home / ".config")


def state_home(environ: Mapping[str, str], home: Path) -> Path:
    """Where the person's state lives: `$XDG_STATE_HOME` as `environ` has it, else `home`'s
    `.local/state`. A relative value counts as unset, as in `config_home`."""
    return _xdg(environ.get("XDG_STATE_HOME"), home / ".local" / "state")


def _xdg(value: str | None, default: Path) -> Path:
    return Path(value) if value and Path(value).is_absolute() else default


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


def roots(root: Path) -> tuple[Path, Path]:
    """A root as named (absolute, `..` taken out) and as it resolves: a path is under the root
    when it is under either."""
    return Path(os.path.normpath(root.absolute())), root.resolve()


def passes(path: Path, found: Sequence[Path]) -> list[Path]:
    """The places reading `path` goes through (the path as named, `..` taken out, then each place
    `walked` names) that are under one of `found`, in order: [] when reading it goes nowhere under
    them. Each of `found` should be absolute, as `roots` gives them."""
    absolute = path.absolute()
    places = (Path(os.path.normpath(absolute)), *walked(absolute))
    return [place for place in places if any(place.is_relative_to(root) for root in found)]
