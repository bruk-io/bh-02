"""The control battery against a real container jail, at the jail scope (decision-202).

decision-0001 and law 10: no control grade above `cooperative` ships without a battery that plants
the violation, driven from the host, with a positive control. `tests/control_battery.py` is that
battery for a supervised bwrap jail (decision-201); this is its counterpart for a container, whose
jail scope is `Jail.destroy`: `docker rm -f`, then `docker inspect` finding nothing.

Nothing is started in a container through brig yet (SPEC.md §8), so the survivors are planted by
`docker exec -d`, the test's own door, and the host's own `/bin/ps` and `/proc` are what look for them
-- never brig, and never the daemon: an observation made with the code under test is not an
observation. The three survivors are the battery's own (`control_battery.Survivor`): a `setsid()`
child, a process that ignores `SIGTERM`, and an init the host `SIGSTOP`s (the container's PID 1, the
`docker-init` that `--init` makes, in the place of bwrap's supervisor). Beside each is a plain child
the same `destroy` ends, so a survivor found gone is not one nobody could see, and each is checked to
be planted as meant before it counts.

What the host saw becomes a grade by the battery's own pure rule (`control_battery.proven`), and the
report's `control` axis is held to it in the same test: no higher (a claim nothing planted) and no
lower. The process scope has no cell: there is no `Process` in a container yet, so nothing is graded
there (TASK-0079.10).
"""

from __future__ import annotations

import os
import signal
from collections.abc import Callable

import pytest

from brig.core import Axis, Grade
from brig.core.runtime import Scope
from brig.run import Jail, KillOutcome
from tests.control_battery import Cell, Survivor, proven
from tests.oci_jail import container_of, docker, inspect
from tests.supervised_jail import process_state, running_with, unique_sleep, until

pytestmark = pytest.mark.integration

Make = Callable[..., Jail]

_PLANTED_WITHIN_S = 15.0
_ENDS_WITHIN_S = 4.0
_SIGTERM_BIT = 1 << (signal.SIGTERM - 1)


def _plant(container: str, script: str, *markers: str) -> None:
    """Start `script` detached inside the container, by the test's own door, with `markers` as its
    positional parameters, so that the shell's own command line never holds `sleep <marker>` and
    the host finds only the `sleep` processes themselves."""
    done = docker("exec", "-d", container, "sh", "-c", script, "sh", *markers)
    assert done.returncode == 0, done.stderr


def _running(marker: str) -> bool:
    return bool(running_with(f"sleep {marker}"))


def _planted(*markers: str) -> bool:
    return until(lambda: all(_running(marker) for marker in markers), _PLANTED_WITHIN_S)


def _gone(marker: str) -> bool:
    return until(lambda: not _running(marker), _ENDS_WITHIN_S)


def _dead(pid: int) -> bool:
    return until(lambda: process_state(pid) in ("gone", "Z"), _ENDS_WITHIN_S)


def _pid_of(marker: str) -> int:
    (pid,) = running_with(f"sleep {marker}")
    return pid


def _ignores_sigterm(pid: int) -> bool:
    with open(f"/proc/{pid}/status", encoding="utf-8") as status:
        for line in status:
            if line.startswith("SigIgn:"):
                return bool(int(line.split()[1], 16) & _SIGTERM_BIT)
    return False


def _in_a_session_of_its_own(pid: int) -> bool:
    return os.getsid(pid) == pid


def _init_pid(container: str) -> int:
    entry = inspect(container)
    assert entry is not None
    return int(entry["State"]["Pid"])


def destroy_a_setsid_child(make: Make) -> Cell:
    jail = make()
    container = container_of(jail)
    plain, escaping = unique_sleep()[0], unique_sleep()[0]
    _plant(container, 'sleep "$1" & setsid sleep "$2" & wait', plain, escaping)
    planted = (
        _planted(plain, escaping)
        and _in_a_session_of_its_own(_pid_of(escaping))
        and not _in_a_session_of_its_own(_pid_of(plain))
    )
    jail.destroy()
    return Cell(
        Scope.JAIL,
        Survivor.SETSID_CHILD,
        planted=planted,
        survivor_gone=_gone(escaping),
        control_gone=_gone(plain),
        bystander_gone=False,
    )


