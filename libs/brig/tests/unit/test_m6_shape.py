"""M6 shape verification (task-082): what M6 actually added, pinned.

The M6 equivalent of task-055 (`test_m4_shape.py`) and task-068
(`test_m5_shape.py`). M6 shipped the egress story: `connect_proxy` the
mechanism, `brig/proxy/` the standalone filter process, the confined pairing
and its observer, and the matrix rows that let any of it compose.

What this file pins, and why each is the kind of claim that rots quietly:

1. The layer set is EXACTLY the six that exist. A seventh directory appearing
   under `brig/` fails here until someone writes down what it is.
2. `proxy`'s allow row is EMPTY -- decision-133's whole point. A row that
   silently gained an entry would let the filter import brig, and the
   "standalone process, not a layer" claim would become false while every
   other test stayed green.
3. No raising stub survives anywhere in the M6 surface. `Helper` and
   `HelperLifetime` sat declared-and-never-started since M2, which this
   repo's own CLAUDE.md names as its recurring defect; M6 is where they run.
4. The four mechanisms and their matrix rows are the complete square, so a
   pair added or dropped fails rather than being tolerated.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

import brig.stack

pytestmark = pytest.mark.unit

#: SPEC.md §13's layer set, as of M6. `proxy` joined at decision-133.
_LAYERS = {"core", "mech", "probe", "proxy", "run", "stack"}

#: The mechanisms that exist. `connect_proxy` joined at M6; `bwrap`
#: joined 2026-09-08 (decision-159), which is what takes the square below
#: from six pairs to ten -- including two that no stack can ever compose
#: (see their own rationales in `brig/stack/__init__.py`). A pair the
#: matrix cannot reach still needs a row, because `Stack.compile` refuses
#: an UNKNOWN pair and "unknown" is not the same claim as "impossible".
_MECHANISMS = {"env_scrub", "rlimits", "seatbelt", "connect_proxy", "bwrap"}


def _brig_root() -> Path:
    return Path(brig.stack.__file__).resolve().parents[1]


def _pyproject() -> dict[str, Any]:
    """The workspace root pyproject, which owns `[tool.pypeeker.brig-layers]`.

    Phase 0 landed brig as `packages/brig` and moved the layer table up to the
    root, next to keel's own import table -- the module dir is three levels
    below it (`<root>/packages/brig/brig`).
    """
    text = (_brig_root().parents[1] / "pyproject.toml").read_text()
    parsed: dict[str, Any] = tomllib.loads(text)
    return parsed


def test_the_layer_set_is_exactly_the_six_that_exist() -> None:
    """AC #1a. Directories under `brig/`, compared as a SET -- so a new one
    fails here, and a deleted one fails too. M6 added `proxy` and nothing
    else; no `observe` layer was ever created despite the allow table
    carrying a row for it (see the next test)."""
    root = _brig_root()
    found = {
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(("_", "."))
    }
    assert found == _LAYERS, f"layer set drifted: {found ^ _LAYERS}"


def test_the_allow_table_sanctions_exactly_the_declared_rows() -> None:
    """AC #1b. The allow table is read from the live `pyproject.toml`, not
    quoted, because the claim here is about the CURRENT table rather than
    about drift from a baseline (`test_m5_shape.py` owns that comparison).

    `observe` is in the table and NOT on disk, deliberately: M4 declared the
    row and the layer was never built (decision recorded in
    `test_m4_shape.py`). Pinned so the discrepancy stays a known one.
    """
    allow = _pyproject()["tool"]["pypeeker"]["brig-layers"]["allow"]

    assert set(allow) == _LAYERS | {"observe"}
    assert allow["core"] == []
    assert allow["mech"] == ["core"]
    assert allow["stack"] == ["core", "mech"]
    assert allow["run"] == ["core", "mech", "stack"]


def test_the_proxy_row_is_empty_which_is_the_standalone_process_claim() -> None:
    """AC #1c / decision-133. `brig/proxy/` is a PROCESS, not a layer in the
    flow: it runs trusted-side, outside the jail, spawned per jail as a
    helper. The empty allow row IS that claim, mechanically.

    If this ever gains an entry, the egress filter can import brig and the
    "empty import row" language in decision-133, SPEC.md and
    `connect_proxy`'s own docstring all silently become false -- including
    the reason its denial-signature constant is duplicated rather than
    imported.
    """
    assert _pyproject()["tool"]["pypeeker"]["brig-layers"]["allow"]["proxy"] == []


def test_no_raising_stub_survives_in_the_m6_surface() -> None:
    """AC #2. `NotImplementedError` anywhere under the layers M6 touched.

    SPEC.md §2 law 2: a mechanism that cannot deliver REFUSES, with a named
    exception -- it does not raise a placeholder. The refusals M6 ships
    (`BrigUnavailable`, `NetworkUnsupported`, `PlatformUnsupported`,
    `HelperFailed`) are all named types, none of them this.
    """
    root = _brig_root()
    offenders = [
        f"{path.relative_to(root)}:{n}"
        for sub in ("proxy", "mech", "stack", "run")
        for path in (root / sub).rglob("*.py")
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if "NotImplementedError" in line
    ]
    assert offenders == [], offenders


def test_every_mechanism_pair_has_a_matrix_row_a_complete_square() -> None:
    """AC #1d. N mechanisms means N-choose-2 unordered pairs, and every one must
    be in `COMPATIBILITY_MATRIX` -- `Stack.compile` REFUSES an unknown pair,
    so a missing row is a preset that cannot compile, and an extra row is a
    composition nobody reasoned about.

    task-080/decision-135 added connect_proxy's three; this asserts the
    square is closed rather than that three were added, which is the claim
    that survives the next mechanism -- and it did survive it: decision-159
    added bwrap's four with no edit here beyond `_MECHANISMS` itself.
    """
    from itertools import combinations

    expected = {frozenset(pair) for pair in combinations(sorted(_MECHANISMS), 2)}
    assert set(brig.stack.COMPATIBILITY_MATRIX) == expected

    for pair, entry in brig.stack.COMPATIBILITY_MATRIX.items():
        assert entry.rationale.strip() != "", pair
        assert entry.outer in pair, (pair, entry.outer)
