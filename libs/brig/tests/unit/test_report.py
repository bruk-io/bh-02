"""Tests for brig.core.report: Graded, Floors, EnforcementReport, require().

SPEC.md §4 (grades table, floors), §2 law 1 (honesty over strength), §7
step 2 (coverage is a construction-time invariant).
"""

import pytest

from brig.core.grades import AXES, Axis, Grade
from brig.core.report import (
    EnforcementReport,
    Floors,
    FloorViolation,
    Graded,
    Shortfall,
    require,
    unenforced_report,
)


def _all_axes_at(grade: Grade, detail: str = "") -> dict[Axis, Graded]:
    """Build a full seven-axis grade mapping, all axes at the same grade."""
    return {axis: Graded(grade, detail) for axis in AXES}


@pytest.mark.unit
def test_ec1_floor_refusal_names_axis_and_shortfall() -> None:
    """check_floors raises FloorViolation naming the axis, required, and actual grades."""
    axes = _all_axes_at(Grade.ENFORCED)
    axes[Axis.NETWORK] = Graded(Grade.COOPERATIVE)
    report = EnforcementReport(axes=axes)
    floors = require(network=Grade.ENFORCED)

    with pytest.raises(FloorViolation) as excinfo:
        report.check_floors(floors)

    message = str(excinfo.value)
    assert "network" in message
    assert "enforced" in message
    assert "cooperative" in message
    assert excinfo.value.shortfalls == (
        Shortfall(axis=Axis.NETWORK, required=Grade.ENFORCED, actual=Grade.COOPERATIVE),
    )


@pytest.mark.unit
def test_ec1_control_floor_met_does_not_raise_and_meets_is_true() -> None:
    """Control: the same report against a floor it meets returns cleanly."""
    axes = _all_axes_at(Grade.ENFORCED)
    axes[Axis.NETWORK] = Graded(Grade.COOPERATIVE)
    report = EnforcementReport(axes=axes)
    floors = require(network=Grade.COOPERATIVE)

    report.check_floors(floors)  # must not raise
    assert report.meets(floors) is True
    assert report.shortfalls(floors) == ()


@pytest.mark.unit
@pytest.mark.parametrize("missing_axis", list(AXES))
def test_report_missing_axis_raises_naming_it(missing_axis: Axis) -> None:
    """EnforcementReport with any one axis missing raises ValueError naming it."""
    axes = _all_axes_at(Grade.UNENFORCED)
    del axes[missing_axis]

    with pytest.raises(ValueError, match=missing_axis.value):
        EnforcementReport(axes=axes)


@pytest.mark.unit
def test_report_non_axis_key_raises() -> None:
    """A key in axes that is not an Axis raises ValueError."""
    axes: dict[object, Graded] = {axis: Graded(Grade.UNENFORCED) for axis in AXES}
    del axes[Axis.FS_READ]
    axes["fs_read"] = Graded(Grade.UNENFORCED)  # wrong type: str, not Axis

    with pytest.raises(ValueError):
        EnforcementReport(axes=axes)  # type: ignore[arg-type]


@pytest.mark.unit
def test_graded_best_effort_empty_detail_raises() -> None:
    """Graded(BEST_EFFORT, '') raises ValueError: the gap must be named."""
    with pytest.raises(ValueError):
        Graded(Grade.BEST_EFFORT, "")


@pytest.mark.unit
def test_graded_best_effort_whitespace_detail_raises() -> None:
    """Graded(BEST_EFFORT, '   ') raises ValueError: whitespace is not a name."""
    with pytest.raises(ValueError):
        Graded(Grade.BEST_EFFORT, "   ")


@pytest.mark.unit
def test_graded_cooperative_empty_detail_constructs_fine() -> None:
    """Control: COOPERATIVE with an empty detail is a valid Graded."""
    graded = Graded(Grade.COOPERATIVE, "")
    assert graded.grade is Grade.COOPERATIVE
    assert graded.detail == ""


@pytest.mark.unit
def test_require_rejects_non_axis_keyword() -> None:
    """require() rejects a keyword that is not an Axis value, naming the bad key."""
    with pytest.raises(ValueError, match="bogus_axis"):
        require(bogus_axis=Grade.ENFORCED)


@pytest.mark.unit
def test_unenforced_report_grades_all_seven_unenforced() -> None:
    """unenforced_report() grades every axis UNENFORCED."""
    report = unenforced_report()
    for axis in AXES:
        graded = report.grade_for(axis)
        assert graded.grade is Grade.UNENFORCED


@pytest.mark.unit
def test_unenforced_report_fails_any_floor_above_unenforced() -> None:
    """unenforced_report() fails a floor set above UNENFORCED on every axis."""
    report = unenforced_report()
    floors = require(**{axis.value: Grade.COOPERATIVE for axis in AXES})

    assert report.meets(floors) is False
    shortfalls = report.shortfalls(floors)
    assert len(shortfalls) == len(AXES)
    with pytest.raises(FloorViolation):
        report.check_floors(floors)


