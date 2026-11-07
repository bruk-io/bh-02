"""decision-207 (TASK-0197), against the real darwin sandbox kernel: a
directory between a write root and a carve-out can't be renamed away or
renamed over, and stays as writable as the rest of the root otherwise.

SBPL judges a rename by its source and destination paths only, so until the
pins a jailed process renamed the directory above a carve-out to a name of
its own, rewrote the denied file there, and renamed the directory back. The
pin is `(deny file-write-unlink (literal PIN))`; this file measures the two
refusals it is for and, in the same jail, the control: creating, writing
and removing entries inside a pin, `chmod` and `utimes` on it all still
succeed, so a jail that refused everything would not pass it.

Darwin-gated at module level, visible skip reason, as every other seatbelt
integration file here.
"""

from __future__ import annotations

import os
import sys

import pytest

from brig.core import FsPolicy, Spec
from brig.mech.seatbelt import seatbelt
from brig.run import IoPolicy
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import Stack
from tests.conftest import NewJailDir, launch

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="seatbelt/sandbox-exec is darwin-only (SPEC.md Sec.6's seatbelt roster row)",
)

#: Each step, run inside the jail: a label and a statement. The program prints
#: `label:OK` or `label:DENIED:<strerror>` for each.
_PROGRAM = """\
import os
def attempt(label, step):
    try:
        step()
        print(f'{{label}}:OK')
    except OSError as error:
        print(f'{{label}}:DENIED:{{error.strerror}}')
w = {workspace!r}
attempt('rename_away', lambda: os.rename(f'{{w}}/xdg', f'{{w}}/moved'))
attempt('rename_over', lambda: os.rename(f'{{w}}/mine', f'{{w}}/empty'))
attempt('mkdir_inside', lambda: os.mkdir(f'{{w}}/xdg/new'))
attempt('write_inside', lambda: open(f'{{w}}/xdg/new/f', 'w').write('x'))
attempt('remove_inside', lambda: (os.unlink(f'{{w}}/xdg/new/f'), os.rmdir(f'{{w}}/xdg/new')))
attempt('chmod_pin', lambda: os.chmod(f'{{w}}/xdg', 0o700))
attempt('utime_pin', lambda: os.utime(f'{{w}}/xdg'))
attempt('carve_out', lambda: open(f'{{w}}/xdg/bh-02/startup.py', 'w').write('MARK = 2'))
"""


@pytest.mark.integration
def test_a_pin_refuses_a_rename_away_and_over_it_and_nothing_else(
    new_jail_dir: NewJailDir,
) -> None:
    """`xdg` is between the root and the carve-out `xdg/bh-02`; `empty` is an
    existing, empty directory above the carve-out `empty/bh-02`. Renaming
    `xdg` away, or a directory of the workload's own over `empty`, is refused
    with seatbelt's denial signature; every ordinary write on and in `xdg`
    succeeds; the carve-out's own file stays unwritable, and unchanged."""
    pattern = seatbelt.compile(
        Spec(), build_compile_ctx(Spec(), jail_dir=new_jail_dir(), platform="darwin")
    ).denial_signatures[0]
    jail_dir = new_jail_dir()
    workspace = f"{jail_dir}/workspace"
    os.makedirs(f"{workspace}/xdg/bh-02")
    os.makedirs(f"{workspace}/empty")
    os.makedirs(f"{workspace}/mine/bh-02")
    with open(f"{workspace}/xdg/bh-02/startup.py", "w", encoding="utf-8") as f:
        f.write("MARK = 1\n")
    spec = Spec(
        fs=FsPolicy(
            write_allows=(workspace,),
            write_denies=(f"{workspace}/xdg/bh-02", f"{workspace}/empty/bh-02"),
        )
    )
    jail = Stack([seatbelt]).compile(
        spec, ctx=build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    )
    jail, process = launch(
        jail,
        argv=[sys.executable, "-c", _PROGRAM.format(workspace=workspace)],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="seatbelt-pins",
        jail_dir=jail_dir,
    )
    status = process.wait()
    with open(process.stdout_path, encoding="utf-8", errors="replace") as f:
        said = dict(line.split(":", 1) for line in f.read().splitlines())
    assert status == 0, said

    for refused in ("rename_away", "rename_over", "carve_out"):
        assert said[refused].startswith("DENIED:"), (refused, said)
        assert pattern.search(said[refused]) is not None, (refused, said)
    for allowed in ("mkdir_inside", "write_inside", "remove_inside", "chmod_pin", "utime_pin"):
        assert said[allowed] == "OK", (allowed, said)
    assert os.path.isdir(f"{workspace}/xdg/bh-02") and not os.path.exists(f"{workspace}/moved")
    assert os.path.isdir(f"{workspace}/mine/bh-02")
    with open(f"{workspace}/xdg/bh-02/startup.py", encoding="utf-8") as f:
        assert f.read() == "MARK = 1\n"
