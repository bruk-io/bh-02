"""A read-only macOS menu-bar listing of warden's managed processes."""

from warden_systray_cordis_plugin.tray import Snapshot, TrayApp, TrayConfig, menu_labels
from warden_systray_cordis_plugin.wiring import tray

__all__ = ["Snapshot", "TrayApp", "TrayConfig", "menu_labels", "tray"]
