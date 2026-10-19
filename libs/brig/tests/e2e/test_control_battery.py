"""The control battery against a real supervised bwrap jail (decision-201, TASK-0079.08).

decision-0001 and law 10: no control grade above `cooperative` without a battery that plants the
violation, driven from the host. `tests/control_battery.py` plants a `setsid()` child, a process
that ignores `SIGTERM` and a `SIGSTOP`ped supervisor, each beside a plain child the same ending
ends, ends them with `Process.stop` and with `Jail.destroy`, and records what the host's own
`/bin/ps` and `/proc` saw. Here it runs once per jail type:

- `namespaces`: every process has namespaces of its own (an unprivileged user, a host that lets it).
  A stop ends the process's pid namespace, so nothing outlives it; a stop whose supervisor is
  stopped takes its deadline and ends the jail, a bystander with it.
- `fallback`: the processes share the jail's namespaces (a jail run as uid 0, or the block of
  decision-195 planted). A stop signals the group, so the `setsid()` child outlives it, which is the
  cell that holds the process scope at `cooperative`; `destroy` ends it.

The claim is held to the proof in the same test: the grade `Process.control` gives and the grade the
report's `control` axis gives are each the grade the battery proves at that scope, no higher (a claim
nothing planted) and no lower. And the proof is not vacuous: every cell was planted as meant, its
control ended, and the survivor that outlives a stop in `fallback` is shown to be a real one in the
`namespaces` run by the same plant under a stop without namespaces.

Seatbelt is not here. The battery needs a macOS host, which this was not written on: its grades do
not rise, and the report says it is unproven, not failed (`tests/unit/test_stack_runtime.py`).
"""

from collections.abc import Callable, Iterator

import pytest

from brig.core import Axis, Grade
from brig.core.runtime import Scope
from brig.run import Jail, KillOutcome
from brig.run import _supervised as supervised
from tests import control_battery as battery
from tests.conftest import NewJailDir
from tests.control_battery import Cell, Survivor
from tests.supervised_jail import (
    create_jail,
    needs_a_supervised_jail,
    needs_namespaces,
    sh,
)

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _needs_a_jail() -> None:
    needs_a_supervised_jail()


@pytest.fixture(params=["namespaces", "fallback"])
def mode(request: pytest.FixtureRequest) -> str:
    if request.param == "namespaces":
        needs_namespaces()
    return str(request.param)


Make = Callable[..., Jail]


@pytest.fixture
def make(mode: str, new_jail_dir: NewJailDir) -> Iterator[Make]:
    """`make()` is a fresh supervised jail of the mode under test; `make(namespaces=False)` one
    with the block of decision-195 planted, whatever the mode. Every jail made is destroyed, and
    must end, when the test is done; the directories are removed after, by `new_jail_dir`."""
    made: list[Jail] = []

    def build(*, namespaces: bool | None = None) -> Jail:
        jail_dir = new_jail_dir()
        jail = create_jail(
            jail_dir,
            namespaces=(mode == "namespaces") if namespaces is None else namespaces,
            jail_id="battery",
        )
        made.append(jail)
        return jail

    yield build
    for jail in made:
        report = jail.destroy()
        assert not [item for item in report.items if item.outcome is KillOutcome.FAILED], report


def _what_the_host_saw(cells: tuple[Cell, ...]) -> dict[tuple[Scope, Survivor], tuple[bool, ...]]:
    return {
        (cell.scope, cell.survivor): (
            cell.planted,
            cell.survivor_gone,
            cell.control_gone,
            cell.bystander_gone,
        )
        for cell in cells
    }


def _expected(mode: str) -> dict[tuple[Scope, Survivor], tuple[bool, ...]]:
    """Planted, the survivor gone, the control gone, a bystander gone, for each cell. Every
    survivor is planted and its control ends. Every survivor ends but one: a group-shaped stop, the
    fallback's, leaves a child in a session of its own. A stop through a stopped supervisor ends the
    jail, so a bystander goes with it; no other ending reaches further than it was asked."""
    rows: dict[tuple[Scope, Survivor], tuple[bool, ...]] = {}
    for scope in (Scope.PROCESS, Scope.JAIL):
        for survivor in Survivor:
            outlives = (scope, survivor, mode) == (Scope.PROCESS, Survivor.SETSID_CHILD, "fallback")
            collateral = (scope, survivor) == (Scope.PROCESS, Survivor.STOPPED_SUPERVISOR)
            rows[(scope, survivor)] = (True, not outlives, True, collateral)
    return rows


def test_the_battery_plants_each_survivor_and_the_grades_claimed_are_the_grades_proven(
    mode: str, make: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stop the supervisor does not answer ends the jail at its deadline, twice the grace and
    # this slack: 5 s here, not 14. The deadline's value is not what is proved.
    monkeypatch.setattr(supervised, "SLACK_S", 1.0)

    cells = battery.run(make)

    assert _what_the_host_saw(cells) == _expected(mode)

    process_scope = battery.proven(cells, Scope.PROCESS)
    jail_scope = battery.proven(cells, Scope.JAIL)
    assert process_scope is (Grade.BEST_EFFORT if mode == "namespaces" else Grade.COOPERATIVE)
    assert jail_scope is Grade.ENFORCED

    # The claims, read from a process and a jail of the same type: no higher than the proof, and
    # no lower, so that a grade is raised by a cell and not by a sentence.
    jail = make()
    process = jail.start(sh("exit 0"))
    assert process.wait(10) == 0
    assert process.namespaces is (mode == "namespaces")
    assert process.control.grade is process_scope, process.control
    assert jail.report.axes[Axis.CONTROL].grade is jail_scope, jail.report.axes[Axis.CONTROL]

    # The control for the `namespaces` run: the same `setsid()` plant, stopped in a jail without
    # namespaces (the block planted), is left running by the stop. So a child found gone after a
    # stop in a jail with them is gone because of them, and not because it never was a survivor.
    # (In `fallback` that jail is the one above.)
    if mode == "namespaces":
        without = battery.stop_a_setsid_child(lambda: make(namespaces=False))
        assert without.planted and without.control_gone and not without.survivor_gone, without
