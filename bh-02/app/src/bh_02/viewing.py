"""`bh-02 trajectory ID`: a session's files read, and its trajectory handed to the terminal.

The thin shell around `bh_02.trajectory`, which computes and lays out the trajectory and does no
I/O. This module finds the files (a session's own transcripts and its `rows.jsonl`, and its
sub-agents' transcripts under `agents/NAME/`), reads them, and prints what is new; it opens nothing
for writing and creates nothing. Every file is read through `host_paths` (a walk beneath the sessions'
state that follows no link, from a descriptor it opened read-only), and a name is judged before any
path is made of it, with the rule `bh-02 watch` uses (`bh_02.watching`): the session id the person's
command resolved is checked again here, and a sub-agent is a name in the session's `agents/` directory
that bh-02 could have made, never a name a transcript says. A transcript's `child` is only matched
against those, so no text of the model's is ever a path.

`--follow` reads every file again for each poll, by its path, and prints the lines of the trajectory
it has not printed: a `/clear` or `/compact` that replaced the live file changes nothing about how, as
the lines are told apart by where they are in the trajectory (`Line.key`), never by an offset in a
file that is no longer the one that was read.
"""

import os
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import tzinfo
from pathlib import Path

from bh_02.sessions import ROWS
from bh_02.trajectory import Key, Transcript, is_conversation_file, rendered, trajectory
from bh_02.watching import Refused, refused_agent, refused_session
from host_paths import Link, directory_beneath, read_beneath

__all__ = ["shown"]

_AGENTS = "agents"
_CAP = 256 * 1024 * 1024  # a transcript larger than this is not read
_POLL_S = 1.0


def _file(directory: int, where: Path, agent: str | None, name: str) -> Transcript | None:
    """The file `name` in `directory` (a descriptor), read through no link; None if it has gone since
    the directory was listed.

    Raises:
        Refused: it is a link.
        OSError: it can't be read (it is not a plain file, or is too large).
    """
    try:
        data = read_beneath(directory, [name], cap=_CAP)
        modified = os.stat(name, dir_fd=directory, follow_symlinks=False).st_mtime
    except FileNotFoundError:
        return None
    if isinstance(data, Link):
        raise Refused(f"{where / name} is a link, which bh-02 did not make; it is not read")
    return Transcript(agent, name, modified, data)


def _files(root: Path, names: Sequence[str], agent: str | None) -> list[Transcript]:
    """Every conversation file in the directory `names` reaches beneath `root`; none if the directory
    is not there.

    Raises:
        Refused: a file or the way to it is a link, or can't be read.
    """
    where = root.joinpath(*names)
    try:
        with directory_beneath(root, names) as directory:
            listed = sorted(name for name in os.listdir(directory) if is_conversation_file(name))
            read = [_file(directory, where, agent, name) for name in listed]
    except FileNotFoundError:
        return []
    except OSError as error:
        raise Refused(f"can't read {where}: {error}") from None
    return [transcript for transcript in read if transcript is not None]


def _agents(root: Path, session: str) -> list[str]:
    """The names of the session's sub-agents: the entries of its `agents/` directory that are names
    bh-02 makes (any other is passed over, and no path is made of it).

    Raises:
        Refused: the directory is a link, or can't be listed.
    """
    try:
        with directory_beneath(root, [session, _AGENTS]) as directory:
            return sorted(name for name in os.listdir(directory) if refused_agent(name) is None)
    except FileNotFoundError, NotADirectoryError:
        return []
    except OSError as error:
        raise Refused(f"can't read {root / session / _AGENTS}: {error}") from None


def _read(root: Path, session: str) -> list[Transcript]:
    """The session's transcript files, its own and its sub-agents'.

    Raises:
        Refused: a file can't be read (`_files`).
    """
    own = _files(root, [session], None)
    children = [
        transcript
        for name in _agents(root, session)
        for transcript in _files(root, [session, _AGENTS, name], name)
    ]
    return [*own, *children]


def _rows(root: Path, session: str) -> bytes | None:
    """The session's `rows.jsonl` (its row reloads), read through no link; None for a session that has
    none. The shell makes it at boot, before any reply, so a session with a conversation and none had
    its log removed or never written.

    Raises:
        Refused: it is a link, or can't be read.
    """
    where = root / session / ROWS
    try:
        data = read_beneath(root, [session, ROWS], cap=_CAP)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Refused(f"can't read {where}: {error}") from None
    if isinstance(data, Link):
        raise Refused(f"{where} is a link, which bh-02 did not make; it is not read")
    return data


def shown(
    root: Path,
    session: str,
    *,
    follow: bool,
    tz: tzinfo | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    """The trajectory of session `session` (its directory's name under `root`), a line at a time
    without its newline: what the files hold, then (with `follow`) what is added, until the caller
    stops. The files are read again for each poll and never opened for writing. Times are in the
    zone `tz` (None: the machine's).

    Raises:
        Refused: `session` is not a name bh-02 made, no file is there (not following), or one can't
            be read (`_read`, `_rows`).
    """
    if (why := refused_session(session)) is not None:
        raise Refused(why)
    printed: set[Key] = set()
    while True:
        files = _read(root, session)
        if not files and not follow:
            raise Refused(
                f"session {session} has no conversation yet: its transcript.jsonl is made when the "
                f"first message is sent ({root / session})"
            )
        for line in rendered(trajectory(files, _rows(root, session)), tz, live=follow):
            if line.key not in printed:
                printed.add(line.key)
                yield line.text
        if not follow:
            return
        sleep(_POLL_S)
