"""The verified dial of a reserved socket (decision-185, TASK-0079.33): its pure verdicts.

`brig/run/dial.py` refuses a path that is not a socket before connecting
(`_path_refusal`), and a peer that is not the started process's own listener
after (`_peer_refusal`). Both are pure, so every branch is a value here. The
seam through `Jail` and `Process` is driven with `brig.runtime.fake`, whose
`refusal` stands in for a runtime that found a planted endpoint; its refusal
raises before any socket is made. The real sockets are the integration tier's
(`tests/integration/test_channel_planted_link.py`).
"""

import stat

import pytest

from brig.core import Channel, ChannelKind, Spec
from brig.run import EndpointRefused, Jail
from brig.run.dial import _path_refusal, _Peer, _peer_refusal
from brig.runtime.fake import FakeRuntime
from brig.stack import Stack

pytestmark = pytest.mark.unit

_GROUP = 4242


def test_only_a_socket_is_dialled() -> None:
    assert _path_refusal(stat.S_IFSOCK | 0o755) is None
    assert "symbolic link" in (_path_refusal(stat.S_IFLNK | 0o777) or "")
    for mode in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFIFO, stat.S_IFCHR):
        assert _path_refusal(mode | 0o600) == "it is not a socket"


def test_a_listener_in_the_started_process_group_is_its_own() -> None:
    peer = _Peer(pid=4300, pgid=_GROUP, left=False)
    assert _peer_refusal(peer, group=_GROUP, leader_holds=True) is None


@pytest.mark.parametrize(
    ("peer", "leader_holds", "reason"),
    [
        (None, True, "can't read a socket's peer"),
        (_Peer(pid=0, pgid=None, left=False), True, "can't number its listener"),
        (_Peer(pid=4300, pgid=_GROUP, left=True), True, "has left"),
        (_Peer(pid=4300, pgid=None, left=False), True, "has left"),
        (_Peer(pid=4300, pgid=1, left=False), True, "not the started process's group 4242"),
        (_Peer(pid=4300, pgid=_GROUP, left=False), False, "no longer holds its recorded"),
    ],
)
def test_a_peer_that_is_not_the_process_own_listener_is_refused(
    peer: _Peer | None, leader_holds: bool, reason: str
) -> None:
    refusal = _peer_refusal(peer, group=_GROUP, leader_holds=leader_holds)
    assert refusal is not None and reason in refusal, refusal


def test_the_refusal_names_the_endpoint_and_why() -> None:
    error = EndpointRefused("/j/chan/0123456789abcdef.sock", "it is a symbolic link")
    assert (error.endpoint, error.reason) == (
        "/j/chan/0123456789abcdef.sock",
        "it is a symbolic link",
    )
    assert isinstance(error, RuntimeError) and not isinstance(error, OSError)
    assert "only the started process's own listener" in str(error)


def _started_on_a_channel(runtime: FakeRuntime) -> Jail:
    return Jail.create(
        Stack([]).compile(Spec(channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),))),
        runtime=runtime,
        cwd="/work",
        jail_id="fake-jail",
        jail_dir="/run/brig/jail0",
    )


def test_wait_ready_and_connect_raise_the_runtime_refusal_at_once() -> None:
    runtime = FakeRuntime(refusal="it is a symbolic link")
    jail = _started_on_a_channel(runtime)
    reservation = jail.channel("ctl")
    process = jail.start(["w", reservation.bound_path], channel=reservation)
    with pytest.raises(EndpointRefused, match="symbolic link") as waited:
        process.wait_ready(timeout=30.0)
    assert waited.value.endpoint == process.endpoint
    # Raised on the first ask, never polled until the deadline.
    assert [call.method for call in runtime.calls].count("ready") == 1
    with pytest.raises(EndpointRefused, match="symbolic link"):
        process.connect()
    assert runtime.dialled == []
    # The control: the same jail with no refusal is ready.
    runtime.refusal = None
    process.wait_ready(timeout=1.0)


def test_connect_on_a_process_with_no_channel_says_how_to_start_one() -> None:
    jail = _started_on_a_channel(FakeRuntime())
    process = jail.start(["w"])
    with pytest.raises(ValueError, match=r"channel=jail.channel\(name\)"):
        process.connect()
