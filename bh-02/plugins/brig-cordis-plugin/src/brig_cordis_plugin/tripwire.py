"""What ends a Linux jail when the host undoes one of its mounts: a tripwire on each held path.

bubblewrap holds a path (a write deny, a masked secret, a placeholder) with a mount on the
host's directory entry, and the kernel detaches that mount inside the jail when the host
replaces the entry (a host `git config` renames a new `.git/config` over the old one; editors
save by rename), renames it away or removes it. From then on a cell could write the path. No
mount can be put back from outside (entering the jail's mount namespace is refused: measured),
and a read-only parent directory would break a jailed `git commit` (it creates `.git/index.lock`:
measured), so the jail ends instead, at once, and the next cell's jail holds the path again.

`wires` turns the held paths into what to watch (each one's directory, by name), `decoded` reads
the kernel's inotify records, and `lifted` decides which held paths those events took away: all
three pure. `Tripwire` is the shell: an inotify descriptor, set up before bubblewrap starts, and
a thread that waits on it and kills the jail's process group at the first lift.
"""

import contextlib
import ctypes
import os
import select
import signal
import struct
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

__all__ = ["Tripwire", "decoded", "lifted", "tripped_for", "wires"]

# inotify(7)'s event bits: the ones that undo a mount on a name in a watched directory, and those
# that say the directory itself, or the queue, is gone.
_MOVED_FROM, _MOVED_TO, _CREATE, _DELETE = 0x40, 0x80, 0x100, 0x200
_DELETE_SELF, _MOVE_SELF, _OVERFLOW, _IGNORED = 0x400, 0x800, 0x4000, 0x8000
_ON_A_NAME = _MOVED_FROM | _MOVED_TO | _CREATE | _DELETE
_ON_ITSELF = _DELETE_SELF | _MOVE_SELF | _IGNORED
_MASK = _ON_A_NAME | _DELETE_SELF | _MOVE_SELF
_HEADER = struct.Struct("iIII")  # wd, mask, cookie, len; then `len` bytes of name, NUL-padded


def wires(held: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """The directories to watch, each with the names in it a jail holds a mount on."""
    found: dict[str, list[str]] = {}
    for path in dict.fromkeys(held):
        found.setdefault(str(Path(path).parent), []).append(Path(path).name)
    return {directory: tuple(names) for directory, names in found.items()}


def decoded(data: bytes) -> list[tuple[int, int, str]]:
    """inotify's records in `data`: (watch descriptor, mask, name)."""
    out: list[tuple[int, int, str]] = []
    at = 0
    while at + _HEADER.size <= len(data):
        wd, mask, _, size = _HEADER.unpack_from(data, at)
        name = data[at + _HEADER.size : at + _HEADER.size + size].split(b"\0", 1)[0]
        out.append((wd, mask, os.fsdecode(name)))
        at += _HEADER.size + size
    return out


def lifted(events: Iterable[tuple[str, int, str]], watched: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """The held paths that `events` (directory, mask, name) undid the jail's mount on: a name
    renamed over, renamed away, removed or created; every name in a directory that was itself
    removed or moved; and everything when the kernel's queue overflowed. A cell can do none of
    these to a held name (the mount refuses it), so each is the host's.

    Not `<name>.lock` created (git writes `config.lock`, then renames it over `config`): ending
    the jail there too narrowed nothing measurable (a looping program still got its write into
    the lock 17 times in 20, against 20 in 20), and a cell's own `git config` would end its jail
    with a message blaming the host."""
    out: list[str] = []
    for directory, mask, name in events:
        names = watched.get(directory, ())
        if mask & _OVERFLOW:
            out += [str(Path(d, n)) for d, held in watched.items() for n in held]
        elif mask & _ON_ITSELF:
            out += [str(Path(directory, n)) for n in names]
        elif mask & _ON_A_NAME and name in names:
            out.append(str(Path(directory, name)))
    return tuple(dict.fromkeys(out))


def tripped_for(paths: Sequence[str]) -> str:
    """Why the jail ended itself, for the person (in the cell's answer)."""
    return (
        f"something on the host replaced or removed {', '.join(paths)} (a `git config`, an "
        "editor's save), which lifts the jail's hold on it, so bh-02 ended the jail; the next "
        "one holds it again"
    )


class Tripwire:
    """An inotify descriptor watching the directories of a jail's held paths (`wires`), made
    before bubblewrap starts so nothing that happens from then on is missed, and, once the jail
    runs, a thread that kills its process group at the first event that lifts a hold
    (`lifted`) and keeps why (`tripped`). Built only on Linux; `stop` before the jail's
    placeholders are removed, which would read as lifts."""

    def __init__(self, held: Iterable[str]) -> None:
        self.tripped = ""
        self._watched = wires(held)
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._fd: int = self._libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self._fd < 0:
            raise OSError(
                ctypes.get_errno(), "inotify_init1 failed: the jail can't see the host undo its mounts"
            )
        self._dirs: dict[int, str] = {}
        for directory in self._watched:
            wd = self._libc.inotify_add_watch(self._fd, os.fsencode(directory), _MASK)
            if wd < 0:
                error = ctypes.get_errno()
                os.close(self._fd)
                raise OSError(error, f"can't watch {directory} for the host undoing the jail's mounts")
            self._dirs[wd] = directory
        self._stop_r, self._stop_w = os.pipe()
        self._thread: threading.Thread | None = None

    def arm(self, group: int) -> None:
        """Start the thread that ends process group `group` at the first lift."""
        self._thread = threading.Thread(target=self._watch, args=(group,), name="bh-02 tripwire", daemon=True)
        self._thread.start()

    def _watch(self, group: int) -> None:
        while True:
            ready, _, _ = select.select([self._fd, self._stop_r], [], [])
            if self._stop_r in ready:
                return
            try:
                data = os.read(self._fd, 1 << 16)
            except BlockingIOError:
                continue
            events = [(self._dirs.get(wd, ""), mask, name) for wd, mask, name in decoded(data)]
            if paths := lifted(events, self._watched):
                self.tripped = tripped_for(paths)  # first: whoever sees the jail gone asks why
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(group, signal.SIGKILL)
                return

    def stop(self) -> None:
        """Stop watching and let go of the descriptor: from here on nothing ends the jail."""
        os.write(self._stop_w, b"x")
        if self._thread is not None:
            self._thread.join()
        for fd in (self._fd, self._stop_r, self._stop_w):
            with contextlib.suppress(OSError):
                os.close(fd)
