"""What the control battery's cells prove, as a grade (decision-201, TASK-0079.08).

`tests/control_battery.py` plants survivors in a real jail and records what the host saw; `proven` is
the pure rule from those cells to the highest grade they prove at a scope, and the grades `Jail.report`
and `Process.control` are held to it by `tests/e2e/test_control_battery.py`. A rule that could not say
no would let any claim through, so each way a claim fails to be proved is shown here: a survivor that
outlives its ending, an ending that reaches further than it was asked, a survivor never planted, and
a control the ending did not end (an ending that ends nothing). Pure: cells made by hand.
"""

import dataclasses

import pytest

from brig.core import Grade
from brig.core.runtime import Scope
from tests.control_battery import Cell, Survivor, proven

pytestmark = pytest.mark.unit


def _cell(scope: Scope, survivor: Survivor, **seen: bool) -> Cell:
    """A cell in which everything went as the battery means it to: planted, the survivor and its
    control gone, nothing else gone. `seen` overrides what the host saw."""
    return Cell(
        scope,
        survivor,
        **{
            "planted": True,
            "survivor_gone": True,
            "control_gone": True,
            "bystander_gone": False,
            **seen,
        },
    )


def _battery(scope: Scope, **seen: dict[str, bool]) -> list[Cell]:
    """One cell per survivor at `scope`; `seen` maps a survivor's name to what to override."""
    return [_cell(scope, survivor, **seen.get(survivor.name, {})) for survivor in Survivor]


def test_every_survivor_planted_and_ended_with_its_control_proves_enforced() -> None:
    for scope in Scope:
        assert proven(_battery(scope), scope) is Grade.ENFORCED


def test_a_survivor_that_outlives_the_ending_proves_cooperative_and_no_more() -> None:
    """A control that reached the plain child and not the one that opted out. The fallback's
    `setsid()` child outliving a stop is this cell."""
    for survivor in Survivor:
        cells = _battery(Scope.PROCESS, **{survivor.name: {"survivor_gone": False}})
        assert proven(cells, Scope.PROCESS) is Grade.COOPERATIVE, survivor


def test_an_ending_that_also_ended_a_bystander_proves_best_effort() -> None:
    """The survivor ended, and so did a process the ending was not asked about: the stop whose
    supervisor did not answer, which ends the jail at its deadline."""
    cells = _battery(Scope.PROCESS, STOPPED_SUPERVISOR={"bystander_gone": True})
    assert proven(cells, Scope.PROCESS) is Grade.BEST_EFFORT


def test_a_survivor_that_outlives_is_worse_than_a_bystander_that_went() -> None:
    cells = _battery(
        Scope.PROCESS,
        SETSID_CHILD={"survivor_gone": False},
        STOPPED_SUPERVISOR={"bystander_gone": True},
    )
    assert proven(cells, Scope.PROCESS) is Grade.COOPERATIVE


@pytest.mark.parametrize("survivor", list(Survivor), ids=lambda survivor: survivor.name)
def test_a_cell_that_was_not_planted_as_meant_proves_nothing(survivor: Survivor) -> None:
    """Gone is no evidence for a survivor that was never a survivor (a `setsid()` child in no
    session of its own, a process that did not ignore `SIGTERM`, a supervisor never stopped)."""
    cells = _battery(Scope.JAIL, **{survivor.name: {"planted": False}})
    assert proven(cells, Scope.JAIL) is Grade.UNENFORCED


@pytest.mark.parametrize("survivor", list(Survivor), ids=lambda survivor: survivor.name)
def test_an_ending_that_did_not_end_its_control_proves_nothing(survivor: Survivor) -> None:
    """The positive control: if the plain child is still there the ending ended nothing, and a
    survivor found gone, or found there, says nothing of it. Not even `cooperative`."""
    for gone in (True, False):
        cells = _battery(
            Scope.JAIL, **{survivor.name: {"control_gone": False, "survivor_gone": gone}}
        )
        assert proven(cells, Scope.JAIL) is Grade.UNENFORCED, (survivor, gone)


def test_a_battery_missing_a_survivor_proves_nothing() -> None:
    cells = _battery(Scope.JAIL)
    for missing in Survivor:
        short = [cell for cell in cells if cell.survivor is not missing]
        assert proven(short, Scope.JAIL) is Grade.UNENFORCED, missing
    assert proven([], Scope.JAIL) is Grade.UNENFORCED


def test_a_scope_is_proved_by_its_own_cells_alone() -> None:
    """The jail's cells say nothing of a process's stop, and the other way round: a process scope
    that fails leaves the jail scope's proof as it was."""
    jail_cells = _battery(Scope.JAIL)
    process_cells = _battery(Scope.PROCESS, SETSID_CHILD={"survivor_gone": False})
    both = [*jail_cells, *process_cells]
    assert proven(both, Scope.JAIL) is Grade.ENFORCED
    assert proven(both, Scope.PROCESS) is Grade.COOPERATIVE
    assert proven(jail_cells, Scope.PROCESS) is Grade.UNENFORCED
    assert proven(process_cells, Scope.JAIL) is Grade.UNENFORCED


def test_the_cell_is_a_value_so_a_proof_cannot_be_edited_after_it_was_seen() -> None:
    cell = _cell(Scope.JAIL, Survivor.SETSID_CHILD)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cell.survivor_gone = False  # type: ignore[misc]
