"""A macOS menu-bar app listing warden's managed processes: read-only, refreshed on a timer.

AppKit state belongs to the main thread; nothing here runs anything. `TrayApp` is
constructed and `.run()` is called by whichever code owns the main thread (`warden.cli`,
when it does), not by the cordis row that binds it (see `wiring.py`).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import rumps

__all__ = ["Snapshot", "TrayApp", "TrayConfig", "menu_labels"]


@runtime_checkable
class Snapshot(Protocol):
    """What this plugin needs of `processes`: the names currently registered."""

    @property
    def names(self) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class TrayConfig:
    title: str = "warden"
    refresh_seconds: float = 2.0


def menu_labels(names: Sequence[str]) -> list[str]:
    """What the menu shows for a set of registered names: sorted, for a stable order."""
    return sorted(names) or ["(no processes)"]


class TrayApp(rumps.App):  # type: ignore[misc]
    """A read-only listing of `processes.names`, refreshed every `config.refresh_seconds`.

    `on_quit`, if set before `.run()`, runs before the app quits: `rumps`'s own quit tears
    the process down (`NSApp terminate:`) without unwinding anything of warden's, so the
    shell sets this to its own shutdown before handing control to AppKit's run loop.
    """

    def __init__(self, processes: Snapshot, config: TrayConfig) -> None:
        super().__init__(config.title, quit_button=None)
        self._processes = processes
        self.on_quit: Callable[[], None] | None = None
        self._refresh(None)
        self._timer = rumps.Timer(self._refresh, config.refresh_seconds)
        self._timer.start()

    def _refresh(self, _timer: object) -> None:
        self.menu.clear()
        self.menu.update(
            [rumps.MenuItem(label, callback=None) for label in menu_labels(self._processes.names)]
        )
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self._quit))

    def _quit(self, _sender: object) -> None:
        if self.on_quit is not None:
            self.on_quit()
        rumps.quit_application()
