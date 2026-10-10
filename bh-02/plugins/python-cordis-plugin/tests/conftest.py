"""What every test of the kernel starts from."""

import pytest


@pytest.fixture(autouse=True)
def _a_config_home_of_its_own(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person's startup file is `$XDG_CONFIG_HOME/bh-02/kernel.py`: every test starts with
    the variable naming an empty directory of its own, outside the test's `tmp_path` (a kernel's
    root in many tests), so no test runs the person's own file. A test of that file writes there."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))
