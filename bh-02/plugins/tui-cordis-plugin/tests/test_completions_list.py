"""Under Pilot: the composer's list of commands (decision-0003): what it shows, the keys it
takes while open, when it opens and closes, and that it reads the commands once per opening."""

import asyncio
from collections.abc import Mapping
from typing import Any

from textual.command import CommandPalette
from textual.content import Content
from textual.pilot import Pilot

from tui_cordis_plugin import BhApp, frame
from tui_cordis_plugin.messages import Asked, Shown, TurnEnded, TurnStarted
from tui_cordis_plugin.widgets import ApprovalScreen, Completions, Composer, Transcript
from tui_cordis_plugin.widgets.completions import row

_SIZE = (100, 30)


class _Models:
    """A `/model` spec whose `choices` counts its calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.names = ["haiku", "opus"]

    def choices(self) -> list[dict[str, str]]:
        self.calls += 1
        return [{"args": name, "help": f"switch to {name}"} for name in self.names]


def _specs(models: _Models) -> list[Mapping[str, Any]]:
    return [
        {"name": "model", "help": "show or switch the model", "usage": "[NAME]", "choices": models.choices},
        {"name": "agents", "help": "the agents", "usage": "[stop NAME]"},
        {"name": "clear", "help": "start afresh", "usage": ""},
    ]


async def _open(pilot: Pilot[None], models: _Models | None = None) -> _Models:
    """Push the specs into the app's frame and let the composer take focus."""
    models = models or _Models()
    pilot.app.frame.commands(lambda: _specs(models))
    await pilot.pause()
    return models


def _listed(app: BhApp) -> list[str]:
    return [e.call for e in app.query_one(Completions).shown]


def _composer(app: BhApp) -> Composer:
    return app.query_one(Composer)


async def _line(app: BhApp) -> str:
    """The next line sent to the input, as the broker reads it (stripped)."""
    return (await asyncio.wait_for(app.bridge.line(), 1)).strip()


async def _no_line(app: BhApp) -> None:
    """Nothing was sent to the input."""
    await asyncio.sleep(0.1)
    assert not app.bridge.kept


async def test_a_slash_shows_the_matching_commands_between_the_transcript_and_the_composer() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press("/")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert listed.display and _listed(app) == [
            "/model", "/model haiku", "/model opus", "/agents", "/clear", "/help", "/exit",
        ]  # fmt: skip
        assert app.query_one(Transcript).region.bottom <= listed.region.y
        assert listed.region.bottom <= _composer(app).region.y
        await pilot.press("m", "o")
        await pilot.pause()
        assert _listed(app) == ["/model", "/model haiku", "/model opus"]
        assert isinstance(app.focused, Composer)  # the composer keeps the keys


async def test_a_line_that_is_not_a_one_line_slash_shows_nothing() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"hello /mo")
        await pilot.pause()
        assert not app.query_one(Completions).display
        _composer(app).text = ""
        await pilot.press("/", "m", "ctrl+j", "x")  # a second line closes it
        await pilot.pause()
        assert not app.query_one(Completions).display


async def test_arguments_are_listed_through_choices_and_the_rows_are_one_line_each() -> None:
    app = BhApp()
    async with app.run_test(size=(40, 30)) as pilot:
        await _open(pilot)
        await pilot.press(*"/model h")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert _listed(app) == ["/model haiku"]
        _composer(app).text = "/"  # every entry, at 40 columns
        await pilot.pause()
        assert listed.region.height == len(listed.shown)  # no row wraps at 40 columns
        for index in range(len(listed.shown)):
            assert row(listed.shown[index], 38).cell_length <= 38


def test_a_row_is_plain_text_cut_with_an_ellipsis_with_the_help_dimmed() -> None:
    entry = frame.PaletteEntry("/model", "[bold]show[/] or switch the model " * 3, "[NAME]")
    whole = row(entry, 400)
    assert isinstance(whole, Content) and whole.plain.startswith("/model [NAME]  [bold]show[/]")
    assert any(span.style == "dim" for span in whole.spans)
    cut = row(entry, 30)
    assert cut.cell_length <= 30 and cut.plain.endswith("…")


