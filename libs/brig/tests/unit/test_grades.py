"""Tests for brig.core.grades: Axis and Grade enums with semantic ordering."""

import pytest

from brig.core import (
    AXES,
    BEST_EFFORT,
    COOPERATIVE,
    ENFORCED,
    GRADES_ORDERED,
    UNENFORCED,
    Grade,
)


@pytest.mark.unit
def test_grade_lexical_order_cannot_be_reintroduced() -> None:
    """Prove that lexical comparison is impossible, not merely discouraged."""

    def attempt_lexical_comparison() -> bool:
        """Attempt to compare grades lexically."""
        return Grade.BEST_EFFORT < Grade.COOPERATIVE  # type: ignore[operator, no-any-return]

    with pytest.raises(TypeError):
        attempt_lexical_comparison()


@pytest.mark.unit
def test_grades_ordered_values_and_ranks() -> None:
    """Pin the order and ranks of GRADES_ORDERED."""
    # Values must be in semantic order: weakest to strongest
    assert tuple(g.value for g in GRADES_ORDERED) == (
        "unenforced",
        "cooperative",
        "best_effort",
        "enforced",
    )
    # Ranks must map to indices
    assert [g.rank for g in GRADES_ORDERED] == [0, 1, 2, 3]


@pytest.mark.unit
def test_is_at_least_semantics() -> None:
    """Pin is_at_least comparison semantics."""
    # Every grade is at least itself
    for grade in GRADES_ORDERED:
        assert grade.is_at_least(grade)

    # ENFORCED is at least UNENFORCED
    assert ENFORCED.is_at_least(UNENFORCED)

    # UNENFORCED is NOT at least COOPERATIVE
    assert not UNENFORCED.is_at_least(COOPERATIVE)


@pytest.mark.unit
def test_axes_complete_and_ordered() -> None:
    """Pin the AXES tuple: all 7 axes in SPEC order."""
    assert tuple(a.value for a in AXES) == (
        "fs_read",
        "fs_write",
        "network",
        "limits",
        "env",
        "channel_exclusivity",
        "control",
    )
    assert len(AXES) == 7


@pytest.mark.unit
def test_module_level_names_bound_to_enum_members() -> None:
    """Verify that the module-level names point to Grade enum members."""
    assert UNENFORCED is Grade.UNENFORCED
    assert COOPERATIVE is Grade.COOPERATIVE
    assert BEST_EFFORT is Grade.BEST_EFFORT
    assert ENFORCED is Grade.ENFORCED
