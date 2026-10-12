"""`Handle` driven through `brig.runtime.fake` (decision-178, TASK-0079.02).

The runtime seam has two implementations from the start: `HostRuntime` and
`FakeRuntime`. These tests hold `Handle` to delegating every control action
(`alive`, `interrupt`, `wait`, `kill`, `exec`) to the runtime it carries: each
answer here comes from the fake, and the fake's log says what it was asked,
about which record, at which scope. Nothing is spawned, signalled or read.

Planted once and reverted (2026-10-12): with `Handle` and `exec_in_jail`
asking a fresh `HostRuntime()` instead of the handle's own runtime, every
delegation test here failed (9 of 13; the other four do not delegate).
"""

import dataclasses
import signal

import pytest

from brig.core import Grade, Spec
from brig.core.runtime import RUNTIME_AXES, Capability, RuntimeKind, Scope, runtime_grades
from brig.run import Handle, KillOutcome, SubprocessLauncher
from brig.run.exec_ import ExecFidelity, ExecHandle
from brig.run.host import HostRuntime
from brig.run.runtime import IoPolicy, JailRecord, NoSupervisor, Runtime, Supervisor
from brig.runtime.fake import FAKE_PID_BASE, Call, FakeRuntime, FakeSupervisor
from brig.stack import Stack

_JAIL_DIR = "/nonexistent/brig-fake-jail"


def _handle(runtime: FakeRuntime) -> Handle:
    """A `Handle` the way `SubprocessLauncher.launch` builds one: the
    runtime's `create`, which starts nothing (decision-181), then a first
    `start`."""
    jail = Stack([]).compile(Spec())
    record = runtime.create(jail, cwd="/work", jail_id="fake-jail", jail_dir=_JAIL_DIR, tether=None)
    # The first start goes through the fake's supervisor directly, so a
    # runtime built with no supervisor still has a first process to name.
    first = FakeSupervisor(runtime, record).start(("sleep", "100"), cwd="/work", io=IoPolicy())
    return Handle(
        jail_id=record.jail_id,
        jail_dir=record.jail_dir,
        launcher_name="fake",
        pid=first.pid,
        pgid=first.pgid,
        start_time=first.start_time,
        argv=first.argv,
        cwd=record.cwd,
        jail_env=jail.env,
        wrap_prefix=record.wrap_prefix,
        spec=jail.spec,
        report=jail.report,
        signatures=jail.signatures,
        channels={},
        stdout_path=first.stdout_path,
        stderr_path=first.stderr_path,
        runtime=runtime,
    )


def _methods(runtime: FakeRuntime) -> list[str]:
    return [call.method for call in runtime.calls]


@pytest.mark.unit
def test_both_runtimes_implement_both_protocols() -> None:
    """The protocols have two implementations, checked by mypy at these
    assignments and by the attributes here."""
    fake = FakeRuntime()
    host = HostRuntime()
    runtimes: tuple[Runtime, ...] = (fake, host)
    record = _handle(fake).record()
    supervisors: tuple[Supervisor | None, ...] = (fake.supervisor(record), host.supervisor(record))
    assert all(supervisor is not None for supervisor in supervisors)
    assert [runtime.kind for runtime in runtimes] == [RuntimeKind.FAKE, RuntimeKind.HOST]


@pytest.mark.unit
def test_the_host_runtime_offers_what_the_subprocess_launcher_does() -> None:
    """The host runtime offers exactly the launcher's capabilities, in one
    vocabulary since decision-179 retired `LaunchFeature` for `Capability`."""
    assert HostRuntime().capabilities == SubprocessLauncher.capabilities
    assert {c.value for c in Capability} == {"NEW_PROCESS_GROUP", "PTY", "DETACH"}


@pytest.mark.unit
def test_record_carries_the_handles_identity() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)
    record = handle.record()
    assert isinstance(record, JailRecord)
    created = runtime.calls[0].subject
    assert isinstance(created, JailRecord)
    assert created.processes == ()  # create starts nothing (decision-181)
    assert record == dataclasses.replace(created, processes=(runtime.calls[1].subject,))
    (first,) = record.processes
    assert (first.pid, first.pgid) == (handle.pid, handle.pgid)
    assert first.id == runtime.first(record).id  # named by its stdio's records directory
    assert handle.pid >= FAKE_PID_BASE


@pytest.mark.unit
def test_the_fake_has_a_kind_of_its_own_and_its_records_say_so() -> None:
    """decision-181: `RuntimeKind.FAKE`, graded `unenforced` on both runtime
    axes with a detail saying it is a test double, named by no mechanism; a
    fake jail's record says `FAKE` whatever kind its jail was compiled for."""
    runtime = FakeRuntime()
    handle = _handle(runtime)
    assert Stack([]).compile(Spec()).runtime is RuntimeKind.HOST
    assert handle.record().kind is RuntimeKind.FAKE
    grades = runtime_grades(RuntimeKind.FAKE)
    assert set(grades) == RUNTIME_AXES
    assert {graded.grade for graded in grades.values()} == {Grade.UNENFORCED}
    assert all("test double" in graded.detail for graded in grades.values())


