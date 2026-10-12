"""decision-181 in a real bubblewrap jail: no LISTEN grant reaches brig's records.

bwrap grants a channel its endpoint's whole directory, read-write. decision-174
refused an endpoint directly in the jail directory, which left a gap planted on
2026-10-12 (TASK-0079.04's notes): an endpoint at `<jail_dir>/execs/k.sock`
compiled under bwrap and bound `<jail_dir>/execs` read-write into the jail, the
directory teardown signalled by. Records now live under `<jail_dir>/procs/`,
and every mechanism that compiles a LISTEN channel refuses an endpoint at or
under it (and under `execs/` until TASK-0079.28 deletes it).

Each case is the plant and the refusal in one: if the compile accepts the
layout, the jail is launched and tries to write a registration through the
grant, and the test fails naming what landed on the host. Seen failing that way
before the fix, for both directories (TASK-0079.25's notes); refused after,
with nothing launched. Observed on the host with `os.path`, never through brig.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run.compile_ctx import build_compile_ctx
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack

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
def jail_dir() -> Iterator[str]:
    path = tempfile.mkdtemp(prefix="bg-recs-")
    try:
        yield path
    finally:
        shutil.rmtree(path)


#: Writes a registration where teardown would read one; prints its token only
#: when the write landed.
_SCRIPT = """
D="$1"
mkdir -p "$D/0123456789abcdef" && echo MADE_DIR
echo '{"pid": 2, "pgid": 2, "start_time": ""}' > "$D/0123456789abcdef/record.json" && echo WROTE
echo '{"pid": 2, "pgid": 2, "start_time": ""}' > "$D/2.json" && echo WROTE_FLAT
"""


@pytest.mark.integration
@pytest.mark.parametrize("records", ["procs", "execs"])
def test_an_endpoint_under_the_records_is_refused_and_nothing_is_written(
    jail_dir: str, records: str
) -> None:
    directory = os.path.join(jail_dir, records)
    os.makedirs(directory)
    endpoint = os.path.join(directory, "k.sock")
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    try:
        jail = Stack([bwrap]).compile(spec, ctx=ctx)
    except ValueError as refusal:
        message = str(refusal)
        assert os.path.realpath(endpoint) in message, message
        assert os.path.join(os.path.realpath(jail_dir), records) in message, message
        assert f"{os.path.realpath(jail_dir)}/chan/" in message, message
        assert os.listdir(directory) == []
        return
    # The plant: the layout compiled, so try the forgery it allows.
    handle = SubprocessLauncher().launch(
        jail,
        argv=["/bin/sh", "-c", _SCRIPT, "sh", directory],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="bwrap-records-refused",
        jail_dir=jail_dir,
    )
    handle.wait(timeout=_WAIT_TIMEOUT_S)
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()
    landed = sorted(os.listdir(directory))
    pytest.fail(
        f"an endpoint at {endpoint} compiled, and the jail wrote through its grant: "
        f"{stdout.split()} -> {directory} holds {landed}"
    )
