"""The `memory` tool at work: a memory saved, read or deleted in the auto memory directory
(`host.auto_memory`), from bh-02's own process, outside the jail.

That is safe, and the only reason it is: the code that writes is bh-02's, not the model's, and it
writes only beneath that one directory, which the jailed model can already write without being
asked. The model can leave anything there, so every name is opened through no link
(`host_paths`): a link, a second name for a file or anything but a regular file is refused with
the reason and left as it is, and nothing outside the directory is read, written or removed.

A save checks MEMORY.md before it writes anything, writes the topic file, then the index, each
whole or not at all (`write_beneath`), so the index never lacks a line for a memory that was
saved or keeps one for a memory that was deleted, except where a person wrote the line.

A save and a delete also hold an exclusive `flock` on the memory directory (opened through no
link, `host_paths.directory_beneath`) for their whole read, change and write of MEMORY.md, so two
sessions on one project (or two worktrees) saving or deleting at once never read the same old
index and have the last rename win: the other's line would be lost until saved again. The lock
is advisory (every writer that matters is bh-02's own tool, never a write the model makes through
Python) and goes with the descriptor, closed as `directory_beneath` leaves it, so a crashed
session holds nothing.
"""

import asyncio
import contextlib
import fcntl
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePath
from typing import Any, assert_never

from host_paths import (
    Link,
    Linked,
    NotOneFile,
    directory_beneath,
    read_beneath,
    remove_beneath,
    write_beneath,
)
from memory_cordis_plugin.auto import INDEX
from memory_cordis_plugin.keeping import (
    Action,
    Delete,
    Read,
    Save,
    index_line,
    topic_file,
    topic_text,
    understood,
    with_line,
)
from memory_cordis_plugin.reading import LIMIT

__all__ = ["call", "keep"]

type Json = Mapping[str, Any]

_BYTES = {"encoding": "utf-8", "errors": "surrogateescape"}  # an index a person wrote comes back whole


async def call(directory: Path, input: Json) -> Json:
    """One call of the `memory` tool, as the tools broker runs it: the text the model reads, as
    `{"content": ...}`. A call that is refused says why and writes nothing; the work is done in a
    thread, so a slow disk never holds the event loop the TUI shares."""
    asked = understood(input)
    if isinstance(asked, str):
        return {"content": asked}
    return {"content": await asyncio.to_thread(keep, directory, asked)}


def keep(directory: Path, asked: Action) -> str:
    """Do what `asked` asks in `directory`, and say what happened: the text the model reads. A
    name the model made a link, or a second name for another file, is refused, saying so."""
    match asked:
        case Save():
            return _saved(directory, asked)
        case Read():
            return _read(directory, asked.name)
        case Delete():
            return _deleted(directory, asked.name)
        case _ as unreachable:
            assert_never(unreachable)


def _saved(directory: Path, save: Save) -> str:
    """`save` written under a lock on `directory`: the index checked first, so a refusal writes
    nothing; then the topic file, then the index with the memory's line."""
    file = topic_file(save.name)
    try:
        with _locked(directory) as at:
            try:
                index = _index(at)
                replaced = write_beneath(at, [file], topic_text(save).encode())
            except OSError as error:
                return _failed(error, f"save the memory {save.name!r}")
            try:
                write_beneath(at, [INDEX], with_line(index, save.name, index_line(save)).encode(**_BYTES))
            except OSError as error:
                return (
                    f"error: the memory {save.name!r} was written to {file}, but {INDEX} could not be "
                    f"updated, so it has no line there yet: {error}"
                )
    except OSError as error:
        return _failed(error, f"save the memory {save.name!r}")
    return (
        f"{'updated' if replaced else 'saved'} the memory {save.name!r} ({save.kind}) in {file}, "
        f"and its line in {INDEX}"
    )


def _read(directory: Path, name: str) -> str:
    """The text of the memory `name`, or why it can't be read."""
    file = topic_file(name)
    try:
        found = read_beneath(directory, [file], cap=LIMIT)
    except FileNotFoundError as error:
        return _failed(error, f"read the memory {name!r}") if not directory.is_dir() else _unknown(name)
    except OSError as error:
        return _failed(error, f"read the memory {name!r}")
    if isinstance(found, Link):
        return f"error: bh-02 did not read {file}: it is a link (to {found.target}), which is not followed"
    return found.decode("utf-8", errors="replace")


def _deleted(directory: Path, name: str) -> str:
    """The memory `name` deleted under a lock on `directory`: its topic file and its line in the
    index. A line whose file is already gone is taken out too."""
    file = topic_file(name)
    try:
        with _locked(directory) as at:
            index = _index(at)
            try:
                remove_beneath(at, [file])
                had_file = True
            except FileNotFoundError:
                had_file = False
            lines = with_line(index, name, None)
            if not had_file and lines == index:
                return _unknown(name)
            if lines != index:
                try:
                    write_beneath(at, [INDEX], lines.encode(**_BYTES))
                except OSError as error:
                    return (
                        f"error: the memory {name!r} was deleted, but {INDEX} could not be updated, so "
                        f"its line is still there: {error}"
                    )
    except OSError as error:
        return _failed(error, f"delete the memory {name!r}")
    return f"deleted the memory {name!r}" + (
        f" and its line in {INDEX}" if had_file else f": it had no file, so only its line in {INDEX} went"
    )


@contextlib.contextmanager
def _locked(directory: Path) -> Iterator[int]:
    """`directory`, opened through no link (`host_paths.directory_beneath`) and held under an
    exclusive `flock` for a save or delete's whole read, change and write of MEMORY.md: its
    descriptor, to read and write beneath instead of `directory` itself, so the lock covers every
    step. The lock goes with the descriptor, released when it is closed on leaving, so a crashed
    session holds nothing. Raises what `directory_beneath` raises when `directory` is not there,
    or is a link on the way."""
    with directory_beneath(directory, []) as at:
        fcntl.flock(at, fcntl.LOCK_EX)
        yield at


def _index(directory: int) -> str:
    """MEMORY.md as it reads now ('' when there is none yet), read through no link beneath the
    locked directory `directory`. Raises OSError for an index that is not to be read or
    rewritten: a link, a second name for another file, or a file that is too large."""
    try:
        found = read_beneath(directory, [INDEX], cap=LIMIT)
    except FileNotFoundError:
        return ""
    if isinstance(found, Link):
        raise Linked(f"{INDEX} is a link (to {found.target}), which is not followed", PurePath(INDEX))
    return found.decode(**_BYTES)


def _unknown(name: str) -> str:
    return (
        f"error: there is no memory named {name!r}; MEMORY.md, in your prompt, lists the memories there are"
    )


def _failed(error: OSError, doing: str) -> str:
    """Why bh-02 did not `doing`, for the model: the reason, and for a link or a second name,
    that it was left where it is."""
    left = (
        " It was left as it is; choose another name, or ask the person."
        if isinstance(error, Linked | NotOneFile)
        else ""
    )
    return f"error: bh-02 did not {doing}: {error}.{left}"
