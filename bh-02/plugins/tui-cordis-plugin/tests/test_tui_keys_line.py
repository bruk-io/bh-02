"""The line under the composer that names the everyday keys (TASK-0089.08): what it says at each
width, that it fits an 80-column terminal, and that every key it names does what it says (the keys
are read from the line itself and pressed), and is in the docs' Keys table."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from textual.command import CommandPalette
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp, render
from tui_cordis_plugin.messages import Shown, TurnEnded
from tui_cordis_plugin.widgets import Composer, Keys, StatusBar, Transcript

_DOCS = Path(__file__).resolve().parents[4] / "docs" / "bh-02" / "using" / "commands.md"
_FULL = render.keys_line(500)
_EIGHT = ("send", "new line", "stop", "scroll", "history", "copy reply", "palette", "quit")


def _items(line: str, gap: str = "  ") -> list[tuple[str, str]]:
    """A line as (key, what it does) pairs: each item is a key, a space and its words."""
    return [tuple(item.split(" ", 1)) for item in line.split(gap)]  # type: ignore[misc]


def _row(app: BhApp) -> str:
    """The text of the row the line is drawn on."""
    keys = app.query_one(Keys)
    rows = "\n".join(
        "".join(segment.text for segment in app.screen._compositor.render_update(full=True).strips[y])  # noqa: SLF001
        for y in range(app.size.height)
    ).splitlines()
    return rows[keys.region.y].strip()


# The words, pure.


def test_the_widest_form_names_the_eight_keys_in_full_in_this_order() -> None:
    assert [what for _, what in _items(_FULL.plain)] == list(_EIGHT)
    assert [key for key, _ in _items(_FULL.plain)] == [
        "Enter",
        "Ctrl-J",
        "Esc",
        "PgUp/PgDn",
        "↑/↓",
        "Ctrl-T",
        "Ctrl-P",
        "Ctrl-Q",
    ]
    assert _FULL.cell_length == 116  # what the widest form needs


def test_each_key_is_bold_and_its_words_are_plain() -> None:
    styled = {_FULL.plain[span.start : span.end] for span in _FULL.spans if "bold" in str(span.style)}
    assert styled == {"Enter", "Ctrl-J", "Esc", "PgUp/PgDn", "↑/↓", "Ctrl-T", "Ctrl-P", "Ctrl-Q"}


def test_a_line_of_80_columns_names_all_eight_in_a_short_form_and_fits_beside_its_margin() -> None:
    """The widget keeps a one-cell left margin, so an 80-column terminal gives it 79 cells."""
    line = render.keys_line(79)
    assert line.cell_length <= 79
    assert line.plain == "↵ send ^J newline Esc stop PgUp/Dn scroll ↑↓ history ^T copy ^P palette ^Q quit"
    for word in ("send", "newline", "stop", "scroll", "history", "copy", "palette", "quit"):
        assert word in line.plain.split()


def test_at_every_width_the_line_fits_and_quit_is_the_last_thing_it_says() -> None:
    for width in range(7, 140):
        line = render.keys_line(width)
        assert line.cell_length <= width and line.plain.endswith("quit"), width


def test_a_narrower_line_never_names_more_keys_than_a_wider_one_and_gives_the_least_everyday_up_first() -> (
    None
):
    counts = [len(render.keys_line(width).plain.split(" ")) for width in range(7, 140)]
    assert counts == sorted(counts)  # widening only ever adds
    seen = [render.keys_line(width).plain for width in (79, 71, 60, 45, 27, 16, 7)]
    words = [{w for w in line.split() if w.isalpha()} for line in seen]
    assert "copy" in words[0] and "copy" not in words[1]  # copy goes first
    assert "history" in words[1] and "history" not in words[2]  # then history
    assert "scroll" in words[2] and "scroll" not in words[3]  # then scroll, new line
    assert words[3] >= {"send", "newline", "stop", "palette", "quit"}
    assert words[4] == {"stop", "palette", "quit", "Esc"}
    assert words[6] == {"quit"}  # and quit is never given up
    assert render.keys_line(0).plain == "^Q quit"  # below that the widget crops it


# On screen.


@pytest.mark.parametrize("width", [80, 100, 120, 60, 40])
async def test_the_line_sits_under_the_composer_and_shows_the_widest_form_that_fits(width: int) -> None:
    app = BhApp()
    async with app.run_test(size=(width, 24)) as pilot:
        await pilot.pause()
        keys, composer, bar = (app.query_one(each) for each in (Keys, Composer, StatusBar))
        assert composer.region.bottom == keys.region.y and keys.region.bottom == bar.region.y
        assert keys.region.height == 1 and keys.region.width == width
        assert _row(app) == render.keys_line(width - 1).plain  # beside its one-cell margin
        assert "…" not in _row(app)  # fitted, not cut


async def test_it_fits_again_when_the_terminal_is_resized() -> None:
    app = BhApp()
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        assert _row(app) == _FULL.plain
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert _row(app) == render.keys_line(79).plain and "↵ send" in _row(app)
        await pilot.resize_terminal(50, 24)
        await pilot.pause()
        assert _row(app) == render.keys_line(49).plain and _row(app).endswith("quit")
        await pilot.resize_terminal(140, 24)
        await pilot.pause()
        assert _row(app) == _FULL.plain


# Every key it names does what it says.


async def _send(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    await pilot.press(*"hello", keys[0])
    assert await asyncio.wait_for(app.bridge.line(), 1) == "hello"
    assert app.query_one(Composer).text == ""


async def _new_line(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    for key in (*keys, "shift+enter"):  # the docs' table names Shift+Enter beside it
        app.query_one(Composer).clear()
        await pilot.press("a", key, "b")
        assert app.query_one(Composer).text == "a\nb" and not app.bridge.kept, key


async def _stop(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    turn = asyncio.ensure_future(app.bridge.interrupted())  # a reply waiting to be stopped
    await pilot.pause()
    assert app.bridge.turn_running
    await pilot.press(keys[0])
    await asyncio.wait_for(turn, 1)  # it heard it


async def _scroll(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    for n in range(60):
        app.post_message(Shown({"type": "text", "text": f"line {n}\n\n"}))
    await pilot.pause()
    transcript = app.query_one(Transcript)
    end = transcript.scroll_y
    assert end > 0 and end == transcript.max_scroll_y
    up, down = keys  # PgUp/PgDn
    await pilot.press(up)
    await pilot.pause()
    assert transcript.scroll_y < end
    await pilot.press(down)
    await pilot.pause()
    assert transcript.scroll_y == end


async def _history(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    await pilot.press(*"first", "enter")
    assert await asyncio.wait_for(app.bridge.line(), 1) == "first"
    await pilot.press(*"dra")
    up, down = keys  # ↑/↓
    await pilot.press(up)
    assert app.query_one(Composer).text == "first"
    await pilot.press(down)
    assert app.query_one(Composer).text == "dra"  # the draft comes back


async def _copy(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    app.post_message(Shown({"type": "text", "text": "the whole reply"}))
    app.post_message(TurnEnded())
    await pilot.pause()
    await pilot.press(keys[0])
    assert app.clipboard == "the whole reply"


async def _palette(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    await pilot.press(keys[0])
    await pilot.pause()
    assert isinstance(app.screen, CommandPalette)


async def _quit(app: BhApp, pilot: Pilot[None], keys: list[str]) -> None:
    await pilot.press(keys[0])
    await pilot.pause()
    assert not app.is_running


_DOES: dict[str, Callable[[BhApp, Pilot[None], list[str]], Awaitable[None]]] = {
    "send": _send,
    "new line": _new_line,
    "stop": _stop,
    "scroll": _scroll,
    "history": _history,
    "copy reply": _copy,
    "palette": _palette,
    "quit": _quit,
}
_PRESSED = {"Enter": "enter", "Esc": "escape", "PgUp": "pageup", "PgDn": "pagedown", "↑": "up", "↓": "down"}


def _pressed(shown: str) -> list[str]:
    """The names Textual gives the keys a line shows as `Ctrl-J`, `PgUp/PgDn` or `↑/↓`."""
    return [_PRESSED.get(part) or part.lower().replace("-", "+") for part in shown.split("/")]


def test_every_key_the_line_names_has_a_check_below_and_no_check_is_left_without_a_key() -> None:
    assert [what for _, what in _items(_FULL.plain)] == list(_DOES)


@pytest.mark.parametrize(("shown", "what"), _items(_FULL.plain))
async def test_the_key_does_what_the_line_says(shown: str, what: str) -> None:
    app = BhApp()
    async with app.run_test(size=(100, 24)) as pilot:
        await _DOES[what](app, pilot, _pressed(shown))


# The docs' Keys table lists the same keys.


def _table_keys() -> str:
    """The first column of the Keys table in the docs, as one text."""
    section = _DOCS.read_text().split("## Keys", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| Key")]
    return "\n".join(row.split("|")[1] for row in rows)


def _in_the_docs(shown: str) -> list[str]:
    """How the docs spell each key a line shows: `Ctrl+J`, `PageUp`, `Up`."""
    spelled = {"PgUp": "PageUp", "PgDn": "PageDown", "↑": "Up", "↓": "Down"}
    return [spelled.get(part) or part.replace("Ctrl-", "Ctrl+") for part in shown.split("/")]


@pytest.mark.skipif(not _DOCS.exists(), reason="the docs are not beside the package")
@pytest.mark.parametrize(("shown", "what"), _items(_FULL.plain))
def test_the_docs_keys_table_lists_the_key(shown: str, what: str) -> None:
    table = _table_keys()
    for spelling in _in_the_docs(shown):
        assert f"`{spelling}`" in table, f"{what}: the Keys table in {_DOCS.name} lacks {spelling}"


@pytest.mark.skipif(not _DOCS.exists(), reason="the docs are not beside the package")
def test_the_docs_keys_table_lists_both_ways_to_start_a_new_line() -> None:
    assert "`Ctrl+J`, `Shift+Enter`" in _table_keys()
