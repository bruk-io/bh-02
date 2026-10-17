"""Opening a file the model may have written, beneath a root, so that no link it made chooses
what is opened: the one opener for every package that reads such a file on the host, and the one
writer (and remover) of a file in a directory the model can write.

The walk starts at the root (the caller's to trust: opened as named, links and all) and opens
each name beneath it on its own, with these flags, each for a reason:

- `O_NOFOLLOW` on every name: a link the model made, anywhere on the way or at the end, could
  lead to a file the jail hides (`local.env`). A link on the way stops the walk (`Linked`); one
  at the end is not followed but answered (`Link`), for the caller to decide.
- `O_DIRECTORY` on every name but the last: a file on the way is not walked through.
- `O_NONBLOCK` on every name: opening a FIFO the model left in a file's place returns at once
  rather than waiting for a writer that never comes. On a directory it costs nothing, and holds
  on a system that opens a name before it checks `O_DIRECTORY`.
- `O_CLOEXEC` on every descriptor: a program bh-02 starts meanwhile inherits none.
- `O_NOCTTY` on the file: a terminal device opened by the read never becomes bh-02's.

Then the file is judged by the descriptor it was opened as, never by its name again, so a swap
after the walk changes nothing: a regular file (not a FIFO, a device or a directory) with one
name (a hard link is a second name for a file the jail may hide, and a file removed since it
was opened has none), no larger than the caller's cap, and read through that descriptor to at
most the cap, so a file that grew since is refused too.

Writing and removing walk the same way, then judge the name as it stands: a link there, a second
name for the file, or anything but a regular file is refused (`Linked`, `NotOneFile`), never
followed, replaced or removed. A write is made to a file of its own under a name the model
cannot guess (`O_CREAT | O_EXCL | O_NOFOLLOW`, by descriptor beneath the directory), and then
moved over the name. The move replaces whatever the name is by then, a link the model planted
after the check among it, and follows nothing, so no write reaches past the directory however
quick the model is, and a reader sees the old file or the new one, never half of it.
"""

import contextlib
import os
import secrets
import stat
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

__all__ = [
    "Link",
    "Linked",
    "NotOneFile",
    "TooLarge",
    "directory_beneath",
    "read_beneath",
    "remove_beneath",
    "write_beneath",
]

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY
_ROOT = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC  # the caller's to trust, links and all
_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOCTTY


@dataclass(frozen=True)
class Link:
    """The last name is a link, not followed: what it points to (`target`), as it reads."""

    target: str


class Linked(OSError):
    """A name beneath the root is a link, so the walk stopped there (a directory on the way), or
    the file to write or remove is one: `part`, the names from the root up to and including it."""

    def __init__(self, message: str, part: PurePath) -> None:
        super().__init__(message)
        self.part = part


class NotOneFile(OSError):
    """What the names reach is not a regular file with one name: its `mode` (`st_mode`) and how
    many `names` it has (`st_nlink`), as the descriptor it was opened as says."""

    def __init__(self, message: str, mode: int, names: int) -> None:
        super().__init__(message)
        self.mode = mode
        self.names = names


class TooLarge(OSError):
    """The file is larger than the caller's cap (`cap`, in bytes)."""

    def __init__(self, message: str, cap: int) -> None:
        super().__init__(message)
        self.cap = cap


@contextlib.contextmanager
def directory_beneath(root: Path | int, names: Sequence[str]) -> Iterator[int]:
    """The directory `names` reaches beneath `root` (a path, or a directory's descriptor, left
    open), opened a name at a time through no link: its descriptor, closed on leaving. No names
    is the root itself. Raises `Linked` when a name on the way is a link, NotADirectoryError
    when one is not a directory, and the OSError opening it gave otherwise (it is not there,
    it may not be opened), each naming the part."""
    shown = _shown(root)
    _one_each(names)
    at = os.open(root, _ROOT) if isinstance(root, Path) else os.dup(root)
    try:
        for depth, name in enumerate(names, start=1):
            try:
                below = os.open(name, _DIRECTORY, dir_fd=at)
            except OSError as error:
                raise _stopped(error, at, name, shown, PurePath(*names[:depth])) from None
            os.close(at)
            at = below
        yield at
    finally:
        os.close(at)


