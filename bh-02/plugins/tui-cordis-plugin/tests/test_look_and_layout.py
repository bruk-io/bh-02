"""The look and the layout: every stylesheet parses against each theme (as a real launch
parses them), the themes are live under Pilot, the sidebar folds away on a narrow screen, and
the status bar shortens its fields in a fixed order and never drops the jail."""

import pytest
from rich.cells import cell_len
from textual.color import Color
from textual.css.errors import UnresolvedVariableError
from textual.css.stylesheet import Stylesheet
from textual.widgets import OptionList

from tui_cordis_plugin import BhApp, bh01_theme, frame, render, theme, widgets
from tui_cordis_plugin.messages import Asked
from tui_cordis_plugin.widgets import ApprovalScreen, Composer, SidebarPanel, StatusBar
from tui_cordis_plugin.widgets.status_bar import fit

_THEMES = [each.name for each in theme.themes()]
_JAIL = "unjailed fs_write ✗ network ✗ fs_read ✗ env ✗"
_JAIL_FORMS = render.jail_forms(False, dict.fromkeys(("fs_write", "network", "fs_read", "env"), "unenforced"))


def _sheets() -> list[str]:
    """Every stylesheet the app has: its own and each widget's (whatever `widgets` exports)."""
    classes = [getattr(widgets, name) for name in widgets.__all__]
    return [BhApp.CSS, *(css for cls in classes if (css := getattr(cls, "DEFAULT_CSS", "")).strip())]


def _parse(variables: dict[str, str], sheets: list[str]) -> None:
    sheet = Stylesheet(variables=variables)
    for index, css in enumerate(sheets):
        sheet.add_source(css, read_from=("sheet", str(index)), is_default_css=True)
    sheet.parse()


def _variables(name: str) -> dict[str, str]:
    app = BhApp()
    app.theme = name
    return app.get_css_variables()


@pytest.mark.parametrize("name", _THEMES)
def test_every_stylesheet_parses_against_each_theme(name: str) -> None:
    """What a real launch does at startup, which `run_test()` alone does not prove."""
    _parse(_variables(name), _sheets())


def test_an_undefined_token_fails_the_parse() -> None:
    """The check above can fail: a sheet naming a token no theme defines does not parse."""
    with pytest.raises(UnresolvedVariableError, match="bh-nope"):
        _parse(_variables(theme.NAME), [*_sheets(), "Static { color: $bh-nope; }"])


def test_the_themes_define_the_same_tokens_and_the_defaults_cover_them() -> None:
    dark, light = theme.themes()
    assert (dark.name, light.name) == (bh01_theme.DARK, bh01_theme.LIGHT) and dark.name == theme.NAME
    assert set(dark.variables) == set(light.variables) == set(theme.VARIABLES)
    assert {"bh-text-muted", "bh-border", "bh-primary-glow", "bh-surface-overlay"} <= set(dark.variables)


async def test_the_dark_theme_is_live_and_the_light_one_restyles_everything_mounted() -> None:
    app = BhApp()
    async with app.run_test(size=(120, 36)) as pilot:
        composer = app.query_one(Composer)
        assert app.theme == bh01_theme.DARK
        assert composer.styles.border_top[1] == Color.parse(bh01_theme.DARK_VARIABLES["bh-ring"])
        assert app.screen.styles.background == Color.parse(bh01_theme.DARK_VARIABLES["bh-bg"])
        app.theme = bh01_theme.LIGHT
        await pilot.pause()
        assert app.screen.styles.background == Color.parse(bh01_theme.LIGHT_VARIABLES["bh-bg"])
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"name": "python", "input": {"code": "print(1)"}}, answer))
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)
        dialog = app.screen.query_one("#approval")
        assert dialog.styles.background == Color.parse(bh01_theme.LIGHT_VARIABLES["bh-surface-overlay"])
        assert 0 < app.screen.styles.background.a < 1  # the conversation shows through


