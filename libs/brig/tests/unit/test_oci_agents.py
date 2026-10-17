"""The decisions behind a container's two agents, as pure functions (decision-203, TASK-0079.10).

Which agent a container has, whether a connection is its PID 1's, what an announcement is and which
host process it names, how `docker exec` is asked to start a process, and how each agent's processes
are graded: each is a function of plain data, so each is checked on any machine with no Docker on
it. That the decisions are right about a real daemon is `tests/integration/test_oci_processes.py`'s.
"""

from __future__ import annotations

import json

import pytest

from brig.core import Grade
from brig.core.runtime import ContainerAgent, RuntimeKind
from brig.run import ExecFidelity
from brig.run.jail import _container_control, _fidelity
from brig.run.runtime import ContainerRecord
from brig.runtime._oci_agent import (
    ContainerState,
    StartVerdict,
    container_state,
    missing_interpreter_reason,
    peer_refusal,
    start_verdict,
)
from brig.runtime._oci_exec import (
    SHIM,
    announced_pid,
    exec_argv,
    nspid_of,
    pick_host_pid,
    spawn_failure,
)

pytestmark = pytest.mark.unit


# --- which agent: what `docker start` and the container's state say ------------------------------


def _inspected(
    *, status: str = "created", exit_code: int = 127, error: str = "x", pid: int = 0
) -> str:
    return json.dumps(
        [{"State": {"Status": status, "ExitCode": exit_code, "Error": error, "Pid": pid}}]
    )


def test_a_start_that_returned_zero_started_whatever_the_state_says() -> None:
    assert start_verdict(0, None) is StartVerdict.STARTED
    state = container_state(_inspected(status="running", exit_code=0, error="", pid=7))
    assert start_verdict(0, state) is StartVerdict.STARTED


def test_only_a_command_not_found_in_a_container_that_never_started_is_a_missing_interpreter() -> (
    None
):
    """Docker's code 127 on a container still `created`, measured for `/usr/bin/python3` and the bare
    `python3` in `ubuntu:24.04`. 126 (there and not executable, measured for `/etc/hostname`) is a
    failure: no container is made as something else for it (law 2)."""
    created = container_state(_inspected(status="created", exit_code=127))
    assert start_verdict(1, created) is StartVerdict.NO_INTERPRETER
    for state in (
        container_state(_inspected(status="created", exit_code=126)),
        container_state(_inspected(status="exited", exit_code=127)),  # it ran, and ended with 127
        container_state(_inspected(status="created", exit_code=0)),
        None,  # the daemon could not be asked: not an answer
    ):
        assert start_verdict(1, state) is StartVerdict.FAILED, state


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        "[]",
        "[{}]",
        json.dumps([{"State": {"Status": 1}}]),
        _inspected() + _inspected(),
    ],
)
def test_output_that_is_not_one_containers_state_is_no_state(stdout: str) -> None:
    assert container_state(stdout) is None


def test_the_state_is_read_from_the_cli_s_own_json() -> None:
    assert container_state(
        _inspected(status="running", exit_code=0, error="", pid=42)
    ) == ContainerState(status="running", exit_code=0, error="", pid=42)


def test_the_reason_a_container_is_docker_exec_names_the_interpreter_and_the_code_or_the_choice() -> (
    None
):
    missing = missing_interpreter_reason("/usr/bin/python3", "ubuntu:24.04")
    assert "'/usr/bin/python3'" in missing and "127" in missing and "'ubuntu:24.04'" in missing
    chosen = missing_interpreter_reason(None, "ubuntu:24.04")
    assert "interpreter=None" in chosen and "127" not in chosen


# --- the connection is the container's PID 1 -----------------------------------------------------


def test_only_the_containers_pid_1_may_be_the_supervisor() -> None:
    assert peer_refusal(4711, 4711) is None
    other = peer_refusal(4712, 4711)
    assert other is not None and "4712" in other and "4711" in other
    unknown = peer_refusal(4711, 0)
    assert unknown is not None and "not known" in unknown
    assert peer_refusal(0, 0) is not None  # a peer the kernel cannot number is never vouched for


# --- the exec agent: the command, the announcement, the process it names -------------------------


def test_the_exec_command_passes_the_files_and_the_argv_as_parameters_never_in_the_script() -> None:
    argv = exec_argv(
        "/usr/bin/docker",
        "c" * 64,
        cwd="/work",
        pidfile="/chan/0123456789abcdef.pid",
        gate="/chan/0123456789abcdef.go",
        argv=("/bin/echo", "$(rm -rf /)", "a b"),
    )
    assert argv == (
        "/usr/bin/docker",
        "exec",
        "--workdir",
        "/work",
        "--",
        "c" * 64,
        "/bin/sh",
        "-c",
        SHIM,
        "brig-exec",
        "/chan/0123456789abcdef.pid",
        "/chan/0123456789abcdef.go",
        "/bin/echo",
        "$(rm -rf /)",
        "a b",
    )
    assert "rm -rf" not in SHIM and "/chan" not in SHIM  # nothing a caller chose is in the script


