"""Process identity: a pid plus the moment that process started.

**A pid is not an identity.** SPEC.md section 9 named the window and
decision-144 accepted it: a `Handle` records the workload's pid and pgid at
spawn, and a later liveness check or teardown -- possibly in another process,
possibly minutes later -- signals those numbers. Between the two, the leader
can exit, be reaped, and have its number handed to something else entirely.
`alive()` then reads `True` against a stranger, and teardown signals one.

decision-155 (2026-09-08) closes that by recording a second fact at launch:
**when** the process started. A pid identifies a slot; a pid plus a start
time identifies an occupant, because the kernel never rewinds a running
process's start time and never hands the same (pid, start time) pair to two
processes in the same boot. So every liveness and kill decision in this
layer asks two questions instead of one, and a recycled pid reads as gone.

**Where the stamp comes from.** Two readings, one per platform family, both
of them the process table's own answer rather than an inference:

- Linux: `/proc/<pid>/stat` field 22, `starttime` -- clock ticks since boot,
  the canonical answer and the one `pidfd`-less code has always used. The
  `comm` field can contain spaces and parentheses, so the parse starts after
  the LAST `)`, never at the second field of a naive `split()`.
- Everything else POSIX (darwin, the only other platform brig runs on today):
  `/bin/ps -o lstart= -p <pid>`, the absolute start time as text. Never a
  bare `ps` -- alias-proof per decision-026, the same rule `teardown.py`
  follows. Its resolution is one second, which is coarse, and that is stated
  rather than hidden: two processes that hold the same pid within the same
  second are indistinguishable here. A pid is not reused within a second on
  any system this library targets (darwin allocates pids sequentially through
  a 99999-wide space), so the residual window is narrower than the one it
  replaces by orders of magnitude -- narrowed, not eliminated, which is the
  honest claim.

**The unknown stamp is a real value, not an error.** `UNKNOWN` (the empty
string) is what a launch records when the process was already gone before the
stamp could be read -- a fast workload that exits within microseconds of the
spawn, the same race `_spawn_pgid.py` documents for `getpgid`. A handle
carrying `UNKNOWN` degrades to exactly the pid-only behaviour that shipped
before this module existed: no worse than the old code, and it says so at
every call site rather than silently pretending to a check it cannot make.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Final

#: The stamp recorded when a process's start time could not be read -- the
#: process was already gone, or the platform has no reading. Comparisons
#: against it degrade to a pid-existence check (see `identity_holds`).
UNKNOWN: Final = ""

_LINUX_PREFIX: Final = "linux-starttime:"
_PS_PREFIX: Final = "ps-lstart:"


def _linux_start_stamp(pid: int) -> str | None:
    """`/proc/<pid>/stat`'s `starttime` field, or `None`."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as stat:
            text = stat.read()
    except OSError:
        return None
    # `comm` is parenthesized and may itself contain spaces and parentheses,
    # so the fields after it begin past the LAST ')'. `starttime` is field
    # 22 overall, which is index 19 of what follows `comm`.
    close = text.rfind(")")
    if close < 0:
        return None
    fields = text[close + 1 :].split()
    if len(fields) < 20:
        return None
    return f"{_LINUX_PREFIX}{fields[19]}"


def _ps_start_stamp(pid: int) -> str | None:
    """`/bin/ps -o lstart= -p <pid>`, or `None` when there is no such row."""
    try:
        done = subprocess.run(
            ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    line = done.stdout.strip()
    if done.returncode != 0 or not line:
        return None
    # Collapse runs of spaces: `lstart` pads the day-of-month, and a stamp
    # that changed shape between two readings of the same process would be
    # a false mismatch.
    return f"{_PS_PREFIX}{' '.join(line.split())}"


def start_stamp(pid: int) -> str:
    """When the process at `pid` started, as an opaque comparable string.

    `UNKNOWN` when there is no such process, or the reading failed. Never
    raises: a stamp that cannot be taken is a fact to record, not an error
    to propagate into a launch path that has already spawned something.
    """
    stamp = _linux_start_stamp(pid) if sys.platform.startswith("linux") else _ps_start_stamp(pid)
    return stamp if stamp is not None else UNKNOWN


def pid_exists(pid: int) -> bool:
    """Whether `pid` names any process at all -- the cheap half.

    `os.kill(pid, 0)` sends no signal; it runs the kernel's own
    existence/permission check. `PermissionError` means the process exists
    and belongs to someone else, which is existence, so it is `True`.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def identity_holds(pid: int, stamp: str) -> bool:
    """True when `pid` still names the process `stamp` was taken from.

    False for a pid that names nothing, and false for a pid the OS has
    handed to a different process -- which is the whole point: **a recycled
    pid reads as gone**, never as the original still running.

    With `stamp == UNKNOWN` this degrades, deliberately and visibly, to a
    pid-existence check: nothing was recorded to compare against, and
    inventing a mismatch would report a live workload as gone.
    """
    if not pid_exists(pid):
        return False
    if stamp == UNKNOWN:
        return True
    current = start_stamp(pid)
    if current == UNKNOWN:
        # The process existed a moment ago and now has no row: it ended
        # between the two reads. Gone is the honest answer.
        return False
    return current == stamp


def recycled(pid: int, stamp: str) -> bool:
    """True only when `pid` names a process that is DEMONSTRABLY not ours.

    Deliberately narrower than `not identity_holds(...)`, and the difference
    is the case where the pid names nothing at all. A leader that has exited
    and been reaped leaves a pid that names nothing -- but its process
    *group* can still hold live children, and teardown must go on signalling
    that group. Only a pid whose current occupant is a different process is
    a reason to signal nothing at all.
    """
    if stamp == UNKNOWN:
        return False
    current = start_stamp(pid)
    return current != UNKNOWN and current != stamp
