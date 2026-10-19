"""The jail directory `tests/conftest.py` gives a test: new, short, resolved, and gone after it.

Every integration and e2e test takes its jail directory from `jail_dir` / `new_jail_dir` since
TASK-0151, so what those promise is read here, once, from the filesystem: a directory no earlier
process used (never named from the pid, which a later process with the same pid is handed with
the earlier one's files), short enough for the proxy's port file and an `AF_UNIX` path, resolved
the way `CompileCtx` requires, and removed with what the jail left in it.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests import conftest
from tests.conftest import NewJailDir

pytestmark = pytest.mark.integration

#: The longest a jail directory's path may be: `/tmp/bg-` and eight characters is 16, and a
#: channel socket in it (`<jail_dir>/chan/<16 hex>.sock`) must still fit `sun_path`'s 104 bytes.
_LONGEST_PATH = 24


def test_a_jail_dir_is_new_empty_short_and_resolved(
    jail_dir: str, new_jail_dir: NewJailDir
) -> None:
    other = new_jail_dir()

    assert jail_dir != other, "two directories asked for in one test are one"
    for path in (jail_dir, other):
        assert os.path.isdir(path)
        assert os.listdir(path) == [], f"{path} was not empty when the test got it"
        assert os.path.realpath(path) == path, f"{path} is not resolved"
        assert os.path.dirname(path) == os.path.realpath("/tmp")
        assert len(path) <= _LONGEST_PATH, f"{path} is longer than {_LONGEST_PATH}"


def test_every_directory_made_is_removed_with_what_is_in_it() -> None:
    with conftest.jail_dirs() as make:
        first, second = make(), make()
        os.makedirs(os.path.join(first, "procs", "0123456789abcdef"))
        Path(first, "procs", "0123456789abcdef", "record.json").write_text("{}")
        Path(second, "proxy.port").write_text("1")
        assert os.path.isdir(first) and os.path.isdir(second)

    assert not os.path.lexists(first)
    assert not os.path.lexists(second)


def test_a_directory_written_into_while_it_is_removed_is_removed_in_the_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A jail the test did not destroy has a supervisor that writes its exit record into
    `<jail_dir>/supervisor` as the tree is removed, and `rmtree` meets a directory that is not
    empty (seen as a leftover `bg-<8>/supervisor/exit` after `test_bwrap_network`). Here the
    first try is followed by exactly that write. THE CONTROL is in the same test: the directory
    is there after the first try, so a fixture that tried once would have left it."""
    real_rmtree: Callable[..., None] = shutil.rmtree
    after_each_try: list[bool] = []

    def removing_while_something_writes(path: str, ignore_errors: bool = False) -> None:
        real_rmtree(path, ignore_errors=ignore_errors)
        if not after_each_try:
            os.makedirs(os.path.join(path, "supervisor"))
            Path(path, "supervisor", "exit").write_text("0")
        after_each_try.append(os.path.lexists(path))

    with conftest.jail_dirs() as make:
        path = make()
        monkeypatch.setattr(shutil, "rmtree", removing_while_something_writes)

    assert after_each_try == [True, False], after_each_try
    assert not os.path.lexists(path)
