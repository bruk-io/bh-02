"""managed_process against a real subprocess: spawn, then terminate on exit."""

import os

from warden_cordis_plugin.process import managed_process


async def test_spawns_the_command_and_terminates_it_on_exit() -> None:
    async with managed_process(("sleep", "5")) as process:
        pid = process.pid
        os.kill(pid, 0)  # raises if no process with this pid exists
    assert not _alive(pid)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
