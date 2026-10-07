"""What every test of the context files starts from."""

import pytest


@pytest.fixture(autouse=True)
def _no_xdg_config_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Your context file is `$XDG_CONFIG_HOME/bh-02/context.toml`, else the config's `home`'s
    `.config/bh-02/context.toml`: every test starts with the variable unset, so a test that
    writes under its temporary `home` reads that, never the person's own. A test of the variable
    sets it."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
