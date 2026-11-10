"""What a Linux jail does with mounts, as decisions: bubblewrap holds a deny or a mask with a mount
on the host's own directory entry, so which denies it can mount (`mountable`), which of the mounts
brig made the host undoing would let an input in (`tripwired`), and what the person is told
(`notice_for`, `released_for`). Pure; what they read of the host is handed in (`facts`).
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol

__all__ = [
    "mountable",
    "notice_for",
    "released_for",
    "tripwired",
]


class _Kind(Protocol):
    @property
    def name(self) -> str: ...


class _Mount(Protocol):
    """What the tripwire reads of one of brig's mounts (`Jail.mounts`): how it is mounted and where."""

    @property
    def kind(self) -> _Kind: ...
    @property
    def target(self) -> str: ...


def tripwired(mounts: Iterable[_Mount]) -> tuple[str, ...]:
    """The paths a Linux jail holds with a mount the host can undo, read off the mounts brig made
    (`Jail.mounts`, never a plan of bh-02's own): every read-only mount beneath a writable one (a
    write deny, a masked secret, a placeholder, a readable tree nested in a root) and every
    writable one beneath another (brig's rename pins: a directory between a root and a deny, bound
    writable over itself so the command can't rename it). Replacing, moving or removing one on the
    host ends the jail (`Tripwire`): the kernel detaches a mount inside the jail when the host
    does that to its entry, and a pin renamed away takes the mounts beneath it along. A mount at or
    outside every writable one is not here: nothing in the jail can write there."""
    held = [(mount.kind.name, mount.target) for mount in mounts]
    writable = [target for kind, target in held if kind == "WRITABLE"]
    return tuple(
        dict.fromkeys(
            target
            for kind, target in held
            if kind in ("READ_ONLY", "WRITABLE") and any(target.startswith(w + "/") for w in writable)
        )
    )


def notice_for(holds: Sequence[str]) -> str:
    """What the person should know at the start of a session about the secrets a jail holds with a
    mount the host can undo (`holds`), or nothing."""
    if not holds:
        return ""
    return (
        f"The jail keeps inputs from reading {', '.join(holds)}. It does that with a mount "
        "on each path that is there. The host can undo a mount: when a file at one of these paths "
        "is replaced (an editor saves by renaming a new file over it) or removed while the Python "
        "process runs, bh-02 ends the jail at once (a running input with it) and the next input's "
        "jail holds the path again. A program an input left running can still read or rewrite it "
        "in the milliseconds that takes, so edit them after `/release`."
    )


def released_for(running: bool = False) -> str:
    """What `/release` tells the person after it has stopped what it could: that a program this
    jail started still runs (`running`: an owner that did not stop its own), whose jail holds
    what it holds. Empty when nothing does."""
    if not running:
        return ""
    return (
        "A program this runner started still runs (its row did not stop it on /release), and "
        "its jail holds what it holds: /rows shows the rows; /restart one, then /release again."
    )


def mountable(denies: Sequence[str], instead: Mapping[str, str]) -> tuple[str, ...]:
    """The write denies bubblewrap can mount, each once, with `instead` mapping a deny to the
    path denied in its place. An absent one under a path that exists as a FILE (`.git/hooks`
    where `.git` is a worktree's or submodule's `gitdir:` pointer) can't have a mount point made
    for it (bwrap: "Can't mkdir parents ... Not a directory", and the Python process never starts), so it
    maps to that file, bound read-only over itself: neither rewritten nor removed, so nothing is
    ever created under it. An absent one whose parent is absent too (`.git/config` in a project
    that is not a repository) maps to its topmost absent ancestor (`.git`): one empty directory
    held on the host rather than a `.git/config` directory inside one, which would break the
    person's own `git init` there while the Python process runs."""
    return tuple(dict.fromkeys(instead.get(deny, deny) for deny in denies))
