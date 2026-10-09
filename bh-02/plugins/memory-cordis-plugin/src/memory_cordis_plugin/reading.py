"""Reading a memory file so that nothing the model changed chooses what is read.

The model can write the project (from the jail), and bh-02 reads its CLAUDE.md files in its own
process, outside the jail, then tells the model what they say. So a file in the project is
walked to from the project's root through no link (`O_NOFOLLOW` on every part) and read from
what that opened, only when it is a regular file with one name; a link there is read as its
target, the same way, only when that is another of the memory files found (a CLAUDE.md linking
to the AGENTS.md beside it). A file outside the project (yours, the managed policy's, one in a
directory above the project) is read as it is named, unless its way passes through the project
(`host_paths.passes`, the walk the models file and the kernel's startup files are held to): a
link of yours into the project, whose end the model could repoint, is not followed. None named
like a secret (`local.env`, `.env`, `*.env`) is read, and none larger than Claude Code reads
(4 MiB).
"""

import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path, PurePath

from host_paths import MOST_LINKS, passes, roots

__all__ = ["LIMIT", "read", "secret", "under"]

LIMIT = 4 * 1024 * 1024  # a memory file larger than this is skipped, as Claude Code skips one
_SECRET = re.compile(r"^\.env(\..*)?$|\.env$")  # local.env, .env, .env.local, prod.env: never read


def secret(path: Path) -> bool:
    """Whether a file is named like a secret (`local.env`, `.env`, `*.env`): never read."""
    return bool(_SECRET.search(path.name))


def under(path: Path, found: Sequence[Path]) -> PurePath | None:
    """Where the absolute `path`, as named (`..` taken out), is from the project's root (`found`,
    as `host_paths.roots` gives them); None when it is outside."""
    named = Path(os.path.normpath(path))
    return next((named.relative_to(r) for r in found if named.is_relative_to(r)), None)


def read(path: Path, files: Sequence[Path], root: Path) -> str:
    """The text of `path`, read so that nothing the model changed since it was found chooses
    what is read. `files` are the memory files found with it (a link in the project may lead only
    to one of them); `root` is the project's, and every path absolute.

    One in the project is walked to from its root through no link (`O_NOFOLLOW` on every part),
    and read from what that opened only when it is a regular file with one name; a link there is
    read as its target, the same way, only when that is another of `files`. One outside the
    project is read as it is named, unless its way passes through the project. Raises OSError
    saying why a file was not read."""
    found = roots(root)
    if secret(path):
        raise OSError(f"{path} is named like a secret, so bh-02 did not read it")
    at, named = _rooted(path, found), path
    for _ in range(MOST_LINKS):
        inside = under(at, found)
        if inside is None:
            if passes(named, found):
                raise OSError(
                    f"{named} is reached through the project, where the model could change what it "
                    "is, so bh-02 did not read it"
                )
            return _named(named)
        text, link = _opened(found[-1], inside.parts)
        if link is None:
            return text
        target = _rooted(at.parent / link, found)
        if target not in {_rooted(file, found) for file in files} or secret(target):
            raise OSError(
                f"{at} is a link to {link}, which is not another memory file, so bh-02 did not read it"
            )
        at = named = target
    raise OSError(f"{path} leads through more than {MOST_LINKS} links, so bh-02 did not read it")


def _named(path: Path) -> str:
    """A file outside the project, read as named: a regular file (a pipe is not waited on) no
    larger than `LIMIT`."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as file:
        found = os.fstat(file.fileno())
        if not stat.S_ISREG(found.st_mode):
            raise OSError(f"{path} is not a regular file, so bh-02 did not read it")
        if found.st_size > LIMIT:
            raise OSError(f"{path} is larger than 4 MiB, so bh-02 skipped it, as Claude Code does")
        return file.read().decode("utf-8", errors="replace")


def _opened(root: Path, parts: Sequence[str]) -> tuple[str, str | None]:
    """The file `parts` names under the directory `root`, walked to through no link: its text and
    None, or, when its last part is a link, '' and what that link points to. Raises OSError when a
    directory on the way is a link or not a directory, or the file is not a regular file with one
    name (a hard link; a pipe, opened without waiting for a writer), or is larger than `LIMIT`."""
    if not parts:
        raise IsADirectoryError(f"{root} is the project's root, not a file, so bh-02 did not read it")
    here = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for depth, part in enumerate(parts[:-1], start=1):
            try:
                below = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=here)
            except OSError as error:
                raise OSError(
                    f"{root.joinpath(*parts)} is reached through {root.joinpath(*parts[:depth])}, "
                    f"which is a link or not a directory ({error.strerror}), so bh-02 did not read it"
                ) from None
            os.close(here)
            here = below
        try:
            opened = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=here)
        except OSError as error:
            try:
                return "", os.readlink(parts[-1], dir_fd=here)
            except OSError:  # not a link: gone, or can't be opened
                raise error from None
    finally:
        os.close(here)
    with os.fdopen(opened, "rb") as file:
        found = os.fstat(file.fileno())
        if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            raise OSError(
                f"{root.joinpath(*parts)} is not a regular file with one name (it has another name, "
                "or is a pipe, a device, ...), so bh-02 did not read it"
            )
        if found.st_size > LIMIT:
            raise OSError(
                f"{root.joinpath(*parts)} is larger than 4 MiB, so bh-02 skipped it, as Claude Code does"
            )
        return file.read().decode("utf-8", errors="replace"), None


def _rooted(path: Path, found: Sequence[Path]) -> Path:
    """The absolute `path` as named, `..` taken out, and from the resolved root when it is in the
    project, so a file in it has one name however the root was named."""
    inside = under(path, found)
    return Path(os.path.normpath(path)) if inside is None else found[-1] / inside
