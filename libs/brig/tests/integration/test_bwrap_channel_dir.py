"""decision-174, restated by decision-186, in a real bubblewrap jail: a channel
never makes the jail directory writable.

bwrap granted a channel its endpoint's whole directory, read-write, and
directly in the jail directory that made brig's own control state (its exec
registrations and exit file then, its process records since decision-181, the
logs) writable from inside the jail: planted before decision-174, a
registration directory, the exit file and `x` all landed on the host. Since
decision-186 a channel names no path, and its one grant is the runtime's
channel directory `<jail_dir>/chan`, so this checks both halves against a real
mechanism:

- the grant, from `build_compile_ctx` through `bwrap.compile`, with nothing
  launched: the channel directory is the one read-write mount, never the jail
  directory;
- in a running jail: the channel directory is writable, while the jail still
  cannot write a record under `procs/` or its own exit record, and the exit
  status `wait()` reads is the workload's.

Observed on the host with `os.path`, never through brig.
"""

from __future__ import annotations

import os
import sys

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
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


def _spec() -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )


@pytest.mark.integration
def test_a_channel_is_granted_the_channel_directory_never_the_jail_directory(
    jail_dir: str,
) -> None:
    """The grant as compiled from a real context: one read-write bind, the
    channel directory at itself, and nothing at the jail directory. Nothing is
    launched, so nothing is made in the jail directory either."""
    spec = _spec()
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    argv = bwrap.compile(spec, ctx).wrap(("/bin/true",))
    binds = [(argv[i + 1], argv[i + 2]) for i, arg in enumerate(argv) if arg == "--bind"]
    chan = os.path.join(ctx.jail_dir, "chan")
    assert binds == [(chan, chan)], argv
    assert ctx.jail_dir not in {path for pair in binds for path in pair}
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
@pytest.mark.parametrize("namespaces", [True, False], ids=["as-the-host-gives", "no-namespaces"])
def test_the_channel_directory_works_and_the_rest_of_the_jail_directory_is_sealed(
    run_id: str,
    jail_dir: str,
    namespaces: bool,
) -> None:
    chan = os.path.join(jail_dir, "chan")
    spec = _spec()
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
        namespaces=namespaces,
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
    # (A process in namespaces of its own writes into the directory made for it, decision-195.)
    inside = (
        os.path.join(chan, process.id, "inside")
        if process.namespaces
        else os.path.join(chan, "inside")
    )
    assert os.path.isfile(inside)
    assert status == 3
