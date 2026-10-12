"""`Jail` and `Process`: a running jail as its embedder holds it, and each process in it.

SPEC.md section 9, "The Jail and its processes" (decision-181, TASK-0079.26).
A jail is `Jail.create` (the runtime's `create`, which starts nothing) and
then a `jail.start` per process, the first included; an exec sibling is a
second `start`, the same call, recorded the same way. Every control call
delegates to the jail's runtime (`brig/run/runtime.py`): `alive`, `destroy`
and `processes` to the `Runtime`, `start`, `interrupt`, `wait` and `stop` to
its `Supervisor`.

**What the jail knows.** A jail holds, in memory, the processes its dict
named and every process it started itself, in start order: `destroy` ends
those by the identity it holds, never by a disk copy, and reports a disk copy
that disagrees as its own `FAILED` item (`teardown.kill_named`). Every other
record the runtime finds is a start made elsewhere, read like any other.

**Rehydration takes the embedder's runtimes.** `to_dict` carries data only;
`Jail.from_dict(d, runtimes=...)` sends the jail to the runtime the embedder
passed under the kind its dict names, and refuses a kind it did not pass, or
a runtime whose own `kind` is another (law 2). A fake jail's dict says `FAKE`,
so it never reaches `HostRuntime`.

**Absent, not raising** (SPEC.md section 9's law). `Jail.start` and
`Jail.probe` are absent when the jail cannot start: its runtime has no
supervisor, or it was created tethered in another process (the tether's fd
did not cross `to_dict`, and a start here would run untethered). A
rehydrated jail starts only when its dict and its runtime's own record of it
(`Runtime.tethered`, `<jail_dir>/jail.json` for a host jail) both say
untethered, so a hand-edited dict can't give a tethered jail its `start`
back.
`Process.interrupt`, `stop` and `wait` are absent on a process of a jail with
no supervisor. Each is a property that raises `AttributeError` then, so
`hasattr` is false, and a type checker still knows the call where it is
there (TASK-0079.26's settled point 1).
"""

import dataclasses
import signal
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Protocol

from brig.core import Battery, Channel, EnforcementReport, Event, ProbeReport, SignatureBook, Spec
from brig.core.runtime import RuntimeKind
from brig.run import _records, _waiters
from brig.run._dicts import channels_from_list, channels_to_list, report_from_dict, report_to_dict
from brig.run.events import stamp_all
from brig.run.exec_ import ExecFidelity
from brig.run.readiness import wait_ready as _wait_ready
from brig.run.runtime import IoPolicy, JailRecord, NoSupervisor, ProcessRecord, Runtime, Supervisor
from brig.run.teardown import KillReport
from brig.stack import CompiledJail

HANDLE_VERSION: Final = 6
"""The version of a jail's dict (a `Handle`'s before it). Bumped 1 -> 2 by
task-046 (`wrap_prefix` and `jail_env` became REQUIRED top-level keys) and
2 -> 3 by task-076 (`helper_pids`). SPEC.md section 5's posture applies here
too -- "There is no migration framework and no tolerated extra field" -- so an
older dict is refused outright rather than defaulted in.

Bumped 3 -> 4 by decision-152 (2026-09-08), which changes the format in both
directions at once: `events_path` and `env` are GONE, and `compile_events` is
new and required. `events_path` named a file that no longer exists. `env` was
the launching process's whole environment, and dropping it is what makes a
serialized handle safe for the embedder's own log to carry.

Bumped 4 -> 5 by decision-155 (2026-09-08): `start_time` and `helper_stamps`
are new and REQUIRED. They are the second half of an identity a pid alone
cannot carry -- a handle that named only pids could not tell this jail from
whatever the OS handed those numbers to next, and defaulting them in for an
older dict would be exactly the silent downgrade that posture forbids.

Bumped 5 -> 6 by decision-181 (TASK-0079.26): a `Jail`'s dict. The first
process's fields (`pid`, `pgid`, `start_time`, `argv`, `stdout_path`,
`stderr_path`) and `launcher_name` are gone, and `runtime`, `tethered` and
`processes` are new and required. `Handle`'s dict, unchanged in shape, is
written as 6 too until TASK-0079.28 deletes it."""

