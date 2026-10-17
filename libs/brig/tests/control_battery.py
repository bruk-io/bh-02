"""The control battery (decision-201, TASK-0079.08): survivors planted from the host.

decision-0001 and law 10: no control grade above `cooperative` ships without a battery that plants
the violation, driven from the host, with a positive control. Control is graded at two scopes
(SPEC.md section 4): the jail's, which `Jail.destroy` delivers and the report's `control` axis
grades, and one process's, which `Process.stop` delivers and `Process.control` grades. This module
plants, in a real supervised bwrap jail, what a hostile or wedged program does to outlive an
ending, ends it from the host, and records what the host saw, one `Cell` per survivor and ending.

Three survivors:

- a `setsid()` child, which leaves its process group and so a stop that signals the group;
- a process that ignores `SIGTERM`, which an ending's first rung does not end;
- a supervisor the host `SIGSTOP`s, which answers no request and reads no end-of-file.

Beside each is a **positive control** (WORKFLOW.md: a control belongs in the same test as the
claim): a plain child the same ending ends, planted and observed the same way, so that a survivor
found gone is not a survivor nobody could see, and an ending that ends nothing is not a pass. At
the process scope a **bystander** is planted too, a process the stop was not asked about, and a
bystander found gone is the stop reaching further than the process: a stop whose supervisor does
not answer ends the jail at its deadline, and the cell says so.

Nothing here asks brig whether a thing ended. An observation made with the code under test is not an
observation (WORKFLOW.md, evidence rules), so every "running" and "gone" is `/bin/ps` and `/proc`,
read by the host (`tests.supervised_jail.running_with`, `process_state`).

`proven` is the other half: the highest grade a battery's cells prove for a scope, a pure function
of what the host saw. A claim above it is a claim nothing planted; the e2e test holds the grades
`Jail.report` and `Process.control` give to it, per scope and per jail type.
"""

import os
import signal
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from brig.core import Grade
from brig.core.runtime import Scope
from brig.run import Jail, SupervisorUnresponsive
from tests.supervised_jail import (
    instance_group,
    process_state,
    python,
    running_with,
    supervisor_host_pid,
    unique_sleep,
    until,
)

#: Makes a fresh supervised jail of the jail type under test. The caller owns its end.
Rig = Callable[[], Jail]

#: How long the host waits, after an ending has returned, for what it ended to leave the process
#: table (the kernel removes a killed process a moment later). It is also how long a survivor is
#: looked for before it is called one, so that neither is a timing accident.
_ENDS_WITHIN_S = 4.0
#: How long the host waits for a plant to show in the process table.
_PLANTED_WITHIN_S = 15.0

_SIGTERM_BIT = 1 << (signal.SIGTERM - 1)


class Survivor(Enum):
    """What the battery plants."""

    SETSID_CHILD = "a setsid() child"
    IGNORES_SIGTERM = "a process that ignores SIGTERM"
    STOPPED_SUPERVISOR = "a stopped supervisor"


@dataclass(frozen=True, slots=True)
class Cell:
    """What the host saw of one survivor and one ending.

    `scope` names the ending: `PROCESS` is `Process.stop`, `JAIL` is `Jail.destroy`. `planted`: the
    host saw the survivor and its control running, and the survivor as it is meant to be (in a
    session of its own, ignoring `SIGTERM` as `/proc` says, `SIGSTOP`ped). `survivor_gone` and
    `control_gone`: the host found each gone after the ending. `bystander_gone`: a process the
    ending was not asked about is gone too (`PROCESS` only: a destroy asks about everything)."""

    scope: Scope
    survivor: Survivor
    planted: bool
    survivor_gone: bool
    control_gone: bool
    bystander_gone: bool


def proven(cells: Iterable[Cell], scope: Scope) -> Grade:
    """The highest grade `cells` prove for `scope` (SPEC.md section 4, decision-201). Pure.

    Every survivor must have been planted at the scope, beside a control the same ending ended:
    otherwise nothing was proved and the answer is `UNENFORCED`. Then a survivor that outlived the
    ending is a process that opted out of a control that only reached a compliant one:
    `COOPERATIVE`. Then an ending that also ended a process it was not asked about reached the
    survivor and more, a gap to name: `BEST_EFFORT`. Otherwise `ENFORCED`."""
    mine = tuple(cell for cell in cells if cell.scope is scope)
    if {cell.survivor for cell in mine} != set(Survivor):
        return Grade.UNENFORCED
    if not all(cell.planted and cell.control_gone for cell in mine):
        return Grade.UNENFORCED
    if not all(cell.survivor_gone for cell in mine):
        return Grade.COOPERATIVE
    if any(cell.bystander_gone for cell in mine):
        return Grade.BEST_EFFORT
    return Grade.ENFORCED


