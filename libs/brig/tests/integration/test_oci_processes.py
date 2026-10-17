"""A container's processes, started through brig (decision-203, TASK-0079.10).

A container jail has an agent for its processes, found out at `create`: brig's supervisor as the
container's PID 1 where the image has python3 (`bh-02-linux-jail:latest`), `docker exec` where it has
none (`ubuntu:24.04`). This file runs both against the Docker daemon of the machine, and every
observation is the test's own (the host's `/proc`, `/bin/ps`, `docker inspect`), never the runtime's:
an observation made with the code under test is not an observation (WORKFLOW.md).

- what each agent is and what a process of it is graded (`Process.fidelity`, `Process.control`);
- that a process is recorded before it runs a byte (the exec agent's gate);
- the channel directory: a process binds its reserved socket in a bind-mounted directory and the host
  dials it through the verified dial, across the container's pid namespace;
- the control battery (`tests/control_battery.py`) planted in each, the claim held to the proof;
- what the supervisor's start refuses (a peer that is not PID 1, an interpreter that cannot run).

The tier skips, naming `docker info` or the missing image, where the daemon or an image is not there.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from brig.core import Axis, Channel, ChannelKind, Grade, Spec
from brig.core.runtime import ContainerAgent, Scope
from brig.run import EndpointRefused, ExecFidelity, Jail, KillOutcome, WorkloadSpawnFailed
from brig.run import _supervised as supervised
from brig.runtime import _oci_exec
from brig.runtime._oci_agent import AgentStartFailed, accept_hello, bind_rendezvous
from brig.runtime.oci import OciCreateFailed
from tests import control_battery as battery
from tests.control_battery import Cell, Harness, Survivor
from tests.oci_jail import (
    IMAGE,
    PYTHON_IMAGE,
    PYTHON_INTERPRETER,
    allow_list,
    container_of,
    docker,
    inspect,
    needs_python_image,
)
from tests.supervised_jail import process_state, running_with, sh, unique_sleep, until

pytestmark = pytest.mark.integration

Make = Callable[..., Jail]


@dataclass(frozen=True)
class Agent:
    """A jail type under test: the image, the interpreter the mechanism is given, and the agent that
    must come of it. `exec` is `ubuntu:24.04`, which has no python3, with the default interpreter
    named: the supervisor is tried, `docker start` answers 127, and the container is made again for
    `docker exec`."""

    name: str
    image: str
    interpreter: str | None
    expected: ContainerAgent


SUPERVISOR = Agent("supervisor", PYTHON_IMAGE, PYTHON_INTERPRETER, ContainerAgent.SUPERVISOR)
EXEC = Agent("exec", IMAGE, PYTHON_INTERPRETER, ContainerAgent.EXEC)
#: The exec agent in an image that has python3, for the tests whose process needs an interpreter.
EXEC_WITH_PYTHON = Agent("exec+python", PYTHON_IMAGE, None, ContainerAgent.EXEC)


@pytest.fixture(autouse=True)
def _needs_images() -> None:
    needs_python_image()


@pytest.fixture(params=[SUPERVISOR, EXEC], ids=lambda agent: agent.name)
def agent(request: pytest.FixtureRequest) -> Agent:
    assert isinstance(request.param, Agent)
    return request.param


def _jail(make: Make, agent: Agent, **more: Any) -> Jail:
    spec = more.pop("spec", Spec(fs=allow_list()))
    return make(spec, image=agent.image, interpreter=agent.interpreter, **more)


def _record(jail: Jail) -> Any:
    return jail._record()


def _init_pid(jail: Jail) -> int:
    entry = inspect(container_of(jail))
    assert entry is not None
    return int(entry["State"]["Pid"])


def _status_fields(pid: int) -> dict[str, str]:
    """The confinement fields of `/proc/<pid>/status`, read by the host."""
    wanted = ("Uid", "CapEff", "CapBnd", "NoNewPrivs", "Seccomp")
    with open(f"/proc/{pid}/status", encoding="utf-8") as status:
        return {
            line.split(":")[0]: line.split(":", 1)[1].strip()
            for line in status
            if line.split(":")[0] in wanted
        }


def _cmdline(pid: int) -> list[str]:
    with open(f"/proc/{pid}/cmdline", "rb") as cmdline:
        return cmdline.read().decode(errors="replace").split("\0")


# --- which agent, and what a process of it says --------------------------------------------------


def test_the_agent_found_at_create_is_the_supervisor_where_python_is_and_exec_where_it_is_not(
    make_oci_jail: Make, agent: Agent
) -> None:
    jail = _jail(make_oci_jail, agent)
    record = _record(jail).container
    entry = inspect(container_of(jail))
    assert entry is not None and record.agent is agent.expected
    assert record.init_pid == int(entry["State"]["Pid"])
    if agent.expected is ContainerAgent.SUPERVISOR:
        # The supervisor is the container's PID 1 and nothing else is: no `--init`, its program the
        # file bound read-only, its one argument the rendezvous path in the channel directory.
        assert not entry["HostConfig"].get("Init")
        assert entry["Config"]["Cmd"][:3] == [PYTHON_INTERPRETER, "-I", "/.brig-supervisor.py"]
        init = _cmdline(record.init_pid)
        assert init[0].endswith("python3") and "/.brig-supervisor.py" in init
        mounts = {m["Destination"]: m for m in entry["Mounts"]}
        assert mounts["/.brig-supervisor.py"]["RW"] is False
        assert record.agent_reason == ""
        assert _record(jail).namespaces is not None
    else:
        assert entry["HostConfig"]["Init"] is True
        assert entry["Config"]["Cmd"] == ["sleep", "infinity"]
        assert "/usr/bin/python3" in record.agent_reason and "127" in record.agent_reason
    chan = os.path.realpath(jail.jail_dir) + "/chan"
    assert {m["Destination"]: m["RW"] for m in entry["Mounts"]}[chan] is True
    # Nothing listens once the jail is made, and nothing the create made is left in the channel
    # directory: the supervisor's rendezvous is gone, as are the exec agent's files.
    assert os.listdir(chan) == []


def test_a_process_is_started_waited_for_and_graded_by_the_agent_that_holds_it(
    make_oci_jail: Make, agent: Agent
) -> None:
    jail = _jail(make_oci_jail, agent)
    process = jail.start(sh("echo out; echo err >&2; exit 3"))
    assert process.wait(10) == 3
    with open(process.stdout_path, encoding="utf-8") as out:
        assert out.read() == "out\n"
    with open(process.stderr_path, encoding="utf-8") as err:
        assert err.read() == "err\n"
    assert process.fidelity is ExecFidelity.SAME_INSTANCE
    assert process.namespaces is False
    assert process.control.grade is Grade.COOPERATIVE
    detail = process.control.detail
    assert "setsid()" in detail and "tests/integration/test_oci_processes.py" in detail
    if agent.expected is ContainerAgent.SUPERVISOR:
        assert "request to brig's supervisor" in detail
        assert "share the container's namespaces because" in detail
    else:
        assert "host's ladder" in detail and "docker exec because" in detail
        assert "/usr/bin/python3" in detail  # the reason it is docker exec, in the grade
    assert [p.id for p in jail.processes()] == [process.id]


def test_a_stop_ends_the_process_group_verified_and_the_status_is_the_agents(
    make_oci_jail: Make, agent: Agent
) -> None:
    jail = _jail(make_oci_jail, agent)
    marker, argv = unique_sleep()
    other_marker, other = unique_sleep()
    victim, bystander = jail.start(argv), jail.start(other)
    assert until(lambda: running_with(f"sleep {marker}") and running_with(f"sleep {other_marker}"))
    report = victim.stop()
    (item,) = report.items
    assert item.outcome is KillOutcome.ENDED, item
    assert until(lambda: not running_with(f"sleep {marker}"))
    assert running_with(f"sleep {other_marker}")  # the bystander was not asked about
    assert bystander.alive() and not victim.alive()
    status = victim.wait(10)
    # `-15` is the supervisor's report of a process the signal ended; `128 + 15` is all
    # `docker exec` says of one.
    assert status == (-15 if agent.expected is ContainerAgent.SUPERVISOR else 143)


def test_an_interrupt_is_a_sigint_to_the_group_whichever_agent_delivers_it(
    make_oci_jail: Make, agent: Agent
) -> None:
    jail = _jail(make_oci_jail, agent)
    process = jail.start(sh("trap 'exit 42' INT; sleep 5 & wait"))
    # The shell must have installed its trap before the signal, or SIGINT ends it by default:
    # `/proc` says SIGINT (bit 2) is caught.
    assert until(lambda: "trap" in " ".join(_cmdline(process.pid)))
    assert until(lambda: _caught(process.pid, signal.SIGINT))
    assert process.interrupt() is True
    assert process.wait(10) == 42


def _caught(pid: int, number: int) -> bool:
    """Whether `/proc` says the process catches signal `number` (`SigCgt`), read by the host."""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("SigCgt:"):
                    return bool(int(line.split()[1], 16) & (1 << (number - 1)))
    except OSError:
        return False
    return False


def test_a_process_that_is_not_there_or_has_nowhere_to_run_is_a_failed_start_that_leaves_nothing(
    make_oci_jail: Make, agent: Agent
) -> None:
    jail = _jail(make_oci_jail, agent)
    chan = os.path.realpath(jail.jail_dir) + "/chan"
    with pytest.raises(WorkloadSpawnFailed, match="no/such/prog"):
        jail.start(["/no/such/prog"])
    with pytest.raises(WorkloadSpawnFailed):
        jail.start(["/bin/true"], cwd="/nowhere/at/all")
    assert os.listdir(chan) == []
    assert jail.processes() == ()
    assert not os.path.exists(os.path.join(jail.jail_dir, "procs")) or not os.listdir(
        os.path.join(jail.jail_dir, "procs")
    )
    # ... and the jail is unharmed: the control for a refusal that broke it.
    assert jail.start(sh("exit 0")).wait(10) == 0


def test_destroy_ends_the_container_and_every_process_in_it(
    make_oci_jail: Make, agent: Agent
) -> None:
    jail = _jail(make_oci_jail, agent)
    marker, argv = unique_sleep()
    jail.start(argv)
    assert until(lambda: running_with(f"sleep {marker}"))
    report = jail.destroy()
    assert {item.kind: item.outcome for item in report.items}["container"] is KillOutcome.ENDED
    assert until(lambda: not running_with(f"sleep {marker}"))
    assert inspect(container_of(jail)) is None


def test_a_process_of_either_agent_is_in_the_confinement_of_the_containers_own_init(
    make_oci_jail: Make, agent: Agent
) -> None:
    """The ground of `SAME_INSTANCE` (and of law 2 for the exec agent): a `docker exec` process is
    not given more than the container's init has. User, capabilities, `no-new-privileges` and the
    seccomp filter, each read from `/proc` by the host."""
    jail = _jail(make_oci_jail, agent)
    process = jail.start(sh("sleep 30"))
    assert until(lambda: process.alive())
    init = _status_fields(_init_pid(jail))
    mine = _status_fields(process.pid)
    assert mine == init
    assert init["CapEff"] == init["CapBnd"] == "0000000000000000"
    assert init["NoNewPrivs"] == "1" and init["Seccomp"] == "2"


def test_docker_refuses_a_process_namespaces_of_its_own_so_none_is_claimed(
    make_oci_jail: Make,
) -> None:
    """Measured (SPEC.md section 8, decision-203): under `--cap-drop ALL`, Docker's default seccomp
    profile refuses `unshare(CLONE_NEWUSER)`, so the supervisor finds it can give a process no
    namespaces of its own and the process scope is group-shaped. The control: a process in the
    same container that asks for nothing of the kind runs."""
    jail = _jail(make_oci_jail, SUPERVISOR)
    refused = jail.start(["/usr/bin/unshare", "--user", "true"])
    assert refused.wait(10) != 0
    with open(refused.stderr_path, encoding="utf-8") as err:
        assert "not permitted" in err.read()
    assert jail.start(["/usr/bin/true"]).wait(10) == 0
    namespaces = _record(jail).namespaces
    assert namespaces is not None and namespaces.held is False and namespaces.reason


# --- the gate: a process is recorded before it runs a byte --------------------------------------


def test_the_exec_agents_process_is_held_at_the_gate_until_its_record_is_written(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    jail = _jail(make_oci_jail, EXEC)
    seen: dict[str, Any] = {}
    real = _oci_exec._write_gate

    def look_then_open(gate: str, word: bytes, **more: Any) -> bool:
        if word == b"go\n":
            procs = os.path.join(jail.jail_dir, "procs")
            (directory,) = os.listdir(procs)
            record_path = os.path.join(procs, directory, "record.json")
            seen["record"] = os.path.exists(record_path)
            with open(os.path.join(procs, directory, "stdout.log"), encoding="utf-8") as out:
                seen["output"] = out.read()
            with open(record_path, encoding="utf-8") as record:
                seen["state"] = process_state(json.load(record)["pid"])
        return real(gate, word, **more)

    monkeypatch.setattr(_oci_exec, "_write_gate", look_then_open)
    process = jail.start(sh("echo ran"))
    assert process.wait(10) == 0
    # At the moment the gate opened the record was on disk, the process had written nothing and was
    # asleep in the shim; after it opened, the program ran.
    assert seen == {"record": True, "output": "", "state": "S"}
    with open(process.stdout_path, encoding="utf-8") as out:
        assert out.read() == "ran\n"


def test_an_announced_pid_that_is_not_the_shim_is_refused_and_nothing_runs(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A co-tenant that forges the announcement names some other process; the host checks the
    process it maps is the shim of this start (its command line carries the start's id), refuses,
    and lets the held shim go to exit, so the program never runs."""
    jail = _jail(make_oci_jail, EXEC)
    init = _init_pid(jail)
    monkeypatch.setattr(_oci_exec, "find_host_pid", lambda container_pid, init_pid: init)
    marker, argv = unique_sleep()
    with pytest.raises(WorkloadSpawnFailed, match="not allowed to run"):
        jail.start(argv)
    assert until(lambda: not running_with(os.path.realpath(jail.jail_dir)))
    assert not running_with(f"sleep {marker}")
    assert jail.processes() == ()


