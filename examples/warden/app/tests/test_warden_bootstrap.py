"""Booting the shipped layer, and a patched one, the way the CLI does."""

import asyncio
import os

import pytest

from cordis import Row, boot
from warden import CompositionError, layers, run
from warden_cordis_plugin import Processes


async def test_the_shipped_layer_boots_and_supervises_a_process_until_cancelled() -> None:
    task = asyncio.create_task(run(layers()))
    await asyncio.sleep(0.2)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_shutting_down_terminates_every_registered_process() -> None:
    override = Row("example", config={"name": "example", "command": ["sleep", "5"]})
    booted = await boot([str(layer) for layer in layers()], [override])
    processes: Processes = booted.runtime.root.get("processes")
    process = processes.get("example")
    assert process is not None
    os.kill(process.pid, 0)  # still running
    await booted.runtime.shutdown()
    with pytest.raises(ProcessLookupError):
        os.kill(process.pid, 0)


async def test_a_second_process_registers_alongside_the_first() -> None:
    extra = Row("worker", "warden:supervised", {"name": "worker", "command": ["sleep", "5"]})
    booted = await boot([str(layer) for layer in layers()], [extra])
    try:
        processes: Processes = booted.runtime.root.get("processes")
        assert sorted(processes.names) == ["example", "worker"]
    finally:
        await booted.runtime.shutdown()


async def test_a_command_that_cannot_spawn_fails_the_composition() -> None:
    override = Row("example", config={"name": "example", "command": ["/no/such/warden-test-binary"]})
    with pytest.raises(CompositionError) as raised:
        await asyncio.wait_for(run(layers(), overrides=[override]), 2)
    assert "could not start" in raised.value.message
