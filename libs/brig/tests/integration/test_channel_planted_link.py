"""The host dials a reserved socket only when its own process answers (decision-185, TASK-0079.33).

A process of a jail can write the jail's channel directory, so it can put a
link at a reserved socket's path (its own, or a co-tenant's) pointing at a
host socket outside the jail. Before decision-185 `Process.wait_ready`
reported READY on one and the host's connect reached the outside listener
(seen: the bwrap test below, against the pre-fix code). Here the planted link
points at a listener THIS TEST starts in a scratch directory, never at a real
host socket. Each refusal is paired with the control in the same jail: a
genuine reservation connects and its own process answers.

Observed on the host with `socket`, never through brig: whether the outside
listener was ever connected to is its own `accept`.
"""

import os
import shutil
import socket
import sys
import tempfile
import time
from collections.abc import Iterator

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run import (
    EndpointRefused,
    HostRuntime,
    Jail,
    Process,
    Reservation,
    ReservationRefused,
)
from brig.run.compile_ctx import build_compile_ctx
from brig.run.dial import dial
from brig.runtime.fake import FakeRuntime
from brig.stack import Stack
from tests.conftest import teardown_group, workload_argv

_READY_S = 15.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")

#: Puts a link at argv[1] pointing at argv[2], then stays.
_PLANT = "import os, sys, time; os.symlink(sys.argv[2], sys.argv[1]); time.sleep(60)"

#: Listens on argv[1] and answers every connection with argv[2], until ended.
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

#: Listens on argv[1], then forks: the child keeps the socket and accepts, the
#: listener itself exits (a daemon that forks after `listen`). Once the
#: listener is reaped (`kill(pid, 0)` finds no process, not even a zombie),
#: the child writes the file argv[2], so the test asks only after it has left.
_FORK_AFTER_LISTEN = """import os, socket, sys, time
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(sys.argv[1])
s.listen(4)
parent = os.getpid()
if os.fork():
    os._exit(0)
while True:
    try:
        os.kill(parent, 0)
    except ProcessLookupError:
        break
    time.sleep(0.01)
open(sys.argv[2], "w").close()
while True:
    c, _ = s.accept()
    c.close()"""


@pytest.fixture
def jail_dir() -> Iterator[str]:
    path = tempfile.mkdtemp(prefix="bg-plant-", dir="/tmp")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def outside() -> Iterator[socket.socket]:
    """A listener of this test's own, in a scratch directory outside any jail:
    the host socket a planted link points at. Non-blocking, so `accept` says
    at once whether anything connected."""
    directory = tempfile.mkdtemp(prefix="bg-outside-", dir="/tmp")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(os.path.join(directory, "host.sock"))
        listener.listen(4)
        listener.setblocking(False)
        yield listener
    finally:
        listener.close()
        shutil.rmtree(directory, ignore_errors=True)


def _python(run_id: str, code: str, *args: str) -> list[str]:
    return workload_argv(run_id, " ".join(["python3", "-c", f"'{code}'", *args]))


def _create(jail_dir: str, *, confined: bool) -> Jail:
    own = os.path.join(jail_dir, "own")
    os.makedirs(own)
    fs = (
        FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path)),
        )
        if confined
        else FsPolicy()
    )
    spec = Spec(fs=fs, channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),))
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    return Jail.create(
        Stack([bwrap] if confined else []).compile(spec, ctx=ctx),
        runtime=HostRuntime(),
        cwd="/",
        jail_id="planted-link",
        jail_dir=jail_dir,
    )


def _never_connected(listener: socket.socket) -> bool:
    try:
        connection, _ = listener.accept()
    except BlockingIOError:
        return True
    connection.close()
    return False


def _greeting(process: Process) -> str:
    with process.connect() as client:
        client.settimeout(_READY_S)
        return client.recv(64).decode()


def _wait_for_link(path: str) -> None:
    deadline = time.monotonic() + _READY_S
    while not os.path.islink(path):
        if time.monotonic() >= deadline:
            raise AssertionError(f"the workload never planted its link at {path}")
        time.sleep(0.02)


