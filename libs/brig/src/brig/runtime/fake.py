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

from brig.core.runtime import Capability, RuntimeKind, Scope
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
    which fake processes still run, and the log of calls. `exit_status` is
    what `Supervisor.wait` answers for any process that has ended (`None`: they
    never end on their own, so a wait reaches its deadline). `has_supervisor`
    `False` makes `supervisor` return `None`, a jail that can only be destroyed."""

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
        self._next_pid = FAKE_PID_BASE

    @property
    def kind(self) -> RuntimeKind:
        return RuntimeKind.HOST

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self._capabilities

    def _spawn(self, argv: Sequence[str], jail_dir: str, io: IoPolicy) -> ProcessRecord:
        """A new fake process, running until stopped or destroyed."""
        pid = self._next_pid
        self._next_pid += 1
        self._running.add(pid)
        return ProcessRecord(
            pid=pid,
            pgid=pid,
            start_time=FAKE_STAMP,
            argv=tuple(argv),
            stdout_path=os.path.join(jail_dir, io.stdout_name),
            stderr_path=os.path.join(jail_dir, io.stderr_name),
        )

    def running(self, process: ProcessRecord) -> bool:
        """Whether `process` has neither ended nor been stopped."""
        return process.pid in self._running

    def _end(self, process: ProcessRecord) -> KillOutcome:
        """End `process`: `ENDED` if it ran, `ALREADY_GONE` if not."""
        if process.pid in self._running:
            self._running.discard(process.pid)
            return KillOutcome.ENDED
        return KillOutcome.ALREADY_GONE

    def create(
        self,
        jail: CompiledJail,
        *,
        argv: Sequence[str],
        cwd: str,
        io: IoPolicy,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """A record for a jail whose first process is `argv`. The fake
        applies no wrap: its wrap prefix is empty, so a later start is
        `PLAIN`. Refuses nothing; `capabilities` is only reported."""
        first = self._spawn(argv, jail_dir, io)
        record = JailRecord(
            kind=self.kind,
            jail_id=jail_id,
            jail_dir=jail_dir,
            cwd=cwd,
            jail_env=frozendict(jail.env),
            wrap_prefix=(),
            first=first,
        )
        self.calls.append(Call("create", Scope.JAIL, record))
        return record

    def alive(self, jail: JailRecord) -> bool:
        self.calls.append(Call("alive", Scope.JAIL, jail))
        return self.running(jail.first)

    def destroy(self, jail: JailRecord) -> KillReport:
        """Ends the first process and every process the supervisors started; one
        item each, the first process first."""
        self.calls.append(Call("destroy", Scope.JAIL, jail))
        first = KillItem(
            kind="workload_group",
            identity=str(jail.first.pgid),
            outcome=self._end(jail.first),
            detail="",
        )
        siblings = tuple(
            KillItem(kind="exec_sibling", identity=str(pid), outcome=KillOutcome.ENDED, detail="")
            for pid in sorted(self._running)
        )
        self._running.clear()
        return KillReport(items=(first, *siblings))

    def supervisor(self, jail: JailRecord) -> Supervisor | None:
        self.calls.append(Call("supervisor", Scope.JAIL, jail))
        return FakeSupervisor(self, jail) if self.has_supervisor else None


@dataclass(frozen=True, slots=True)
class FakeSupervisor:
    """`FakeRuntime`'s supervisor for one jail. Its state is the runtime's."""

    runtime: FakeRuntime
    jail: JailRecord

    def start(self, argv: Sequence[str], *, cwd: str, io: IoPolicy) -> ProcessRecord:
        process = self.runtime._spawn(
            (*(self.jail.wrap_prefix or ()), *argv), self.jail.jail_dir, io
        )
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
        kind = "workload_group" if process == self.jail.first else "exec_sibling"
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
