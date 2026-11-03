"""What a Linux jail does with mounts, as decisions on a `Policy`: bubblewrap holds a deny or a
mask with a mount on the host's own directory entry, so which denies it can mount (`mountable`,
`uncovered`), which masks it holds under a root an input may write (`held`), which paths the
host undoing would let an input in (`tripwired`), and what the person is told (`notice_for`,
`graded`, `released_for`). Pure; what they read of the host is handed in (`facts`).
"""

from collections.abc import Collection, Mapping, Sequence

from runner_cordis_plugin.policy import Policy

__all__ = [
    "graded",
    "held",
    "mountable",
    "notice_for",
    "released_for",
    "tripwired",
    "uncovered",
]


def uncovered(denies: Sequence[str]) -> tuple[str, ...]:
    """The write denies that no other one contains. bubblewrap mounts each in turn, and one
    inside a directory already bound read-only (an absent secret under a directory the host
    imports code from) would need a mount point made on a read-only mount, which fails the
    launch; the outer deny holds it already."""
    return tuple(d for d in denies if not any(d.startswith(o + "/") for o in denies if o != d))


def held(policy: Policy, absent: Collection[str]) -> tuple[str, ...]:
    """The masks a Linux jail (`policy`, `allowlisted`) holds at or under a root an input
    may write: one that is there (not in `absent`), which bubblewrap masks with a mount on the
    path itself, and an absent one no input can create, at or under a write deny (a directory
    bound read-only), where only
    the host could put a file, which the jail could then read. A mount is on the host's
    directory entry, so replacing that entry on the host (an editor saves by renaming a new file
    over it) or removing it detaches the mount inside the jail, and an input can then read and
    rewrite what is there (measured). Not an absent one nothing holds (a `hide`n file the project
    has none of): an input may create it, and a file the host creates there is readable, which
    brig's `fs_read` grade names. The rest are outside every writable root, where the allowlist
    alone keeps them out of the jail."""
    roots, denies = policy.writable, policy.write_denies
    return tuple(
        d
        for d in policy.masks
        if any(d == r or d.startswith(r + "/") for r in roots)
        and (d not in absent or any(d == w or d.startswith(w + "/") for w in denies))
    )


def tripwired(policy: Policy, absent: Collection[str]) -> tuple[str, ...]:
    """The paths a Linux jail holds with a mount that the host can undo: every write deny under
    a root an input may write (an existing path bound read-only over itself, or a placeholder) and
    every secret held there (`held`; `absent` names the masks that are not there). Replacing,
    moving or removing one on the host ends the jail (`Tripwire`); a deny outside every writable
    root is not mounted at all. Never a path an input may create: that would end the jail it
    runs in, blaming the host."""
    roots = policy.writable
    under = [d for d in policy.write_denies if any(d.startswith(r + "/") for r in roots)]
    return tuple(dict.fromkeys([*under, *held(policy, absent)]))


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


def graded(report: Mapping[str, str], holds: Sequence[str]) -> dict[str, str]:
    """brig's grades, with `fs_read` best-effort while a Linux jail holds a secret with a mount
    (`held`): brig grades a masked path enforced, and it is, until the host replaces or
    removes it."""
    out = dict(report)
    if holds and out.get("fs_read") == "enforced":
        out["fs_read"] = "best_effort"
    return out


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