def _planted_link_refused(
    run_id: str, jail_dir: str, listener: socket.socket, *, confined: bool
) -> None:
    jail = _create(jail_dir, confined=confined)
    planted, genuine = jail.channel("ctl"), jail.channel("ctl")
    target = listener.getsockname()
    attacker = jail.start(_python(run_id, _PLANT, planted.bound_path, target), channel=planted)
    server = jail.start(_python(run_id, _SERVE, genuine.bound_path, "genuine"), channel=genuine)
    try:
        _wait_for_link(planted.endpoint)
        assert os.readlink(planted.endpoint) == target
        with pytest.raises(EndpointRefused, match="symbolic link") as waited:
            attacker.wait_ready(_READY_S)
        assert waited.value.endpoint == planted.endpoint
        with pytest.raises(EndpointRefused, match="symbolic link"):
            attacker.connect()
        assert _never_connected(listener), "the host connected to the planted link's target"
        # The control: a genuine reservation in the same jail is ready and its
        # own process answers the dial.
        server.wait_ready(_READY_S)
        assert _greeting(server) == "genuine"
    finally:
        jail.destroy()
        teardown_group(attacker)
        teardown_group(server)


@pytest.mark.integration
def test_a_link_planted_in_a_bwrap_jail_is_refused_by_readiness_and_connect(
    run_id: str, jail_dir: str, outside: socket.socket
) -> None:
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"bwrap needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )
    _planted_link_refused(run_id, jail_dir, outside, confined=True)


@pytest.mark.integration
def test_a_link_planted_with_the_empty_stack_is_refused_by_readiness_and_connect(
    run_id: str, jail_dir: str, outside: socket.socket
) -> None:
    _planted_link_refused(run_id, jail_dir, outside, confined=False)


@pytest.mark.integration
def test_a_link_swapped_in_after_the_path_check_is_refused_by_the_peer_check(
    run_id: str, jail_dir: str, outside: socket.socket
) -> None:
    """The race the path check can't close: the link is swapped in between
    the `lstat` and the `connect`. Played by an `lstat` that follows the link
    (it sees the target's socket). The connect then reaches the outside
    listener, whose peer is this test's process, not the started process's
    group: refused, and the host sent nothing."""
    jail = _create(jail_dir, confined=False)
    reservation = jail.channel("ctl")
    process = jail.start(_python(run_id, "import time; time.sleep(60)"), channel=reservation)
    try:
        os.symlink(outside.getsockname(), reservation.endpoint)
        with pytest.raises(EndpointRefused, match="not the started process's group"):
            dial(
                reservation.endpoint,
                group=process._record.pgid,
                leader_pid=process.pid,
                leader_stamp=process.start_time,
                lstat=os.stat,
            )
        connection, _ = outside.accept()
        with connection:
            connection.settimeout(_READY_S)
            assert connection.recv(64) == b"", "the host sent something to a listener not its own"
    finally:
        jail.destroy()
        teardown_group(process)


@pytest.mark.integration
def test_a_co_tenant_listening_at_a_sibling_reservation_is_refused(
    run_id: str, jail_dir: str
) -> None:
    """A real socket at the path (the path check passes), bound by another
    start of the same jail: its group is not the sibling's."""
    jail = _create(jail_dir, confined=False)
    own, sibling = jail.channel("ctl"), jail.channel("ctl")
    squatter = jail.start(_python(run_id, _SERVE, sibling.bound_path, "squatter"), channel=own)
    victim = jail.start(_python(run_id, "import time; time.sleep(60)"), channel=sibling)
    try:
        for _ in range(int(_READY_S / 0.02)):
            try:
                victim.connect().close()
            except EndpointRefused as refused:
                assert "not the started process's group" in refused.reason, refused.reason
                break
            except OSError:
                time.sleep(0.02)
        else:
            raise AssertionError("the squatter never listened, or its listener was dialled")
        with pytest.raises(EndpointRefused):
            victim.wait_ready(_READY_S)
    finally:
        jail.destroy()
        teardown_group(squatter)
        teardown_group(victim)


@pytest.mark.integration
def test_a_listener_that_left_after_listening_is_refused(run_id: str, jail_dir: str) -> None:
    """The kernel names the process that called `listen`; one that has since
    exited is no vouching peer, even when the socket's holder is in the
    group (the safe direction for a daemon that forks after `listen`)."""
    jail = _create(jail_dir, confined=False)
    reservation = jail.channel("ctl")
    left = os.path.join(jail_dir, "own", "left")
    body = f"python3 -c '{_FORK_AFTER_LISTEN}' {reservation.bound_path} {left}; sleep 60"
    process = jail.start(workload_argv(run_id, body), channel=reservation)
    try:
        deadline = time.monotonic() + _READY_S
        while not os.path.exists(left):
            assert time.monotonic() < deadline, "the listener never left"
            time.sleep(0.02)
        with pytest.raises(EndpointRefused, match="has left"):
            process.wait_ready(_READY_S)
    finally:
        jail.destroy()
        teardown_group(process)