def read_beneath(root: Path | int, names: Sequence[str], *, cap: int) -> bytes | Link:
    """The bytes of the file `names` reaches beneath `root` (a path, or a directory's descriptor,
    left open), walked to through no link (`directory_beneath`) and read from the descriptor it
    was opened as; or, when the last name is a link, what it points to (`Link`), not followed.
    Raises what `directory_beneath` raises for the way there; `NotOneFile` when the file is not a
    regular file with one name; `TooLarge` over `cap` bytes; and the OSError opening it gave
    otherwise (it is gone since it was found, it may not be read)."""
    if not names:
        raise ValueError("a file beneath a root needs at least its own name")
    _one_each(names)
    *way, last = names
    shown = _shown(root).joinpath(*names)
    with directory_beneath(root, way) as directory:
        try:
            opened = os.open(last, _FILE, dir_fd=directory)
        except OSError as error:
            try:  # O_NOFOLLOW's answer for a link: say where it points, for the caller
                return Link(os.readlink(last, dir_fd=directory))
            except OSError:  # not a link: gone, or can't be opened
                raise type(error)(error.errno, error.strerror, str(shown)) from None
    try:
        found = os.fstat(opened)
        if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            raise NotOneFile(
                f"{shown} is not a regular file with one name (it has another name, or none, or is "
                "a pipe, a device, a directory, ...)",
                found.st_mode,
                found.st_nlink,
            )
        with os.fdopen(os.dup(opened), "rb") as file:
            data = file.read(cap + 1) if found.st_size <= cap else b""
        if found.st_size > cap or len(data) > cap:
            raise TooLarge(f"{shown} is larger than {cap:,} bytes", cap)
        return data
    finally:
        os.close(opened)


def write_beneath(root: Path | int, names: Sequence[str], data: bytes) -> bool:
    """Write `data` as the file `names` reaches beneath `root` (a path, or a directory's
    descriptor, left open), through no link: the directory is walked to as `directory_beneath`
    does, and the file made whole under a name of its own and moved over the name, so a reader
    never sees half of it. Readable by its owner alone. True when it replaced a file, False when
    it made a new one. Raises ValueError for names that are none or not one step each, what
    `directory_beneath` raises for the way there; `Linked` when the name is a link (never
    followed, never replaced); `NotOneFile` when it is anything but a regular file with one
    name; and the OSError writing it gave otherwise (no room, no permission). A write that fails
    leaves nothing of its own behind."""
    if not names:
        raise ValueError("a file beneath a root needs at least its own name")
    _one_each(names)
    *way, last = names
    with directory_beneath(root, way) as directory:
        replaces = _is_ours(directory, names, _shown(root), missing_ok=True)
        temporary = f".{last}.{secrets.token_hex(8)}.tmp"
        made = os.open(temporary, _CREATE, 0o600, dir_fd=directory)
        try:
            with os.fdopen(made, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.rename(temporary, last, src_dir_fd=directory, dst_dir_fd=directory)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary, dir_fd=directory)
            raise
    return replaces


def remove_beneath(root: Path | int, names: Sequence[str]) -> None:
    """Remove the file `names` reaches beneath `root` (a path, or a directory's descriptor, left
    open), walked to through no link. Raises ValueError for names that are none or not one step
    each, what `directory_beneath` raises for the way there; FileNotFoundError when it is not
    there; `Linked` when the name is a link and `NotOneFile` when it is anything but a regular
    file with one name, either left where it is."""
    if not names:
        raise ValueError("a file beneath a root needs at least its own name")
    _one_each(names)
    *way, last = names
    with directory_beneath(root, way) as directory:
        _is_ours(directory, names, _shown(root), missing_ok=False)
        os.unlink(last, dir_fd=directory)


def _is_ours(directory: int, names: Sequence[str], root: Path, *, missing_ok: bool) -> bool:
    """Whether the last of `names` (beneath `root`, as shown) is a file in `directory` to write or
    remove: True for a regular file with one name, False when it is not there and `missing_ok`.
    Raises `Linked` for a link (judged without following it) and `NotOneFile` for anything but a
    file with one name."""
    shown = root.joinpath(*names)
    try:
        found = os.stat(names[-1], dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError as error:
        if missing_ok:
            return False
        raise FileNotFoundError(error.errno, error.strerror, str(shown)) from None
    if stat.S_ISLNK(found.st_mode):
        raise Linked(f"{shown} is a link, which is not followed beneath {root}", PurePath(*names))
    if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
        raise NotOneFile(
            f"{shown} is not a regular file with one name (it has another name, or is a pipe, a "
            "device, a directory, ...)",
            found.st_mode,
            found.st_nlink,
        )
    return True


def _one_each(names: Sequence[str]) -> None:
    """Each name is one step beneath the root: a `/` in one would walk the steps it joins
    following links, and `..` would leave the root."""
    for name in names:
        if not name or name in {".", ".."} or "/" in name:
            raise ValueError(f"each name beneath a root is one name, not a path or '.' or '..': {name!r}")


def _shown(root: Path | int) -> Path:
    """How the root is named in an error: its path, or where its descriptor is."""
    return root if isinstance(root, Path) else Path(f"/dev/fd/{root}")


def _stopped(error: OSError, at: int, name: str, root: Path, part: PurePath) -> OSError:
    """Why opening `name` (the directory `part` beneath `root`) failed, as the error to raise: a
    link (`O_NOFOLLOW` answers ENOTDIR or ELOOP for one; which it was, the name's own stat says),
    else what opening it said (not a directory, not there, ...), naming the part."""
    with contextlib.suppress(OSError):
        if stat.S_ISLNK(os.stat(name, dir_fd=at, follow_symlinks=False).st_mode):
            return Linked(f"{root / part} is a link, which is not followed beneath {root}", part)
    return type(error)(error.errno, error.strerror, str(root / part))
