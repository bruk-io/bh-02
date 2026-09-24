"""M0 placeholder: proves the gates have something real to chew on."""

import pytest

from brig.core import ENFORCED, GRADES_ORDERED, UNENFORCED


@pytest.mark.unit
def test_grades_are_ordered_weakest_first() -> None:
    assert GRADES_ORDERED[0] == UNENFORCED
    assert GRADES_ORDERED[-1] == ENFORCED
    assert len(set(GRADES_ORDERED)) == 4
