"""What every test of the jail starts from."""

import pytest


@pytest.fixture(autouse=True)
def _a_jail_config_home_of_its_own(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Some tests start a real kernel, whose default `startup` runs the person's own
    `$XDG_CONFIG_HOME/bh-02/kernel.py` first: every test starts with the variable naming an empty
    directory of its own, so none runs the developer's file (its aside would come before what the
    test reads)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))
