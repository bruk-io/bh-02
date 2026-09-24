"""The command palette's commands (bh-01's command-palette): the ones rows offer through the
frame, plus `/help` and `/exit`. Textual's own `CommandPalette` draws them; this provider
reads the app's entries each time it opens, so a command registered later is there too."""

from collections.abc import Sequence
from functools import partial
from typing import Protocol, runtime_checkable

from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.content import Content
from textual.markup import escape

from tui_cordis_plugin.frame import PaletteEntry

__all__ = ["CommandsProvider"]


@runtime_checkable
class _Palette(Protocol):
    """What the provider needs of the app: its entries now, and a way to run one."""

    def palette_entries(self) -> Sequence[PaletteEntry]: ...
    def choose(self, entry: PaletteEntry) -> None: ...


class CommandsProvider(Provider):
    """Every command, listed on open and matched as the person types."""

    def _app(self) -> _Palette:
        app = self.app
        if not isinstance(app, _Palette):
            raise TypeError(
                f"CommandsProvider serves an app with palette_entries() and choose(); "
                f"{type(app).__name__} has neither: list it in that app's COMMANDS only"
            )
        return app

    async def discover(self) -> Hits:
        app = self._app()
        for entry in app.palette_entries():
            yield DiscoveryHit(
                Content(entry.call) + _usage(entry),
                partial(app.choose, entry),
                text=entry.call,
                help=escape(entry.help),
            )

    async def search(self, query: str) -> Hits:
        app = self._app()
        matcher = self.matcher(query)
        for entry in app.palette_entries():
            if (score := matcher.match(entry.call)) > 0:
                shown = matcher.highlight(entry.call) + _usage(entry)
                yield Hit(score, shown, partial(app.choose, entry), text=entry.call, help=escape(entry.help))


def _usage(entry: PaletteEntry) -> Content:
    """A command's usage after its name, as plain text: `[NAME]` is not markup."""
    return Content(f" {entry.usage}" if entry.usage else "")