async def test_a_narrow_screen_hides_the_sidebar_and_ctrl_b_toggles_it() -> None:
    app = BhApp()
    async with app.run_test(size=(90, 30)) as pilot:
        sidebar = app.query_one(SidebarPanel)
        assert isinstance(app.focused, Composer)  # Ctrl-B works from where focus starts
        assert not sidebar.display
        await pilot.press("ctrl+b")
        assert sidebar.display and sidebar.region.width > 0
        assert isinstance(app.focused, OptionList) and app.focused in sidebar.query(OptionList)
        await pilot.press("ctrl+b")
        assert not sidebar.display and isinstance(app.focused, Composer)
    app = BhApp()
    async with app.run_test(size=(120, 30)) as pilot:
        sidebar = app.query_one(SidebarPanel)
        assert sidebar.display
        await pilot.press("ctrl+b")
        assert not sidebar.display


_FIELDS = {
    "jail": _JAIL_FORMS,
    "session": ("20260922-143015-a1b2 (resumed)", "a1b2 ↻"),
    "model": "claude-opus-5-5[1m]",
}
_FULL = {
    "usage": frame.usage_forms(frame.Usage(12_345, 678, 0.1234)),
    "jail": render.jail_forms(True, dict.fromkeys(("fs_write", "network", "fs_read", "env"), "enforced")),
    "model": "claude-opus-5-5[1m]",
    "session": ("20260923-000014-b1c2 (resumed)", "b1c2 ↻"),
}
_NEW_SESSION = {"session": ("20260923-000014-b1c2", "b1c2")}


def test_the_status_line_keeps_a_fixed_order_whatever_order_the_fields_came_in() -> None:
    line = fit(dict(reversed(_FULL.items())) | {"extra": "x"}, 300)
    assert [part.split(":")[0] for part in line.split("  │  ")] == [
        "session",
        "model",
        "jail",
        "usage",
        "extra",
    ]
    assert fit(_FULL, 300) == line.removesuffix("  │  extra: x")


@pytest.mark.parametrize("width", [118, 98, 78])  # 120, 100 and 80 columns less the padding
def test_at_ordinary_widths_every_field_shows_and_usage_keeps_its_output_tokens_and_cost(width: int) -> None:
    line = fit(_FULL, width)
    assert cell_len(line) <= width
    assert [part.split(":")[0] for part in line.split(" │ ")] == ["session", "model", "jail", "usage"]
    assert "jail: jailed w✓ n✓ r✓ e✓" in line or "jail: jailed ✓✓✓✓" in line  # every grade
    assert "678" in line and "$0.12" in line  # usage's output tokens and cost
    assert "b1c2 ↻" in line or "b1c2 (resumed)" in line  # the session's id (or its last part), resumed


def test_shortening_goes_a_step_at_a_time_and_stops_once_the_line_fits() -> None:
    wide = fit(_FULL, 300)
    assert "fs_write ✓" in wide and "12k in · 678 out · $0.1234" in wide and "  │  " in wide
    assert " │ " in fit(_FULL, cell_len(wide) - 4) and "fs_write ✓" in fit(_FULL, cell_len(wide) - 4)
    assert fit(_FULL, 140) == (  # the session's short id, still marked resumed, makes room
        "session: b1c2 ↻ │ model: claude-opus-5-5[1m] │ jail: jailed fs_write ✓ network ✓ "
        "fs_read ✓ env ✓ │ usage: 12k in · 678 out · $0.1234"
    )
    assert fit(_FULL, 118) == (  # usage in short and the jail's initials make room for the whole id
        "session: 20260923-000014-b1c2 (resumed) │ model: claude-opus-5-5[1m] │ jail: jailed w✓ n✓ r✓ e✓ │ "
        "usage: 12k/678 $0.12"
    )
    assert fit(_FULL, 98) == (  # then the session's short id after all
        "session: b1c2 ↻ │ model: claude-opus-5-5[1m] │ jail: jailed w✓ n✓ r✓ e✓ │ usage: 12k/678 $0.12"
    )
    assert fit(_FULL | _NEW_SESSION, 90) == (  # closer still
        "session: b1c2 │ model: claude-opus-5-5[1m] │ jail: jailed w✓n✓r✓e✓ │ usage: 12k/678 $0.12"
    )
    assert fit(_FULL | {"model": "default"}, 78) == (  # then the grades alone, then a cut
        "session: b1c2 ↻ │ model: default │ jail: jailed ✓✓✓✓ │ usage: 12k/678 $0.12"
    )
    assert fit(_FULL, 78) == "session: b1c2 ↻ │ model: claude-op… │ jail: jailed ✓✓✓✓ │ usage: 12k/678 $0.12"