def destroy_a_process_that_ignores_sigterm(make: Make) -> Cell:
    jail = make()
    container = container_of(jail)
    plain, ignored = unique_sleep()[0], unique_sleep()[0]
    _plant(container, 'sleep "$1" & trap "" TERM; exec sleep "$2"', plain, ignored)
    planted = _planted(plain, ignored) and until(
        lambda: _ignores_sigterm(_pid_of(ignored)), _PLANTED_WITHIN_S
    )
    planted = planted and not _ignores_sigterm(_pid_of(plain))
    ignorer = _pid_of(ignored)
    jail.destroy()
    return Cell(
        Scope.JAIL,
        Survivor.IGNORES_SIGTERM,
        planted=planted,
        survivor_gone=_dead(ignorer),
        control_gone=_gone(plain),
        bystander_gone=False,
    )


def destroy_a_container_whose_init_is_stopped(make: Make) -> Cell:
    jail = make()
    container = container_of(jail)
    plain, escaping = unique_sleep()[0], unique_sleep()[0]
    _plant(container, 'sleep "$1" & setsid sleep "$2" & wait', plain, escaping)
    planted = _planted(plain, escaping) and _in_a_session_of_its_own(_pid_of(escaping))
    init = _init_pid(container)
    os.kill(init, signal.SIGSTOP)
    planted = planted and until(lambda: process_state(init) == "T")
    jail.destroy()
    return Cell(
        Scope.JAIL,
        Survivor.STOPPED_SUPERVISOR,
        planted=planted,
        survivor_gone=_dead(init) and _gone(escaping),
        control_gone=_gone(plain),
        bystander_gone=False,
    )


_CELLS = (
    destroy_a_setsid_child,
    destroy_a_process_that_ignores_sigterm,
    destroy_a_container_whose_init_is_stopped,
)


def test_the_battery_plants_each_survivor_and_the_grade_claimed_is_the_grade_proven(
    make_oci_jail: Make,
) -> None:
    cells = tuple(cell(make_oci_jail) for cell in _CELLS)

    # Every survivor was planted as meant and its control ended: nothing here is vacuous.
    assert [(cell.survivor, cell.planted, cell.control_gone) for cell in cells] == [
        (Survivor.SETSID_CHILD, True, True),
        (Survivor.IGNORES_SIGTERM, True, True),
        (Survivor.STOPPED_SUPERVISOR, True, True),
    ]
    # What the host saw: `destroy` ended every survivor, a stopped init included.
    assert [cell.survivor_gone for cell in cells] == [True, True, True]
    proof = proven(cells, Scope.JAIL)
    assert proof is Grade.ENFORCED

    # The claim, read from a jail of the same type: no higher than the proof, and no lower, so that
    # a grade is raised by a cell and not by a sentence.
    jail = make_oci_jail()
    assert jail.report.axes[Axis.CONTROL].grade is proof, jail.report.axes[Axis.CONTROL]


def test_the_battery_can_tell_a_survivor_from_nothing_the_control_for_the_observation(
    make_oci_jail: Make,
) -> None:
    """Before the ending, the host sees the survivors and their controls running; after a container
    is stopped with `SIGSTOP` and not ended they are still there. So "gone" after `destroy` is
    `destroy`'s doing and not a plant that never took, or an observation that sees nothing."""
    jail = make_oci_jail()
    container = container_of(jail)
    plain, escaping = unique_sleep()[0], unique_sleep()[0]
    _plant(container, 'sleep "$1" & setsid sleep "$2" & wait', plain, escaping)
    assert _planted(plain, escaping)
    init = _init_pid(container)
    os.kill(init, signal.SIGSTOP)
    try:
        assert until(lambda: process_state(init) == "T")
        assert _running(plain) and _running(escaping)  # stopped init, nobody ended anything
    finally:
        os.kill(init, signal.SIGCONT)
    report = jail.destroy()
    assert {i.kind: i.outcome for i in report.items} == {"container": KillOutcome.ENDED}
    assert _gone(plain) and _gone(escaping)
