"""Unit tests for the zombie rule in teardown's membership scan (TASK-0077,
decision-171): a process in state `Z` has exited, so it is not a member that
survives."""

from __future__ import annotations

import pytest

from brig.run.teardown import _live_group_members

_PS = """\
  100   100 Ss
  101   100 S
  102   100 Z
  103   100 Z+
  200   200 Sl
  garbage
"""


@pytest.mark.unit
def test_a_zombie_is_not_a_surviving_member() -> None:
    assert _live_group_members(_PS, 100) == [100, 101]


@pytest.mark.unit
def test_a_group_of_only_zombies_is_empty() -> None:
    assert _live_group_members("  7  7 Z\n  8  7 Z+\n", 7) == []


@pytest.mark.unit
def test_other_groups_and_unparsable_rows_are_ignored() -> None:
    assert _live_group_members(_PS, 200) == [200]
    assert _live_group_members(_PS, 999) == []
