"""The rlimits trampoline loads nothing of brig but itself (TASK-0079.21, decision-200).

`python -I -m brig.trampoline` runs outermost on the host, once per jail start, so what it
imports is a wait the jail's start pays for before bwrap begins. As `brig.mech.trampoline` it
imported the package `brig.mech` first, and that `__init__` imports every mechanism and
`brig.core`: 22ms of the program's 53. `brig-layers` keeps the program's own source to the
standard library (its row is empty); this is the other half, which no source scan sees: what a
*parent package's* `__init__` pulls in on the way to it. It is read from a real interpreter's
`sys.modules`, started the way the trampoline is (`-I`), beside a control that the same probe does
see brig's other packages load when they are asked for.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration

#: Prints each brig module the interpreter holds once `module` is imported, one per line.
_LOADED = (
    "import sys, {module}\nprint(*sorted(m for m in sys.modules if m.split('.')[0] == 'brig'))"
)


def _brig_modules_loaded_by(module: str) -> set[str]:
    done = subprocess.run(
        [sys.executable, "-I", "-c", _LOADED.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return set(done.stdout.split())


def test_running_the_trampoline_loads_brig_and_the_trampoline_and_nothing_else() -> None:
    """The entry point `-m` runs is the package's `__main__`: importing it (it does nothing
    until run as `__main__`) loads exactly the parents it needs, `brig` and `brig.trampoline`."""
    assert _brig_modules_loaded_by("brig.trampoline.__main__") == {
        "brig",
        "brig.trampoline",
        "brig.trampoline.__main__",
    }


def test_the_probe_sees_a_mechanism_package_load_everything_under_it() -> None:
    """THE CONTROL: the same probe, asked for `brig.mech.rlimits`, sees `brig.mech`'s `__init__`
    load every mechanism and `brig.core`, which is what the trampoline used to pay for. Without
    this the test above could pass because the probe reads nothing."""
    loaded = _brig_modules_loaded_by("brig.mech.rlimits")
    assert {"brig.mech.bwrap", "brig.mech.seatbelt", "brig.core.spec"} <= loaded
