"""Resolving the process group of a child this package just spawned (task-075).

Both spawn sites in this package -- `launcher.py`'s workload launch and
`exec_.py`'s exec sibling -- call `os.getpgid(pid)` immediately after
`subprocess.Popen(..., start_new_session=True)` returns. On darwin that call
raises ESRCH when the child has ALREADY EXITED by then: confirmed at the raw
syscall level in task-075 (`getpgid()` refuses to resolve a zombie even
though `/bin/ps` still shows its group; Linux resolves it). A fast command
(`/usr/bin/true`, an `echo` probe) exits within microseconds, so under any
scheduling delay the read races the exit and crashes the spawn path at the
worst possible moment -- after the process exists but before ANYTHING is
recorded about it: no SPAWN/EXEC event, no `Handle`/`ExecHandle`, no exit
waiter. The orphaned `Popen`'s zombie then lingers until the GC reaps it,
and the session-end leak sweep reports that residue as a leaked process --
task-075's reproduced signature (a `ProcessLookupError` out of
`exec_in_jail`, plus an unreaped `<defunct>` child of the harness at
teardown).

**The pid-reuse seam is ACCEPTED, not overlooked -- decision-144.** The
integer this returns is recorded on the `Handle` and signalled by teardown
later, possibly from another process, so in principle it could name a
recycled pid by then. That ruling states the window precisely, why there is
no atomic alternative at this layer (POSIX has no "signal this group if it is
still mine"; `pidfd_open` is Linux-only), and the four conditions under which
the acceptance ends -- running as root, holding a pid across a durable
boundary, Linux support landing, or teardown doing anything beyond
signalling. Read it before concluding this is an oversight.

The fallback is not an inference about launcher details: with
`start_new_session=True` the child ran `setsid()` before `exec`, so its
process group was its own pid from birth to death, and no other process can
create or join a group bearing that number. Recording `pgid == pid` when the
read is impossible because the child is already gone records the same fact
`os.getpgid` would have returned while the child was alive.
"""

from __future__ import annotations

import os
import subprocess


def spawn_pgid(proc: subprocess.Popen[bytes]) -> int:
    """The process group of a just-spawned `start_new_session=True` child.

    Read via `os.getpgid` while the child is alive; the child's own pid when
    darwin's ESRCH says the child has already exited (see the module
    docstring for why that records the same fact, not a guess)."""
    pid = proc.pid
    try:
        return os.getpgid(pid)
    except ProcessLookupError:
        return pid
