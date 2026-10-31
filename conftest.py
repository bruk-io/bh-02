"""Which tests share the host's state, so that pytest-xdist runs them one after another.

`scripts/check` runs the suite as `pytest -n auto --dist loadgroup`: the tests spread over every core,
except that the tests of one group below run on one worker, in turn. A bare `pytest PATH` stays serial
(`-n` is not in `addopts`) and ignores the groups. A test joins a group when it takes something of the
host's that one test at a time may hold; the group is named here, with why, because a group can span
members (a mark in each test file would repeat its name and its reason). A new test that takes the same
thing goes into the group, in this table.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Group:
    """Tests that must not run beside each other: `modules` are paths from the repository root, the test
    files whose tests all belong."""

    name: str
    why: str
    modules: tuple[str, ...]


GROUPS = (
    Group(
        name="jail-lock",
        why=(
            "A Linux jail of bh-02 holds /tmp/bh-02-jails-<uid>.lock shared for as long as it runs, and "
            "removes its placeholders (and its record) only when it can take that lock exclusively, "
            "that is, when no other jail of the user runs (runner_cordis_plugin.jail: `_hold`, "
            "`_clear_up`). The lock is one file per user, so a jail that one worker starts keeps the "
            "placeholders of a jail another worker stops, and the tests that assert nothing is left "
            "behind fail. Every test that starts a BrigJail on the default lock is in these modules; "
            "the ones that give their BrigJail a lock of their own (TASK-0085, TASK-0091) are among "
            "them, safe alone and so only as slow as the others. test_host_values.py boots "
            "runner:confined and expects it to refuse before any jail starts; it is here because a "
            "regression in that refusal would start one on the default lock."
        ),
        modules=(
            "bh-02/app/tests/test_host_values.py",
            "bh-02/app/tests/test_python_repl.py",
            "bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py",
            "bh-02/plugins/runner-cordis-plugin/tests/test_runner_tmux.py",
            "bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py",
        ),
    ),
)


def group_of(module: str) -> str | None:
    """The name of the group the test file `module` (a path from the repository root) belongs to."""
    return next((group.name for group in GROUPS if module in group.modules), None)


@pytest.hookimpl(tryfirst=True)  # before pytest-xdist reads the marks to name each test's group
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(_ROOT) and (name := group_of(item.path.relative_to(_ROOT).as_posix())):
            item.add_marker(pytest.mark.xdist_group(name))
