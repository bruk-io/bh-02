"""/restart over a real loader: the rows that run it must survive it (TASK-0185)."""

import asyncio
from collections.abc import Callable

from cordis import Effects, bind, boot, component
from cordis.composition import Row


class _Output:
    def __init__(self) -> None:
        self.notices: list[str] = []

    async def notice(self, message: str) -> None:
        self.notices.append(message)


@component(provides=("input", "output"))
async def _ui() -> Effects:
    yield bind("output", _Output())
    yield bind("input", object())


async def _settled(read: Callable[[], dict[str, str]], want: dict[str, str]) -> dict[str, str]:
    """The loader's status once it equals `want`, or what it is after a second."""
    status: dict[str, str] = {}
    for _ in range(50):
        status = read()
        if status == want:
            break
        await asyncio.sleep(0.02)
    return status


async def test_restarting_the_ui_or_jobs_never_leaves_a_row_unmounted() -> None:
    booted = await boot(
        [],
        overrides=[
            Row("commands", "commands_cordis_plugin.wiring:registry"),
            Row("ui", f"{__name__}:_ui"),
            Row("jobs", "commands_cordis_plugin.wiring:jobs"),
            Row("operator", "commands_cordis_plugin.wiring:operator"),
        ],
        watch=None,
    )
    rt, loader = booted.runtime, booted.loader
    every_row_up = {rid: "active" for rid in ("commands", "ui", "jobs", "operator")}
    assert await _settled(loader.status, every_row_up) == every_row_up
    for line in ("/restart ui", "/restart jobs"):
        answer = await rt.root.get("commands").run(line)
        assert isinstance(answer, str) and "is refused" in answer, line
        await asyncio.sleep(0.2)
        assert await _settled(loader.status, every_row_up) == every_row_up, line
        assert rt.root.get("output") is not None, line
    await rt.root.get("commands").run("/restart operator")  # a row nothing in jobs' chain needs restarts
    await asyncio.sleep(0.2)
    assert await _settled(loader.status, every_row_up) == every_row_up
    await rt.shutdown()
