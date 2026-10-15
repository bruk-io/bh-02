"""The groups in the repository's `conftest.py` keep tests that share the host's state on one
pytest-xdist worker. A group names its tests by file, so a renamed file, or a new file that starts a
jail, would leave the suite flaky under `-n auto` with nothing to say why; these say it."""

import importlib.util
import re
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[3]
# a test file that builds a jail of bh-02's own (`BrigJail(...)`), or boots the confined runner row
_STARTS_A_JAIL = re.compile(r'BrigJail\(|runner:confined"')


def _conftest() -> ModuleType:
    """The repository's `conftest.py`, loaded by path (its name is every conftest's)."""
    loader = SourceFileLoader("root_conftest", str(_ROOT / "conftest.py"))
    spec = importlib.util.spec_from_loader("root_conftest", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_every_file_a_group_names_is_a_test_file_that_exists() -> None:
    gone = [
        f"{group.name}: {module}"
        for group in _conftest().GROUPS
        for module in group.modules
        if not (_ROOT / module).is_file()
    ]
    assert not gone, f"a group names a file that is not there (renamed? update conftest.py): {gone}"


def test_every_test_file_that_starts_a_jail_is_in_a_group() -> None:
    """A jail of bh-02's own holds `/tmp/bh-02-jails-<uid>.lock` for as long as it runs, so a test that
    starts one must not run beside another (the `jail-lock` group): a file that starts one belongs in
    a group of the repository's `conftest.py`, with a reason there."""
    conftest = _conftest()
    files = [
        path.relative_to(_ROOT).as_posix()
        for tree in ("bh-02", "examples")
        for path in sorted((_ROOT / tree).glob("**/tests/**/test_*.py"))
        if path != Path(__file__).resolve() and _STARTS_A_JAIL.search(path.read_text())  # not this pattern
    ]
    assert files, "no test file starts a jail: the pattern no longer finds what it is for"
    ungrouped = [path for path in files if conftest.group_of(path) is None]
    assert not ungrouped, f"these start a jail but are in no group of conftest.py (jail-lock?): {ungrouped}"
