"""A module planted in the workload's working directory runs in none of brig's host-side
programs: SPEC.md section 8, decision-169 (TASK-0075).

The launch runs one jail through every interpreter brig starts on the host: the exit wrapper
(`python -c`), the tether's watcher it starts (`python -c`), the rlimits trampoline (`python -m
brig.trampoline`, outermost) and the egress proxy (`python -m brig.proxy`, a
`JAIL_LIFETIME` helper), each started in the workload's directory. That directory holds a
planted `subprocess.py`, `signal.py` and `brig/` package, each of which, imported, appends its
name to a record outside the directory and then hands its importer the real module (so a plant
that ran shows in the record, not as a launch that broke). Before decision-169 the record read
`signal`, `subprocess` and `brig`, each from a process outside any jail.

THE CONTROL, in the same test: an interpreter started the way brig's were before the ruling
(no `-I`, in the same directory) imports every plant, so the empty record is the flag working,
not plants that could never have run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from brig.core import Limits, NetworkPolicy, Spec
from brig.mech import CompileCtx
from brig.mech.connect_proxy import ConnectProxy
from brig.mech.rlimits import rlimits
from brig.run import IoPolicy, Jail, Process
from brig.stack import Stack
from tests.conftest import NewJailDir, launch, teardown_group, workload_argv

pytestmark = pytest.mark.integration


#: Imported, a plant records its name and pid, then loads the real module from the path
#: without the planted directory and leaves that in `sys.modules`, which is what the import
#: statement that found the plant returns.
_PLANT = """\
import importlib.machinery, importlib.util, os, sys
with open({record!r}, "a") as _record:
    _record.write(f"{{__name__}} {{os.getpid()}}\\n")
_path = [p for p in sys.path if os.path.realpath(p or ".") != {root!r}]
_spec = importlib.machinery.PathFinder.find_spec(__name__, _path)
_real = importlib.util.module_from_spec(_spec)
sys.modules[__name__] = _real
_spec.loader.exec_module(_real)
"""


def _plant(root: str, record: str) -> None:
    source = _PLANT.format(record=record, root=root)
    Path(root, "subprocess.py").write_text(source)
    Path(root, "signal.py").write_text(source)
    Path(root, "brig").mkdir()
    Path(root, "brig", "__init__.py").write_text(source)


def _planted_that_ran(record: str) -> list[str]:
    try:
        return sorted(line.split()[0] for line in Path(record).read_text().splitlines())
    except FileNotFoundError:
        return []


def _group_has_ended(pgid: int, within: float = 10.0) -> bool:
    """The group has no live member, per `/bin/ps` (a zombie counts as ended: where PID 1 does
    not reap, an orphaned watcher stays one)."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        rows = subprocess.run(
            ["/bin/ps", "-Ao", "pgid=,stat="], capture_output=True, text=True, check=True
        ).stdout.split("\n")
        live = [
            r for r in rows if r.split()[:1] == [str(pgid)] and not r.split()[1].startswith("Z")
        ]
        if not live:
            return True
        time.sleep(0.05)
    return False


def test_a_module_planted_in_the_workload_s_directory_runs_in_no_host_side_program(
    run_id: str, new_jail_dir: NewJailDir
) -> None:
    # The workload's directory (planted), one for the record, and the jail directory.
    root, elsewhere, jail_dir = new_jail_dir(), new_jail_dir(), new_jail_dir()
    record = os.path.join(elsewhere, "ran")
    _plant(root, record)
    spec = Spec(
        limits=Limits(cpu_seconds=60), network=NetworkPolicy(allowed_domains=("localhost",))
    )
    ctx = CompileCtx(jail_dir=jail_dir, platform=sys.platform)
    compiled = Stack([rlimits, ConnectProxy(sys.executable)]).compile(spec, ctx=ctx)
    tether_read, tether_write = os.pipe()
    launched: tuple[Jail, Process] | None = None
    try:
        launched = launch(
            compiled,
            argv=workload_argv(run_id, f"printf ran > {jail_dir}/workload"),
            cwd=root,
            io=IoPolicy(),
            jail_id="host-interpreters-isolated",
            jail_dir=jail_dir,
            tether=tether_read,
        )
        jail, process = launched
        assert process.wait(timeout=30.0) == 0, Path(process.stderr_path).read_text()
        # The workload ran behind the trampoline and the proxy's published port, so both
        # programs got past their imports.
        assert Path(jail_dir, "workload").read_text() == "ran"
        # The watcher ends its group once the tether's last write end closes, past its imports.
        os.close(tether_write)
        tether_write = -1
        assert _group_has_ended(process._record.pgid), "the tether's watcher did not end its group"

        ran = _planted_that_ran(record)
        assert ran == [], f"planted modules imported on the host: {ran}"
    finally:
        os.close(tether_read)
        if tether_write != -1:
            os.close(tether_write)
        if launched is not None:
            launched[0].destroy()
            teardown_group(launched[1])

    # THE CONTROL: no `-I`, the same directory, and every plant runs.
    for argv in (
        [sys.executable, "-c", "import subprocess"],
        [sys.executable, "-m", "brig.trampoline", "--", "true"],
    ):
        subprocess.run(argv, cwd=root, check=True)
    assert set(_planted_that_ran(record)) == {"brig", "signal", "subprocess"}