@pytest.mark.unit
def test_shortfalls_are_in_axes_order() -> None:
    """shortfalls() reports missed axes in AXES order, not insertion order."""
    axes = _all_axes_at(Grade.ENFORCED)
    axes[Axis.CONTROL] = Graded(Grade.UNENFORCED)
    axes[Axis.FS_READ] = Graded(Grade.UNENFORCED)
    report = EnforcementReport(axes=axes)
    floors = require(control=Grade.ENFORCED, fs_read=Grade.ENFORCED)

    shortfalls = report.shortfalls(floors)
    assert [s.axis for s in shortfalls] == [Axis.FS_READ, Axis.CONTROL]


@pytest.mark.unit
def test_grade_stronger_than_floor_is_not_a_shortfall() -> None:
    """An axis graded stronger than its floor meets it (is_at_least, not ==).

    This is the case a `==`-instead-of-`is_at_least` mutation gets wrong:
    ENFORCED exceeds a COOPERATIVE floor and must not count as a shortfall.
    """
    axes = _all_axes_at(Grade.UNENFORCED)
    axes[Axis.LIMITS] = Graded(Grade.ENFORCED)
    report = EnforcementReport(axes=axes)
    floors = require(limits=Grade.COOPERATIVE)

    assert report.shortfalls(floors) == ()
    assert report.meets(floors) is True
    report.check_floors(floors)  # must not raise


@pytest.mark.unit
def test_floor_absent_axis_is_not_a_floor() -> None:
    """An axis absent from Floors has no minimum: a weak grade there is not a shortfall."""
    axes = _all_axes_at(Grade.UNENFORCED)
    axes[Axis.FS_WRITE] = Graded(Grade.ENFORCED)
    report = EnforcementReport(axes=axes)
    floors = require(fs_write=Grade.ENFORCED)  # only fs_write has a floor

    assert report.meets(floors) is True
    assert report.shortfalls(floors) == ()


@pytest.mark.unit
def test_enforcement_report_axes_survives_mutation_delete_axis() -> None:
    """AC #1: Mutating the source dict after construction does not affect the report."""
    axes = _all_axes_at(Grade.ENFORCED)
    report = EnforcementReport(axes=axes)

    # Verify all axes are present before mutation
    assert len(report.axes) == len(AXES)
    original_axes_copy = dict(report.axes)

    # Mutate the source dict by deleting an axis
    del axes[Axis.NETWORK]

    # Report should be unchanged
    assert len(report.axes) == len(AXES)
    assert dict(report.axes) == original_axes_copy


@pytest.mark.unit
def test_enforcement_report_axes_survives_mutation_rebind_axis() -> None:
    """AC #1: Mutating the source dict by rebinding an axis does not affect the report."""
    axes = _all_axes_at(Grade.ENFORCED)
    report = EnforcementReport(axes=axes)

    # Verify original grade
    original_grade = report.axes[Axis.NETWORK]
    assert original_grade.grade is Grade.ENFORCED

    # Mutate the source dict by rebinding an axis
    axes[Axis.NETWORK] = Graded(Grade.UNENFORCED)

    # Report should be unchanged
    assert report.axes[Axis.NETWORK] == original_grade
    assert report.axes[Axis.NETWORK].grade is Grade.ENFORCED


@pytest.mark.unit
def test_enforcement_report_axes_mutation_inverse_control_delete() -> None:
    """AC #2: Mutating the source dict BEFORE construction DOES change the object."""
    axes = _all_axes_at(Grade.ENFORCED)

    # Delete an axis BEFORE construction
    del axes[Axis.NETWORK]

    # Construction should fail with missing axis error
    with pytest.raises(ValueError, match=Axis.NETWORK.value):
        EnforcementReport(axes=axes)


@pytest.mark.unit
def test_enforcement_report_axes_mutation_inverse_control_rebind() -> None:
    """AC #2: Mutating the source dict by rebinding BEFORE construction DOES change."""
    axes = _all_axes_at(Grade.ENFORCED)

    # Rebind NETWORK to COOPERATIVE BEFORE construction
    axes[Axis.NETWORK] = Graded(Grade.COOPERATIVE, "test detail")

    # Construct with the modified dict
    report = EnforcementReport(axes=axes)

    # Report should reflect the COOPERATIVE grade
    assert report.axes[Axis.NETWORK].grade is Grade.COOPERATIVE
    assert report.axes[Axis.NETWORK].detail == "test detail"