# --- the channel directory ----------------------------------------------------------------------

_LISTEN = r"""
import os, socket, sys
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(sys.argv[1])
server.listen(1)
print("listening", flush=True)
while True:
    connection, _ = server.accept()
    try:
        connection.sendall(b"hello from " + str(os.getpid()).encode())
    except OSError:
        pass  # the host's readiness connect closes at once, which is a dial like any other
    connection.close()
"""


@pytest.fixture(params=[SUPERVISOR, EXEC_WITH_PYTHON], ids=lambda agent: agent.name)
def with_python(request: pytest.FixtureRequest) -> Agent:
    assert isinstance(request.param, Agent)
    return request.param


def _channel_spec() -> Spec:
    return Spec(fs=allow_list(), channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),))


def test_a_process_binds_its_reserved_socket_and_the_host_dials_it_through_the_verified_dial(
    make_oci_jail: Make, with_python: Agent
) -> None:
    jail = _jail(make_oci_jail, with_python, spec=_channel_spec())
    reservation = jail.channel("ctl")
    chan = os.path.realpath(jail.jail_dir) + "/chan"
    assert os.path.dirname(reservation.bound_path) == chan
    assert reservation.endpoint == reservation.bound_path  # one directory, mounted at its own path
    process = jail.start(
        [PYTHON_INTERPRETER, "-I", "-c", _LISTEN, reservation.bound_path], channel=reservation
    )
    process.wait_ready(20)
    with process.connect() as connection:
        said = connection.recv(100)
    assert said.startswith(b"hello from ")
    # The listener is a process of the container's own pid namespace, numbered for the host.
    assert int(said.split()[-1]) != process.pid
    assert process.endpoint == reservation.endpoint and process.channel == "ctl"