# ---------------------------------------------------------------------------------------------
# What is planted, and how the host sees it.
# ---------------------------------------------------------------------------------------------

#: A program with two children: a plain one in its process group, and one that leaves it for a
#: session of its own. Both are a `sleep` whose duration is a marker no other process has.
_PLANT_SETSID = r"""
import os, sys, time
plain, escaping = sys.argv[1:3]
if os.fork() == 0:
    os.execv('/bin/sleep', ['sleep', plain])
if os.fork() == 0:
    os.setsid()
    os.execv('/bin/sleep', ['sleep', escaping])
print('planted', flush=True)
time.sleep(600)
"""

#: A program that ignores `SIGTERM` and says nothing else.
_PLANT_IGNORER = r"""
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print('planted', flush=True)
while True:
    time.sleep(1)
"""


def _running(marker: str) -> bool:
    """Whether the host's process table holds a live `sleep` with this marker as its duration."""
    return bool(running_with(f"sleep {marker}"))


def _planted(*markers: str) -> bool:
    return until(lambda: all(_running(marker) for marker in markers), _PLANTED_WITHIN_S)


def _gone(marker: str) -> bool:
    return until(lambda: not _running(marker), _ENDS_WITHIN_S)


def _dead(pid: int) -> bool:
    """Whether the process is gone or a zombie (running_with does not count one either)."""
    return until(lambda: process_state(pid) in ("gone", "Z"), _ENDS_WITHIN_S)


def _ignores_sigterm(pid: int) -> bool:
    """Whether `/proc` says the process ignores `SIGTERM` (`SigIgn`), read by the host."""
    with open(f"/proc/{pid}/status", encoding="utf-8") as status:
        for line in status:
            if line.startswith("SigIgn:"):
                return bool(int(line.split()[1], 16) & _SIGTERM_BIT)
    return False


def _in_a_session_of_its_own(marker: str, parent_pid: int) -> bool:
    (child,) = running_with(f"sleep {marker}")
    return os.getsid(child) != os.getsid(parent_pid)


def _stop_the_supervisor(jail: Jail) -> int:
    """`SIGSTOP` the jail's PID 1 from the host and return its host pid once `/proc` says `T`;
    `0` when it never does."""
    pid = supervisor_host_pid(instance_group(jail))
    os.kill(pid, signal.SIGSTOP)
    return pid if until(lambda: process_state(pid) == "T") else 0


# ---------------------------------------------------------------------------------------------
# The cells: `Process.stop`, then `Jail.destroy`.
# ---------------------------------------------------------------------------------------------


def stop_a_setsid_child(rig: Rig) -> Cell:
    jail = rig()
    plain, escaping, aside = (unique_sleep() for _ in range(3))
    parent = jail.start(python(_PLANT_SETSID, plain[0], escaping[0]))
    jail.start(aside[1])
    planted = _planted(plain[0], escaping[0], aside[0]) and _in_a_session_of_its_own(
        escaping[0], parent.pid
    )
    parent.stop()
    return Cell(
        Scope.PROCESS,
        Survivor.SETSID_CHILD,
        planted=planted,
        survivor_gone=_gone(escaping[0]),
        control_gone=_gone(plain[0]),
        bystander_gone=not _running(aside[0]),
    )


def stop_a_process_that_ignores_sigterm(rig: Rig) -> Cell:
    jail = rig()
    plain, aside = unique_sleep(), unique_sleep()
    ignorer = jail.start(python(_PLANT_IGNORER))
    control = jail.start(plain[1])
    jail.start(aside[1])
    planted = (
        _planted(plain[0], aside[0])
        and until(lambda: _ignores_sigterm(ignorer.pid), _PLANTED_WITHIN_S)
        and not _ignores_sigterm(control.pid)
    )
    control.stop()
    ignorer.stop()
    return Cell(
        Scope.PROCESS,
        Survivor.IGNORES_SIGTERM,
        planted=planted,
        survivor_gone=_dead(ignorer.pid),
        control_gone=_gone(plain[0]),
        bystander_gone=not _running(aside[0]),
    )


