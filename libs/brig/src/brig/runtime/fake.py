"""`FakeRuntime`: the runtime protocols' second implementation, for tests.

Pure: it starts nothing, signals nothing and reads nothing. It answers every
`Runtime` and `Supervisor` call from its own state and logs the call, with the
scope the call acts at, so a test can drive `Handle` (or anything else written
against the protocols) and check what was asked of the runtime. Its pids
start at `FAKE_PID_BASE`, far above any real pid limit, so a fake record that
leaked to real teardown would name no process.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from signal import Signals
from typing import Final

from brig.core.runtime import PROCS_DIRNAME, Capability, RuntimeKind, Scope
from brig.run.runtime import IoPolicy, JailRecord, ProcessRecord, Supervisor
from brig.run.teardown import KillItem, KillOutcome, KillReport
from brig.stack import CompiledJail

#: The first pid a `FakeRuntime` hands out. Linux caps pids at 2**22.
FAKE_PID_BASE: Final = 10_000_000

#: The start-time stamp every fake process carries.
FAKE_STAMP: Final = "fake"


@dataclass(frozen=True, slots=True)
class Call:
    """One call a `FakeRuntime` or its supervisor answered: the method's name, the
    scope it acts at (`JAIL` for the runtime's, `PROCESS` for the supervisor's),
    and the record or argv it was about."""

    method: str
    scope: Scope
    subject: JailRecord | ProcessRecord | tuple[str, ...]


class FakeRuntime:
    """A runtime whose instance is a set of pids it made up.

    A class because it holds state its own methods (and its supervisors') change:
    which fake processes still run, which jail started which, and the log of
    calls. `exit_status` is what `Supervisor.wait` answers for any process that
    has ended (`None`: they never end on their own, so a wait reaches its
    deadline). `has_supervisor` `False` makes `supervisor` return `None`, a jail
    that can only be destroyed.

    Its `kind` is `RuntimeKind.FAKE` (decision-181), whatever kind the jail was
    compiled for, so its records say `FAKE` and can't be sent to a real
    runtime."""

    def __init__(
        self,
        *,
        exit_status: int | None = None,
        has_supervisor: bool = True,
        capabilities: frozenset[Capability] = frozenset(Capability),
    ) -> None:
        self.exit_status = exit_status
        self.has_supervisor = has_supervisor
        self._capabilities = capabilities
        self.calls: list[Call] = []
        self._running: set[int] = set()
        self._started: dict[str, list[ProcessRecord]] = {}
        self._next_pid = FAKE_PID_BASE

    @property
    def kind(self) -> RuntimeKind:
        return RuntimeKind.FAKE

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self._capabilities

    def _spawn(self, argv: Sequence[str], jail: JailRecord, io: IoPolicy) -> ProcessRecord:
        """A new fake process in `jail`, running until stopped or destroyed."""
        pid = self._next_pid
        self._next_pid += 1
        self._running.add(pid)
        started = self._started.setdefault(jail.jail_id, [])
        process_id = f"{pid:016x}"
        directory = os.path.join(jail.jail_dir, PROCS_DIRNAME, process_id)
        process = ProcessRecord(
            id=process_id,
            order=len(started),
            pid=pid,
            pgid=pid,
            start_time=FAKE_STAMP,
            argv=tuple(argv),
            stdout_path=os.path.join(directory, io.stdout_name),
            stderr_path=os.path.join(directory, io.stderr_name),
        )
        started.append(process)
        return process

    def running(self, process: ProcessRecord) -> bool:
        """Whether `process` has neither ended nor been stopped."""
        return process.pid in self._running

    def _end(self, process: ProcessRecord) -> KillOutcome:
        """End `process`: `ENDED` if it ran, `ALREADY_GONE` if not."""
        if process.pid in self._running:
            self._running.discard(process.pid)
            return KillOutcome.ENDED
        return KillOutcome.ALREADY_GONE

    def _processes(self, jail: JailRecord) -> tuple[ProcessRecord, ...]:
        """Every process of `jail`: the ones it names, then every other one
        this runtime started in it, in start order."""
        named = {process.pid for process in jail.processes}
        started = self._started.get(jail.jail_id, [])
        return (*jail.processes, *(p for p in started if p.pid not in named))

    def create(
        self,
        jail: CompiledJail,
        *,
        cwd: str,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """A record for a jail with no process in it (decision-181). The fake
        applies no wrap: its wrap prefix is empty, so every start is `PLAIN`.
        Refuses nothing; `capabilities` is only reported, and `tether` is
        ignored."""
        record = JailRecord(
            kind=self.kind,
            jail_id=jail_id,
            jail_dir=jail_dir,
            cwd=cwd,
            jail_env=frozendict(jail.env),
            wrap_prefix=(),
        )
        self.calls.append(Call("create", Scope.JAIL, record))
        return record

    def processes(self, jail: JailRecord) -> tuple[ProcessRecord, ...]:
        """Every process of `jail`, in start order (`_processes`)."""
        self.calls.append(Call("processes", Scope.JAIL, jail))
        return self._processes(jail)

    def process_alive(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `process` has neither ended nor been stopped."""
        del jail
        self.calls.append(Call("process_alive", Scope.PROCESS, process))
        return self.running(process)

    def alive(self, jail: JailRecord) -> bool:
        """Whether any process of `jail` still runs."""
        self.calls.append(Call("alive", Scope.JAIL, jail))
        return any(self.running(process) for process in self._processes(jail))

    def destroy(self, jail: JailRecord) -> KillReport:
        """Ends every process of `jail`, one item each in start order: the
        first `workload_group`, every later one `exec_sibling`."""
        self.calls.append(Call("destroy", Scope.JAIL, jail))
        return KillReport(
            items=tuple(
                KillItem(
                    kind="workload_group" if position == 0 else "exec_sibling",
                    identity=str(process.pgid),
                    outcome=self._end(process),
                    detail="",
                )
                for position, process in enumerate(self._processes(jail))
            )
        )

    def supervisor(self, jail: JailRecord) -> Supervisor | None:
        self.calls.append(Call("supervisor", Scope.JAIL, jail))
        return FakeSupervisor(self, jail) if self.has_supervisor else None

    def first(self, jail: JailRecord) -> ProcessRecord | None:
        """The first process of `jail`, or `None` when nothing was started."""
        processes = self._processes(jail)
        return processes[0] if processes else None


@dataclass(frozen=True, slots=True)
class FakeSupervisor:
    """`FakeRuntime`'s supervisor for one jail. Its state is the runtime's."""

    runtime: FakeRuntime
    jail: JailRecord

    def start(self, argv: Sequence[str], *, cwd: str, io: IoPolicy) -> ProcessRecord:
        process = self.runtime._spawn((*(self.jail.wrap_prefix or ()), *argv), self.jail, io)
        self.runtime.calls.append(Call("start", Scope.PROCESS, process))
        return process

    def signal(self, process: ProcessRecord, sig: Signals) -> bool:
        """Delivered while `process` runs; the fake takes no signal's
        default action, so nothing ends."""
        self.runtime.calls.append(Call(f"signal:{sig.name}", Scope.PROCESS, process))
        return self.runtime.running(process)

    def wait(self, process: ProcessRecord, timeout: float | None) -> int | None:
        """`exit_status`, and `process` counts as ended, when the runtime
        has one; `None`, the deadline, when it does not."""
        self.runtime.calls.append(Call("wait", Scope.PROCESS, process))
        if self.runtime.exit_status is None:
            return None
        self.runtime._end(process)
        return self.runtime.exit_status

    def stop(self, process: ProcessRecord) -> KillReport:
        self.runtime.calls.append(Call("stop", Scope.PROCESS, process))
        first = self.runtime.first(self.jail)
        kind = (
            "workload_group" if first is not None and process.pid == first.pid else "exec_sibling"
        )
        return KillReport(
            items=(
                KillItem(
                    kind=kind,
                    identity=str(process.pgid),
                    outcome=self.runtime._end(process),
                    detail="",
                ),
            )
        )