def test_a_socket_a_co_tenant_binds_at_another_processes_path_is_refused(
    make_oci_jail: Make, with_python: Agent
) -> None:
    """The peer check across the container's pid namespace: process B binds the path reserved for
    process A. A's `connect` is refused because the listener is not in A's group (decision-185),
    the host speaking nothing to it. B's own dial, the control, is not."""
    jail = _jail(make_oci_jail, with_python, spec=_channel_spec())
    for_a, for_b = jail.channel("ctl"), jail.channel("ctl")
    sleeper = jail.start(sh("sleep 60"), channel=for_a)
    squatter = jail.start(
        [PYTHON_INTERPRETER, "-I", "-c", _LISTEN, for_a.bound_path], channel=for_b
    )
    assert until(lambda: os.path.exists(for_a.bound_path), 20)
    with pytest.raises(EndpointRefused, match="process group"):
        sleeper.connect()
    assert squatter.alive()


def test_a_link_planted_at_a_reserved_socket_is_not_followed(
    make_oci_jail: Make, with_python: Agent, tmp_path: Any
) -> None:
    jail = _jail(make_oci_jail, with_python, spec=_channel_spec())
    reservation = jail.channel("ctl")
    outside = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    target = str(tmp_path / "host.sock")
    outside.bind(target)
    outside.listen(1)
    accepted: list[socket.socket] = []
    threading.Thread(target=lambda: accepted.append(outside.accept()[0]), daemon=True).start()
    process = jail.start(sh("sleep 60"), channel=reservation)
    os.symlink(target, reservation.bound_path)
    with pytest.raises(EndpointRefused, match="symbolic link"):
        process.connect()
    assert accepted == []  # the host never connected to what the link named
    outside.close()