@pytest.mark.unit
def test_alive_and_kill_ask_the_runtime() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)
    assert handle.alive() is True

    report = handle.kill()

    assert [(item.kind, item.outcome) for item in report.items] == [
        ("workload_group", KillOutcome.ENDED)
    ]
    assert handle.alive() is False
    assert _methods(runtime) == ["create", "start", "alive", "destroy", "alive"]
    assert runtime.calls[3] == Call("destroy", Scope.JAIL, handle.record())


@pytest.mark.unit
def test_interrupt_signals_the_first_process_through_the_supervisor() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)

    assert handle.interrupt() is True

    assert runtime.calls[-1] == Call(
        f"signal:{signal.SIGINT.name}", Scope.PROCESS, handle.record().processes[0]
    )


@pytest.mark.unit
def test_interrupt_without_an_supervisor_is_not_delivered() -> None:
    runtime = FakeRuntime(has_supervisor=False)
    handle = _handle(runtime)
    assert handle.interrupt() is False
    assert _methods(runtime) == ["create", "start", "supervisor"]


@pytest.mark.unit
def test_wait_returns_the_supervisors_status() -> None:
    runtime = FakeRuntime(exit_status=7)
    handle = _handle(runtime)
    assert handle.wait(timeout=0.0) == 7
    assert runtime.calls[-1] == Call("wait", Scope.PROCESS, handle.record().processes[0])


@pytest.mark.unit
def test_wait_raises_timeout_when_the_supervisor_reaches_the_deadline() -> None:
    handle = _handle(FakeRuntime(exit_status=None))
    with pytest.raises(TimeoutError, match="did not exit within"):
        handle.wait(timeout=0.0)


@pytest.mark.unit
def test_wait_without_an_supervisor_refuses() -> None:
    handle = _handle(FakeRuntime(has_supervisor=False))
    with pytest.raises(NoSupervisor):
        handle.wait(timeout=0.0)


@pytest.mark.unit
def test_exec_starts_a_sibling_through_the_supervisor() -> None:
    runtime = FakeRuntime(exit_status=3)
    handle = _handle(runtime)

    sibling = handle.exec(["true"])

    assert isinstance(sibling, ExecHandle)
    start = runtime.calls[-1]
    assert (start.method, start.scope) == ("start", Scope.PROCESS)
    assert sibling.pid == handle.pid + 1
    assert sibling.argv == ("true",)
    assert sibling.fidelity is ExecFidelity.PLAIN
    assert sibling.stdout_path.startswith(f"{_JAIL_DIR}/procs/")
    assert sibling.stdout_path.endswith("/stdout.log")
    assert sibling.stdout_path != handle.stdout_path
    assert sibling.wait(timeout=0.0) == 3
    assert runtime.calls[-1] == Call("wait", Scope.PROCESS, start.subject)


@pytest.mark.unit
def test_exec_without_an_supervisor_refuses() -> None:
    handle = _handle(FakeRuntime(has_supervisor=False))
    with pytest.raises(NoSupervisor):
        handle.exec(["true"])


@pytest.mark.unit
def test_the_supervisor_stops_one_process_and_destroy_ends_the_rest() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)
    supervisor = runtime.supervisor(handle.record())
    assert supervisor is not None
    one = supervisor.start(["a"], cwd="/work", io=IoPolicy())
    two = supervisor.start(["b"], cwd="/work", io=IoPolicy())

    stopped = supervisor.stop(one)

    assert [(i.kind, i.outcome) for i in stopped.items] == [("exec_sibling", KillOutcome.ENDED)]
    assert runtime.running(one) is False
    assert runtime.running(two) is True
    # A stopped process is still the jail's (decision-181): destroy reports
    # it, already gone, beside the one it ends.
    assert [(i.kind, i.identity, i.outcome) for i in handle.kill().items] == [
        ("workload_group", str(handle.pgid), KillOutcome.ENDED),
        ("exec_sibling", str(one.pgid), KillOutcome.ALREADY_GONE),
        ("exec_sibling", str(two.pgid), KillOutcome.ENDED),
    ]


@pytest.mark.unit
def test_the_runtime_is_not_serialized_and_survives_replace() -> None:
    """`to_dict` carries data only; a rehydrated handle gets `HostRuntime`,
    and `dataclasses.replace` keeps the runtime the handle had."""
    runtime = FakeRuntime()
    handle = _handle(runtime)
    assert "runtime" not in handle.to_dict()
    assert isinstance(Handle.from_dict(handle.to_dict()).runtime, HostRuntime)
    assert dataclasses.replace(handle, report=handle.report).runtime is runtime
    assert Handle.from_dict(handle.to_dict()) == handle
