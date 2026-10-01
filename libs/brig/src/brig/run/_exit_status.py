"""The exit file: how a jail ended, readable by a process that never ran it.

**What this restores, and what it deliberately does not bring back.**
decision-152 (2026-09-08) deleted the per-jail event stream, and SPEC.md
section 11 named the one capability that genuinely went with it: an exit
status readable by a process that never parented the workload. `Handle.wait`
answered in the launching process and raised `ExitStatusUnobservable`
everywhere else, so a rehydrated handle -- the shape an embedder uses to
clean up after a runtime that died holding a jail -- could tear a jail down
but never say how it ended. decision-156 (2026-09-08) gives that back
WITHOUT the stream: not a log, not an appender, not a tail. One file, one
line, written once.

**The wrapper.** `SubprocessLauncher` no longer spawns the compiled jail's
argv directly. It spawns this module's `WRAPPER_SOURCE` under the launching
interpreter, and *that* spawns the jail's argv as its own child, waits for
it, and writes the status to `<jail_dir>/exit` -- written to a `.partial`
name and renamed, so a reader sees a complete status or no file at all,
never a half-written one. The wrapper is the workload's parent, which is
what makes the status exact: `Popen.wait()` distinguishes "exited 143" from
"killed by SIGTERM" (`143` versus `-15`), and a `/bin/sh` wrapper reading
`$?` cannot. That distinction is the whole reason this is a Python program
rather than four lines of shell.

**The wrapper is outside the confinement, and that is the point.** The
jail's own `wrap` (seatbelt, env scrub, the rlimits trampoline) is applied to
the wrapper's CHILD, exactly as before -- the wrapper prepends nothing to the
compiled argv and changes nothing about it, so what the jail runs is
unchanged, and `Handle.argv` still reports the jail's own compiled argv
rather than this plumbing. What the wrapper adds is one trusted-side process
per jail, the same shape as a `JAIL_LIFETIME` helper, whose only job is to
outlive its child by the microseconds it takes to write a number.

Three consequences, stated rather than left to be discovered:

- **`Handle.pid` is the wrapper's pid**, and the jail's own process is its
  child in the same process group. Teardown is group-shaped at every rung
  (SPEC.md section 9), so nothing about kill changes; `alive()` tracks the
  wrapper, which lives exactly as long as the workload plus the write.
- **A `SIGKILL`ed group writes nothing.** `SIGKILL` cannot be caught, so a
  jail torn down by the ladder's last rung leaves no exit file and
  `ExitStatusUnobservable` is still the honest answer there. The killer holds
  the `KillReport`, which is the record of that ending. The wrapper does hold
  `SIGTERM`/`SIGINT`/`SIGHUP`/`SIGQUIT` -- with a handler, never `SIG_IGN`,
  because `SIG_IGN` survives `exec` and would hand the workload an immunity
  the Spec never granted it -- so the ordinary teardown rung and
  `Handle.interrupt` both still end with a status on disk.
- **The record belongs to ONE launch** (decision-162, 2026-09-08). `wait`
  prefers this file over any live observation, so a stale record left by an
  earlier launch into the same directory would be returned as the new jail's
  status the instant it was asked. `clear_exit_status` -- called by the
  launcher before it stages or spawns anything -- is what makes "the file is
  there" mean "this workload ended".
- **A jail that may write its own `jail_dir` may write this file.** The
  wrapper's own write is the last one, so the status a reader finds after the
  jail is gone is the wrapper's; a workload can only forge one while it is
  still running, which is a window in which the real status does not exist
  yet anyway. brig grades enforcement, not a workload's honesty about
  itself, and this file makes no claim it cannot keep.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Sequence
from typing import Final

#: `<jail_dir>/exit`. SPEC.md section 9 names the path, so it is a constant
#: rather than a parameter: a rehydrated handle finds the file from
#: `jail_dir` alone, with nothing else to be told.
EXIT_FILENAME: Final = "exit"

_PARTIAL_SUFFIX: Final = ".partial"

#: The wrapper program, run as `python -c WRAPPER_SOURCE <exit file>
#: <ready fd> <argv...>`. Kept as a string rather than a module so that
#: running it needs no importable `brig` inside the launched environment and
#: no `if __name__` guard for pypeeker's `import-time-side-effects` rule to
#: find. It is pure text here and executable only when a launcher passes it
#: to an interpreter, which is what makes it unit-testable as data.
WRAPPER_SOURCE: Final = '''\
"""brig exit wrapper: run one argv, record how it ended, end the same way."""

import os
import signal
import subprocess
import sys

exit_file = sys.argv[1]
ready_fd = int(sys.argv[2])
tether_fd = None if sys.argv[3] == "-" else int(sys.argv[3])
argv = sys.argv[4:]

#: The tether's watcher (decision-167): blocks on the tether until every write end is gone,
#: then ends its own process group, the jail's. SIGINT is ignored, because `interrupt` is for
#: the workload; SIGTERM keeps its default, so teardown's first rung ends it like any member.
#: Nothing it runs is exec'd, so the ignored disposition reaches nothing else.
TETHER = (
    "import os, signal, sys\\n"
    "signal.signal(signal.SIGINT, signal.SIG_IGN)\\n"
    "fd = int(sys.argv[1])\\n"
    "try:\\n"
    "    while os.read(fd, 512):\\n"
    "        pass\\n"
    "except OSError:\\n"
    "    pass\\n"
    "os.killpg(0, signal.SIGKILL)\\n"
)


def _hold(signum, frame):
    """Keep this process alive through a group signal long enough to write.

    A HANDLER, never `signal.SIG_IGN`: an ignored disposition survives
    `exec` into the workload, which would silently make the jail immune to
    the very signal teardown's first rung sends. A handler is reset to the
    default in any process that execs, so the workload's disposition is
    untouched.
    """
    del signum, frame


for _name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGQUIT"):
    signal.signal(getattr(signal, _name), _hold)

try:
    if tether_fd is not None:
        # Before the workload, so there is no moment it runs untethered. In this process's
        # group (no new session): its `killpg(0, ...)` is the jail's group, and while it lives
        # that group's number can't be handed to anyone else.
        subprocess.Popen(
            [sys.executable, "-c", TETHER, str(tether_fd)],
            pass_fds=(tether_fd,),
            stdin=subprocess.DEVNULL,
        )
        os.close(tether_fd)
    proc = subprocess.Popen(argv)
except OSError as exc:
    os.write(ready_fd, ("err:%s: %s" % (type(exc).__name__, exc)).encode())
    os.close(ready_fd)
    sys.exit(127)
os.write(ready_fd, b"ok")
os.close(ready_fd)

code = proc.wait()

tmp = exit_file + ".partial"
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
try:
    os.write(fd, str(code).encode())
finally:
    os.close(fd)
os.replace(tmp, exit_file)

if code < 0:
    # End the way the workload ended, so the launching process's own
    # `Popen.wait()` reports the same thing the file does. Translating a
    # signal death into an exit code here would make the two disagree.
    sig = -code
    try:
        signal.signal(sig, signal.SIG_DFL)
    except (OSError, RuntimeError, ValueError):
        pass
    os.kill(os.getpid(), sig)
sys.exit(code if code >= 0 else 128 - code)
'''


class WorkloadSpawnFailed(OSError):
    """The wrapper started but could not spawn the jail's own argv.

    Raised out of `launch()` so a workload that cannot be exec'd is a LAUNCH
    failure, exactly as it was when the launcher spawned the argv itself.
    Without this the wrapper would swallow it: `launch()` would return a
    `Handle` for a jail that was already dead, and the mistake would surface
    later and somewhere else as a readiness timeout.
    """


def exit_path(jail_dir: str) -> str:
    """Where this jail's exit status is written."""
    return os.path.join(jail_dir, EXIT_FILENAME)


