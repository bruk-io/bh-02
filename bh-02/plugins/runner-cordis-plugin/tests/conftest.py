"""What every test of the jail starts from."""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from runner_cordis_plugin import BrigJail


@pytest.fixture(autouse=True)
def _a_jail_config_home_of_its_own(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Some tests start a real Python process, whose default `startup` runs the person's own
    `$XDG_CONFIG_HOME/bh-02/startup.py` first: every test starts with the variable naming an empty
    directory of its own, so none runs the developer's file (its aside would come before what the
    test reads)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))


@pytest.fixture(autouse=True)
async def _every_jail_ended(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """A shared jail outlives its programs until the runner row ends (`BrigJail.close`), and these
    tests have no row: each jail a test started ends with it, as a session's does, so none holds
    the jail lock, or a supervisor, into the next test."""
    started: list[BrigJail] = []
    real = BrigJail.start

    async def start(self: BrigJail, argv_for: Any, *, cwd: str) -> Any:
        started.append(self)
        return await real(self, argv_for, cwd=cwd)

    monkeypatch.setattr(BrigJail, "start", start)
    yield
    for jail in started:
        await jail.close()