@pytest.mark.integration
def test_a_peer_the_kernel_cannot_report_is_refused_not_waited_out(
    run_id: str, jail_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """decision-186 (TASK-0079.33's review): `HostRuntime.ready` read any
    `OSError` from the dial as "nothing listens yet", and a failed read of
    the peer after the connect succeeded is one, so `wait_ready` waited out
    its whole timeout on a socket that answered. The peer read is made to
    fail (`getsockopt` refusing, as a kernel can): `wait_ready` and `connect`
    raise `EndpointRefused` naming the error at once. The control, same
    jail, same process: with the read restored, it is ready and answers."""
    jail = _create(jail_dir, confined=False)
    reservation = jail.channel("ctl")
    process = jail.start(
        _python(run_id, _SERVE, reservation.bound_path, "genuine"), channel=reservation
    )

    def unreadable(sock: socket.socket) -> None:
        raise OSError(22, "Invalid argument")

    try:
        with monkeypatch.context() as patched:
            patched.setattr("brig.run.dial._read_peer", unreadable)
            # Only once something listens can the peer read be reached.
            deadline = time.monotonic() + _READY_S
            while True:
                try:
                    with socket.socket(socket.AF_UNIX) as probe:
                        probe.connect(reservation.bound_path)
                    break
                except OSError:
                    assert time.monotonic() < deadline, "the genuine listener never listened"
                    time.sleep(0.02)
            start = time.monotonic()
            with pytest.raises(EndpointRefused, match="could not report who listens"):
                process.wait_ready(_READY_S)
            assert time.monotonic() - start < _READY_S / 3, "the refusal was waited out"
            with pytest.raises(EndpointRefused, match="Invalid argument"):
                process.connect()
        process.wait_ready(_READY_S)
        with process.connect() as dialled:
            assert dialled.recv(64) == b"genuine"
    finally:
        jail.destroy()
        teardown_group(process)


@pytest.mark.integration
def test_host_supervisor_start_refuses_a_forged_reservation(run_id: str, jail_dir: str) -> None:
    """decision-184's refusal by `HostSupervisor.start` itself, against
    `HostRuntime` (not the fake): each forgery refused before anything is
    made or spawned; the control, a genuine reservation, starts."""
    jail = _create(jail_dir, confined=False)
    genuine = jail.channel("ctl")
    chan = os.path.dirname(genuine.bound_path)
    outside_chan = os.path.join(jail_dir, "own", "0123456789abcdef.sock")
    forgeries = (
        Reservation("ctl", outside_chan, outside_chan),
        Reservation(
            "ctl", f"{chan}/../chan/0123456789abcdef.sock", f"{chan}/0123456789abcdef.sock"
        ),
        Reservation("ctl", f"{chan}/docker.sock", f"{chan}/docker.sock"),
        Reservation("ctl", genuine.bound_path, "/run/docker.sock"),
    )
    procs = os.path.join(jail_dir, "procs")
    try:
        for forged in forgeries:
            with pytest.raises(ReservationRefused, match="not this jail's"):
                jail.start(_python(run_id, "import time; time.sleep(60)"), channel=forged)
            assert not os.path.isdir(procs) or os.listdir(procs) == [], forged
        assert jail.processes() == ()
        process = jail.start(
            _python(run_id, _SERVE, genuine.bound_path, "genuine"), channel=genuine
        )
        with pytest.raises(ReservationRefused, match="already binds"):
            jail.start(_python(run_id, "import time; time.sleep(60)"), channel=genuine)
        assert len(jail.processes()) == 1
        process.wait_ready(_READY_S)
    finally:
        jail.destroy()
        for started in jail.processes():
            teardown_group(started)


@pytest.mark.integration
def test_the_fake_runtime_connect_hands_back_one_end_of_a_pair() -> None:
    runtime = FakeRuntime()
    jail = Jail.create(
        Stack([]).compile(Spec(channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),))),
        runtime=runtime,
        cwd="/work",
        jail_id="fake-jail",
        jail_dir="/run/brig/jail0",
    )
    reservation = jail.channel("ctl")
    process = jail.start(["w", reservation.bound_path], channel=reservation)
    with process.connect() as ours:
        ours.sendall(b"ping")
        (theirs,) = runtime.dialled
        with theirs:
            assert theirs.recv(4) == b"ping"
    runtime.listening = False
    with pytest.raises(ConnectionRefusedError):
        process.connect()
