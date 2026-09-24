"""`Handle`: the serializable, rehydratable proof of a launched jail.

SPEC.md section 9 defines the finished shape:

    class Handle:
        def to_dict(self) -> dict: ...
        @classmethod
        def from_dict(cls, d) -> Handle: ...
        def wait_ready(self, channel: str, timeout: float) -> None
        def alive(self) -> bool
        def stat(self) -> JailStat
        def interrupt(self) -> bool
        def kill(self) -> KillReport
        def dial(self, channel: str) -> Connection
        def exec(self, argv, *, interactive=False) -> ExecHandle
        def console(self) -> Console | None
        def probe(self, battery) -> ProbeReport

Task-019 shipped the complete M2 shape. What lands HERE:

- `to_dict` / `from_dict` -- full serialization, re-running construction
  validation on the way back in (SPEC.md section 5's posture, carried over
  from `Spec.from_dict`); refuses an unknown top-level key.
- `alive()`, `stat() -> JailStat`, `wait()`, `interrupt()`.
- `kill`, `wait_ready`, `exec` -- delegating to `teardown.kill_jail`,
  `readiness.wait_ready`, and `exec_.exec_in_jail`.

What is still ABSENT from the surface, under SPEC.md section 9's own law
("An unimplemented capability is absent from the surface, never a raising
stub... A method that raises lies to `hasattr` and to every embedder that
feature-detects"): `dial` and `console`. `events()` left this list by being
DELETED from the finished shape rather than by arriving -- decision-152
(2026-09-08) removed the per-jail event stream, and with it the `EventCursor`
that method was going to return; the sensor records an embedder actually
wants are `compile_events` (a field, below) and `exit_events()` (a method),
both of them plain data.

**Identity, and the exit file (decision-155 and decision-156, 2026-09-08).**
Two fields arrived together with `HANDLE_VERSION` 5, and both close a gap
SPEC.md section 9 had been naming rather than fixing. `start_time` (plus
`helper_stamps`, one per helper) makes the recorded pids an identity instead
of a number: every liveness and kill decision in this layer compares pid AND
start time, so a pid the OS recycled reads as gone. And `wait()` now reads
`<jail_dir>/exit` when this process holds no observation of its own, which
gives a REHYDRATED handle back the exit status decision-152 took from it --
without bringing back the event stream that used to carry it.

**`interrupt()` (decision-151, 2026-09-08)** is the one method here that
arrived rather than left. It was ABSENT for the same reason `dial` and
`console` still are -- M2's ambiguity A10 -- and an embedder running many
actions in one jail is what made shipping it worth doing: without it, cancelling one
action meant killing the whole jail and every other action in flight with it.
See the method's own docstring for the mechanism and for what its return
value does and does not claim.
"""

from __future__ import annotations

import os
import signal
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from brig.core import (
    AXES,
    Axis,
    Battery,
    Channel,
    ChannelKind,
    EnforcementReport,
    Event,
    Grade,
    Graded,
    ProbeReport,
    SignatureBook,
    Spec,
)
from brig.run import _exit_status, _identity, _waiters
from brig.run.exec_ import exec_in_jail as _exec_in_jail
from brig.run.readiness import wait_ready as _wait_ready
from brig.run.teardown import kill_jail as _kill_jail

HANDLE_VERSION: Final = 5
"""Bumped 1 -> 2 by task-046 (`wrap_prefix` and `jail_env` became REQUIRED
top-level keys) and 2 -> 3 by task-076 (`helper_pids`). SPEC.md section 5's
posture applies to `Handle` too -- "There is no migration framework and no
tolerated extra field" -- so an older dict is refused outright rather than
defaulted in.

Bumped 3 -> 4 by decision-152 (2026-09-08), which changes the format in both
directions at once: `events_path` and `env` are GONE, and `compile_events` is
new and required. `events_path` named a file that no longer exists. `env` was
the launching process's whole environment, and dropping it is what makes a
serialized handle safe for the embedder's own log to carry (see the class
docstring).

Bumped 4 -> 5 by decision-155 (2026-09-08): `start_time` and `helper_stamps`
are new and REQUIRED. They are the second half of an identity a pid alone
cannot carry -- a handle that named only pids could not tell this jail from
whatever the OS handed those numbers to next, and defaulting them in for an
older dict would be exactly the silent downgrade that posture forbids."""

