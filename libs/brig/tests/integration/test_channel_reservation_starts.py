"""Reserve-then-start against real processes (decision-184, TASK-0079.05).

Two starts in ONE jail, each on a socket reserved in the runtime's channel
directory `<jail_dir>/chan`, each dialled from the host at its own endpoint:
in a real bubblewrap jail (where the directory is the mechanism's one grant,
decision-186), and with the empty stack. Readiness is a
connect, never the path's existence: a socket file bound and left with
nothing listening is not ready. And `create` refuses a `chan` that is a link,
since a bind follows one.

Observed on the host with `socket` and `os.path`, never through brig.
"""

import os
import shutil
import socket
import sys
import tempfile
from collections.abc import Iterator

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run import HostRuntime, Jail, WaitReadyTimeout
from brig.run.compile_ctx import build_compile_ctx
from brig.stack import Stack
from tests.conftest import teardown_group, workload_argv

_READY_S = 15.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")

#: Listens on argv[1] and answers every connection with argv[2], until ended
#: (a readiness probe closes at once, so a failed send is not an ending).
_SERVE = """import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(sys.argv[1])
s.listen(4)
while True:
    c, _ = s.accept()
    try:
        c.sendall(sys.argv[2].encode())
    except OSError:
        pass
    c.close()"""

#: Binds argv[1] and closes it without listening: a socket file, no listener.
_STALE = """import socket, sys, time
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(sys.argv[1])
s.close()
time.sleep(60)"""


@pytest.fixture
def jail_dir() -> Iterator[str]:
    path = tempfile.mkdtemp(prefix="bg-res-", dir="/tmp")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _python(run_id: str, code: str, *args: str) -> list[str]:
    return workload_argv(run_id, " ".join(["python3", "-c", f"'{code}'", *args]))


def _spec(jail_dir: str, *, confined: bool) -> Spec:
    fs = (
        FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
        )
        if confined
        else FsPolicy()
    )
    return Spec(fs=fs, channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),))


def _create(jail_dir: str, *, confined: bool) -> Jail:
    spec = _spec(jail_dir, confined=confined)
    stack = Stack([bwrap] if confined else [])
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    return Jail.create(
        stack.compile(spec, ctx=ctx),
        runtime=HostRuntime(),
        cwd="/",
        jail_id="channel-reservation",
        jail_dir=jail_dir,
    )


def _greeting(endpoint: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(_READY_S)
        client.connect(endpoint)
        return client.recv(64).decode()


def _two_starts_two_sockets(run_id: str, jail_dir: str, *, confined: bool) -> None:
    jail = _create(jail_dir, confined=confined)
    chan = os.path.join(os.path.realpath(jail_dir), "chan")
    first, second = jail.channel("ctl"), jail.channel("ctl")
    a = jail.start(_python(run_id, _SERVE, first.bound_path, "first"), channel=first)
    b = jail.start(_python(run_id, _SERVE, second.bound_path, "second"), channel=second)
    try:
        a.wait_ready(_READY_S)
        b.wait_ready(_READY_S)
        assert (a.endpoint, b.endpoint) == (first.endpoint, second.endpoint)
        if a.namespaces:
            # each process sees a directory of its own over the channel directory (decision-196):
            # the host's path to its socket is in that, named for the socket
            assert a.endpoint != a.bound_path and b.endpoint != b.bound_path
            assert os.path.dirname(os.path.dirname(a.endpoint or "")) == chan
            assert os.path.dirname(os.path.dirname(b.endpoint or "")) == chan
        else:
            assert os.path.dirname(a.endpoint or "") == os.path.dirname(b.endpoint or "") == chan
        assert a.endpoint != b.endpoint
        # Each dialled from the host reaches its own process, and nothing else.
        assert (_greeting(first.endpoint), _greeting(second.endpoint)) == ("first", "second")
        assert [(p.channel, p.bound_path) for p in jail.processes()] == [
            ("ctl", first.bound_path),
            ("ctl", second.bound_path),
        ]
    finally:
        report = jail.destroy()
        teardown_group(a)
        teardown_group(b)
    assert report.items and all(
        item.outcome.name in ("ENDED", "ALREADY_GONE") for item in report.items
    )


@pytest.mark.integration
def test_two_starts_in_a_bwrap_jail_each_get_a_socket_dialled_from_the_host(
    run_id: str, jail_dir: str
) -> None:
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"bwrap needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )
    _two_starts_two_sockets(run_id, jail_dir, confined=True)


@pytest.mark.integration
def test_two_starts_with_the_empty_stack_each_get_a_socket_dialled_from_the_host(
    run_id: str, jail_dir: str
) -> None:
    _two_starts_two_sockets(run_id, jail_dir, confined=False)


@pytest.mark.integration
def test_a_socket_file_with_nothing_listening_is_not_ready(run_id: str, jail_dir: str) -> None:
    jail = _create(jail_dir, confined=False)
    reservation = jail.channel("ctl")
    process = jail.start(_python(run_id, _STALE, reservation.bound_path), channel=reservation)
    try:
        with pytest.raises(WaitReadyTimeout):
            process.wait_ready(1.0)
        # The control: the file is there, so a path check would have said ready.
        assert os.path.exists(reservation.endpoint)
    finally:
        jail.destroy()
        teardown_group(process)


@pytest.mark.integration
def test_create_refuses_a_channel_directory_that_is_a_link(jail_dir: str) -> None:
    elsewhere = tempfile.mkdtemp(prefix="bg-else-", dir="/tmp")
    try:
        os.symlink(elsewhere, os.path.join(jail_dir, "chan"))
        with pytest.raises(FileExistsError, match="not a directory brig made"):
            _create(jail_dir, confined=False)
        # The control: a real directory there is kept and used.
        os.unlink(os.path.join(jail_dir, "chan"))
        os.mkdir(os.path.join(jail_dir, "chan"))
        assert _create(jail_dir, confined=False).channel("ctl").bound_path
    finally:
        shutil.rmtree(elsewhere)
