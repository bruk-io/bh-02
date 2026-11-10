"""What bh-02 learns from the host before it can judge a policy: the links on the way to its
interpreter (one walk, for the policy's `links` and for the Linux jail's readable trees) and the
person's git identity. Everything here reads the filesystem or runs `git`; the decisions on what it
finds are in `policy` and `mounts`.
"""

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = [
    "git_identity",
    "instead",
    "interpreter_files",
    "links_on_the_way",
]

#: How many links one lookup follows before the kernel gives up (ELOOP): `links_on_the_way` stops there.
_MAX_LINKS = 40


@dataclass(frozen=True, slots=True)
class _Link:
    """A link met on the way to a file: `entry`, where it sits on disk (absolute, in the directory
    that physically holds it), and `through`: whether the lookup goes on through it (a link to a
    directory in the middle of a path) rather than ending at it."""

    entry: str
    through: bool


def interpreter_files(spelled: Sequence[str]) -> tuple[str, ...]:
    """The files the interpreter bh-02 itself runs on is: where each name in `spelled` (how the host
    reaches it: `sys.executable`, the base installation's `bin/python3`) leads once every link on
    the way is followed, as `spec_for` is handed `host`'s paths, resolved. The file, not the names:
    a write through any of them reaches it, and a mount holds it, where the entry of a link in a
    writable directory is held by none. A name that is empty (an embedded interpreter has no
    `sys.executable`) leads nowhere and is left out."""
    return tuple(dict.fromkeys(str(Path(name).resolve()) for name in spelled if name))


def _stepped(
    here: PurePosixPath, pending: Sequence[str], led_to: str | None
) -> tuple[PurePosixPath, tuple[str, ...]]:
    """One step of the kernel's lookup of a path, as `links_on_the_way` takes it: `here` is the
    directory reached, as it physically is (no link in it), and `pending` what is left to look up,
    its first component the one just looked at, which `led_to` says is a link (to this text) or
    not (`None`). Returns the directory the lookup is in and what is left. A component that is not
    a link is entered (`..` leaves); a link is replaced by what it leads to, which starts at `/` if
    absolute and at the directory that holds the link if not."""
    part, rest = pending[0], tuple(pending[1:])
    if led_to is None:
        return (here.parent if part == ".." else here / part), rest
    target = PurePosixPath(led_to)
    if target.is_absolute():
        return PurePosixPath(target.anchor), (*target.parts[1:], *rest)
    return here, (*target.parts, *rest)


def links_on_the_way(spelled: Sequence[str]) -> tuple[_Link, ...]:
    """Every link on the way from each name in `spelled` (`interpreter_files`) to the file it leads
    to, the entry of each as it sits on disk: the link `python3` in a venv, the `python` it leads to,
    a link to a directory in the middle of a path (uv's `cpython-3.15-<platform>`, which the venv's
    `python` goes through), one the target of another leads through, in the order met, each once
    (the first sighting's `through`). Walked one component at a time (`_stepped`), so each link is
    found in the directory that physically holds it (a name reached through a link to a directory
    is that directory's, which is where a mount lands), and what `policy.link_directories` decides on
    is where the entries are. The kernel's own limit on links in one lookup ends a loop, which is
    no interpreter.

    The policy wants every link (a mount on the file does not hold the entry of one, so its
    directory is denied); the Linux jail wants the `through` ones of a command's own path (a tree
    reached through a link must be named as the link too, or bubblewrap's mount lands elsewhere).
    A name that is not absolute is looked up from the working directory.

    Raises:
        OSError: a link was replaced as it was read (the host changed its Python while a jail
            started).
    """
    found: dict[str, _Link] = {}
    for name in spelled:
        if not name:
            continue
        path = PurePosixPath(name)
        here = PurePosixPath(path.anchor) if path.is_absolute() else PurePosixPath(Path.cwd())
        pending, followed = (path.parts[1:] if path.is_absolute() else path.parts), 0
        while pending and followed <= _MAX_LINKS:
            entry = Path(here, pending[0])
            led_to = os.readlink(entry) if entry.is_symlink() else None
            if led_to is not None:
                found.setdefault(str(entry), _Link(str(entry), through=len(pending) > 1))
                followed += 1
            here, pending = _stepped(here, pending, led_to)
    return tuple(found.values())


def git_identity(cwd: str) -> tuple[str, str]:
    """`user.name` and `user.email` as git resolves them on the host for `cwd` (the project's own
    config over the person's global one); empty when git or either is missing, and then a jailed
    commit says what git says without them."""
    git = shutil.which("git")
    if git is None:
        return "", ""
    found = []
    for key in ("user.name", "user.email"):
        try:
            done = subprocess.run(
                [git, "config", "--get", key], cwd=cwd, capture_output=True, text=True, timeout=5
            )
        except OSError, subprocess.SubprocessError:
            found.append("")
        else:
            found.append(done.stdout.strip() if done.returncode == 0 else "")
    return found[0], found[1]


def instead(denies: Sequence[str], writable: Sequence[str]) -> dict[str, str]:
    """Each absent write deny whose nearest existing ancestor is a file, mapped to that file;
    and each whose parent is absent too, under a write root, mapped to its topmost absent
    ancestor (see `mounts.mountable`)."""
    roots = [Path(r) for r in writable]
    found: dict[str, str] = {}
    for deny in denies:
        path, top = Path(deny), Path(deny)
        while not path.exists() and path != path.parent:
            top, path = path, path.parent
        if str(path) != deny and path.exists() and not path.is_dir():
            found[deny] = str(path)
        elif str(top) != deny and any(top.is_relative_to(r) and top != r for r in roots):
            found[deny] = str(top)
    return found
