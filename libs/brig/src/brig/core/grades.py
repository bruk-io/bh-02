"""Axes and grades: the report's fixed vocabulary with semantic ordering.

SPEC.md §4 defines the seven axes and four grades. Both are plain Enum (not
StrEnum) so that lexical comparison is a runtime TypeError rather than a
silently-wrong answer. Grade.is_at_least() and Grade.rank encode the
semantic order.
"""

from enum import Enum
from typing import Final


class Axis(Enum):
    """The seven axes of the enforcement report (SPEC.md §4)."""

    FS_READ = "fs_read"
    FS_WRITE = "fs_write"
    NETWORK = "network"
    LIMITS = "limits"
    ENV = "env"
    CHANNEL_EXCLUSIVITY = "channel_exclusivity"
    CONTROL = "control"


class Grade(Enum):
    """The four grades of enforcement, ordered weakest-first (SPEC.md §4).

    Grades are ordered semantically, not lexically. Comparison via <, >, etc.
    is deliberately a TypeError; use is_at_least() instead.
    """

    UNENFORCED = "unenforced"
    COOPERATIVE = "cooperative"
    BEST_EFFORT = "best_effort"
    ENFORCED = "enforced"

    @property
    def rank(self) -> int:
        """Semantic rank: 0 (weakest) to 3 (strongest)."""
        return _GRADE_RANKS[self]

    def is_at_least(self, other: Grade) -> bool:
        """True if self's rank >= other's rank (self is at least as strong)."""
        return self.rank >= other.rank


# Internal mapping: grade -> rank. Defined after the enum so we can reference
# the members. This is filled in below.
_GRADE_RANKS: dict[Grade, int] = {}

# Semantic order: weakest first
GRADES_ORDERED: Final[tuple[Grade, ...]] = (
    Grade.UNENFORCED,
    Grade.COOPERATIVE,
    Grade.BEST_EFFORT,
    Grade.ENFORCED,
)

# Populate the rank mapping
for idx, grade in enumerate(GRADES_ORDERED):
    _GRADE_RANKS[grade] = idx

# The seven axes in SPEC §4 table order
AXES: Final[tuple[Axis, ...]] = (
    Axis.FS_READ,
    Axis.FS_WRITE,
    Axis.NETWORK,
    Axis.LIMITS,
    Axis.ENV,
    Axis.CHANNEL_EXCLUSIVITY,
    Axis.CONTROL,
)
