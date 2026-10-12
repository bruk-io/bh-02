"""`Jail` and `Process` delegating through `brig.runtime.fake` (decision-178,
TASK-0079.02; held to `Jail` since decision-183, TASK-0079.28).

The runtime seam has two implementations from the start: `HostRuntime` and
`FakeRuntime`. These tests hold the jail to delegating every control action
(`alive`, `interrupt`, `wait`, `destroy`, a sibling `start`) to the runtime it
was created with: each answer here comes from the fake, and the fake's log
says what it was asked, about which record, at which scope. Nothing is
spawned, signalled or read.

Until decision-183 these tests drove `Jail` (planted once and reverted on
2026-10-12: with the handle asking a fresh `HostRuntime()` instead of its own
runtime, 9 of 13 failed). They hold `Jail` to the same delegation: a jail
whose calls went to any runtime but the one passed to `create` (or to
`from_dict`) fails every test here that reads the fake's log. Where a call is
now absent rather than refusing (a jail with no supervisor has no `start`,
its processes no `interrupt` or `wait`, SPEC.md section 9), the test says so.
"""

import dataclasses
import signal

import pytest

from brig.core import Grade, Spec
from brig.core.runtime import RUNTIME_AXES, Capability, RuntimeKind, Scope, runtime_grades
from brig.run import ExecFidelity, Jail, KillOutcome, Process, _records
from brig.run.host import HostRuntime
from brig.run.runtime import IoPolicy, JailRecord, ProcessRecord, Runtime, Supervisor
from brig.runtime.fake import FAKE_PID_BASE, Call, FakeRuntime, FakeSupervisor
from brig.stack import Stack

_JAIL_DIR = "/nonexistent/brig-fake-jail"


def _jail(runtime: FakeRuntime) -> tuple[Jail, Process]:
    """A jail with one process, the way an embedder makes one: `Jail.create`,
    which starts nothing (decision-181), then a first `start`."""
    jail = Jail.create(
        Stack([]).compile(Spec()),
        runtime=runtime,
        cwd="/work",
        jail_id="fake-jail",
        jail_dir=_JAIL_DIR,
    )
    return jail, jail.start(("sleep", "100"))


def _without_a_supervisor(runtime: FakeRuntime) -> tuple[Jail, ProcessRecord]:
    """A jail whose runtime offers no supervisor, holding one process: its
    first start goes through the fake's supervisor directly (the jail itself
    has no `start` to make it), and the jail is rehydrated with that record
    named, as an embedder holding a destroy-only jail would."""
    created = Jail.create(
        Stack([]).compile(Spec()),
        runtime=FakeRuntime(),
        cwd="/work",
        jail_id="fake-jail",
        jail_dir=_JAIL_DIR,
    )
    first = FakeSupervisor(runtime, created._record()).start(
        ("sleep", "100"), cwd="/work", io=IoPolicy()
    )
    d = {**created.to_dict(), "processes": [_records.to_json(first)]}
    return Jail.from_dict(d, runtimes={RuntimeKind.FAKE: runtime}), first


def _methods(runtime: FakeRuntime) -> list[str]:
    return [call.method for call in runtime.calls]


@pytest.mark.unit
def test_both_runtimes_implement_both_protocols() -> None:
    """The protocols have two implementations, checked by mypy at these
    assignments and by the attributes here."""
    fake = FakeRuntime()
    host = HostRuntime()
    runtimes: tuple[Runtime, ...] = (fake, host)
    record = _jail(fake)[0]._record()
    supervisors: tuple[Supervisor | None, ...] = (fake.supervisor(record), host.supervisor(record))
    assert all(supervisor is not None for supervisor in supervisors)
    assert [runtime.kind for runtime in runtimes] == [RuntimeKind.FAKE, RuntimeKind.HOST]