async def test_eight_entries_on_a_short_terminal_leave_the_transcript_its_newest_line() -> None:
    app = BhApp()
    async with app.run_test(size=(80, 15)) as pilot:
        app.frame.commands(lambda: [{"name": f"cmd{n}", "help": "x", "usage": ""} for n in range(12)])
        for n in range(30):
            app.post_message(Shown({"type": "text", "text": f"line {n}\n\n"}))
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert listed.region.height == 8
        transcript = app.query_one(Transcript)
        assert transcript.region.height >= 1
        assert transcript.max_scroll_y - transcript.scroll_y <= 1  # the newest line stays in view


async def test_tab_completes_without_running_and_focus_stays() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"/mo", "tab")
        await pilot.pause()
        assert _composer(app).text == "/model "
        assert isinstance(app.focused, Composer)
        await _no_line(app)
        assert _listed(app) == ["/model haiku", "/model opus"]  # the model's choices


async def test_tab_with_the_list_closed_moves_focus_as_before() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press("a")
        assert _composer(app).text == "a"
        await pilot.press("tab")
        await pilot.pause()
        assert _composer(app).text == "a"  # Tab was not typed
        assert app.focused is not _composer(app)  # it moved focus off the composer


async def test_enter_on_a_prefix_takes_the_highlight_and_a_command_with_arguments_gets_a_space() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"/mo", "enter")
        await pilot.pause()
        assert _composer(app).text == "/model "
        assert _listed(app) == ["/model haiku", "/model opus"]
        await _no_line(app)


async def test_enter_runs_a_command_typed_as_a_strict_prefix() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"/he", "enter")
        assert await _line(app) == "/help"
        await pilot.pause()
        assert _composer(app).text == ""
        assert not app.query_one(Completions).display


