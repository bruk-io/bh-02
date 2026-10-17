"""The pure pieces of a process's namespaces (decision-195, decision-196, TASK-0079.07).

What a real jail shows of them is `tests/e2e/test_process_namespaces.py`'s. This file holds the
parts that are data in, data out: the host path of a socket in a directory of its own, the first
rung of the ladder for a pid namespace's init, the supervisor's own copy of that rule (which is
text, and can't import brig, so a test holds the two to one answer), the grade of a process's
control.
"""

from __future__ import annotations

import ast
import signal
from typing import Any

import pytest

from brig.core import Grade
from brig.run._supervised import namespaces_of
from brig.run._supervisor_program import SUPERVISOR_SOURCE
from brig.run.jail import _process_control
from brig.run.runtime import (
    ProcessNamespaces,
    Reservation,
    reservation_refusal,
    reserved_socket,
    socket_endpoint,
)
from brig.run.teardown import term_rung

pytestmark = pytest.mark.unit

_CHAN = "/run/brig/jail0/chan"
_TOKEN = "0123456789abcdef"


# ---------------------------------------------------------------------------------------------
# The host path of a socket.
# ---------------------------------------------------------------------------------------------


def test_a_socket_is_at_the_path_it_binds_unless_the_process_has_a_directory_of_its_own() -> None:
    bound = reserved_socket(_CHAN, _TOKEN)
    assert bound == f"{_CHAN}/{_TOKEN}.sock"
    assert socket_endpoint(bound, namespaces=False) == bound
    # the process sees one directory over the channel directory, named for its socket's token
    assert socket_endpoint(bound, namespaces=True) == f"{_CHAN}/{_TOKEN}/{_TOKEN}.sock"


def test_a_reservation_is_refused_for_the_endpoint_the_jail_would_not_hand_out() -> None:
    bound = reserved_socket(_CHAN, _TOKEN)
    private = socket_endpoint(bound, namespaces=True)
    ok = Reservation(channel="ctl", bound_path=bound, endpoint=private)
    assert reservation_refusal(ok, chan=_CHAN, endpoint=private, taken=frozenset()) is None
    # the other mode's endpoint is not this jail's
    same = Reservation(channel="ctl", bound_path=bound, endpoint=bound)
    reason = reservation_refusal(same, chan=_CHAN, endpoint=private, taken=frozenset())
    assert reason is not None and "is not the host path the runtime dials" in reason
    assert reservation_refusal(same, chan=_CHAN, endpoint=bound, taken=frozenset()) is None


# ---------------------------------------------------------------------------------------------
# The first rung of the ladder, for a leader that is a pid namespace's init.
# ---------------------------------------------------------------------------------------------

_TERM = 1 << (signal.SIGTERM - 1)


def _status(*, nspid: str, caught: int = 0, ignored: int = 0) -> str:
    return (
        "Name:\tpython3\nState:\tS (sleeping)\n"
        f"NSpid:\t{nspid}\nSigIgn:\t{ignored:016x}\nSigCgt:\t{caught:016x}\n"
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        # an ordinary process, handling nothing: SIGTERM is delivered and ends it
        (_status(nspid="1234"), signal.SIGTERM),
        # PID 1 of a namespace of its own with no handler: the kernel would drop SIGTERM
        (_status(nspid="1234\t7\t1"), signal.SIGKILL),
        (_status(nspid="1234\t1"), signal.SIGKILL),
        # ... but it handles it, or ignores it: SIGTERM, and its grace
        (_status(nspid="1234\t7\t1", caught=_TERM), signal.SIGTERM),
        (_status(nspid="1234\t7\t1", ignored=_TERM), signal.SIGTERM),
        # another signal handled is no help to SIGTERM
        (_status(nspid="1234\t7\t1", caught=1 << (signal.SIGINT - 1)), signal.SIGKILL),
        # a process that is not its namespace's init, however deep
        (_status(nspid="1234\t7\t5"), signal.SIGTERM),
        # a status brig can't read is an ordinary process
        ("", signal.SIGTERM),
        ("NSpid:\t1234\t7\t1\n", signal.SIGTERM),
        (_status(nspid="1234\t7\t1").replace("SigCgt:\t0", "SigCgt:\tzz"), signal.SIGTERM),
    ],
)
def test_the_first_rung_is_sigkill_only_for_an_init_that_would_drop_sigterm(
    status: str, expected: signal.Signals
) -> None:
    assert term_rung(status) == expected


# ---------------------------------------------------------------------------------------------
# The supervisor's own copy of the rule agrees with the host's.
# ---------------------------------------------------------------------------------------------


def _supervisor_signal_for_init(status: str) -> Any:
    """The program's `signal_for_init`, compiled out of its text, reading `status` as the
    process's `/proc/<pid>/status`: the function and the constant it uses, nothing else of the
    program runs."""
    tree = ast.parse(SUPERVISOR_SOURCE)
    wanted = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "signal_for_init")
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "UNTERMINATING" for t in node.targets)
        )
    ]
    assert len(wanted) == 2
    namespace: dict[str, Any] = {"signal": signal}

    class _Status:
        def __enter__(self) -> _Status:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return status.encode()

    namespace["open"] = lambda path, mode="r": _Status()
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "<supervisor>", "exec"), namespace)
    return namespace["signal_for_init"]


@pytest.mark.parametrize("caught", [0, _TERM])
@pytest.mark.parametrize("ignored", [0, _TERM])
def test_the_supervisor_and_the_host_send_an_init_the_same_sigterm(
    caught: int, ignored: int
) -> None:
    status = _status(nspid="1234\t7\t1", caught=caught, ignored=ignored)
    assert _supervisor_signal_for_init(status)(7, signal.SIGTERM) == term_rung(status)


