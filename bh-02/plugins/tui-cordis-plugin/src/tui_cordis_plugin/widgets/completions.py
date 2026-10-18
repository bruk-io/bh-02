"""The composer's list of commands (decision-0003): the entries a `/` line completes, between
the chat view and the composer. It never takes focus, so the composer keeps the keys, and it
takes plain `PaletteEntry` values, nothing of the commands broker."""

from collections.abc import Callable, Sequence

from rich.cells import cell_len, set_cell_size
from textual import events
from textual.content import Content
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from tui_cordis_plugin import frame
from tui_cordis_plugin.frame import PaletteEntry

__all__ = ["MAX_ROWS", "Completions", "row"]

MAX_ROWS = 8  # the list is at most this tall, and scrolls past it


def row(entry: PaletteEntry, width: int) -> Content:
    """One entry as one line of at most `width` cells: its call, its usage when it takes
    arguments, then its help dimmed, the help cut with an ellipsis. Plain text, never markup:
    a usage like `[NAME]` is what it says."""
    head = _cut(f"{entry.call} {entry.usage}" if entry.usage else entry.call, width)
    room = width - cell_len(head)
    help_ = _cut(f"  {entry.help}", room) if entry.help and room > 2 else ""
    return Content(head) + Content.styled(help_, "dim")


def _cut(text: str, width: int) -> str:
    """`text` within `width` cells, ending in an ellipsis when it was cut."""
    if cell_len(text) <= width:
        return text
    return set_cell_size(text, max(width - 1, 0)).rstrip() + "…" if width > 0 else ""


class Completions(OptionList):
    """The entries a `/` line matches, one line each. It is opened with a snapshot of the
    entries (read once), shown filtered as the text changes, and closed when the line stops
    being one that completes. `shut` keeps it closed (Esc) until it is closed."""

    can_focus = False

    DEFAULT_CSS = f"""
    Completions {{
        display: none;
        height: auto;
        max-height: {MAX_ROWS};
        border: none;
        padding: 0 1;
        background: $bh-surface;
    }}
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id, compact=True)
        self._snapshot: tuple[PaletteEntry, ...] | None = None
        self._shown: tuple[PaletteEntry, ...] = ()
        self._moved = False
        self._shut = False

    @property
    def is_open(self) -> bool:
        """Whether the list is showing entries (a key it handles is then its)."""
        return bool(self._shown)

    @property
    def shown(self) -> tuple[PaletteEntry, ...]:
        return self._shown

    def update_for(
        self, text: str, read: Callable[[], Sequence[PaletteEntry]], *, allowed: bool = True
    ) -> None:
        """Follow the composer's `text`. A one-line `/` line opens the list, taking its entries
        from `read` just once per opening; each change filters them. Anything else closes it,
        and so does `allowed` false (a question is up); after `shut` it stays closed."""
        if not allowed or not frame.slash_line(text):
            self.close()
        elif not self._shut:
            if self._snapshot is None:
                self._snapshot = tuple(read())
            self._show(frame.completions(self._snapshot, text))

    def close(self) -> None:
        """Close it and forget the opening: the next one reads the entries again."""
        self._snapshot = None
        self._shut = False
        self._show(())

    def shut(self) -> None:
        """Hide it for this line (Esc): it opens again only after `close`."""
        self._shut = True
        self._show(())

    def _show(self, entries: tuple[PaletteEntry, ...]) -> None:
        self._shown = entries
        self._moved = False
        self.display = bool(entries)
        self._draw()
        self.highlighted = 0 if entries else None

    def _draw(self) -> None:
        width = self.size.width - 2 if self.size.width else self.app.size.width - 2
        self.clear_options()
        self.add_options([Option(row(entry, width)) for entry in self._shown])

    def on_resize(self, event: events.Resize) -> None:
        """Cut the rows to the new width, the highlight kept."""
        if self._shown:
            kept = self.highlighted
            self._draw()
            self.highlighted = kept

    def move(self, step: int) -> None:
        """Move the highlight by `step` rows, wrapping, and remember that the person did."""
        if self._shown:
            self._moved = True
            self.highlighted = ((self.highlighted or 0) + step) % len(self._shown)

    @property
    def highlight(self) -> PaletteEntry | None:
        index = self.highlighted
        return self._shown[index] if index is not None and index < len(self._shown) else None

    def taken_by_enter(self, text: str) -> PaletteEntry | None:
        """The highlighted entry when Enter takes it (`frame.enter_takes`), else None."""
        entry = self.highlight
        return entry if frame.enter_takes(text, entry, self._moved) else None

    def entry_at(self, index: int) -> PaletteEntry | None:
        """The entry in row `index`, if it is one."""
        return self._shown[index] if 0 <= index < len(self._shown) else None
