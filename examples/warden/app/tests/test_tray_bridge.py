"""`run_with_tray`'s shutdown bridge, without AppKit: a fake `tray` row stands in for
`warden-systray:tray`, so these run on the test's own thread and never touch rumps.

`run_with_tray` blocks the calling thread on `_Tray.run()`; the fake's `run()` simulates an
immediate quit by calling `on_quit()` itself and returning, so these tests call
`run_with_tray` directly rather than driving anything interactively.
"""

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cordis import Row
from warden import CompositionError, layers
from warden.bootstrap import run_with_tray

# An importable module of a fake `tray` row: binds a factory the same shape `warden-systray:
# tray` does, but `run()` fires `on_quit` itself instead of opening a menu bar.
_FAKE_TRAY = """
from cordis import Effects, bind, component

captured: dict[str, object] = {}


class FakeApp:
    def __init__(self, processes):
        self._processes = processes
        self.on_quit = None

    def run(self):
        process = self._processes.get("example")
        captured["pid"] = process.pid if process is not None else None
        if self.on_quit is not None:
            self.on_quit()


@component(provides=("tray",))
async def app(*, processes):
    yield bind("tray", lambda: FakeApp(processes))
"""


@pytest.fixture
def fake_tray(tmp_path: Path) -> Iterator[Any]:
    (tmp_path / "faketray.py").write_text(_FAKE_TRAY)
    sys.path.insert(0, str(tmp_path))
    try:
        import faketray

        yield faketray
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("faketray", None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


def test_quitting_the_tray_shuts_down_and_terminates_the_supervised_process(fake_tray: Any) -> None:
    overrides = [
        Row("tray", "faketray:app"),
        Row("example", config={"name": "example", "command": ["sleep", "5"]}),
    ]
    run_with_tray(layers(), overrides)  # blocks until the fake's run() quits, above
    pid = fake_tray.captured["pid"]
    assert pid is not None
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_a_composition_that_cannot_start_raises_before_the_tray_ever_runs(fake_tray: Any) -> None:
    overrides = [
        Row("tray", "faketray:app"),
        Row("example", config={"name": "example", "command": ["/no/such/warden-test-binary"]}),
    ]
    with pytest.raises(CompositionError):
        run_with_tray(layers(), overrides)
    assert "pid" not in fake_tray.captured  # the fake's run() never got called
