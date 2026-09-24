"""The StatusBar: the fields rows push through the frame (CONTRACTS.md: frame), in one line."""

from collections.abc import Mapping, Sequence

from rich.cells import cell_len
from textual import events
from textual.widgets import Static

__all__ = ["StatusBar", "fit"]

_SEPARATOR = "  │  "
_NARROW_SEPARATOR = " │ "
# The fields bh-02 pushes, in the order they are shown; any other field follows, in push order.
_RANK = ("session", "model", "jail", "usage")
# Which field goes first when even shortened they do not fit (any other field before these);
# the jail's is never dropped or cut: its grades are the reason to look at the bar.
_DROP = ("session", "model", "usage")
_WHOLE = frozenset({"jail"})
# Whose shorter forms are taken first when the line is too wide (any other field's after
# these, the jail's last): the session's short id and usage's short form say the same; the
# jail's axis names are what make its grades readable.
_SHORTEN_FIRST = ("session", "usage")
_SHORTEN_LAST = ("jail",)
# A shortened field keeps at least this many cells of its text (the ellipsis included).
_MIN_CELLS = 8

# A field's forms: its full text, then any shorter forms its producer gives, each shorter than
# the last (the frame's `status(field, text, *shorter)`). A plain string is one form.
type Forms = str | Sequence[str]


def _ordered[T](fields: Mapping[str, T]) -> dict[str, T]:
    """The fields in the bar's fixed order (`_RANK`), any other after them as pushed."""
    ranked = [f for f in _RANK if f in fields]
    return {f: fields[f] for f in [*ranked, *(f for f in fields if f not in _RANK)]}


def _forms(value: Forms) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value) or ("",)


def _shortening_order(forms: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Each field once per shorter form it has, in the order they are taken."""
    first = [f for f in _SHORTEN_FIRST if f in forms]
    last = [f for f in _SHORTEN_LAST if f in forms]
    middle = [f for f in forms if f not in first and f not in last]
    return [f for f in [*first, *middle, *last] for _ in forms[f][1:]]


def fit(fields: Mapping[str, Forms], width: int) -> str:
    """Return `field: text` pairs in one line of at most `width` cells, if shortening can.

    Each field is its forms, fullest first (see `Forms`). The fields are shown in a fixed
    order (session, model, jail, usage, then any other), and shortened a step at a time until
    they fit: narrower separators; then each field's shorter forms, one at a time (the
    session's first, then usage's, any other's, the jail's last). Once the line fits, every
    field gets back the fullest form that still fits, the session's first, so a step taken
    early is undone if a later one made enough room. If the shortest forms do not fit: the
    widest field is cut (ending in `…`), down to a few cells each; then fields are dropped,
    any other field first, then session, model, usage. The jail's field is never cut or
    dropped; if it alone is too wide, the widget crops it at the right edge.
    """
    forms = {field: _forms(value) for field, value in _ordered(fields).items()}
    level = dict.fromkeys(forms, 0)

    def width_of(separator: str) -> int:
        return cell_len(_line({f: forms[f][level[f]] for f in forms}, separator))

    separator = _SEPARATOR if width_of(_SEPARATOR) <= width else _NARROW_SEPARATOR
    order = _shortening_order(forms)
    for field in order:
        if width_of(separator) <= width:
            break
        level[field] += 1
    if width_of(separator) <= width:
        for field in dict.fromkeys(order):  # give back the fullest form that fits, in order
            while level[field] > 0:
                level[field] -= 1
                if width_of(separator) > width:
                    level[field] += 1
                    break
    texts = {f: forms[f][level[f]] for f in forms}
    while (over := cell_len(_line(texts, separator)) - width) > 0:
        cuttable = [f for f, t in texts.items() if f not in _WHOLE and cell_len(t) > _MIN_CELLS]
        if cuttable:
            widest = max(cuttable, key=lambda f: cell_len(texts[f]))
            texts[widest] = _ellipsize(texts[widest], max(_MIN_CELLS, cell_len(texts[widest]) - over))
            continue
        droppable = [f for f in reversed(texts) if f not in _RANK] + [f for f in _DROP if f in texts]
        if not droppable:
            break
        del texts[droppable[0]]
    return _line(texts, separator)


def _line(texts: Mapping[str, str], separator: str = _SEPARATOR) -> str:
    return separator.join(f"{field}: {text}" for field, text in texts.items())


def _ellipsize(text: str, cells: int) -> str:
    """`text` cut to at most `cells` cells, its last one an ellipsis; at a word's end if the
    cut falls after one (`20260922-1 (resumed)` becomes `20260922-1…`, not `20260922-1 (…`)."""
    cut = text
    while cut and cell_len(cut) + 1 > cells:
        cut = cut[:-1]
    if " " in cut and not text[len(cut) :].startswith(" "):
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


class StatusBar(Static):
    """One line along the bottom: `field: text` pairs in a fixed order (see `fit`), shortened
    to fit the width (again whenever it changes)."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        width: 100%;
        background: $bh-surface-recessed;
        color: $bh-text 70%;  /* bh-01's text-muted is 2.6:1 here; this is 5.8:1 (light: 5.4:1) */
        padding: 0 1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", markup=False, id=id)
        self._fields: dict[str, Forms] = {}

    def show_fields(self, fields: Mapping[str, Forms]) -> None:
        """Show every field as `field: text`, shortened to fit (each field is its text, or its
        forms fullest first)."""
        self._fields = dict(fields)
        self._refit()

    def on_resize(self, event: events.Resize) -> None:
        self._refit()

    def _refit(self) -> None:
        width = self.content_size.width
        full = {field: _forms(value)[0] for field, value in _ordered(self._fields).items()}
        self.update(fit(self._fields, width) if width > 0 else _line(full))
