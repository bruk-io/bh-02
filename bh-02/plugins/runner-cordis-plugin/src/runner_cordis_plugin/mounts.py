"""What a Linux jail does with mounts, as decisions on a `Policy`: bubblewrap holds a deny or a
mask with a mount on the host's own directory entry, so which denies it can mount (`mountable`),
which masks it holds under a root an input may write (`held`), which paths the host undoing would
let an input in (`tripwired`), and what the person is told (`notice_for`, `released_for`). Pure;
what they read of the host is handed in (`facts`).
"""

from collections.abc import Mapping, Sequence

from runner_cordis_plugin.policy import Policy

__all__ = [
    "held",
    "mountable",
    "notice_for",
    "released_for",
    "tripwired",
]


def held(policy: Policy) -> tuple[str, ...]:
    """The masks a Linux jail (`policy`, `allowlisted`) holds at or under a root an input may
    write. bubblewrap masks each with a mount on the path itself (an absent one first gets a
    directory brig makes there, so no input can create it), and a mount is on the host's directory
    entry: replacing that entry on the host (an editor saves by renaming a new file over it) or
    removing it detaches the mount inside the jail, and an input can then read and rewrite what is
    there (measured). A mask under another is hidden already and mounted by nothing. The rest are
    outside every writable root, where the allowlist alone keeps them out of the jail."""
    roots, masks = policy.writable, policy.masks
    return tuple(
        m
        for m in masks
        if any(m == r or m.startswith(r + "/") for r in roots)
        and not any(o != m and m.startswith(o + "/") for o in masks)
    )


def tripwired(policy: Policy) -> tuple[str, ...]:
    """The paths a Linux jail holds with a mount that the host can undo: every write deny under
    a root an input may write (an existing path bound read-only over itself, or a placeholder) and
    every secret held there (`held`). Replacing, moving or removing one on the host ends the jail
    (`Tripwire`); a deny outside every writable root is not mounted at all."""
    roots = policy.writable
    under = [d for d in policy.write_denies if any(d.startswith(r + "/") for r in roots)]
    return tuple(dict.fromkeys([*under, *held(policy)]))


def notice_for(platform: str, holds: Sequence[str]) -> str:
    """What the person should know at the start of a session about the secrets under a root an
    input may write (`held`), or nothing: on darwin seatbelt matches paths, so nothing the host
    does to them lets an input in."""
    if platform != "linux" or not holds:
        return ""
    return (
        f"The jail keeps inputs from reading {', '.join(holds)}. On Linux it does that with a mount "
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
