"""The chat row driven by hand: it owns one piece of work, and binds it as `done`."""

from chat_cordis_plugin.testing import Echo, Noted, Queued, Screen, Typed
from chat_cordis_plugin.wiring import converse
from cordis.testing import drive


async def test_the_chat_is_exactly_one_background_effect_bound_as_done() -> None:
    effects = await drive(
        converse(loop=Echo(), input=Typed(), output=Screen(), commands=Noted(), jobs=Queued())
    )
    assert [e.name for e in effects] == ["background", "bind"]
    assert effects[1].args[0] == "done"
    effects[0].args[0].close()  # the coroutine drive never ran
