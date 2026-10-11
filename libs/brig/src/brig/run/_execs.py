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
from dataclasses import dataclass
from typing import Final

#: Subdirectory of `jail_dir` holding one file per registered sibling.
EXECS_DIRNAME: Final = "execs"

_SUFFIX: Final = ".json"

#: A process id the kernel can hand out is above 1 (0 names the caller's own
#: group to `killpg`, 1 is init) and below 2**31 (`pid_t` is 32 bits signed).
#: A registration naming anything else is not one brig wrote.
_PID_LIMIT: Final = 2**31


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
    that number to next (`_identity.UNKNOWN` where the host couldn't read
    it; teardown signals nothing for such a registration, decision-172).
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


@dataclass(frozen=True, slots=True)
class Registration:
    """One readable registration: the sibling's pid, its group, and its stamp."""

    pid: int
    pgid: int
    start_time: str


@dataclass(frozen=True, slots=True)
class Unreadable:
    """A file in the registration directory that is not a registration.

    `reason` says what was wrong with it, for whoever has to inspect it."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Scan:
    """What the registration directory holds: the readable registrations in
    registration order, and every file that could not be read."""

    registrations: tuple[Registration, ...]
    unreadable: tuple[Unreadable, ...]


def _is_process_id(value: object) -> bool:
    """Whether `value` is an int a process or group id can hold (2 up to 2**31)."""
    return type(value) is int and 1 < value < _PID_LIMIT


def _parse(text: str) -> Registration | str:
    """The registration `text` holds, or the reason it is not one."""
    try:
        record = json.loads(text)
    except ValueError as error:
        return f"not JSON ({error})"
    if type(record) is not dict:
        return f"expected a JSON object, got {type(record).__name__}"
    missing = [key for key in ("pid", "pgid", "start_time") if key not in record]
    if missing:
        return f"missing key(s) {', '.join(missing)}"
    pid, pgid, start_time = record["pid"], record["pgid"], record["start_time"]
    if not (_is_process_id(pid) and _is_process_id(pgid)):
        return f"'pid'/'pgid' must both be ints from 2 to {_PID_LIMIT - 1}, got {pid!r}/{pgid!r}"
    if type(start_time) is not str:
        return f"'start_time' must be a str, got {start_time!r}"
    return Registration(pid, pgid, start_time)


def scan(jail_dir: str) -> Scan:
    """Read every registration under `jail_dir`, never raising on one that is
    unreadable: it is returned in `Scan.unreadable` for the caller to report.

    Registrations are in registration order (the file's own mtime, with the
    pid as a tiebreaker so the order is total rather than arbitrary).
    Unreadable ones are in name order.

    An empty scan for a jail that has no `execs` directory at all -- a jail
    that never exec'd is not an error, and neither is a rehydrated handle
    pointed at a jail directory that has since been swept.

    A file that vanishes between the listing and the read was deregistered by
    a `wait()` that returned meanwhile; gone is what teardown looks for, so it
    is skipped. Any OTHER failure to read a file is an `Unreadable`: skipping
    it silently would be the quiet half-teardown SPEC.md section 9 forbids,
    and raising would stop the teardown of everything else.
    """
    directory = execs_dir(jail_dir)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return Scan((), ())

    found: list[tuple[float, Registration]] = []
    unreadable: list[Unreadable] = []
    for name in names:
        if not name.endswith(_SUFFIX):
            continue
        path = os.path.join(directory, name)
        try:
            mtime = os.stat(path).st_mtime
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError) as error:
            unreadable.append(Unreadable(path, f"cannot be read ({error})"))
            continue
        parsed = _parse(text)
        if isinstance(parsed, str):
            unreadable.append(Unreadable(path, parsed))
        else:
            found.append((mtime, parsed))
    found.sort(key=lambda entry: (entry[0], entry[1].pid))
    return Scan(tuple(registration for _mtime, registration in found), tuple(unreadable))


def live(jail_dir: str) -> list[tuple[int, int, str]]:
    """`(pid, pgid, start_time)` for every readable registration, in
    registration order. Files `scan` calls unreadable are left out; only
    tests call this, and teardown reads `scan` so it can report them."""
    return [(r.pid, r.pgid, r.start_time) for r in scan(jail_dir).registrations]