async def test_enter_sends_what_was_typed_when_it_is_not_a_strict_prefix_of_the_highlight() -> None:
    """The Enter rule: typed text is never replaced by an entry the person did not pick."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"/model", "enter")  # an exact call: it lists the models
        assert await _line(app) == "/model"
        await pilot.press(*"/model ", "enter")  # a trailing space, no argument
        assert await _line(app) == "/model"
        await pilot.press(*"/model h", "enter")  # prefixes a choice: sent as typed
        assert await _line(app) == "/model h"
        await pilot.press(*"/agents stop general-2", "enter")  # the list knows nothing of it
        assert await _line(app) == "/agents stop general-2"


async def test_down_then_enter_takes_the_choice_and_up_moves_back() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"/model ", "down", "up", "down", "enter")
        assert await _line(app) == "/model opus"
        await pilot.press(*"/model h", "down", "enter")  # moved: takes /model haiku? the list has it only
        assert await _line(app) == "/model haiku"


async def test_escape_closes_the_list_for_the_line_and_the_text_area_never_sees_it() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press(*"/mo", "escape")
        await pilot.pause()
        assert _composer(app).text == "/mo" and not app.query_one(Completions).display
        await pilot.press("d")  # the line changes: still the same line, so it stays shut
        await pilot.pause()
        assert not app.query_one(Completions).display
        _composer(app).text = ""
        await pilot.pause()
        await pilot.press("/")  # it stopped being a / line: it opens again
        await pilot.pause()
        assert app.query_one(Completions).display


async def test_a_new_line_closes_the_list_whichever_key_makes_it() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        for key in ("ctrl+j", "shift+enter"):
            _composer(app).text = ""
            await pilot.press("/")
            await pilot.pause()
            assert app.query_one(Completions).display
            await pilot.press(key)
            await pilot.pause()
            assert not app.query_one(Completions).display
            assert "\n" in _composer(app).text


async def test_a_click_on_a_row_runs_it_and_the_composer_keeps_focus() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press("/")
        await pilot.pause()
        index = _listed(app).index("/clear")
        await pilot.click(Completions, offset=(4, index))
        assert await _line(app) == "/clear"
        assert isinstance(app.focused, Composer)
        assert _composer(app).text == ""


async def test_the_list_never_takes_focus() -> None:
    assert Completions.can_focus is False
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press("/")
        await pilot.pause()
        await pilot.click(Completions, offset=(4, 1))
        await pilot.pause()
        assert not any(isinstance(w, Completions) for w in (app.focused,))
        assert isinstance(app.focused, Composer)


async def test_a_question_closes_the_list_and_none_opens_while_one_is_up() -> None:
    app = BhApp(grace=0.05)
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press("/")
        await pilot.pause()
        assert app.query_one(Completions).display
        answer = app.bridge.question()
        assert answer is not None
        app.post_message(Asked({"tool": "bash", "input": {"command": "ls"}}, answer))
        await pilot.pause(0.1)
        assert isinstance(app.screen, ApprovalScreen) and not app.query_one(Completions).display
        _composer(app).text = "/mo"  # typed while a question is up
        await pilot.pause()
        assert not app.query_one(Completions).display
        await pilot.press("n")  # the answer: no
        await pilot.pause(0.1)
        assert await answer is False and not app.asking
        assert not app.query_one(Completions).display  # not reopened until the text changes
        assert isinstance(app.focused, Composer)
        _composer(app).text = "/m"
        await pilot.pause()
        assert app.query_one(Completions).display


async def test_the_palette_over_an_open_list_closes_it_and_its_choice_opens_the_arguments() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause(0.1)
        assert isinstance(app.screen, CommandPalette) and not app.query_one(Completions).display
        await pilot.press(*"model", "enter")  # `/model` takes arguments: it goes in the composer
        await pilot.pause(0.2)
        assert _composer(app).text == "/model " and isinstance(app.focused, Composer)
        assert _listed(app) == ["/model haiku", "/model opus"]


async def test_choices_are_read_once_per_opening_and_not_per_key() -> None:
    """The snapshot per opening: planted as a read per key, this fails."""
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        models = await _open(pilot)
        await pilot.press(*"/model hai")
        await pilot.pause()
        assert models.calls == 1
        models.names.append("sonnet")  # added meanwhile: the open list does not read again
        await pilot.press("z")
        await pilot.pause()
        assert models.calls == 1 and _listed(app) == []
        _composer(app).text = ""  # closed, and the next opening reads again
        await pilot.press(*"/model s")
        await pilot.pause()
        assert models.calls == 2 and _listed(app) == ["/model sonnet"]


async def test_commands_changing_while_open_are_not_read_and_a_gone_one_is_sent_as_chosen() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        specs: list[Mapping[str, Any]] = []
        await pilot.press(*"/cl")
        await pilot.pause()
        app.frame.commands(lambda: specs)  # every command gone since the list opened
        await pilot.press("e")
        await pilot.pause()
        assert _listed(app) == ["/clear"]
        await pilot.press("enter")  # `/cle` is a strict prefix: it takes the stale entry
        assert await _line(app) == "/clear"  # the chat row answers it as an unknown command


async def test_enter_on_an_entry_while_a_reply_streams_is_drawn_after_the_reply() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        await _open(pilot)
        app.post_message(TurnStarted())
        app.post_message(Shown({"type": "text", "text": "streaming"}))
        await pilot.pause()
        await pilot.press(*"/he", "enter")
        await pilot.pause()
        transcript = app.query_one(Transcript)
        assert ("user", "› /help") not in transcript.blocks()  # held until the reply ends
        assert await _line(app) == "/help"
        app.post_message(TurnEnded())
        await pilot.pause()
        assert transcript.blocks()[-1] == ("user", "› /help")


async def test_a_command_text_is_shown_as_text_and_its_control_characters_are_not() -> None:
    app = BhApp()
    async with app.run_test(size=_SIZE) as pilot:
        app.frame.commands(
            lambda: [{"name": "odd\x1bname", "help": "[red]not markup[/]\x07", "usage": "[ARG]"}]
        )
        await pilot.pause()
        await pilot.press("/", "o")
        await pilot.pause()
        listed = app.query_one(Completions)
        assert [e.call for e in listed.shown] == ["/oddname"]
        prompt = listed.get_option_at_index(0).prompt
        assert isinstance(prompt, Content)
        assert prompt.plain.startswith("/oddname [ARG]") and "[red]not markup[/]" in prompt.plain
        assert "\x1b" not in prompt.plain and "\x07" not in prompt.plain