@pytest.mark.unit
def test_the_host_runtime_offers_a_new_group_and_detachment_and_no_pty() -> None:
    """The host runtime offers exactly what the `subprocess` launcher did
    until decision-183, in one vocabulary since decision-179 retired
    `LaunchFeature` for `Capability`."""
    assert HostRuntime().capabilities == frozenset(
        {Capability.NEW_PROCESS_GROUP, Capability.DETACH}
    )
    assert {c.value for c in Capability} == {"NEW_PROCESS_GROUP", "PTY", "DETACH"}


@pytest.mark.unit
def test_the_record_carries_the_jails_identity() -> None:
    runtime = FakeRuntime()
    jail, first = _jail(runtime)
    record = jail._record()
    assert isinstance(record, JailRecord)
    created = runtime.calls[0].subject
    assert isinstance(created, JailRecord)
    assert created.processes == ()  # create starts nothing (decision-181)
    started = next(call.subject for call in runtime.calls if call.method == "start")
    assert record == dataclasses.replace(created, processes=(started,))
    (held,) = record.processes
    assert (held.id, held.pid) == (first.id, first.pid)
    assert first.pid >= FAKE_PID_BASE


@pytest.mark.unit
def test_the_fake_has_a_kind_of_its_own_and_its_records_say_so() -> None:
    """decision-181: `RuntimeKind.FAKE`, graded `unenforced` on both runtime
    axes with a detail saying it is a test double, named by no mechanism; a
    fake jail's record says `FAKE` whatever kind its jail was compiled for."""
    runtime = FakeRuntime()
    jail, _first = _jail(runtime)
    assert Stack([]).compile(Spec()).runtime is RuntimeKind.HOST
    assert jail._record().kind is RuntimeKind.FAKE
    grades = runtime_grades(RuntimeKind.FAKE)
    assert set(grades) == RUNTIME_AXES
    assert {graded.grade for graded in grades.values()} == {Grade.UNENFORCED}
    assert all("test double" in graded.detail for graded in grades.values())


@pytest.mark.unit
def test_alive_and_destroy_ask_the_runtime() -> None:
    runtime = FakeRuntime()
    jail, _first = _jail(runtime)
    assert jail.alive() is True

    report = jail.destroy()

    assert [(item.kind, item.outcome) for item in report.items] == [
        ("workload_group", KillOutcome.ENDED)
    ]
    assert jail.alive() is False
    assert _methods(runtime) == ["create", "supervisor", "supervisor", "start"] + [
        "alive",
        "destroy",
        "alive",
    ]
    assert runtime.calls[-2] == Call("destroy", Scope.JAIL, jail._record())


@pytest.mark.unit
def test_interrupt_signals_the_first_process_through_the_supervisor() -> None:
    runtime = FakeRuntime()
    jail, first = _jail(runtime)

    assert first.interrupt() is True

    assert runtime.calls[-1] == Call(
        f"signal:{signal.SIGINT.name}", Scope.PROCESS, jail._record().processes[0]
    )


@pytest.mark.unit
def test_a_process_of_a_jail_without_a_supervisor_has_no_interrupt() -> None:
    """Until decision-183 a handle with no supervisor returned `False` (not
    delivered); `Process.interrupt` is absent instead (SPEC.md section 9's
    law), and asking for it asks the runtime for its supervisor and nothing
    else."""
    runtime = FakeRuntime(has_supervisor=False)
    jail, _first = _without_a_supervisor(runtime)
    (process,) = jail.processes()
    before = len(runtime.calls)
    assert not hasattr(process, "interrupt")
    assert {call.method for call in runtime.calls[before:]} == {"supervisor"}


@pytest.mark.unit
def test_wait_returns_the_supervisors_status() -> None:
    runtime = FakeRuntime(exit_status=7)
    jail, first = _jail(runtime)
    assert first.wait(timeout=0.0) == 7
    assert runtime.calls[-1] == Call("wait", Scope.PROCESS, jail._record().processes[0])