# --- what the supervisor's start refuses --------------------------------------------------------


def test_a_connection_that_is_not_the_containers_pid_1_is_refused(tmp_path: Any) -> None:
    """The accept's peer check, with a real socket and a stand-in for the container: a process other
    than the one named as PID 1 connects, and the host refuses it before reading a byte."""
    path = str(tmp_path / "agent.sock")
    listener = bind_rendezvous(path)

    def connect() -> None:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        client.connect(path)
        client.send(b'{"hello": 1, "protocol": 2}')
        client.close()

    threading.Thread(target=connect, daemon=True).start()
    with pytest.raises(AgentStartFailed, match="the process that connected is pid"):
        accept_hello(
            listener, init_pid=os.getpid() + 100000, alive=lambda: True, unresponsive=lambda: None
        )
    listener.close()


def test_a_container_that_ends_before_the_supervisor_connects_is_found_in_a_second_not_a_minute(
    tmp_path: Any,
) -> None:
    """The accept's liveness check, with a real listener nobody connects to and a stand-in for the
    container that is gone: it raises when the container is asked after, well inside the 60 s."""
    path = str(tmp_path / "agent.sock")
    listener = bind_rendezvous(path)
    started = time.monotonic()
    with pytest.raises(AgentStartFailed, match="container ended before the supervisor connected"):
        accept_hello(listener, init_pid=1, alive=lambda: False, unresponsive=lambda: None)
    assert time.monotonic() - started < 10
    listener.close()