#: How often `wait()` re-asks `alive()` while polling. The two cheap
#: sources (this process's waiter record, the exit file) are polled far
#: more often; the liveness question exists only to turn "still running"
#: into "gone, and nothing recorded it", and paying a `/bin/ps` fifty times
#: a second to ask it sooner buys nothing.
_LIVENESS_POLL_S: Final = 0.25

_TOP_LEVEL_KEYS: Final = frozenset(
    {
        "version",
        "jail_id",
        "jail_dir",
        "launcher_name",
        "pid",
        "pgid",
        "start_time",
        "argv",
        "cwd",
        "jail_env",
        "wrap_prefix",
        "spec",
        "report",
        "signatures",
        "channels",
        "compile_events",
        "stdout_path",
        "stderr_path",
        "helper_pids",
        "helper_stamps",
    }
)
_REQUIRED_KEYS: Final = tuple(_TOP_LEVEL_KEYS - {"version"})
_CHANNEL_KEYS: Final = frozenset({"name", "kind", "endpoint"})
_REPORT_AXIS_KEYS: Final = frozenset({"grade", "detail"})


def _report_to_dict(report: EnforcementReport) -> dict[str, Any]:
    """`EnforcementReport` has no `to_dict` of its own (core ships only
    `Spec`'s per task-007) -- this is the Handle-scoped serialization of it,
    private to this module. Same shape idiom as `Spec.to_dict`: enums as
    their `.value` string, one entry per axis."""
    return {
        axis.value: {"grade": report.axes[axis].grade.value, "detail": report.axes[axis].detail}
        for axis in AXES
    }


def _report_from_dict(d: Mapping[str, Any]) -> EnforcementReport:
    """Inverse of `_report_to_dict`. Runs `EnforcementReport`'s own
    constructor, so a missing axis or bogus grade string raises from there,
    not from a from_dict-specific check (same posture as `Spec.from_dict`).
    Also refuses an unknown key inside any per-axis entry (SPEC.md section 5:
    "an unknown key at any level is a refusal"), same shape as
    `_channels_from_list`'s check."""
    axes: dict[Axis, Graded] = {}
    for axis in AXES:
        if axis.value not in d:
            raise ValueError(f"Handle.from_dict: report is missing axis {axis.value!r}")
        entry = d[axis.value]
        unknown = set(entry) - _REPORT_AXIS_KEYS
        if unknown:
            raise ValueError(
                f"Handle.from_dict: unknown key(s) {sorted(unknown)!r} in report[{axis.value!r}]"
            )
        axes[axis] = Graded(grade=Grade(entry["grade"]), detail=entry.get("detail", ""))
    return EnforcementReport(axes=axes)


def _channels_to_list(channels: Mapping[str, Channel]) -> list[dict[str, str]]:
    return [
        {"name": c.name, "kind": c.kind.value, "endpoint": c.endpoint} for c in channels.values()
    ]


def _channels_from_list(raw: Sequence[Mapping[str, Any]]) -> dict[str, Channel]:
    result: dict[str, Channel] = {}
    for entry in raw:
        unknown = set(entry) - _CHANNEL_KEYS
        if unknown:
            raise ValueError(f"Handle.from_dict: unknown key(s) {sorted(unknown)!r} in channels[]")
        channel = Channel(
            name=entry["name"],
            kind=ChannelKind(entry["kind"]),
            endpoint=entry["endpoint"],
        )
        result[channel.name] = channel
    return result


class ExitStatusUnobservable(RuntimeError):
    """The workload is gone and NOTHING recorded how it ended.

    Raised rather than returning a status, because every stand-in is a lie in
    the dangerous direction. `0` reads as a clean exit -- which in a denial
    test means the jail failed to deny, and in an allowed-case control means
    a write was never observed at all. Five integration helpers made exactly
    that substitution (`except ChildProcessError: return 0`) before the exit
    status was recorded at all.

    **What this no longer means (decision-156, 2026-09-08).** It used to mean
    "you are not the launching process": the status lived only in that
    process's memory, so a rehydrated `Handle` -- the shape an embedder uses
    to clean up after a runtime that died holding a jail -- got this refusal
    every time. It does not any more. The exit wrapper writes the status to
    `<jail_dir>/exit` (`brig/run/_exit_status.py`), which any process holding
    the handle can read, so a rehydrated handle now answers.

    What is left is exactly the case where **no wrapper ever wrote**:

    - the group was `SIGKILL`ed, which no process can survive long enough to
      record anything -- the killer holds the `KillReport`, which is that
      ending's record;
    - the jail directory has been swept, so the file that existed is gone;
    - the handle names a jail this launcher never wrapped.

    In none of those does a status exist to be read, which is why the answer
    is a refusal and not a number.
    """


