"""The row: a tray-app factory bound under `tray`, built (but not run) when it activates."""

from cordis import Effects, bind, component
from warden_systray_cordis_plugin.tray import Snapshot, TrayApp, TrayConfig

__all__ = ["tray"]


@component(provides=("tray",))
async def tray(*, processes: Snapshot, config: TrayConfig) -> Effects:
    """Fills the `tray` row: `use = "warden-systray:tray"`.

    Binds a zero-argument factory, not a constructed `TrayApp`: this component runs on
    whichever thread's event loop the runtime is on, but `TrayApp` wraps AppKit state that
    belongs to the main thread. The shell, the one thing that owns the main thread, calls
    the factory there, then `.run()`.
    """
    yield bind("tray", lambda: TrayApp(processes, config))