@pytest.mark.parametrize(
    ("number", "caught", "ignored", "sent"),
    [
        (signal.SIGTERM, 0, 0, signal.SIGKILL),  # would end any other process: ends it
        (signal.SIGINT, 0, 0, signal.SIGKILL),
        (signal.SIGUSR1, 0, 0, signal.SIGKILL),
        (signal.SIGHUP, 0, 0, signal.SIGKILL),
        (signal.SIGRTMIN, 0, 0, signal.SIGKILL),  # a realtime signal terminates by default too
        (signal.SIGINT, 1 << (signal.SIGINT - 1), 0, signal.SIGINT),  # handled: the handler runs
        (signal.SIGTERM, 0, _TERM, signal.SIGTERM),  # ignored: ignored, as for any process
        (signal.SIGKILL, 0, 0, signal.SIGKILL),
        (signal.SIGSTOP, 0, 0, signal.SIGSTOP),
        (signal.SIGCONT, 0, 0, signal.SIGCONT),  # none of these end a process by default
        (signal.SIGCHLD, 0, 0, signal.SIGCHLD),
        (signal.SIGURG, 0, 0, signal.SIGURG),
        (signal.SIGWINCH, 0, 0, signal.SIGWINCH),
        (signal.SIGTSTP, 0, 0, signal.SIGTSTP),
    ],
)
def test_a_signal_to_an_init_is_what_it_would_be_to_any_process(
    number: int, caught: int, ignored: int, sent: int
) -> None:
    status = _status(nspid="1234\t7\t1", caught=caught, ignored=ignored)
    assert _supervisor_signal_for_init(status)(7, number) == sent


# ---------------------------------------------------------------------------------------------
# The grade of a process's control.
# ---------------------------------------------------------------------------------------------


def test_a_process_in_namespaces_is_best_effort_and_names_what_the_battery_proved_and_the_gap() -> (
    None
):
    """decision-201: the control battery proves a stop ends a process in namespaces of its own, a
    `setsid()` child included, and that a stop the supervisor does not answer ends the jail: the
    gap, named, which is what holds the grade at `best_effort`."""
    graded = _process_control(namespaces=True, supervised=True, reason="")
    assert graded.grade is Grade.BEST_EFFORT
    assert "ends the process's pid namespace" in graded.detail and "setsid()" in graded.detail
    assert "tests/e2e/test_control_battery.py" in graded.detail
    assert "ends the whole jail" in graded.detail  # the gap `best_effort` requires named


def test_a_process_without_them_is_cooperative_and_says_what_a_stop_leaves_and_why() -> None:
    graded = _process_control(
        namespaces=False, supervised=True, reason="unshare(...): No space left on device"
    )
    assert graded.grade is Grade.COOPERATIVE
    assert (
        "signals the process's group" in graded.detail
        and "only the jail's destroy()" in graded.detail
    )
    assert "because unshare(...): No space left on device" in graded.detail
    # a jail rehydrated elsewhere doesn't know why; it doesn't claim to
    unknown = _process_control(namespaces=False, supervised=True, reason=None)
    assert "because" not in unknown.detail and "signals the process's group" in unknown.detail
    # a runtime with no supervisor gives no process a namespace, and says so
    plain = _process_control(namespaces=False, supervised=False, reason=None)
    assert "gives a process no namespace" in plain.detail


def test_only_namespaces_raise_a_process_above_cooperative_and_every_other_case_stays_there() -> (
    None
):
    """The battery proves the process scope only where the namespaces are: the fallback's own
    cell has a `setsid()` child outliving the stop (observed), and a jail with no supervisor was
    not run against. Neither is graded above `cooperative`, for any reason the supervisor gave."""
    held = _process_control(namespaces=True, supervised=True, reason="")
    assert held.grade is Grade.BEST_EFFORT
    for reason in (None, "", "uid 0", "unshare(...): No space left on device"):
        not_held = _process_control(namespaces=False, supervised=True, reason=reason)
        assert not_held.grade is Grade.COOPERATIVE, reason
        assert not_held != held
        assert "outlives stop (observed" in not_held.detail
    plain = _process_control(namespaces=False, supervised=False, reason=None)
    assert plain.grade is Grade.COOPERATIVE
    assert "unproven, not failed" in plain.detail


# ---------------------------------------------------------------------------------------------
# What a supervisor's hello says of the namespaces.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hello", "expected"),
    [
        ({"namespaces": {"held": True, "reason": ""}}, ProcessNamespaces(True, "")),
        (
            {"namespaces": {"held": False, "reason": "unshare: No space left on device"}},
            ProcessNamespaces(False, "unshare: No space left on device"),
        ),
        # a hello that says nothing, or says it badly, claims nothing: no namespaces, and why
        ({}, ProcessNamespaces(False, "the supervisor did not say whether it could")),
        (
            {"namespaces": "yes"},
            ProcessNamespaces(False, "the supervisor did not say whether it could"),
        ),
        (
            {"namespaces": {"held": 1}},
            ProcessNamespaces(False, "the supervisor did not say whether it could"),
        ),
        ({"namespaces": {"held": True, "reason": 5}}, ProcessNamespaces(True, "")),
    ],
)
def test_a_hello_claims_namespaces_only_when_it_says_so_in_so_many_words(
    hello: dict[str, object], expected: ProcessNamespaces
) -> None:
    assert namespaces_of(hello) == expected
