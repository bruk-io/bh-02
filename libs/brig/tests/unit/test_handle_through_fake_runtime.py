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

from brig.core import Spec
from brig.core.runtime import Capability, RuntimeKind, Scope
from brig.run import Handle, KillOutcome, SubprocessLauncher
from brig.run.exec_ import ExecFidelity, ExecHandle
from brig.run.host import HostRuntime
from brig.run.runtime import Agent, IoPolicy, JailRecord, NoAgent, Runtime
from brig.runtime.fake import FAKE_PID_BASE, Call, FakeRuntime
from brig.stack import Stack

_JAIL_DIR = "/nonexistent/brig-fake-jail"


def _handle(runtime: FakeRuntime) -> Handle:
    """A `Handle` the way `SubprocessLauncher.launch` builds one, from the
    record the runtime's `create` returned."""
    jail = Stack([]).compile(Spec())
    record = runtime.create(
        jail,
        argv=("sleep", "100"),
        cwd="/work",
        io=IoPolicy(),
        jail_id="fake-jail",
        jail_dir=_JAIL_DIR,
        tether=None,
    )
    return Handle(
        jail_id=record.jail_id,
        jail_dir=record.jail_dir,
        launcher_name="fake",
        pid=record.first.pid,
        pgid=record.first.pgid,
        start_time=record.first.start_time,
        argv=record.first.argv,
        cwd=record.cwd,
        jail_env=jail.env,
        wrap_prefix=record.wrap_prefix,
        spec=jail.spec,
        report=jail.report,
        signatures=jail.signatures,
        channels={},
        stdout_path=record.first.stdout_path,
        stderr_path=record.first.stderr_path,
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
    agents: tuple[Agent | None, ...] = (fake.agent(record), host.agent(record))
    assert all(agent is not None for agent in agents)
    assert {runtime.kind for runtime in runtimes} == {RuntimeKind.HOST}


@pytest.mark.unit
def test_the_host_runtime_offers_what_the_subprocess_launcher_does() -> None:
    """`Capability` holds `LaunchFeature`'s members by value until step 2,
    and the host runtime offers exactly the launcher's."""
    assert {c.value for c in HostRuntime().capabilities} == {
        f.value for f in SubprocessLauncher.capabilities
    }
    assert {c.value for c in Capability} == {"NEW_PROCESS_GROUP", "PTY", "DETACH"}


@pytest.mark.unit
def test_record_carries_the_handles_identity() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)
    record = handle.record()
    assert isinstance(record, JailRecord)
    assert record == runtime.calls[0].subject
    assert (record.first.pid, record.first.pgid) == (handle.pid, handle.pgid)
    assert handle.pid >= FAKE_PID_BASE


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
    assert _methods(runtime) == ["create", "alive", "destroy", "alive"]
    assert runtime.calls[2] == Call("destroy", Scope.JAIL, handle.record())


@pytest.mark.unit
def test_interrupt_signals_the_first_process_through_the_agent() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)

    assert handle.interrupt() is True

    assert runtime.calls[-1] == Call(
        f"signal:{signal.SIGINT.name}", Scope.PROCESS, handle.record().first
    )


@pytest.mark.unit
def test_interrupt_without_an_agent_is_not_delivered() -> None:
    runtime = FakeRuntime(has_agent=False)
    handle = _handle(runtime)
    assert handle.interrupt() is False
    assert _methods(runtime) == ["create", "agent"]


@pytest.mark.unit
def test_wait_returns_the_agents_status() -> None:
    runtime = FakeRuntime(exit_status=7)
    handle = _handle(runtime)
    assert handle.wait(timeout=0.0) == 7
    assert runtime.calls[-1] == Call("wait", Scope.PROCESS, handle.record().first)


@pytest.mark.unit
def test_wait_raises_timeout_when_the_agent_reaches_the_deadline() -> None:
    handle = _handle(FakeRuntime(exit_status=None))
    with pytest.raises(TimeoutError, match="did not exit within"):
        handle.wait(timeout=0.0)


@pytest.mark.unit
def test_wait_without_an_agent_refuses() -> None:
    handle = _handle(FakeRuntime(has_agent=False))
    with pytest.raises(NoAgent):
        handle.wait(timeout=0.0)


@pytest.mark.unit
def test_exec_starts_a_sibling_through_the_agent() -> None:
    runtime = FakeRuntime(exit_status=3)
    handle = _handle(runtime)

    sibling = handle.exec(["true"])

    assert isinstance(sibling, ExecHandle)
    start = runtime.calls[-1]
    assert (start.method, start.scope) == ("start", Scope.PROCESS)
    assert sibling.pid == handle.pid + 1
    assert sibling.argv == ("true",)
    assert sibling.fidelity is ExecFidelity.PLAIN
    assert sibling.stdout_path.startswith(f"{_JAIL_DIR}/exec-")
    assert sibling.stdout_path.endswith("-stdout.log")
    assert sibling.wait(timeout=0.0) == 3
    assert runtime.calls[-1] == Call("wait", Scope.PROCESS, start.subject)


@pytest.mark.unit
def test_exec_without_an_agent_refuses() -> None:
    handle = _handle(FakeRuntime(has_agent=False))
    with pytest.raises(NoAgent):
        handle.exec(["true"])


@pytest.mark.unit
def test_the_agent_stops_one_process_and_destroy_ends_the_rest() -> None:
    runtime = FakeRuntime()
    handle = _handle(runtime)
    agent = runtime.agent(handle.record())
    assert agent is not None
    one = agent.start(["a"], cwd="/work", io=IoPolicy())
    two = agent.start(["b"], cwd="/work", io=IoPolicy())

    stopped = agent.stop(one)

    assert [(i.kind, i.outcome) for i in stopped.items] == [("exec_sibling", KillOutcome.ENDED)]
    assert runtime.running(one) is False
    assert runtime.running(two) is True
    assert [(i.kind, i.identity) for i in handle.kill().items] == [
        ("workload_group", str(handle.pgid)),
        ("exec_sibling", str(two.pgid)),
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
