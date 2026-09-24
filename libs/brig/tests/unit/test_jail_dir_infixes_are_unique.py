"""No two test files may mint jail directories from the same infix or tag.

Integration and system tests each mint scratch jail directories shaped
`/tmp/bg{os.getpid()}<INFIX><counter>` with a per-file counter; the infix is
what keeps one file's directories from colliding with another's in a single
pytest process (same pid, independent counters -> identical paths). Nothing
enforced that the infixes were distinct: `test_seatbelt_smoke.py` and
`test_handle_signature_book.py` both used `sb`, found by hand and fixed by
hand (smoke now uses `sk`). This test makes the class impossible to
reintroduce.

Parsing rule (task-074): for every occurrence of the literal
`/tmp/bg{os.getpid()}`, capture the literal characters immediately after it,
up to the next `{` or quote -- that is the file's STATIC infix for that
occurrence. An EMPTY capture means no static infix exists and a dynamic
disambiguator follows the pid directly -- `{tag}{run_id[:8]}` in six files.
Those are NOT exempt, they are checked on their `tag` instead, because
`run_id` does not disambiguate them: `tests/conftest.py`'s `run_id` fixture is
`scope="session"`, ONE token for the whole pytest process, not per test. An
earlier version of this pin claimed it was a per-test `uuid4().hex` and
exempted the whole dynamic group on that basis; the claim was false and the
exemption was hiding a live collision -- `test_probe_runner.py` and
`test_battery_targets.py` both minted `/tmp/bg{pid}ws{run_id[:8]}0` from
independent counters in the same integration run. Same pid, same session
token, same tag, counters both starting at zero: byte-identical paths, the
exact `sb` class this file exists to close.

A non-empty static infix must be used by at most ONE file; the failure names
the infix and every colliding file. Pure: reads source text only -- no
subprocess, no network, no clock (.claude/rules/unit-tests.md).
"""

from __future__ import annotations

import pathlib
import re

import pytest

_TESTS_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCANNED_DIRS = (_TESTS_ROOT / "integration", _TESTS_ROOT / "e2e")
_MARKER = "/tmp/bg{os.getpid()}"


def _static_infixes(source: str) -> list[str]:
    """Every NON-EMPTY static infix minted after `_MARKER` in `source`.

    Each capture runs from just past the marker to the next `{` (a new
    interpolation -- dynamic, not part of the static infix) or the closing
    quote (end of the literal). Empty captures are dropped: see the module
    docstring for why they cannot collide."""
    infixes: list[str] = []
    start = 0
    while (idx := source.find(_MARKER, start)) != -1:
        infix = ""
        for ch in source[idx + len(_MARKER) :]:
            if ch == "{" or ch in "\"'":
                break
            infix += ch
        if infix:
            infixes.append(infix)
        start = idx + len(_MARKER)
    return infixes


def _dynamic_tags(source: str) -> list[str]:
    """Every literal tag passed to a `_new_root(run_id, "<tag>")`-shaped call.

    These files carry no static infix -- the tag is the only per-file part of
    the path, since `run_id` is session-scoped and the counter restarts at
    zero in every file. So the tag must be unique across files for exactly
    the reason a static infix must be."""
    return re.findall(r"_new_root\(\s*run_id\s*,\s*[\"']([^\"']+)[\"']", source)


@pytest.mark.unit
def test_no_two_test_files_share_a_jail_dir_infix() -> None:
    users: dict[str, set[str]] = {}
    for directory in _SCANNED_DIRS:
        for path in sorted(directory.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for infix in _static_infixes(source) + _dynamic_tags(source):
                users.setdefault(infix, set()).add(path.name)
    collisions = {infix: files for infix, files in users.items() if len(files) > 1}
    assert not collisions, (
        "jail-dir infix collision -- these files mint identical "
        "/tmp/bg{pid}<infix><counter> paths from independent counters in one "
        "pytest process: "
        + "; ".join(
            f"infix {infix!r}: {', '.join(sorted(files))}"
            for infix, files in sorted(collisions.items())
        )
    )
