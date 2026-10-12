"""decision-174 in a real bubblewrap jail: where a LISTEN endpoint may sit.

bwrap grants a channel its endpoint's whole directory, read-write. Directly in
the jail directory that made brig's own control state (`execs/`, `exit`, the
logs) writable from inside the jail: planted before the fix, `mkdir execs`,
`exit` and `x` all landed on the host. The compile now refuses that layout,
and this checks both halves against a real mechanism:

- the refusal, from `build_compile_ctx` through `Stack.compile`, with nothing
  launched (so the forgery cannot happen);
- the remedy: an endpoint in a subdirectory still gets its own directory
  writable, while the jail still cannot write `execs/` or `exit`, and the exit
  record `wait()` reads is the workload's.

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
J="$1"; C="$2"
mkdir "$J/execs" && echo MADE_EXECS
echo 0 > "$J/exit" && echo WROTE_EXIT
echo x > "$J/x" && echo WROTE_X
echo ok > "$C/inside" && echo CHANNEL_DIR
exit 3
"""

_FORGED = ("MADE_EXECS", "WROTE_EXIT", "WROTE_X")


@pytest.mark.integration
def test_an_endpoint_in_a_subdirectory_works_and_the_rest_of_the_jail_directory_is_sealed(
    jail_dir: str,
) -> None:
    chan = os.path.join(jail_dir, "chan")
    os.makedirs(chan)
    spec = _spec(os.path.join(chan, "ctl.sock"))
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    signature = bwrap.compile(spec, ctx).denial_signatures[0]
    jail = Stack([bwrap]).compile(spec, ctx=ctx)
    handle = SubprocessLauncher().launch(
        jail,
        argv=["/bin/sh", "-c", _SCRIPT, "sh", ctx.jail_dir, chan],
        cwd="/",
        io=IoPolicy(),
        jail_id="bwrap-channel-dir",
        jail_dir=jail_dir,
    )
    status = handle.wait(timeout=_WAIT_TIMEOUT_S)
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()
    with open(handle.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr = f.read()

    forged = [token for token in _FORGED if token in stdout]
    assert not forged, f"the jail wrote its own jail directory: {forged}\n{stderr}"
    assert signature.search(stderr) is not None, stderr
    assert not os.path.exists(os.path.join(jail_dir, "execs"))
    assert not os.path.exists(os.path.join(jail_dir, "x"))
    # The control, same jail, same run: the channel's own directory is written,
    # and the exit record is the workload's status, not a forged one.
    assert "CHANNEL_DIR" in stdout, (stdout, stderr)
    assert os.path.isfile(os.path.join(chan, "inside"))
    assert status == 3