def test_an_interpreter_that_is_there_and_cannot_run_is_a_failure_and_no_fallback(
    make_oci_jail: Make,
) -> None:
    """Only a command that is not found (127) is reason to start with `docker exec`: a file that
    is there and cannot be run (126) is the embedder's mistake, and a container is not made as
    something else for it (law 2). Nothing is left behind."""
    with pytest.raises(OciCreateFailed, match="docker start failed"):
        make_oci_jail(
            Spec(fs=allow_list()),
            image=PYTHON_IMAGE,
            interpreter="/etc/hostname",
            jail_id="oci-notrun-" + os.urandom(4).hex(),
        )
    assert (
        docker(
            "ps", "-a", "--filter", "label=brig.jail", "--format", '{{.Label "brig.jail"}}'
        ).stdout.count("oci-notrun-")
        == 0
    )


def test_a_supervisor_that_ends_at_once_is_a_failed_create_and_leaves_no_container(
    make_oci_jail: Make,
) -> None:
    with pytest.raises(OciCreateFailed, match="not running right after docker start"):
        make_oci_jail(
            Spec(fs=allow_list()),
            image=PYTHON_IMAGE,
            interpreter="/usr/bin/false",
            jail_id="oci-ends-" + os.urandom(4).hex(),
        )
    assert (
        docker(
            "ps", "-a", "--filter", "label=brig.jail", "--format", '{{.Label "brig.jail"}}'
        ).stdout.count("oci-ends-")
        == 0
    )