_TOP_LEVEL_KEYS: Final = frozenset(
    {
        "version",
        "runtime",
        "tethered",
        "jail_id",
        "jail_dir",
        "cwd",
        "jail_env",
        "wrap_prefix",
        "spec",
        "report",
        "signatures",
        "channels",
        "compile_events",
        "helper_pids",
        "helper_stamps",
        "processes",
    }
)
_REQUIRED_KEYS: Final = tuple(sorted(_TOP_LEVEL_KEYS - {"version"}))
_WHO: Final = "Jail.from_dict"

#: The stdio files a start gets when it names none.
_DEFAULT_IO: Final = IoPolicy()


class _Start(Protocol):
    """`Jail.start`'s signature, for the property that offers it."""

    def __call__(
        self, argv: Sequence[str], /, *, cwd: str | None = None, io: IoPolicy = _DEFAULT_IO
    ) -> Process: ...


class _Wait(Protocol):
    """`Process.wait`'s signature, for the property that offers it."""

    def __call__(self, timeout: float | None = None) -> int: ...


def _fidelity(wrap_prefix: tuple[str, ...] | None) -> ExecFidelity:
    """How a process stands to the jail's confinement, decided per jail, never
    per start (decision-181): an identical wrapper for a non-empty prefix, a
    plain process for an empty one. Pure."""
    return ExecFidelity.EQUIVALENT_PROFILE if wrap_prefix else ExecFidelity.PLAIN


@dataclass(frozen=True, slots=True)
class Process:
    """One process in a jail: its identity and where its output went.

    `id` names its records (`<jail_dir>/procs/<id>/` for `HostRuntime`); `pid`
    and `start_time` are an identity, not a number (decision-155); `pid` is
    its exit wrapper, which leads its group. `argv` is what was spawned (the
    jail's wrap prefix included). `fidelity` is the jail's (decision-181).
    `interrupt`, `stop` and `wait` are absent when its jail has no supervisor.
    """

    id: str
    pid: int
    start_time: str
    argv: tuple[str, ...]
    stdout_path: str
    stderr_path: str
    fidelity: ExecFidelity
    _record: ProcessRecord = field(repr=False, compare=False)
    _jail: Jail = field(repr=False, compare=False)

    def _supervisor(self) -> Supervisor:
        """The supervisor of this process's jail, asked now.

        Raises:
            AttributeError: the jail has none, so the call is absent.
        """
        supervisor = self._jail._supervisor()
        if supervisor is None:
            raise AttributeError(
                f"process {self.id} of jail {self._jail.jail_id!r} has no supervisor to "
                "signal, wait for or stop it through; destroy its jail instead"
            )
        return supervisor

    @property
    def interrupt(self) -> Callable[[], bool]:
        """`SIGINT` to this process's group, after checking its leader's
        identity: `True` when the kernel accepted it for delivery, not that
        anything stopped; `False` when not delivered (gone, recycled, not
        permitted). Absent without a supervisor.

        Raises:
            AttributeError: the jail has no supervisor.
        """
        supervisor = self._supervisor()
        return lambda: supervisor.signal(self._record, signal.SIGINT)

    @property
    def stop(self) -> Callable[[], KillReport]:
        """SPEC.md section 9's ladder against this process's group alone,
        verified, one item. Its record stays, so a later `destroy` reports it
        `ALREADY_GONE`. Absent without a supervisor.

        Raises:
            AttributeError: the jail has no supervisor.
        """
        supervisor = self._supervisor()
        return lambda: supervisor.stop(self._record)

    @property
    def wait(self) -> _Wait:
        """Block for this process's exit status (`Popen.returncode`'s
        convention). In the process that started it, it answers once the
        process's leader has left (decision-182); anywhere else, from its exit
        record. Never invents a status. Absent without a supervisor.

        The returned call raises `TimeoutError` while the process still runs
        at `timeout` (`None`: no deadline), and `ExitStatusUnobservable` once
        it is gone and nothing recorded how it ended.

        Raises:
            AttributeError: the jail has no supervisor.
        """
        supervisor = self._supervisor()

        def wait(timeout: float | None = None) -> int:
            status = supervisor.wait(self._record, timeout)
            if status is None:
                raise TimeoutError(f"process {self.id} (pid {self.pid}) still ran at {timeout}s")
            return status

        return wait

    def alive(self) -> bool:
        """Whether this process's leader still holds its identity: a recycled
        pid and a zombie read gone. Answers for the leader; `stop` and
        `destroy` end groups."""
        jail = self._jail
        return jail._runtime.process_alive(jail._record(), self._record)

    def exit_events(self) -> tuple[Event, ...]:
        """What the jail's mechanism sensors made of this process's ending,
        stamped, as the process that started it observed it; the empty tuple
        while it runs, when nothing was recognised, and in any other
        process."""
        observed = _waiters.recorded_exit(self.pid)
        return () if observed is None else observed.events


