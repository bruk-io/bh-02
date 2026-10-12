"""decision-174 in a real bubblewrap jail: where a LISTEN endpoint may sit.

bwrap grants a channel its endpoint's whole directory, read-write. Directly in
the jail directory that made brig's own control state (its exec
registrations and exit file then, its process records since decision-181, the
logs) writable from inside the jail: planted before the fix, a registration
directory, the exit file and `x` all landed on the host. The compile now refuses that layout,
and this checks both halves against a real mechanism:

- the refusal, from `build_compile_ctx` through `Stack.compile`, with nothing
  launched (so the forgery cannot happen);
- the remedy: an endpoint in a subdirectory still gets its own directory
  writable, while the jail still cannot write a record under `procs/` or its
  own exit record, and the exit status `wait()` reads is the workload's.

Observed on the host with `os.path`, never through brig.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, ChannelInsideJailDir, bwrap
from brig.run import IoPolicy, _records
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import Stack
from tests.conftest import launch, teardown_group, workload_argv

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
    path = tempfile.mkdtemp(prefix="bg-chan-")
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _spec(endpoint: str) -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )


@pytest.mark.integration
def test_an_endpoint_directly_in_the_jail_directory_is_refused(jail_dir: str) -> None:
    endpoint = os.path.join(jail_dir, "ctl.sock")
    spec = _spec(endpoint)
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    with pytest.raises(ChannelInsideJailDir) as refusal:
        Stack([bwrap]).compile(spec, ctx=ctx)
    assert os.path.realpath(endpoint) in str(refusal.value)
    assert os.path.realpath(jail_dir) in str(refusal.value)
    assert os.listdir(jail_dir) == []


#: Each attempt prints its token only when the write succeeded.
_SCRIPT = """
J="$1"; C="$2"; EXIT="$3"
mkdir "$J/procs/0123456789abcdef" && echo MADE_RECORD
echo 0 > "$EXIT" && echo WROTE_EXIT
echo x > "$J/x" && echo WROTE_X
echo ok > "$C/inside" && echo CHANNEL_DIR
exit 3
"""

_FORGED = ("MADE_RECORD", "WROTE_EXIT", "WROTE_X")


@pytest.mark.integration
def test_an_endpoint_in_a_subdirectory_works_and_the_rest_of_the_jail_directory_is_sealed(
    run_id: str,
    jail_dir: str,
) -> None:
    chan = os.path.join(jail_dir, "chan")
    os.makedirs(chan)
    spec = _spec(os.path.join(chan, "ctl.sock"))
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    signature = bwrap.compile(spec, ctx).denial_signatures[0]
    compiled = Stack([bwrap]).compile(spec, ctx=ctx)
    # The process whose exit record the plant forges: a known, running one,
    # so its record's path is named exactly rather than found by a listing
    # the jail might not be allowed to make.
    jail, holder = launch(
        compiled,
        argv=workload_argv(run_id, "sleep 100"),
        cwd="/",
        io=IoPolicy(),
        jail_id="bwrap-channel-dir",
        jail_dir=jail_dir,
    )
    holder_exit = _records.exit_path(jail_dir, holder.id)
    try:
        process = jail.start(["/bin/sh", "-c", _SCRIPT, "sh", ctx.jail_dir, chan, holder_exit])
        status = process.wait(timeout=_WAIT_TIMEOUT_S)
        # Read while the holder still runs: it has written no exit record of
        # its own, so one there now is the jail's forgery.
        exit_forged = os.path.exists(holder_exit)
    finally:
        teardown_group(holder)
    with open(process.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()
    with open(process.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr = f.read()

    forged = [token for token in _FORGED if token in stdout]
    assert not forged, f"the jail wrote its own jail directory: {forged}\n{stderr}"
    assert signature.search(stderr) is not None, stderr
    assert not os.path.exists(os.path.join(jail_dir, "procs", "0123456789abcdef"))
    assert not os.path.exists(os.path.join(jail_dir, "x"))
    assert os.path.isdir(os.path.dirname(holder_exit)), "CONTROL failed: no record to forge"
    assert not exit_forged, "the jail forged the running process's exit record"
    # The control, same jail, same run: the channel's own directory is written,
    # and the exit record is the workload's status, not a forged one.
    assert "CHANNEL_DIR" in stdout, (stdout, stderr)
    assert os.path.isfile(os.path.join(chan, "inside"))
    assert status == 3
