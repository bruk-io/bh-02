"""decision-173 in a real bubblewrap jail: a write root ABOVE the jail
directory does not let the workload write brig's control state there.

Found by an embedder (TASK-0078): run with its working directory at `/tmp`, the
project's write root covered `/tmp/bh-j-*`, and a jailed input wrote an exec
registration, the jail's exit file and `<jail_dir>/x`, all seen on the host.
This plants the same writes against today's layout (decision-181: a record
under `<jail_dir>/procs/`, the running process's own exit record, and `x`)
from inside a jail whose one write root is the jail directory's parent, made in a scratch directory of this test's own
(nothing lands in `/tmp`'s top level but that directory, removed after).

The claim and its controls are one run of one jailed `/bin/sh`: the writes into
the jail directory are refused with the mechanism's own `Read-only file system`
signature and nothing reaches the host, while a write in its scratch `tmp/`
and one beside it in the write root both land, and the exit status `wait()`
reads (from the exit record in that same jail directory) is the workload's.
Observed on the host with `os.path`, never through brig.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator

import pytest

from brig.core import FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run import IoPolicy
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import Stack
from tests.conftest import launch

_WAIT_TIMEOUT_S = 30.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")


@pytest.fixture(autouse=True)
def _needs_bubblewrap() -> None:
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"bwrap needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )


@pytest.fixture
def outer() -> Iterator[str]:
    """The write root: a fresh directory holding the jail directory."""
    path = tempfile.mkdtemp(prefix="bg-seal-")
    try:
        yield path
    finally:
        shutil.rmtree(path)


#: Each attempt prints its token only when the write succeeded. The rename
#: puts the directory straight back, so an unsealed jail still ends cleanly.
_SCRIPT = """
J="$1"; OUTER="$2"
mkdir "$J/procs/0123456789abcdef" && echo MADE_RECORD
echo '{"pid": 1, "pgid": 1, "start_time": ""}' > "$J/procs/0123456789abcdef/record.json" && echo WROTE_RECORD
for d in "$J"/procs/*/; do echo 0 > "$d/exit" && echo WROTE_EXIT; done
echo x > "$J/x" && echo WROTE_X
mv "$J" "$J-moved" && mv "$J-moved" "$J" && echo MOVED_JAIL_DIR
echo ok > "$J/tmp/scratch" && echo SCRATCH
echo ok > "$OUTER/beside" && echo BESIDE
exit 3
"""

_FORGED = ("MADE_RECORD", "WROTE_RECORD", "WROTE_EXIT", "WROTE_X", "MOVED_JAIL_DIR")


@pytest.mark.integration
def test_a_write_root_above_the_jail_directory_cannot_write_it(outer: str) -> None:
    jail_dir = os.path.join(outer, "jail")
    os.makedirs(os.path.join(jail_dir, "tmp"))
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
            write_allows=(outer,),
        )
    )
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    signature = bwrap.compile(spec, ctx).denial_signatures[0]
    compiled = Stack([bwrap]).compile(spec, ctx=ctx)
    _jail, process = launch(
        compiled,
        argv=["/bin/sh", "-c", _SCRIPT, "sh", jail_dir, outer],
        cwd=outer,
        io=IoPolicy(),
        jail_id="bwrap-jail-dir-sealed",
        jail_dir=jail_dir,
    )
    status = process.wait(timeout=_WAIT_TIMEOUT_S)
    with open(process.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()
    with open(process.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr = f.read()

    forged = [token for token in _FORGED if token in stdout]
    assert not forged, f"the jail wrote its own jail directory: {forged}\n{stderr}"
    assert signature.search(stderr) is not None, stderr
    assert not os.path.exists(os.path.join(jail_dir, "procs", "0123456789abcdef"))
    assert not os.path.exists(os.path.join(jail_dir, "x"))
    # The controls, same jail, same run: the scratch and the write root beside
    # the jail directory are written, and the exit record is the workload's.
    assert "SCRATCH" in stdout and "BESIDE" in stdout, (stdout, stderr)
    with open(os.path.join(jail_dir, "tmp", "scratch"), encoding="utf-8") as f:
        assert f.read() == "ok\n"
    assert os.path.isfile(os.path.join(outer, "beside"))
    assert status == 3
