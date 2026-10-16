"""What every test of the python tool starts from."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _a_config_home_of_its_own(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person's startup file is `$XDG_CONFIG_HOME/bh-02/startup.py`: every test starts with
    the variable naming an empty directory of its own, outside the test's `tmp_path` (a Python process's
    root in many tests), so no test runs the person's own file. A test of that file writes there."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))


@pytest.fixture(scope="session")
def _mypy_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One mypy cache for the whole run of a worker: a test that starts a Python process with startup files
    would otherwise pay mypy's cold start (seconds) in a cache of its own, in its `tmp_path`."""
    return tmp_path_factory.mktemp("mypy-cache")


@pytest.fixture(autouse=True)
def _a_warm_mypy_cache(_mypy_cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The cache every test's Python process uses for the type check of the startup files (the tests'
    `_process`, which reads this variable; a test of the default, in the project, unsets it)."""
    monkeypatch.setenv("BH_TEST_MYPY_CACHE", str(_mypy_cache))