@dataclass(slots=True, eq=False)
class Jail:
    """A running jail as its embedder holds it (SPEC.md section 9).

    A class whose own `start` changes it: it remembers each process it
    started, in start order, so `destroy` ends each by the identity it holds.
    Everything else is fixed at `create` or `from_dict`.

    `report`, `spec`, `signatures` and `channels` are the compiled jail's;
    `compile_events` what each mechanism sensor's `known_at_compile()`
    returned, stamped with `jail_id`.
    """

    jail_id: str
    jail_dir: str
    spec: Spec
    report: EnforcementReport
    signatures: SignatureBook
    channels: Mapping[str, Channel]
    compile_events: tuple[Event, ...]
    _runtime: Runtime = field(repr=False)
    _base: JailRecord = field(repr=False)
    _tethered: bool = field(repr=False)
    #: Whether this object was made by `create` in this process, which holds
    #: the jail's tether (decision-181); `False` for one from `from_dict`.
    _created_here: bool = field(repr=False)
    _started: list[ProcessRecord] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.channels = MappingProxyType(dict(self.channels))
        self.compile_events = tuple(self.compile_events)

    @classmethod
    def create(
        cls,
        jail: CompiledJail,
        *,
        runtime: Runtime,
        cwd: str,
        jail_id: str,
        jail_dir: str,
        tether: int | None = None,
    ) -> Jail:
        """Create the jail's instance through `runtime`, with no process in
        it: every process is a `start` (decision-181). `runtime`'s kind must
        be the compiled jail's, or `FAKE` standing in for any.

        `tether` is the read end of a pipe whose write end the caller keeps:
        once every write end is closed, every process the jail started is
        ended. The jail holds a duplicate, so the caller may close its own
        read end once this returns. `None`: the jail lives until its
        processes end or it is destroyed.

        Raises:
            ValueError: `runtime` is of another kind than the compiled jail's.
            LaunchRefused: the jail requires a capability `runtime` lacks.
            JailDirInUse: `jail_dir` holds an earlier jail's records and
                something they name runs, or brig can't tell.
            HelperFailed: a `LAUNCH_SCOPED` helper failed.
            OSError: `tether` is not open, or `jail_dir` could not be written.
        """
        if runtime.kind not in (jail.runtime, RuntimeKind.FAKE):
            raise ValueError(
                f"Jail.create: the jail was compiled for the {jail.runtime.value} runtime, "
                f"and the runtime passed is {runtime.kind.value}; pass a runtime of the "
                "jail's kind (or a fake one, in a test)"
            )
        record = runtime.create(jail, cwd=cwd, jail_id=jail_id, jail_dir=jail_dir, tether=tether)
        return cls(
            jail_id=jail_id,
            jail_dir=jail_dir,
            spec=jail.spec,
            report=jail.report,
            signatures=jail.signatures,
            channels={channel.name: channel for channel in jail.spec.channels},
            compile_events=stamp_all(
                (payload for sensor in jail.sensors for payload in sensor.known_at_compile()),
                jail_id,
            ),
            _runtime=runtime,
            _base=record,
            _tethered=tether is not None,
            _created_here=True,
        )

    def _record(self) -> JailRecord:
        """The jail as its runtime identifies it: what the runtime is asked
        about on every call, its processes the ones this jail knows."""
        return dataclasses.replace(self._base, processes=(*self._base.processes, *self._started))

    def _supervisor(self) -> Supervisor | None:
        return self._runtime.supervisor(self._record())

    def _process(self, record: ProcessRecord) -> Process:
        return Process(
            id=record.id,
            pid=record.pid,
            start_time=record.start_time,
            argv=record.argv,
            stdout_path=record.stdout_path,
            stderr_path=record.stderr_path,
            fidelity=_fidelity(self._base.wrap_prefix),
            _record=record,
            _jail=self,
        )

    def _cannot_start(self) -> str | None:
        """Why this jail cannot start a process, or `None` when it can."""
        if self._supervisor() is None:
            return "its runtime has no supervisor in it"
        if not self._created_here:
            if self._tethered:
                return (
                    "it was created tethered in another process, and its tether did not "
                    "cross to_dict, so a process started here would run untethered"
                )
            if self._runtime.tethered(self._base) is not False:
                return (
                    "its dict says untethered, and its runtime's own record of it (for a "
                    "host jail, jail.json in its jail directory) is missing, unreadable or "
                    "says tethered; a process started here could run untethered"
                )
        return None

    @property
    def start(self) -> _Start:
        """Start `argv` in the jail, under the jail's confinement, never a
        weaker one, and return it as a `Process`; `cwd` defaults to the
        jail's, and `io` names its stdio files. Absent when the jail cannot
        start (no supervisor, or created tethered in another process).

        The returned call raises what the supervisor refuses with
        (`ExecWrapNotAPrefix`, `TetherClosed`, `WorkloadSpawnFailed`,
        `OSError`). A refused start changes nothing: the jail is the
        caller's, to start again or destroy.

        Raises:
            AttributeError: the jail cannot start a process.
        """
        reason = self._cannot_start()
        if reason is not None:
            raise AttributeError(f"jail {self.jail_id!r} has no start: {reason}")
        return self._start

    def _start(
        self, argv: Sequence[str], /, *, cwd: str | None = None, io: IoPolicy = _DEFAULT_IO
    ) -> Process:
        """`start`, once it is known to be there.

        Raises:
            NoSupervisor: the runtime stopped offering a supervisor.
        """
        supervisor = self._supervisor()
        if supervisor is None:
            raise NoSupervisor(f"jail {self.jail_id!r} has no supervisor to start {argv!r} with")
        record = supervisor.start(argv, cwd=self._base.cwd if cwd is None else cwd, io=io)
        self._started.append(record)
        return self._process(record)

    @property
    def probe(self) -> Callable[[Battery], ProbeReport]:
        """Run `battery` in this jail: `battery.run(jail)`, each probe a
        `start`, waited with its deadline and read from its own stdio files;
        its record stays for `destroy` like any process's (decision-181).
        Absent when `start` is.

        Raises:
            AttributeError: the jail cannot start a process.
        """
        reason = self._cannot_start()
        if reason is not None:
            raise AttributeError(f"jail {self.jail_id!r} has no probe: {reason}")
        return lambda battery: battery.run(self)

    def processes(self) -> tuple[Process, ...]:
        """Every process of the jail, in start order: the ones it knows, then
        every other one its runtime finds (a start made elsewhere)."""
        return tuple(self._process(record) for record in self._runtime.processes(self._record()))

    def alive(self) -> bool:
        """True while any process's leader, or any `JAIL_LIFETIME` helper,
        holds its identity; a jail with nothing started and no helper reads
        gone."""
        return self._runtime.alive(self._record())

    def destroy(self) -> KillReport:
        """End every process, then every helper, verified, one item each
        (SPEC.md section 9's ladder): the first process `workload_group`,
        every later one `exec_sibling`. Always there."""
        return self._runtime.destroy(self._record())

    def wait_ready(self, channel: str, timeout: float) -> None:
        """Block until `channel` accepts a connection (SPEC.md section 10).

        Raises:
            UnknownChannel: the jail declares no such channel.
            WaitReadyTimeout: no connection succeeded within `timeout`.
        """
        _wait_ready(self, channel, timeout)

    def to_dict(self) -> dict[str, Any]:
        """Versioned, JSON-native: everything `destroy`, `alive` and a
        process's `wait` need in another process, and the processes this jail
        knows. Carries no fd, no callable and no environment but the jail's
        own overlay."""
        record = self._record()
        return {
            "version": HANDLE_VERSION,
            "runtime": record.kind.value,
            "tethered": self._tethered,
            "jail_id": self.jail_id,
            "jail_dir": self.jail_dir,
            "cwd": record.cwd,
            "jail_env": dict(record.jail_env),
            "wrap_prefix": None if record.wrap_prefix is None else list(record.wrap_prefix),
            "spec": self.spec.to_dict(),
            "report": report_to_dict(self.report),
            "signatures": self.signatures.to_list(),
            "channels": channels_to_list(self.channels),
            "compile_events": [event.to_dict() for event in self.compile_events],
            "helper_pids": list(record.helper_pids),
            "helper_stamps": list(record.helper_stamps),
            "processes": [_records.to_json(process) for process in record.processes],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], *, runtimes: Mapping[RuntimeKind, Runtime]) -> Jail:
        """Inverse of `to_dict`, through the runtimes the embedder passes,
        never one the dict names: the jail goes to `runtimes[kind]`, `kind`
        the one its dict names. Re-runs construction validation, so nothing
        invalid can be smuggled in through a hand-edited dict.

        Raises:
            ValueError: `version` is missing or not 6; a key is unknown or
                missing; the dict names a runtime kind `runtimes` does not
                hold, or one whose runtime's own `kind` is another; a process
                is not a record brig writes, or two share an id; or any
                other field fails its type's own construction.
        """
        if "version" not in d:
            raise ValueError(f"{_WHO}: missing required key 'version'")
        if d["version"] != HANDLE_VERSION:
            raise ValueError(
                f"{_WHO}: unsupported version {d['version']!r}, expected {HANDLE_VERSION!r}"
            )
        unknown = set(d) - _TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(f"{_WHO}: unknown key(s) {sorted(unknown)!r} at top level")
        missing = [key for key in _REQUIRED_KEYS if key not in d]
        if missing:
            raise ValueError(f"{_WHO}: missing required key(s) {missing!r}")

        runtime = _runtime_for(d["runtime"], runtimes)
        if type(d["tethered"]) is not bool:
            raise ValueError(f"{_WHO}: 'tethered' must be a bool, got {d['tethered']!r}")
        record = JailRecord(
            kind=runtime.kind,
            jail_id=d["jail_id"],
            jail_dir=d["jail_dir"],
            cwd=d["cwd"],
            jail_env=frozendict(d["jail_env"]),
            wrap_prefix=None if d["wrap_prefix"] is None else tuple(d["wrap_prefix"]),
            processes=_processes_from_list(d["processes"]),
            helper_pids=tuple(int(pid) for pid in d["helper_pids"]),
            helper_stamps=tuple(str(stamp) for stamp in d["helper_stamps"]),
        )
        return cls(
            jail_id=record.jail_id,
            jail_dir=record.jail_dir,
            spec=Spec.from_dict(d["spec"]),
            report=report_from_dict(d["report"], who=_WHO),
            signatures=SignatureBook.from_list(d["signatures"]),
            channels=channels_from_list(d["channels"], who=_WHO),
            compile_events=tuple(Event.from_dict(raw) for raw in d["compile_events"]),
            _runtime=runtime,
            _base=record,
            _tethered=d["tethered"],
            _created_here=False,
        )