def test_the_shim_checks_the_program_announces_then_waits_at_the_gate_and_execs_only_for_go() -> (
    None
):
    """The order is the design: a program that is not there is exit 127 before any announcement; the
    announcement comes before the gate is read; `exec` is last and follows a `go`. A shim with the
    gate taken out is what the integration tier's gate test was seen failing against."""
    order = [
        SHIM.index("command -v"),
        SHIM.index('echo $$ >"$p"'),
        SHIM.index('read go <"$g"'),
        SHIM.index('[ "$go" = go ] || exit 125'),
        SHIM.index('exec "$@"'),
    ]
    assert order == sorted(order) and len(set(order)) == len(order)


@pytest.mark.parametrize(
    ("text", "pid"),
    [("1234\n", 1234), ("7\n", 7), ("2147483647\n", 2147483647)],
)
def test_an_announcement_is_one_complete_line_of_digits(text: str, pid: int) -> None:
    assert announced_pid(text) == pid


@pytest.mark.parametrize(
    "text",
    [
        "",
        "12",
        "12\r\n",
        "0\n",
        "-5\n",
        "12 \n",
        "1e3\n",
        "12\n34\n",
        "\n",
        "٣\n",
        "12345678901\n",
        "abc\n",
    ],
)
def test_half_a_line_or_anything_that_is_not_a_pid_is_not_an_announcement(text: str) -> None:
    """The file is the jail's to write: a number that is still being written, or not a number, reads
    as "not yet" and is waited out to the deadline, never acted on."""
    assert announced_pid(text) is None


def test_nspid_is_the_pid_in_each_namespace_outermost_first() -> None:
    status = "Name:\tsh\nNSpid:\t12820\t16\nUid:\t0\t0\t0\t0\n"
    assert nspid_of(status) == (12820, 16)
    assert nspid_of("NSpid:\t5\n") == (5,)
    assert nspid_of("Name:\tsh\n") == ()
    assert nspid_of("NSpid:\t5\tx\n") == ()


def test_the_host_process_is_the_one_whose_pid_in_the_containers_namespace_is_the_number() -> None:
    ns, other = "pid:[4026532267]", "pid:[4026531836]"
    rows = [
        (100, (100,), other),  # a host process that happens to be numbered 16
        (12724, (12724, 1), ns),  # the container's init
        (12820, (12820, 16), ns),  # the process the shim announced
        (13001, (13001, 16), other),  # another container's pid 16
        (13002, (13002, 16, 3), "pid:[4026539999]"),  # a nested namespace's 3
    ]
    assert pick_host_pid(rows, 16, ns) == 12820
    assert pick_host_pid(rows, 1, ns) == 12724
    assert pick_host_pid(rows, 99, ns) is None  # gone, or not visible from here
    assert (
        pick_host_pid([(1, (1,), ns)], 1, ns) is None
    )  # the host's own namespace is not a container's
    twice = [*rows, (12999, (12999, 16), ns)]
    assert pick_host_pid(twice, 16, ns) is None  # two answers is a doubt, never a guess


def test_a_start_that_failed_before_the_announcement_says_the_program_the_container_and_what_it_said() -> (
    None
):
    text = spawn_failure(127, "brig: /no/such/prog: not found\n", "/no/such/prog", "ab" * 32)
    assert "'/no/such/prog'" in text and "abababababab" in text and "status 127" in text
    assert "not found" in text
    assert "it said nothing" in spawn_failure(1, "  \n", "x", "cd" * 32)


# --- the grades ---------------------------------------------------------------------------------


def _record(agent: ContainerAgent | None, reason: str = "") -> ContainerRecord:
    return ContainerRecord("a" * 64, "daemon", agent=agent, agent_reason=reason)


def test_a_container_process_is_cooperative_whichever_agent_holds_it_and_says_which() -> None:
    supervised = _container_control(
        _record(ContainerAgent.SUPERVISOR),
        namespaces=False,
        reason="unshare: Operation not permitted",
    )
    exec_ = _container_control(
        _record(ContainerAgent.EXEC, "the image has no python3"), namespaces=False, reason=None
    )
    unknown = _container_control(_record(None), namespaces=False, reason=None)
    for graded in (supervised, exec_, unknown):
        assert graded.grade is Grade.COOPERATIVE
    assert "request to brig's supervisor" in supervised.detail
    assert "because unshare: Operation not permitted" in supervised.detail
    assert "docker exec because the image has no python3" in exec_.detail
    assert "host's ladder" in exec_.detail and "TASK-0130" in exec_.detail
    assert "rehydrated" in unknown.detail


def test_namespaces_held_in_a_container_are_not_graded_above_what_the_battery_proved() -> None:
    """No battery has been run against a container that can give a process namespaces (Docker's
    seccomp profile refuses them), so the claim is the group-shaped one."""
    graded = _container_control(_record(ContainerAgent.SUPERVISOR), namespaces=True, reason="")
    assert graded.grade is Grade.COOPERATIVE and "no control battery" in graded.detail


def test_every_container_process_is_in_the_instance_whatever_the_wrap() -> None:
    assert _fidelity(RuntimeKind.OCI, None, supervised=False) is ExecFidelity.SAME_INSTANCE
    # and the other kinds are as they were
    assert (
        _fidelity(RuntimeKind.HOST, ("bwrap",), supervised=False) is ExecFidelity.EQUIVALENT_PROFILE
    )
    assert _fidelity(RuntimeKind.HOST, (), supervised=False) is ExecFidelity.PLAIN
    assert _fidelity(RuntimeKind.HOST, ("bwrap",), supervised=True) is ExecFidelity.SAME_INSTANCE