def stop_through_a_stopped_supervisor(rig: Rig) -> Cell:
    """The control is a stop the supervisor answers, of a plain process, before it is stopped. The
    stop that follows is not answered: it ends the jail at its deadline (`SupervisorUnresponsive`,
    which the caller shortens with `brig.run._supervised.SLACK_S`), the stopped supervisor, the
    process and the bystander with it."""
    jail = rig()
    control, victim, aside = (unique_sleep() for _ in range(3))
    answered = jail.start(control[1])
    process = jail.start(victim[1])
    jail.start(aside[1])
    planted = _planted(control[0], victim[0], aside[0])
    answered.stop()
    control_gone = _gone(control[0])
    supervisor = _stop_the_supervisor(jail)
    planted = planted and supervisor != 0
    try:
        process.stop()
        planted = False  # a stop that was answered: the supervisor was not wedged
    except SupervisorUnresponsive:
        pass
    return Cell(
        Scope.PROCESS,
        Survivor.STOPPED_SUPERVISOR,
        planted=planted,
        survivor_gone=supervisor != 0 and _dead(supervisor) and _gone(victim[0]),
        control_gone=control_gone,
        bystander_gone=not _running(aside[0]),
    )


def destroy_a_setsid_child(rig: Rig) -> Cell:
    jail = rig()
    plain, escaping = unique_sleep(), unique_sleep()
    parent = jail.start(python(_PLANT_SETSID, plain[0], escaping[0]))
    planted = _planted(plain[0], escaping[0]) and _in_a_session_of_its_own(escaping[0], parent.pid)
    jail.destroy()
    return Cell(
        Scope.JAIL,
        Survivor.SETSID_CHILD,
        planted=planted,
        survivor_gone=_gone(escaping[0]),
        control_gone=_gone(plain[0]),
        bystander_gone=False,
    )


def destroy_a_process_that_ignores_sigterm(rig: Rig) -> Cell:
    jail = rig()
    plain = unique_sleep()
    ignorer = jail.start(python(_PLANT_IGNORER))
    control = jail.start(plain[1])
    planted = (
        _planted(plain[0])
        and until(lambda: _ignores_sigterm(ignorer.pid), _PLANTED_WITHIN_S)
        and not _ignores_sigterm(control.pid)
    )
    jail.destroy()
    return Cell(
        Scope.JAIL,
        Survivor.IGNORES_SIGTERM,
        planted=planted,
        survivor_gone=_dead(ignorer.pid),
        control_gone=_gone(plain[0]),
        bystander_gone=False,
    )


def destroy_a_jail_whose_supervisor_is_stopped(rig: Rig) -> Cell:
    jail = rig()
    plain, escaping = unique_sleep(), unique_sleep()
    parent = jail.start(python(_PLANT_SETSID, plain[0], escaping[0]))
    planted = _planted(plain[0], escaping[0]) and _in_a_session_of_its_own(escaping[0], parent.pid)
    supervisor = _stop_the_supervisor(jail)
    planted = planted and supervisor != 0
    jail.destroy()
    return Cell(
        Scope.JAIL,
        Survivor.STOPPED_SUPERVISOR,
        planted=planted,
        survivor_gone=supervisor != 0 and _dead(supervisor) and _gone(escaping[0]),
        control_gone=_gone(plain[0]),
        bystander_gone=False,
    )


#: Every cell of the battery, in the order they are run.
CELLS: tuple[Callable[[Rig], Cell], ...] = (
    stop_a_setsid_child,
    stop_a_process_that_ignores_sigterm,
    stop_through_a_stopped_supervisor,
    destroy_a_setsid_child,
    destroy_a_process_that_ignores_sigterm,
    destroy_a_jail_whose_supervisor_is_stopped,
)


def run(rig: Rig) -> tuple[Cell, ...]:
    """Every cell, each in a jail of its own made by `rig`."""
    return tuple(cell(rig) for cell in CELLS)