@dataclass(frozen=True, slots=True)
class JailStat:
    """`stat()`'s return shape for M2 -- SPEC.md section 9 also lists
    `rusage`; deferred to the `observe` State surface at M8 (ambiguity A9 in
    the M2 plan: MILESTONES.md M2's scope bullet asks for exactly "pids +
    report")."""

    alive: bool
    pids: tuple[int, ...]
    report: EnforcementReport


@dataclass(frozen=True, slots=True)
class Handle:
    """Everything teardown/observe needs, and nothing a live process's argv
    would be needed for -- identity lives here, not in a relay pid (SPEC.md
    section 9).

    **What is deliberately NOT here: the workload's full environment.** Until
    decision-152 (2026-09-08) this carried `env`, the WORKLOAD's actual
    environment as spawned, which for `SubprocessLauncher` is the launching
    process's own `os.environ` overlaid with the jail's. That made
    `to_dict()` a copy of the operator's environment -- API tokens included
    -- and every embedder that wanted to persist a handle had to invent a
    private, mode-0600 side file to keep it out of its own log. The field is
    gone. `exec_.exec_in_jail` composes `{**os.environ, **jail_env}` fresh at
    exec time in every case, which is what it already did for a non-empty
    `wrap_prefix` and what its docstring already argued for; the serialized
    handle is now plain enough for an embedder's log to hold, which is where
    handle persistence belongs.

    `jail_env` (task-046) is the compiled jail's OWN env overlay --
    `CompiledJail.env` -- and is mechanism-declared policy, not the
    operator's environment.

    `wrap_prefix` (task-046) is the tuple of argv tokens the compiled
    stack's `wrap` prepended ahead of the launched `argv` -- `None` when
    `launcher.py`'s `_derive_wrap_prefix` verified the compiled wrap is
    NOT a pure prefix for this jail's `argv` (SPEC.md section 9: "A mechanism
    that cannot guarantee this refuses exec"). `exec_.exec_in_jail`
    refuses outright on `None` rather than spawn a sibling under a weaker
    confinement than the workload's own.

    `signatures` (task-047) is the `SignatureBook` `Stack.compile` already
    assembled onto `CompiledJail.signatures`, carried through unchanged --
    so a `Handle` rehydrated in a later process (SPEC.md section 9's
    `from_dict`) can still answer "which mechanism claims `Axis.X`, and what
    does its denial look like?" without `run` or `probe` importing `stack` or
    `mech` (SPEC.md section 13): the book is `core`-typed data, not a
    callable or a mechanism reference.

    `compile_events` (decision-152) is what every mechanism sensor's
    `known_at_compile()` returned, stamped with `ts` and this jail's
    `jail_id` by the launcher. It is a field rather than a method because it
    is settled before the workload starts and never changes afterwards --
    the exit half of the same feed IS a method (`exit_events()`), because it
    is not known until the workload ends.
    """

    jail_id: str
    jail_dir: str
    launcher_name: str
    pid: int
    pgid: int
    #: When the process at `pid` started, as `brig/run/_identity.py` reads
    #: it (decision-155). `_identity.UNKNOWN` when the read lost its race
    #: with a workload that had already exited.
    start_time: str
    argv: tuple[str, ...]
    cwd: str
    jail_env: Mapping[str, str]
    wrap_prefix: tuple[str, ...] | None
    spec: Spec
    report: EnforcementReport
    signatures: SignatureBook
    channels: Mapping[str, Channel]
    stdout_path: str
    stderr_path: str
    compile_events: tuple[Event, ...] = ()
    #: pids of this jail's `Step.helpers` processes (SPEC.md section 6).
    #: Serialized with the rest, because a `Handle` rehydrated in another
    #: process must be able to tear the whole jail down -- "kill leaves
    #: nothing" (section 9) covers helpers, and a helper the killing process
    #: cannot name is a helper that outlives the jail it belongs to.
    helper_pids: tuple[int, ...] = ()
    #: One start-time stamp per entry of `helper_pids`, same order
    #: (decision-155). A helper's pid is signalled by teardown in a process
    #: that may not have started it, which is the same reuse window the
    #: workload's own pid has and is closed the same way.
    helper_stamps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "jail_env", MappingProxyType(dict(self.jail_env)))
        object.__setattr__(
            self,
            "wrap_prefix",
            None if self.wrap_prefix is None else tuple(self.wrap_prefix),
        )
        object.__setattr__(self, "channels", MappingProxyType(dict(self.channels)))
        object.__setattr__(self, "compile_events", tuple(self.compile_events))
        object.__setattr__(self, "helper_pids", tuple(self.helper_pids))
        object.__setattr__(self, "helper_stamps", tuple(self.helper_stamps))
        if len(self.helper_stamps) != len(self.helper_pids):
            raise ValueError(
                "Handle: helper_stamps must have one entry per helper pid, got "
                f"{len(self.helper_stamps)} stamp(s) for {len(self.helper_pids)} pid(s)"
            )

    def to_dict(self) -> dict[str, Any]:
        """Versioned, JSON-native dict carrying every field above."""
        return {
            "version": HANDLE_VERSION,
            "jail_id": self.jail_id,
            "jail_dir": self.jail_dir,
            "launcher_name": self.launcher_name,
            "pid": self.pid,
            "pgid": self.pgid,
            "start_time": self.start_time,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "jail_env": dict(self.jail_env),
            "wrap_prefix": None if self.wrap_prefix is None else list(self.wrap_prefix),
            "spec": self.spec.to_dict(),
            "report": _report_to_dict(self.report),
            "signatures": self.signatures.to_list(),
            "channels": _channels_to_list(self.channels),
            "compile_events": [event.to_dict() for event in self.compile_events],
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "helper_pids": list(self.helper_pids),
            "helper_stamps": list(self.helper_stamps),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Handle:
        """Inverse of `to_dict`. Re-runs construction validation (SPEC.md
        section 5's posture, same as `Spec.from_dict`): the result is built
        through `Handle`'s and `Spec`'s and `EnforcementReport`'s ordinary
        constructors, so nothing invalid can be smuggled in via a
        hand-edited dict. Raises `ValueError` for a missing `version`, an
        unsupported `version`, an unknown top-level key, or a missing
        required key."""
        if "version" not in d:
            raise ValueError("Handle.from_dict: missing required key 'version'")
        version = d["version"]
        if version != HANDLE_VERSION:
            raise ValueError(
                f"Handle.from_dict: unsupported version {version!r}, expected {HANDLE_VERSION!r}"
            )
        unknown = set(d) - _TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(f"Handle.from_dict: unknown key(s) {sorted(unknown)!r} at top level")
        missing = [key for key in _REQUIRED_KEYS if key not in d]
        if missing:
            raise ValueError(f"Handle.from_dict: missing required key(s) {sorted(missing)!r}")

        return cls(
            jail_id=d["jail_id"],
            jail_dir=d["jail_dir"],
            launcher_name=d["launcher_name"],
            pid=d["pid"],
            pgid=d["pgid"],
            start_time=d["start_time"],
            argv=tuple(d["argv"]),
            cwd=d["cwd"],
            jail_env=dict(d["jail_env"]),
            wrap_prefix=None if d["wrap_prefix"] is None else tuple(d["wrap_prefix"]),
            spec=Spec.from_dict(d["spec"]),
            report=_report_from_dict(d["report"]),
            signatures=SignatureBook.from_list(d["signatures"]),
            channels=_channels_from_list(d["channels"]),
            compile_events=tuple(Event.from_dict(raw) for raw in d["compile_events"]),
            stdout_path=d["stdout_path"],
            stderr_path=d["stderr_path"],
            helper_pids=tuple(int(pid) for pid in d["helper_pids"]),
            helper_stamps=tuple(str(stamp) for stamp in d["helper_stamps"]),
        )

    def alive(self) -> bool:
        """True while this jail's own leader is running, false once it is
        gone -- and false for a pid the OS has since handed to something
        else.

        Two questions, not one (decision-155, 2026-09-08). First
        `os.kill(pid, 0)`, which sends no signal and only runs the kernel's
        own existence/permission check: `ProcessLookupError` is "no such
        process", while `PermissionError` means the pid exists and belongs
        to someone else, which is existence. Then, for a pid that does
        exist, `brig/run/_identity.py` compares the CURRENT occupant's start
        time against `start_time`, the one this launch recorded. A recycled
        pid therefore reads as **gone**, which is the answer the old
        pid-only check could not give and the reason SPEC.md section 9 used
        to carry a paragraph admitting it.

        Two limits remain, stated rather than left silent. A zombie (exited,
        not yet reaped by its real parent) still reads `True`: it is the same
        process with the same start time, and this method sees existence, not
        reap state. And a handle whose `start_time` is `_identity.UNKNOWN` --
        the launch lost its race with a workload that exited within
        microseconds -- degrades to the pid-only check, because there is
        nothing recorded to compare against."""
        return _identity.identity_holds(self.pid, self.start_time)

    def interrupt(self) -> bool:
        """Deliver `SIGINT` to the workload's process **group**. Returns
        whether the signal was delivered.

        SPEC.md law 7: "Control must not require cooperation. Interrupt and
        kill are delivered by mechanism-level means that work when the jail
        is spinning, wedged, or hostile." `os.killpg` is that means for
        every launcher this library ships: the workload is a process-group
        leader by construction (`start_new_session=True`), so one call
        reaches it and every descendant that has not left the group --
        never a single pid, for the same reason teardown never signals one.

        **What `True` claims, and what it does not.** `True` means the
        kernel accepted the signal for delivery to the group; it is
        `os.killpg` not raising, and nothing more. It is NOT a claim that
        anything stopped: `SIGINT` is catchable, blockable and ignorable,
        and a hostile workload is entitled to do all three. That is exactly
        why `interrupt` is the first rung and `kill` is the ladder --
        `kill`'s own report is the one that carries a VERIFIED outcome,
        because it verifies. `False` means the group was not there to signal
        (`ProcessLookupError`) or this process may not signal it
        (`PermissionError`) -- an honest "not delivered", never an
        exception a caller has to translate.

        **The deliverability grade is already promised, and is not
        re-promised here.** How well control can be delivered for a given
        jail is the `control` axis of the `EnforcementReport` this handle
        already carries (SPEC.md section 4; law 7's "its deliverability is
        itself graded in the report"). This method reads no grade and
        publishes none: a per-call grade would be a second, unsynchronized
        answer to a question the report already answers.

        **The pid-reuse seam decision-144 accepted is closed here**
        (decision-155): before signalling, the leader's recorded start time
        is compared against the pid's current occupant, and a pid the OS has
        recycled returns `False` -- not delivered, because what this handle
        names is gone -- rather than delivering a `SIGINT` to a stranger that
        happens to lead a group with the same number.
        """
        if _identity.recycled(self.pid, self.start_time):
            return False
        try:
            os.killpg(self.pgid, signal.SIGINT)
        except ProcessLookupError, PermissionError:
            return False
        return True

    def wait(self, timeout: float = 30.0) -> int:
        """Block until the workload exits; return the status it exited with.

        The convention is `Popen.returncode`: 0 for a clean exit, non-zero
        for failure, negative for death by signal (`-N` for signal N).

        **Two sources, and they agree** (decision-156, 2026-09-08). In the
        launching process the answer comes from that process's own waiter
        thread (`brig/run/_waiters.py`) -- not from `waitpid`, because the
        launcher drops its `Popen` and a direct `waitpid` here would race the
        reap. Everywhere else, and as the fallback here, it comes from
        `<jail_dir>/exit`, written once by the exit wrapper the launcher runs
        the workload under (`brig/run/_exit_status.py`). The wrapper ends the
        same way its child did, so the number in the file and the number the
        waiter thread observed are the same number by construction.

        Raises `TimeoutError` while the workload is still running at the
        deadline, and `ExitStatusUnobservable` once it is gone with no record
        in either place -- see that exception for the cases that remain. It
        never invents a status.
        """
        deadline = time.monotonic() + timeout
        next_liveness_check = 0.0
        gone = False
        while True:
            record = _waiters.recorded_exit(self.pid)
            if record is not None:
                return record.returncode
            recorded = _exit_status.read_exit_status(self.jail_dir)
            if recorded is not None:
                return recorded
            if gone:
                # Gone, and no record in either place. Give the wrapper and
                # the waiter thread a moment -- ending, writing and
                # recording are not one atomic step.
                grace = time.monotonic() + 1.0
                while time.monotonic() < grace:
                    record = _waiters.recorded_exit(self.pid)
                    if record is not None:
                        return record.returncode
                    recorded = _exit_status.read_exit_status(self.jail_dir)
                    if recorded is not None:
                        return recorded
                    time.sleep(0.02)
                raise ExitStatusUnobservable(
                    f"pid {self.pid} is gone and nothing recorded how jail "
                    f"{self.jail_id!r} ended: no exit file at "
                    f"{_exit_status.exit_path(self.jail_dir)!r} and no observation in "
                    "this process"
                )
            now = time.monotonic()
            if now >= next_liveness_check:
                # `alive()` costs a process-table read on every platform but
                # Linux (`brig/run/_identity.py`), so this loop asks it on a
                # slower cadence than it polls the two cheap sources above.
                # The answer is the same answer, at most `_LIVENESS_POLL_S`
                # later.
                gone = not self.alive()
                next_liveness_check = now + _LIVENESS_POLL_S
                continue
            if now > deadline:
                raise TimeoutError(f"pid {self.pid} did not exit within {timeout}s")
            time.sleep(0.02)

    def exit_events(self) -> tuple[Event, ...]:
        """What this jail's mechanism sensors made of the workload's ending
        (`EventSource.classify_exit`), stamped -- `rlimits` recognizing a
        `SIGXCPU` termination as its own cpu limit tripping is the shipped
        case.

        The empty tuple while the workload is still running, and the empty
        tuple once it has ended with no sensor recognizing anything: those
        are the same answer because they are the same fact -- nothing to
        report. A caller that needs to distinguish "not finished" from
        "finished, nothing to say" asks `alive()` or `wait()`, which are the
        methods whose job that is.
        """
        record = _waiters.recorded_exit(self.pid)
        return () if record is None else record.events

    def stat(self) -> JailStat:
        """M2's `JailStat`: `alive`, the one pid this milestone ever
        launches, and the report unchanged from what the stack compiled --
        M2 has no mechanism that could change a grade after launch."""
        return JailStat(alive=self.alive(), pids=(self.pid,), report=self.report)

    def kill(self) -> Any:
        """Delegates to `teardown.kill_jail` (task-020). `Any` is the
        FINAL M2 return type here, not a placeholder: `KillReport`
        (ambiguity A11) lives in `teardown.py`, which imports nothing from
        here, and naming it would close a cycle. task-020 gave
        `teardown.kill_jail` its concrete return type instead."""
        return _kill_jail(self)

    def wait_ready(self, channel: str, timeout: float) -> None:
        """Delegates to `readiness.wait_ready` (task-021). Final signature
        per SPEC.md section 9."""
        _wait_ready(self, channel, timeout)

    def exec(self, argv: Sequence[str], *, interactive: bool = False) -> Any:
        """Delegates to `exec_.exec_in_jail` (task-022). `Any` is final
        here for the same reason as `kill`'s return type: `ExecHandle`
        (ambiguity A13) lives in the module this one imports, so naming it
        here would close a cycle."""
        return _exec_in_jail(self, argv, interactive)

    def probe(self, battery: Battery) -> ProbeReport:
        """Delegates to `battery.run(self)` (task-050, SPEC.md section 9/12).

        `run` imports nothing from `probe`: `Battery` and `ProbeReport` are
        `core`-typed names (task-045/task-048), which is the whole reason
        they were put there -- `run` may not import `probe` (SPEC.md section
        13), so this method names both its parameter and its return type
        without ever reaching for `brig.probe`."""
        return battery.run(self)