def _runtime_for(raw_kind: object, runtimes: Mapping[RuntimeKind, Runtime]) -> Runtime:
    """The runtime the embedder passed for the kind a dict names.

    Raises:
        ValueError: the kind is no `RuntimeKind`, `runtimes` holds none for
            it, or the one it holds is of another kind.
    """
    try:
        kind = RuntimeKind(raw_kind)
    except ValueError as error:
        raise ValueError(f"{_WHO}: 'runtime' {raw_kind!r} is no runtime kind brig knows") from error
    runtime = runtimes.get(kind)
    if runtime is None:
        passed = ", ".join(sorted(k.value for k in runtimes)) or "none"
        raise ValueError(
            f"{_WHO}: the jail was made by the {kind.value} runtime, and no runtime was "
            f"passed for {kind.value} (passed: {passed}); pass "
            f"runtimes={{RuntimeKind.{kind.name}: <the runtime that made it>}} to rehydrate "
            "it. brig never picks a runtime for a dict"
        )
    if runtime.kind is not kind:
        raise ValueError(
            f"{_WHO}: the runtime passed for {kind.value} is a {runtime.kind.value} runtime; "
            f"pass one whose kind is {kind.value}"
        )
    return runtime


def _processes_from_list(raw: object) -> tuple[ProcessRecord, ...]:
    """The processes a dict names, each checked as a `record.json` is.

    Raises:
        ValueError: `raw` is not a list, an entry is not a record brig writes,
            or two entries share an id.
    """
    if type(raw) is not list:
        raise ValueError(f"{_WHO}: 'processes' must be a list, got {raw!r}")
    processes: list[ProcessRecord] = []
    for entry in raw:
        process_id = entry.get("id") if type(entry) is dict else None
        if type(process_id) is not str or not _records.is_id(process_id):
            raise ValueError(f"{_WHO}: a process entry has no id brig makes: {entry!r}")
        parsed = _records.from_json(entry, process_id)
        if isinstance(parsed, str):
            raise ValueError(f"{_WHO}: process {process_id} {parsed}")
        processes.append(parsed)
    ids = [process.id for process in processes]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{_WHO}: two processes share an id: {ids!r}")
    return tuple(processes)