@pytest.mark.unit
def test_wait_raises_timeout_when_the_supervisor_reaches_the_deadline() -> None:
    _jail_, first = _jail(FakeRuntime(exit_status=None))
    with pytest.raises(TimeoutError, match="still ran"):
        first.wait(timeout=0.0)


@pytest.mark.unit
def test_a_process_of_a_jail_without_a_supervisor_has_no_wait() -> None:
    """Until decision-183 such a handle's `wait` raised `NoSupervisor`; the
    call is absent instead."""
    jail, _first = _without_a_supervisor(FakeRuntime(has_supervisor=False))
    (process,) = jail.processes()
    assert not hasattr(process, "wait")
    with pytest.raises(AttributeError, match="no supervisor"):
        _ = process.wait


@pytest.mark.unit
def test_a_sibling_start_goes_through_the_supervisor() -> None:
    runtime = FakeRuntime(exit_status=3)
    jail, first = _jail(runtime)

    sibling = jail.start(["true"])

    assert isinstance(sibling, Process)
    start = runtime.calls[-1]
    assert (start.method, start.scope) == ("start", Scope.PROCESS)
    assert sibling.pid == first.pid + 1
    assert sibling.argv == ("true",)
    assert sibling.fidelity is ExecFidelity.PLAIN
    assert sibling.stdout_path.startswith(f"{_JAIL_DIR}/procs/")
    assert sibling.stdout_path.endswith("/stdout.log")
    assert sibling.stdout_path != first.stdout_path
    assert sibling.wait(timeout=0.0) == 3
    assert runtime.calls[-1] == Call("wait", Scope.PROCESS, start.subject)


@pytest.mark.unit
def test_a_jail_without_a_supervisor_has_no_start() -> None:
    """Until decision-183 such a handle's `exec` raised `NoSupervisor`; the
    jail's `start` is absent instead."""
    jail, _first = _without_a_supervisor(FakeRuntime(has_supervisor=False))
    assert not hasattr(jail, "start")
    with pytest.raises(AttributeError, match="no supervisor"):
        _ = jail.start


@pytest.mark.unit
def test_the_supervisor_stops_one_process_and_destroy_ends_the_rest() -> None:
    runtime = FakeRuntime()
    jail, first = _jail(runtime)
    one = jail.start(["a"])
    two = jail.start(["b"])

    stopped = one.stop()

    assert [(i.kind, i.outcome) for i in stopped.items] == [("exec_sibling", KillOutcome.ENDED)]
    assert one.alive() is False
    assert two.alive() is True
    # A stopped process is still the jail's (decision-181): destroy reports
    # it, already gone, beside the one it ends.
    assert [(i.kind, i.identity, i.outcome) for i in jail.destroy().items] == [
        ("workload_group", str(first.pid), KillOutcome.ENDED),
        ("exec_sibling", str(one.pid), KillOutcome.ALREADY_GONE),
        ("exec_sibling", str(two.pid), KillOutcome.ENDED),
    ]


@pytest.mark.unit
def test_the_runtime_is_not_serialized_and_rehydration_takes_the_one_passed() -> None:
    """`to_dict` carries data only (the runtime's kind, never the runtime);
    `from_dict` hands the rehydrated jail the runtime the embedder passed,
    and every call it makes goes there."""
    runtime = FakeRuntime()
    jail, first = _jail(runtime)
    d = jail.to_dict()
    assert d["runtime"] == "FAKE"
    assert not any(isinstance(value, FakeRuntime) for value in d.values())

    again = Jail.from_dict(d, runtimes={RuntimeKind.FAKE: runtime})
    assert again.to_dict() == d
    before = len(runtime.calls)
    assert again.alive() is True
    assert runtime.calls[before:] == [Call("alive", Scope.JAIL, again._record())], (
        "the rehydrated jail did not ask the runtime it was given"
    )
    assert first.alive() is True