def test_a_step_a_later_one_made_needless_is_undone_the_session_first() -> None:
    """80 columns, a new session, no usage yet: shortening the jail makes room for the whole id,
    so the id is not left shortened (its last part alone is less to go on)."""
    enforced = render.jail_forms(True, dict.fromkeys(("fs_write", "network", "fs_read", "env"), "enforced"))
    fields = {"session": ("20260923-011910-58d9", "58d9"), "model": "default", "jail": enforced}
    assert fit(fields, 78) == "session: 20260923-011910-58d9 │ model: default │ jail: jailed w✓ n✓ r✓ e✓"
    with_usage = fields | {"usage": frame.usage_forms(frame.Usage(1234, 56, 0.01))}
    assert fit(with_usage, 118) == (  # the whole id here would be 121 cells: its short form stays
        "session: 58d9 │ model: default │ jail: jailed fs_write ✓ network ✓ fs_read ✓ env ✓ │ "
        "usage: 1.2k/56 $0.01"
    )


def test_at_120_columns_the_jail_s_grades_keep_their_axes_beside_usage() -> None:
    fields = {
        "session": ("20260923-004247-3ccd (resumed)", "3ccd ↻"),
        "model": "default",
        "jail": _JAIL_FORMS,
    }
    usage = {"usage": frame.usage_forms(frame.Usage(1234, 56, 0.01))}
    assert f"jail: {_JAIL}" in fit(fields | usage, 118)
    assert "jail: unjailed w✗ n✗ r✗ e✗" in fit(fields | {"model": "claude-opus-5-5[1m]"} | usage, 110)


@pytest.mark.parametrize(
    ("width", "kept"),
    [(60, ["session", "model", "jail"]), (40, ["model", "jail"]), (10, ["jail"])],
)
def test_too_narrow_even_shortened_drops_the_session_first_but_never_the_jail(
    width: int, kept: list[str]
) -> None:
    line = fit(_FIELDS, width)
    assert [field for field in ("session", "model", "jail") if f"{field}: " in line] == kept
    assert "jail: unjailed ✗✗✗✗" in line
    assert ("a1b2 ↻" in line) is ("session" in kept)


def test_a_status_line_that_fits_is_left_whole() -> None:
    fields = {"jail": _JAIL_FORMS, "session": "20260922-1"}
    assert fit(fields, 200) == f"session: 20260922-1  │  jail: {_JAIL}"
    resumed = {"session": "20260922-1 (resumed)", "jail": _JAIL_FORMS}
    assert fit(resumed, 42) == "session: 20260922-1… │ jail: unjailed ✗✗✗✗"  # cut at a word's end


async def test_the_status_bar_refits_when_the_screen_narrows() -> None:
    app = BhApp()
    async with app.run_test(size=(140, 30)) as pilot:
        app.frame.status("jail", *_JAIL_FORMS)
        app.frame.status("session", "20260922-143015-a1b2 (resumed)", "a1b2 ↻")
        await pilot.pause()
        bar = app.query_one(StatusBar)
        assert "(resumed)" in str(bar.content)
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        assert f"jail: {_JAIL}" in str(bar.content) and "a1b2 ↻" in str(bar.content)
        assert cell_len(str(bar.content)) <= bar.content_size.width
