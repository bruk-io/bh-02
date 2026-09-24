"""A layer file on disk, for the tests that boot one the way the CLI does."""

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def patch(tmp_path: Path) -> Callable[[str], Path]:
    written = 0

    def layer(text: str) -> Path:
        nonlocal written
        written += 1
        path = tmp_path / f"layer{written}.toml"
        path.write_text(text)
        return path

    return layer