def test_the_fallback_leaves_one_container_and_no_trace_of_the_attempt(
    make_oci_jail: Make,
) -> None:
    jail_id = "oci-fallback-" + os.urandom(4).hex()
    jail = make_oci_jail(
        Spec(fs=allow_list()), image=IMAGE, interpreter=PYTHON_INTERPRETER, jail_id=jail_id
    )
    listed = docker("ps", "-a", "--no-trunc", "--filter", f"label=brig.jail={jail_id}", "-q")
    assert listed.stdout.split() == [container_of(jail)]
    assert _record(jail).container.agent is ContainerAgent.EXEC


# --- the control battery, planted in each agent's jail --------------------------------------------


def _stop_init(jail: Jail) -> int:
    """`SIGSTOP` the container's PID 1 (the supervisor, or `docker-init`) from the host."""
    pid = _init_pid(jail)
    os.kill(pid, signal.SIGSTOP)
    return pid if until(lambda: process_state(pid) == "T") else 0


def _expected(agent: Agent) -> dict[tuple[Scope, Survivor], tuple[bool, ...]]:
    """Planted, the survivor gone, the control gone, a bystander gone, for each cell. Both agents'
    stops are group-shaped, so the `setsid()` child outlives a stop and is ended by `destroy`. A stop
    through a stopped supervisor ends the jail, a bystander with it; the exec agent asks nobody, so
    the stop is answered and ends the process alone."""
    rows: dict[tuple[Scope, Survivor], tuple[bool, ...]] = {}
    for scope in (Scope.PROCESS, Scope.JAIL):
        for survivor in Survivor:
            outlives = (scope, survivor) == (Scope.PROCESS, Survivor.SETSID_CHILD)
            collateral = (scope, survivor) == (Scope.PROCESS, Survivor.STOPPED_SUPERVISOR) and (
                agent.expected is ContainerAgent.SUPERVISOR
            )
            rows[(scope, survivor)] = (True, not outlives, True, collateral)
    return rows


def test_the_battery_plants_each_survivor_in_each_agents_jail_and_the_grades_are_the_grades_proven(
    make_oci_jail: Make, agent: Agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervised, "SLACK_S", 1.0)
    exec_agent = agent.expected is ContainerAgent.EXEC
    harness = Harness(
        rig=lambda: _jail(make_oci_jail, agent),
        plants=battery.SHELL_PLANTS,
        stop_agent=_stop_init,
        agent_answers_when_stopped=exec_agent,
    )

    cells = battery.run(harness)

    got = {
        (cell.scope, cell.survivor): (
            cell.planted,
            cell.survivor_gone,
            cell.control_gone,
            cell.bystander_gone,
        )
        for cell in cells
    }
    assert got == _expected(agent)

    process_scope = battery.proven(cells, Scope.PROCESS)
    jail_scope = battery.proven(cells, Scope.JAIL)
    # A stop signals a group, and a child that left it outlives the stop, whichever agent signals:
    # `cooperative`. `destroy` is `docker rm -f` and ends everything, a stopped init included.
    assert process_scope is Grade.COOPERATIVE
    assert jail_scope is Grade.ENFORCED

    # The claims, read from a process and a jail of the same type: no higher than the proof, and no
    # lower, so that a grade is raised by a cell and not by a sentence.
    jail = harness.rig()
    process = jail.start(sh("exit 0"))
    assert process.wait(10) == 0
    assert process.control.grade is process_scope, process.control
    assert jail.report.axes[Axis.CONTROL].grade is jail_scope, jail.report.axes[Axis.CONTROL]


def test_the_survivor_is_a_real_one_the_control_for_a_stop_that_leaves_it(
    make_oci_jail: Make, agent: Agent
) -> None:
    """The cell that holds the process scope at `cooperative` is not a plant that never took: the
    same child, in a session of its own, is running after the stop and gone after `destroy`."""
    harness = Harness(
        rig=lambda: _jail(make_oci_jail, agent),
        plants=battery.SHELL_PLANTS,
        stop_agent=_stop_init,
    )
    stopped = battery.stop_a_setsid_child(harness)
    assert stopped.planted and stopped.control_gone and not stopped.survivor_gone
    destroyed = battery.destroy_a_setsid_child(harness)
    assert destroyed.planted and destroyed.control_gone and destroyed.survivor_gone


_ = Cell  # the cell type the battery returns, named for readers of the assertions above
