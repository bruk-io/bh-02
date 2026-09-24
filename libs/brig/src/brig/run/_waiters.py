"""Per-jail exit waiters: who reaps a workload, and where its status lands.

**The problem this solves.** `subprocess._cleanup()` runs inside every
`Popen.__init__` and reaps any exited `Popen` that has been dropped. The
launcher reads `.pid` and drops its `Popen`, so a jailed workload was reaped
by whatever spawned next, anywhere in the process. A caller's own
`os.waitpid(pid)` then raised `ChildProcessError`, which five integration
helpers translated into exit status **0** -- a clean exit. In a denial test
that reads as a jail that failed to deny; in an allowed-case control it reads
as a write that was never observed at all.

**Why not simply hold the `Popen`.** Tried, and it trades the bug for a worse
one: holding the reference takes the reap away from `_cleanup()` without
performing it, so a workload killed by a *rehydrated handle in another
process* lingers as a zombie and `os.kill(pid, 0)` keeps saying it exists.
Three tests assert exactly the opposite, and they are right to -- "kill leaves
nothing" is a shipped property (SPEC.md section 9).

**What this does instead.** One thread per launch, holding the `Popen` and
blocked in `wait()`. It reaps the moment the workload exits -- so no zombie --
and records the status **in this process's memory**, together with the
`Event`s the jail's mechanism sensors make of that ending
(`EventSource.classify_exit`, stamped through `brig/run/events.py`).

**In memory, and the limit that follows, stated rather than left silent.**
Until decision-152 (2026-09-08) the status went into a per-jail JSONL file, so
a `Handle` rehydrated in another process could read it back. That file is
gone, and with it that capability: `Handle.wait()` answers in the process that
launched the workload and raises `ExitStatusUnobservable` anywhere else. The
trade is deliberate. The file bought exactly one reader -- a rehydrated
handle asking "how did it end?" -- at the cost of a second, worse log beside
every embedder's real one; a rehydrated handle's actual job is teardown
("kill leaves nothing"), which needs `alive()` and pgids, not a status. An
embedder that needs the status durably has the events and the status returned
to it at the point they are known and writes them into its own log, which is
where a durable record belongs.

**Not a daemon** (SPEC.md section 1's "no resident daemon"): the thread's
lifetime is exactly the workload's, it is created by a launch and ends when
that workload ends, and it holds no state beyond the one `Popen`. The other
stated limit: if the launching process dies before the workload does, nothing
observes the status at all -- and `Handle.wait()` reports that honestly rather
than inventing one.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass

from brig.core import Event
from brig.mech import EventSource, ExitOutcome
from brig.run.events import stamp_all


@dataclass(frozen=True, slots=True)
class ExitRecord:
    """How one workload ended, as this process observed it.

    Attributes:
        returncode: Python's own subprocess encoding -- zero or positive is
            an exit code, negative is `-signal_number`.
        events: One stamped `Event` per mechanism sensor that recognized
            something in this ending. Empty when no sensor did, which is the
            normal answer and not a gap.
    """

    returncode: int
    events: tuple[Event, ...]


_LOCK = threading.Lock()
_WATCHED: set[int] = set()
_EXITS: dict[int, ExitRecord] = {}


def is_watched(pid: int) -> bool:
    """True when a waiter owns `pid`'s reap, so nothing else should call
    `waitpid` on it -- whoever wins that race, the loser gets ECHILD and the
    status is lost."""
    with _LOCK:
        return pid in _WATCHED


def recorded_exit(pid: int) -> ExitRecord | None:
    """This process's own observation of how `pid` ended, or `None` -- it is
    still running, this process never launched it, or the process that did
    launch it was not this one."""
    with _LOCK:
        return _EXITS.get(pid)


def forget(pid: int) -> None:
    """Drop a recorded exit. For tests that need a clean slate; nothing in
    the library calls it, because a jail's exit is a fact its launching
    process keeps for as long as it lives."""
    with _LOCK:
        _EXITS.pop(pid, None)


def watch(
    proc: subprocess.Popen[bytes],
    *,
    jail_id: str,
    sensors: tuple[EventSource, ...] = (),
) -> None:
    """Reap `proc` when it exits, and record its status and the sensors'
    reading of that ending."""
    pid = proc.pid
    with _LOCK:
        _WATCHED.add(pid)

    def _run() -> None:
        try:
            code = proc.wait()
        except Exception:  # a lost reap must not kill the thread
            code = None
        finally:
            with _LOCK:
                _WATCHED.discard(pid)
        if code is None:
            return  # nothing observed; wait() will say so rather than guess
        outcome = ExitOutcome(returncode=code)
        payloads = [
            payload
            for payload in (sensor.classify_exit(outcome) for sensor in sensors)
            if payload is not None
        ]
        record = ExitRecord(returncode=code, events=stamp_all(payloads, jail_id))
        with _LOCK:
            _EXITS[pid] = record

    threading.Thread(target=_run, name=f"brig-exit-{pid}", daemon=True).start()
