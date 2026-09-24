"""EnforcementReport: the grade of every axis, and the floor a stack must meet.

SPEC.md §4 defines the grades and the floor mechanism; §7 step 2 makes
coverage (all seven axes graded) a construction-time invariant of
EnforcementReport rather than a check some later stack layer might forget;
§2 law 1 is why Graded refuses to let BEST_EFFORT carry an unnamed gap.

Comparison against a floor always goes through Grade.is_at_least — never `<`
or `>` on Grade, which SPEC.md §4 makes a TypeError by design.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from brig.core.grades import AXES, Axis, Grade


@dataclass(frozen=True, slots=True)
class Graded:
    """A single axis's grade plus its detail.

    BEST_EFFORT is defined by its named gap (SPEC.md §4): a Graded carrying
    that grade with an empty or whitespace-only detail does not construct.
    The other three grades accept an empty detail.
    """

    grade: Grade
    detail: str = ""

    def __post_init__(self) -> None:
        if self.grade is Grade.BEST_EFFORT and self.detail.strip() == "":
            raise ValueError(
                "Graded(BEST_EFFORT, ...) requires a non-empty, non-whitespace "
                "detail naming the gap (SPEC.md §4: best_effort is defined by "
                "its named gap)"
            )


@dataclass(frozen=True, slots=True)
class Shortfall:
    """One axis whose actual grade falls short of a required floor."""

    axis: Axis
    required: Grade
    actual: Grade


@dataclass(frozen=True, slots=True)
class Floors:
    """A caller's stated minimums, one per axis. An absent axis has no floor."""

    minimums: Mapping[Axis, Grade] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Take a defensive copy to prevent mutation after construction
        copy = dict(self.minimums)
        object.__setattr__(self, "minimums", MappingProxyType(copy))


_AXIS_BY_VALUE: Mapping[str, Axis] = {axis.value: axis for axis in AXES}
_LEGAL_AXIS_NAMES = ", ".join(axis.value for axis in AXES)


def require(**kwargs: Grade) -> Floors:
    """Build Floors from axis VALUE names, e.g. require(fs_read=Grade.ENFORCED).

    A keyword that is not an Axis value raises ValueError naming the bad key
    and listing the seven legal names.
    """
    minimums: dict[Axis, Grade] = {}
    for key, grade in kwargs.items():
        axis = _AXIS_BY_VALUE.get(key)
        if axis is None:
            raise ValueError(
                f"require() got an unexpected keyword {key!r}; legal axis "
                f"names are: {_LEGAL_AXIS_NAMES}"
            )
        minimums[axis] = grade
    return Floors(minimums=minimums)


class FloorViolation(Exception):
    """Raised when an EnforcementReport misses one or more stated floors."""

    def __init__(self, shortfalls: tuple[Shortfall, ...]) -> None:
        self.shortfalls = shortfalls
        super().__init__(str(self))

    def __str__(self) -> str:
        parts = [
            f"{s.axis.value}: required {s.required.value}, got {s.actual.value}"
            for s in self.shortfalls
        ]
        return "floor violation: " + "; ".join(parts)


@dataclass(frozen=True, slots=True)
class EnforcementReport:
    """The grade of every one of the seven axes (SPEC.md §4).

    Coverage is a construction-time invariant (SPEC.md §7 step 2): all seven
    axes must be present, keyed by Axis. A missing axis raises ValueError
    naming it; a key that is not an Axis raises ValueError. This makes the
    stack's coverage rule a type-level invariant instead of a check some
    later aggregation path might forget.
    """

    axes: Mapping[Axis, Graded]

    def __post_init__(self) -> None:
        for key in self.axes:
            if not isinstance(key, Axis):
                raise ValueError(
                    f"EnforcementReport.axes key {key!r} is not an Axis; "
                    f"legal axis names are: {_LEGAL_AXIS_NAMES}"
                )
        missing = [axis for axis in AXES if axis not in self.axes]
        if missing:
            names = ", ".join(axis.value for axis in missing)
            raise ValueError(
                f"EnforcementReport is missing grades for axis/axes: {names} "
                f"(SPEC.md §7: coverage is a construction-time invariant, "
                f"all seven axes must be graded)"
            )
        # Take a defensive copy to prevent mutation after construction
        copy = dict(self.axes)
        object.__setattr__(self, "axes", MappingProxyType(copy))

    def grade_for(self, axis: Axis) -> Graded:
        return self.axes[axis]

    def shortfalls(self, floors: Floors) -> tuple[Shortfall, ...]:
        """Every axis whose grade is NOT is_at_least the floor, in AXES order.

        Pure: returns, never raises.
        """
        result: list[Shortfall] = []
        for axis in AXES:
            required = floors.minimums.get(axis)
            if required is None:
                continue
            actual = self.axes[axis].grade
            if not actual.is_at_least(required):
                result.append(Shortfall(axis=axis, required=required, actual=actual))
        return tuple(result)

    def meets(self, floors: Floors) -> bool:
        return len(self.shortfalls(floors)) == 0

    def check_floors(self, floors: Floors) -> None:
        """Raise FloorViolation if shortfalls() is non-empty."""
        shortfalls = self.shortfalls(floors)
        if shortfalls:
            raise FloorViolation(shortfalls)


def unenforced_report(detail: str = "") -> EnforcementReport:
    """All seven axes at Grade.UNENFORCED — the empty stack's report.

    SPEC.md §3: "The empty stack is valid and grades every axis unenforced."
    """
    return EnforcementReport(axes={axis: Graded(Grade.UNENFORCED, detail) for axis in AXES})
