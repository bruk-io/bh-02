"""The placeholders a Linux jail makes on the host: bubblewrap holds each absent write-denied
path (`.envrc`, `.vscode`, ...) by mounting over an empty directory on the host, which the jail
makes (and marks as its own, `MARK`) before bubblewrap starts and removes once brig has verified
the worker is gone, never before (a mount point removed while the jail lives is detached inside
it). The record of what a jail made, the order to make and remove it in, how a directory is
known for the jail's, and the lock that says no other bh-02 jail of the user runs (taken
exclusively to remove; shared by every running jail), kept in bh-02's state directory, where
another local user cannot create the name first.
"""

import contextlib
import fcntl
import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from host_paths import state_home

__all__ = [
    "MARK",
    "clear_up",
    "identity",
    "lock_path",
    "made_by_the_jail",
    "open_lock",
    "place",
    "record_text",
    "recorded",
    "recorded_group",
    "records_dir",
    "remove_placeholders",
    "still_made",
]


def made_by_the_jail(absent: Sequence[str]) -> tuple[str, ...]:
    """The directories made on the host for bubblewrap to mount over at absent write-denied
    paths (each path and each missing parent; `absent` lists them all), deepest first: the order
    they can be removed in once the jail is gone (and, reversed, made in)."""
    return tuple(sorted(set(absent), key=lambda p: (-p.count("/"), p)))


def records_dir(environ: Mapping[str, str], home: str) -> str:
    """Where a Linux jail records the placeholders it made, one file per jail: bh-02's state
    directory (`$XDG_STATE_HOME/bh-02`, else `~/.local/state/bh-02`; `host_paths.state_home`),
    outside every jail."""
    return str(state_home(environ, Path(home)) / "bh-02" / "jails")


def lock_path(environ: Mapping[str, str], home: str) -> str:
    """The user's bh-02 jail lock, shared by every running jail and taken exclusively to clean up:
    in bh-02's state directory beside the records (`records_dir`), not in `/tmp`, where another
    local user could create the name first and hold the lock or keep it from being made."""
    return str(state_home(environ, Path(home)) / "bh-02" / "jails.lock")


def open_lock(path: str) -> int:
    """The jail lock's file (`lock_path`), made if it is not there, and its directory with it,
    open for the caller to `flock`.

    Raises:
        OSError: the directory or the file can't be made or opened.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return os.open(path, os.O_RDWR | os.O_CREAT, 0o600)


def identity(found: os.stat_result) -> str:
    """Which directory a placeholder is, where the filesystem takes no `MARK`: its inode and
    when it changed. The inode alone is not enough: a directory removed and made again at the
    same path can get the same one back (measured, on overlayfs). The change time is as fine as
    the kernel's clock tick, so one made again within the same few milliseconds would pass for
    the jail's; and a placeholder something was added to and removed from since (another jail's
    placeholders inside it) reads as changed, and is kept."""
    return f"{found.st_ino}:{found.st_ctime_ns}"


def record_text(made: Sequence[tuple[str, str]], group: int | None = None) -> str:
    """A jail's record of its placeholders: each path, deepest first, with how the directory
    there is known to be the jail's (`mark:<jail id>`, else its `identity`), so a later sweep
    removes only a directory the jail made; and once bubblewrap is started, its process group,
    so a sweep never removes what a jail still alive holds."""
    whole: dict[str, object] = {"made": [[path, found] for path, found in made]}
    if group is not None:
        whole["group"] = group
    return json.dumps(whole) + "\n"


def recorded(text: str) -> list[tuple[str, str]]:
    """The placeholders a record names (`record_text`), each with how the jail knows it; nothing
    for a record that can't be read as one, which is then only removed, and none for an entry that
    names no way to know it (a record edited or damaged), since nothing proves a jail made it."""
    try:
        made = json.loads(text)["made"]
        return [(str(path), found) for path, found in made if isinstance(found, str)]
    except ValueError, KeyError, TypeError:
        return []


def recorded_group(text: str) -> int | None:
    """The process group of the bubblewrap a record names (`record_text`); None when it names
    none (written before bubblewrap started) or can't be read."""
    try:
        group = json.loads(text)["group"]
    except ValueError, KeyError, TypeError:
        return None
    return group if isinstance(group, int) else None


def still_made(was: str, found: str, mark: str | None) -> bool:
    """Whether a directory is still the placeholder a jail recorded as `was`: its `MARK` (the
    jail's id, in an extended attribute the jail set on it as it made it), or where the
    filesystem takes none, its `identity`. A mark survives what is added and removed under it;
    the person's own directory has none."""
    if was.startswith("mark:"):
        return mark == was.removeprefix("mark:")
    return was == found


def remove_placeholders(made: Sequence[tuple[str, str]]) -> None:
    """Remove each placeholder a jail made (deepest first) that is still what it made (an empty
    directory, `still_made`). One the person has put something in, or replaced with one of their
    own, stays. Only once no jail can have mounted over it: removed while a jail lives, it stops
    being a mount point inside it, and the path it denies is writable there."""
    for path, was in made:
        with contextlib.suppress(OSError):
            found = os.lstat(path)
            if stat.S_ISDIR(found.st_mode) and still_made(was, identity(found), _mark_of(path)):
                os.rmdir(path)


def clear_up(lock: int, made: Sequence[tuple[str, str]], record: str | None) -> None:
    """Remove what a jail that is gone made (`made`) and its record, if `lock` can be taken
    exclusively: no other bh-02 jail runs, so none has mounted over them. Else they stay, with
    the record, for the next jail to start with none running."""
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # another jail runs: what it may have mounted over stays, and the record
    remove_placeholders(made)
    if record is not None:
        with contextlib.suppress(OSError):
            os.unlink(record)


#: The extended attribute a Linux jail marks each placeholder with: the jail's id.
MARK = "user.bh-02.placeholder"


def place(path: str, jail_id: str) -> str | None:
    """Make the placeholder at `path`, mark it as this jail's at once, and say how it is known:
    `mark:<id>`, or where the filesystem takes no extended attribute, its `identity`. None when
    something is there already (the person's, or another jail's: never this one's to remove) or
    it can't be made (then bubblewrap makes it, unmarked, or fails to start)."""
    try:
        os.mkdir(path)
    except OSError:
        return None
    mark: Callable[..., None] | None = getattr(os, "setxattr", None)  # Linux only
    if mark is not None:
        try:
            mark(path, MARK, jail_id.encode(), follow_symlinks=False)
        except OSError:
            pass
        else:
            return f"mark:{jail_id}"
    try:
        return identity(os.lstat(path))
    except OSError:
        return None


def _mark_of(path: str) -> str | None:
    """The jail id a placeholder is marked with (`MARK`), or None."""
    read: Callable[..., bytes] | None = getattr(os, "getxattr", None)  # Linux only
    if read is None:
        return None
    try:
        return read(path, MARK, follow_symlinks=False).decode(errors="replace")
    except OSError:
        return None