def partial_path(jail_dir: str) -> str:
    """The name the status is written to before being renamed into place."""
    return exit_path(jail_dir) + _PARTIAL_SUFFIX


def wrapper_argv(
    python: str, jail_dir: str, ready_fd: int, argv: Sequence[str], tether_fd: int | None = None
) -> tuple[str, ...]:
    """`python -c WRAPPER_SOURCE <exit file> <ready fd> <tether fd or -> <argv...>`.

    `tether_fd` (decision-167) is the read end of the launch's tether, inherited by the
    wrapper, which hands it to the watcher it starts before the workload; `-` when the launch
    is not tethered.

    `argv` is the jail's already-compiled argv and is passed through
    untouched -- the wrapper prepends nothing to it, which is what keeps
    `handle.wrap_prefix` (derived from the jail's own `wrap`) a faithful
    prefix for `exec` to reproduce.
    """
    tether = "-" if tether_fd is None else str(tether_fd)
    return (python, "-c", WRAPPER_SOURCE, exit_path(jail_dir), str(ready_fd), tether, *argv)


def clear_exit_status(jail_dir: str) -> None:
    """Remove any exit record left in `jail_dir` by an EARLIER launch.

    Called by the launcher before it spawns, and load-bearing rather than
    tidy (decision-162, 2026-09-08): `Handle.wait` answers from this file
    whenever it is there, so a second jail launched into a directory that
    still holds the first jail's status returns that stale number
    IMMEDIATELY -- before its own workload has run, let alone finished. The
    caller then reads empty stdio and believes it. Both names go: `exit`,
    and the `.partial` a wrapper killed mid-write may have left beside it.

    Missing files are not an error -- the ordinary case is a fresh jail
    directory with neither name in it.
    """
    for path in (exit_path(jail_dir), partial_path(jail_dir)):
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)


def read_exit_status(jail_dir: str) -> int | None:
    """The recorded status for this jail, or `None` if the file is not there.

    `None` means the wrapper never got as far as writing -- the jail is
    still running, or it was `SIGKILL`ed, or no wrapper ever ran (a handle
    pointed at a swept jail directory). It never means zero.

    A file that exists but does not hold an integer is a corrupted record,
    and it raises rather than being read as any particular status: this is
    the one file whose whole job is to not invent a number.
    """
    path = exit_path(jail_dir)
    try:
        with open(path, encoding="utf-8") as recorded:
            text = recorded.read()
    except OSError:
        return None
    try:
        return int(text.strip())
    except ValueError as exc:
        raise ValueError(f"exit record {path!r} does not hold an integer: {text!r}") from exc
