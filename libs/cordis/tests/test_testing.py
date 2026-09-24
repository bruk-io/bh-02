"""`cordis.testing.drive`: a component's effects, read off it without a runtime."""

from typing import Any

import pytest

from cordis import Effects, bind, component, effect
from cordis.testing import drive


def note(ctx: object, text: str) -> tuple[str, None]:
    return text.upper(), None


@component
async def greeter(*, name: str) -> Effects:
    shouted: str = yield effect(note, name)
    yield bind("greeting", f"hello {shouted}")


async def test_drive_returns_the_effects_in_order_and_feeds_replies_back() -> None:
    effects = await drive(greeter(name="ada"), replies=["ADA"])
    assert [e.name for e in effects] == ["note", "bind"]
    assert effects[1].args == ("greeting", "hello ADA")


async def test_drive_answers_none_once_the_script_runs_out() -> None:
    effects = await drive(greeter(name="ada"))
    assert effects[1].args == ("greeting", "hello None")


async def test_drive_refuses_a_component_that_yields_a_non_effect() -> None:
    @component
    async def wrong() -> Effects:
        yield "not an effect"  # type: ignore[misc]

    with pytest.raises(TypeError, match="yielded a str"):
        await drive(wrong())


async def test_drive_a_plugin_component_with_fakes(plugin: Any) -> None:
    effects = await drive(plugin.git_tools(git=plugin.GitClient("git", plugin.FakeSubprocess("clean\n"))))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "git_status")]
    assert await effects[0].args[1]() == "clean\n"  # the bound callable, with its dependency
