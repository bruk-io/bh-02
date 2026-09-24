"""The row driven by hand: it binds a factory, not a constructed (AppKit-backed) app."""

from cordis.testing import drive
from warden_systray_cordis_plugin import TrayConfig, tray


class FakeSnapshot:
    def __init__(self, names: list[str]) -> None:
        self.names = names


async def test_the_row_binds_a_zero_argument_factory_and_runs_nothing() -> None:
    effects = await drive(tray(processes=FakeSnapshot(["example"]), config=TrayConfig()))
    assert [e.name for e in effects] == ["bind"]
    assert effects[0].args[0] == "tray"
    assert callable(effects[0].args[1])  # the factory; not called here, it would touch AppKit
