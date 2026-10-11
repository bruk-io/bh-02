"""Unit tests for the zombie rule in teardown's membership scan (TASK-0077,
decision-171): a process in state `Z` has exited, so it is not a member that
survives."""

from __future__ import annotations

import subprocess

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


@pytest.mark.unit
def test_the_sweep_does_not_call_a_group_gone_that_ps_cannot_see(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `ps` rows for a group `killpg` still finds is unexplained, not ended."""
    from tests import conftest

    monkeypatch.setattr(conftest, "_ps_rows", lambda: [(1, 0, 5, "S", "x")])
    assert conftest._only_zombies_in(9) is False
    assert conftest._only_zombies_in(5) is False
    monkeypatch.setattr(conftest, "_ps_rows", lambda: [(1, 0, 5, "Z", "x"), (2, 0, 5, "Z+", "x")])
    assert conftest._only_zombies_in(5) is True


@pytest.mark.unit
def test_group_alive_reads_a_live_member_alive_and_zombies_or_no_rows_gone() -> None:
    from brig.run import group_alive

    assert group_alive(100, read_table=lambda: _PS) is True
    assert group_alive(7, read_table=lambda: "  7  7 Z\n  8  7 Z+\n") is False
    assert group_alive(999, read_table=lambda: _PS) is False
    assert group_alive(100, read_table=lambda: "") is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "failure",
    [FileNotFoundError("/bin/ps"), subprocess.CalledProcessError(1, "/bin/ps")],
)
def test_group_alive_reads_alive_when_the_process_table_cannot_be_read(
    failure: Exception,
) -> None:
    from brig.run import group_alive

    def unreadable() -> str:
        raise failure

    assert group_alive(100, read_table=unreadable) is True
