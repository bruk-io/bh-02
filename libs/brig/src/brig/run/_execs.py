"""Durable exec-sibling registration: one small file per live sibling.

SPEC.md section 9's binding clause on `exec` is **durability outside the live
object**: "`exec` records the sibling somewhere the handle can read back *in a
later process*, never only as a field on a live `Handle`, so a rehydrated
handle tears down execs it never itself started." *Which* durable record is an
implementation choice, not a spec one (decision-049).

M2's choice was the per-jail event stream: an `EXEC` record with no matching
`EXEC_END`. decision-152 (2026-09-08) deleted that stream, so the choice is
re-made here, and deliberately NOT by keeping a smaller stream under another
name: a registration is a *set of live siblings*, and a file per member is the
shape that says so. One file, named for the sibling's pid, holding its pgid,
created before the sibling can matter and removed the moment its exit status is
observed. Teardown lists the directory.

Three properties the stream had, kept:

- **Cross-process.** The directory lives under `jail_dir`, which is on the
  serialized `Handle`, so a handle rehydrated in a process that never called
  `exec()` finds every sibling.
- **Later than serialization.** A sibling started *after* the handle was
  serialized still registers, because the registration is on the filesystem
  rather than in the dict -- the property decision-042 chose the stream for.
- **pid, PLUS the moment that process started** (decision-155, 2026-09-08).
  A registration is still named for the sibling's pid, but it now carries the
  sibling's start-time stamp as well (`brig/run/_identity.py`), and teardown
  compares both. A pid the OS recycles between one sibling's deregistration
  and a later registration therefore reads as GONE rather than as a sibling
  still to be signalled -- the window SPEC.md section 9 used to name here is
  closed to the resolution of the platform's own start-time reading.

One property it did NOT have, gained: deregistration is a delete, so the live
set is a directory listing rather than a replay of every record ever appended.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Final

#: Subdirectory of `jail_dir` holding one file per registered sibling.
EXECS_DIRNAME: Final = "execs"

_SUFFIX: Final = ".json"


def execs_dir(jail_dir: str) -> str:
    """Where this jail's sibling registrations live."""
    return os.path.join(jail_dir, EXECS_DIRNAME)


def register(jail_dir: str, pid: int, pgid: int, start_time: str) -> str:
    """Record a live sibling. Returns the registration file's path.

    Written whole, in one `os.write` to a freshly-created file, then renamed
    into place -- a reader listing the directory never sees a half-written
    registration, only a name that is there or is not.

    `start_time` is `brig/run/_identity.start_stamp`'s reading for `pid`,
    recorded so teardown can tell this sibling from whatever the OS hands
    that number to next (`_identity.UNKNOWN` where the read lost its race
    with a sibling that had already exited).
    """
    directory = execs_dir(jail_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{pid}{_SUFFIX}")
    tmp = f"{path}.partial"
    encoded = json.dumps({"pid": pid, "pgid": pgid, "start_time": start_time}).encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return path


def deregister(jail_dir: str, pid: int) -> None:
    """Forget a sibling whose exit status has been observed. Idempotent:
    a registration already gone (a second `wait()`, a teardown that got
    there first) is not an error."""
    with contextlib.suppress(OSError):
        os.remove(os.path.join(execs_dir(jail_dir), f"{pid}{_SUFFIX}"))


def live(jail_dir: str) -> list[tuple[int, int, str]]:
    """`(pid, pgid, start_time)` for every still-registered sibling, ordered by
    registration time (the file's own mtime, with the pid as a tiebreaker
    so the order is total rather than arbitrary).

    An empty list for a jail that has no `execs` directory at all -- a jail
    that never exec'd is not an error, and neither is a rehydrated handle
    pointed at a jail directory that has since been swept.
    """
    directory = execs_dir(jail_dir)
    try:
        names = os.listdir(directory)
    except OSError:
        return []

    found: list[tuple[float, int, int, str]] = []
    for name in names:
        if not name.endswith(_SUFFIX) or name.endswith(".partial"):
            continue
        path = os.path.join(directory, name)
        try:
            mtime = os.stat(path).st_mtime
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except FileNotFoundError:
            # Deregistered between the listing and the read -- a sibling
            # whose `wait()` returned while this scan was running. Gone is
            # exactly what this function is looking for, so it is skipped
            # rather than raised. Every OTHER failure IS raised (below):
            # a registration this process cannot read is a registration it
            # cannot tear down, and skipping that silently would be the
            # quiet half-teardown SPEC.md section 9 exists to forbid.
            continue
        pid = record["pid"]
        pgid = record["pgid"]
        start_time = record["start_time"]
        if type(pid) is not int or type(pgid) is not int:
            raise ValueError(
                f"exec registration {path!r}: 'pid'/'pgid' must both be int, got {pid!r}/{pgid!r}"
            )
        if type(start_time) is not str:
            raise ValueError(
                f"exec registration {path!r}: 'start_time' must be a str, got {start_time!r}"
            )
        found.append((mtime, pid, pgid, start_time))
    found.sort()
    return [(pid, pgid, stamp) for _mtime, pid, pgid, stamp in found]
