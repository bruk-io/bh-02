"""`brig/core/events.py` stays pure: task-028 / decision-052 / decision-060.

Two claims, each falsifiable on its own:

1. The module imports nothing but the closed stdlib set below -- no clock,
   no I/O, no randomness, no subprocess. Parsed with `ast`, not imported,
   so a plant (e.g. `import time`) is caught even though `import time` by
   itself would import cleanly.
2. `EventKind`'s vocabulary is exactly the closed set SPEC.md §11 names --
   the two SENSOR kinds, and no others. It was six until decision-152
   (2026-09-08) deleted the per-jail event stream; the four lifecycle kinds
   existed only to be written into it.

This file is deliberately separate from `tests/unit/test_event_record.py`
so that file's test count is undisturbed by the move (task-028 AC #6).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from brig.core.events import EventKind

_CORE_EVENTS_PATH = Path(__file__).resolve().parents[2] / "src" / "brig" / "core" / "events.py"

#: The complete, closed set of top-level import module names `core/events.py`
#: may name. No clock ('time'), no I/O ('os'), no randomness, no subprocess.
_ALLOWED_TOP_LEVEL_IMPORT_MODULES = frozenset(
    {"__future__", "dataclasses", "enum", "types", "typing"}
)


def _top_level_imported_modules(source: str) -> set[str]:
    """The set of module names named by top-level `import`/`from ... import`
    statements in `source`. Only `tree.body` (module-level statements) is
    walked -- an import nested in a function or class is a different claim
    entirely and is not what this test is about."""
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


@pytest.mark.unit
def test_core_events_imports_only_the_closed_stdlib_set() -> None:
    """AC #2: set equality (not membership) against brig/core/events.py's
    top-level imports, so both an added clock import and a silently
    dropped one are loud."""
    actual = _top_level_imported_modules(_CORE_EVENTS_PATH.read_text())
    assert actual == _ALLOWED_TOP_LEVEL_IMPORT_MODULES, (
        f"brig/core/events.py imports outside the closed pure set. "
        f"Extra: {actual - _ALLOWED_TOP_LEVEL_IMPORT_MODULES}. "
        f"Missing: {_ALLOWED_TOP_LEVEL_IMPORT_MODULES - actual}."
    )


@pytest.mark.unit
def test_event_kind_vocabulary_is_exactly_the_sensor_kinds() -> None:
    """The pin's *subject* -- EventKind's closed vocabulary -- has survived
    every change to its membership: four M2 lifecycle kinds, then six with
    `LIMIT_TRIP` and `EXIT`, two after decision-152 (2026-09-08) deleted the
    per-jail event stream, and three since decision-157 (2026-09-08) gave the
    egress proxy's own decisions a reader. `SPAWN` is what
    `EventSource.known_at_compile()` returns (`env_scrub`,
    `connect_proxy`); `LIMIT_TRIP` is what `rlimits`'
    `EventSource.classify_exit()` returns; `EGRESS` is one allow/deny the
    proxy PROCESS made while the workload ran, read back by
    `brig/run/egress.py`. Every deleted member was a
    lifecycle record whose only reader read it back off the deleted file.
    Mutation pairing (task-036 AC #6, same posture as task-032's
    `KillItem.kind` set-equality pin): drop `LIMIT_TRIP`, re-run this test
    by name, watch it fail on the missing value; add a third member, watch
    it fail on the extra value; revert either way and confirm green."""
    assert {member.value for member in EventKind} == {"SPAWN", "LIMIT_TRIP", "EGRESS"}