@pytest.mark.unit
def test_enforcement_report_mutation_does_not_affect_floors_check() -> None:
    """AC #3: Deleting an axis from source dict after construction doesn't change floors check."""
    axes = _all_axes_at(Grade.UNENFORCED)
    axes[Axis.NETWORK] = Graded(Grade.COOPERATIVE)
    report = EnforcementReport(axes=axes)

    # Create floors that require NETWORK to be ENFORCED (will fail)
    floors = require(network=Grade.ENFORCED)

    # Get shortfalls before mutation
    shortfalls_before = report.shortfalls(floors)
    assert len(shortfalls_before) == 1
    assert shortfalls_before[0].axis is Axis.NETWORK
    assert shortfalls_before[0].actual is Grade.COOPERATIVE

    # Mutate the source dict by deleting NETWORK
    del axes[Axis.NETWORK]

    # Floors check should remain the same
    shortfalls_after = report.shortfalls(floors)
    assert shortfalls_after == shortfalls_before
    assert len(shortfalls_after) == 1


@pytest.mark.unit
def test_enforcement_report_axes_mapping_refuses_mutation() -> None:
    """AC #4: The exposed axes mapping refuses direct mutation (TypeError)."""
    axes = _all_axes_at(Grade.ENFORCED)
    report = EnforcementReport(axes=axes)

    # Attempting to assign to the mapping should raise TypeError
    with pytest.raises(TypeError):
        report.axes[Axis.NETWORK] = Graded(Grade.UNENFORCED)  # type: ignore[index]


@pytest.mark.unit
def test_floors_minimums_survives_mutation_delete_axis() -> None:
    """AC #1: Mutating the source dict after Floors construction does not affect it."""
    minimums = {Axis.NETWORK: Grade.ENFORCED, Axis.FS_READ: Grade.COOPERATIVE}
    floors = Floors(minimums=minimums)

    # Verify both axes are present before mutation
    assert len(floors.minimums) == 2
    original_minimums_copy = dict(floors.minimums)

    # Mutate the source dict by deleting an axis
    del minimums[Axis.NETWORK]

    # Floors should be unchanged
    assert len(floors.minimums) == 2
    assert dict(floors.minimums) == original_minimums_copy


@pytest.mark.unit
def test_floors_minimums_survives_mutation_rebind_axis() -> None:
    """AC #1: Mutating the source dict by rebinding an axis does not affect Floors."""
    minimums = {Axis.NETWORK: Grade.ENFORCED, Axis.FS_READ: Grade.COOPERATIVE}
    floors = Floors(minimums=minimums)

    # Verify original grade
    original_network = floors.minimums[Axis.NETWORK]
    assert original_network is Grade.ENFORCED

    # Mutate the source dict by rebinding an axis
    minimums[Axis.NETWORK] = Grade.UNENFORCED

    # Floors should be unchanged
    assert floors.minimums[Axis.NETWORK] == original_network
    assert floors.minimums[Axis.NETWORK] is Grade.ENFORCED


@pytest.mark.unit
def test_floors_minimums_mutation_inverse_control() -> None:
    """AC #2: Mutating the source dict BEFORE Floors construction DOES change it."""
    minimums = {Axis.NETWORK: Grade.ENFORCED, Axis.FS_READ: Grade.COOPERATIVE}

    # Rebind NETWORK BEFORE construction
    minimums[Axis.NETWORK] = Grade.UNENFORCED

    # Construct with the modified dict
    floors = Floors(minimums=minimums)

    # Floors should reflect the UNENFORCED grade
    assert floors.minimums[Axis.NETWORK] is Grade.UNENFORCED


@pytest.mark.unit
def test_floors_minimums_mapping_refuses_mutation() -> None:
    """AC #4: The exposed minimums mapping refuses direct mutation (TypeError)."""
    minimums = {Axis.NETWORK: Grade.ENFORCED, Axis.FS_READ: Grade.COOPERATIVE}
    floors = Floors(minimums=minimums)

    # Attempting to assign to the mapping should raise TypeError
    with pytest.raises(TypeError):
        floors.minimums[Axis.NETWORK] = Grade.UNENFORCED  # type: ignore[index]


@pytest.mark.unit
def test_enforcement_report_equality_with_defensive_copy() -> None:
    """Two reports built from equal mappings are equal."""
    axes1 = _all_axes_at(Grade.ENFORCED)
    axes2 = _all_axes_at(Grade.ENFORCED)

    report1 = EnforcementReport(axes=axes1)
    report2 = EnforcementReport(axes=axes2)

    # Reports should be equal despite coming from separate dicts
    assert report1 == report2


@pytest.mark.unit
def test_floors_equality_with_defensive_copy() -> None:
    """Two Floors built from equal mappings are equal."""
    minimums1 = {Axis.NETWORK: Grade.ENFORCED, Axis.FS_READ: Grade.COOPERATIVE}
    minimums2 = {Axis.NETWORK: Grade.ENFORCED, Axis.FS_READ: Grade.COOPERATIVE}

    floors1 = Floors(minimums=minimums1)
    floors2 = Floors(minimums=minimums2)

    # Floors should be equal despite coming from separate dicts
    assert floors1 == floors2
