"""decision-181, restated by decision-186, in a real bubblewrap jail: no channel
grant reaches brig's records.

bwrap granted a channel its endpoint's whole directory, read-write.
decision-174 refused an endpoint directly in the jail directory, which left a
gap planted on 2026-10-12 (TASK-0079.04's notes): an endpoint at
`<jail_dir>/execs/k.sock` compiled under bwrap and bound `<jail_dir>/execs`
read-write into the jail, the directory teardown signalled by. Records live
under `<jail_dir>/procs/`, and decision-181 refused an endpoint at or under it.
Since decision-186 a channel names no path: its one grant is the runtime's
channel directory `<jail_dir>/chan`, a sibling of `procs/`.

The first test is the claim against a running jail: a channel is declared, so
the channel directory is granted, and a script writes where teardown would read
a registration; nothing lands on the host (the plant: bwrap granting the jail
directory instead of the channel directory makes it fail, TASK-0079.32's
notes). The second is its control: the same script writes through the channel
directory, so the first passes because the records are out of reach, not
because no grant worked. Observed on the host with `os.path`, never through
brig.
"""

from __future__ import annotations

import os
import sys

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
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


#: Writes a registration where teardown would read one; prints its token only
#: when the write landed.
_SCRIPT = """
D="$1"
mkdir -p "$D/0123456789abcdef" && echo MADE_DIR
echo '{"pid": 2, "pgid": 2, "start_time": ""}' > "$D/0123456789abcdef/record.json" && echo WROTE
echo '{"pid": 2, "pgid": 2, "start_time": ""}' > "$D/2.json" && echo WROTE_FLAT
"""

_FORGED = ("0123456789abcdef", "2.json")


def _spec() -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
        ),
        channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
    )


def _write_through(
    jail_dir: str, directory: str, *, namespaces: bool = True
) -> tuple[str, list[str]]:
    """Run the forgery in a jail with a declared channel; what it printed and
    which forged names landed in `directory` on the host. A process in
    namespaces of its own writes the channel directory through the one made for
    it (decision-195), so `directory` is that one when it is the channel's."""
    spec = _spec()
    compiled = Stack([bwrap]).compile(
        spec, ctx=build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    )
    jail, process = launch(
        compiled,
        argv=["/bin/sh", "-c", _SCRIPT, "sh", directory],
        cwd="/",
        jail_id="bwrap-records-refused",
        jail_dir=jail_dir,
        namespaces=namespaces,
    )
    try:
        process.wait(timeout=_WAIT_TIMEOUT_S)
        if process.namespaces and directory == os.path.join(os.path.realpath(jail_dir), "chan"):
            directory = os.path.join(directory, process.id)
        with open(process.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout = f.read()
        landed = sorted(name for name in _FORGED if os.path.lexists(os.path.join(directory, name)))
    finally:
        # Ends the jail's supervisor, its PID 1 since TASK-0079.06, and waits for it: left
        # running, it writes its exit record into `<jail_dir>/supervisor` while the fixture
        # removes the jail directory ("Directory not empty", seen in CI), and the leak sweep
        # meets it still exiting.
        jail.destroy()
    return stdout, landed


_NAMESPACES = pytest.mark.parametrize(
    "namespaces", [True, False], ids=["as-the-host-gives", "no-namespaces"]
)


@pytest.mark.integration
@_NAMESPACES
def test_a_channel_grants_nothing_at_the_records(jail_dir: str, namespaces: bool) -> None:
    records = os.path.join(os.path.realpath(jail_dir), "procs")
    stdout, landed = _write_through(jail_dir, records, namespaces=namespaces)
    assert os.path.isdir(records), "CONTROL failed: the launch wrote no records to forge beside"
    assert landed == [], f"the jail wrote its records: {stdout.split()} -> {landed}"
    assert "WROTE" not in stdout.split() and "WROTE_FLAT" not in stdout.split(), stdout


@pytest.mark.integration
@_NAMESPACES
def test_the_channel_directory_beside_the_records_is_written_through(
    jail_dir: str, namespaces: bool
) -> None:
    """The control: the channel directory is the jail's one grant in the jail
    directory, and the same forgery lands there. Without it, the refusal above
    could pass against a bwrap whose channel grant never let anything
    through."""
    chan = os.path.join(os.path.realpath(jail_dir), "chan")
    stdout, landed = _write_through(jail_dir, chan, namespaces=namespaces)
    assert stdout.split() == ["MADE_DIR", "WROTE", "WROTE_FLAT"], stdout
    assert landed == ["0123456789abcdef", "2.json"], landed
