"""The host's end of a supervisor's control socket, against a stand-in supervisor on the other
end of a real socketpair (decision-191, TASK-0079.06).

`SupervisorLink` is threads and a socket, so the unit tier can't hold it, and it needs no jail: the
peer here is a thread that reads requests and answers as a test says, which is what lets each
claim be made about the host's side alone: replies find their callers by id, descriptors cross both
ways, a missed deadline calls `unresponsive` once and ends the link, a closed socket wakes every
caller, and a link nobody holds closes its end.
"""

from __future__ import annotations

import gc
import json
import os
import socket
import threading
import time
from collections.abc import Callable

import pytest

from brig.run import SupervisorGone, SupervisorUnresponsive
from brig.run._supervisor_link import SupervisorLink, SupervisorRefused

pytestmark = pytest.mark.integration


class Peer:
    """The supervisor's end, driven by the test: `receive` a request, `send` anything."""

    def __init__(self) -> None:
        self.link_end, self.end = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.end.settimeout(10)

    def receive(self) -> tuple[dict[str, object], list[int]]:
        data, fds, _, _ = socket.recv_fds(self.end, 1 << 20, 4)
        assert data, "the link closed its end"
        return json.loads(data), fds

    def send(self, message: dict[str, object], fds: list[int] | None = None) -> None:
        socket.send_fds(self.end, [json.dumps(message).encode()], fds or [])

    def hello(self) -> None:
        self.send({"hello": 1, "protocol": 1})


@pytest.fixture
def peer() -> Peer:
    made = Peer()
    yield made  # type: ignore[misc]
    made.end.close()


def _link(peer: Peer, unresponsive: Callable[[], None] = lambda: None) -> SupervisorLink:
    return SupervisorLink(peer.link_end, unresponsive=unresponsive)


def test_replies_find_their_callers_by_id_whatever_order_they_come_in(peer: Peer) -> None:
    link = _link(peer)
    answers: dict[str, object] = {}

    def ask(name: str) -> None:
        answers[name] = link.request("op", {"who": name}, timeout=10).fields["who"]

    threads = [threading.Thread(target=ask, args=(name,)) for name in ("a", "b", "c")]
    for thread in threads:
        thread.start()
    seen = [peer.receive()[0] for _ in threads]
    assert sorted(str(m["who"]) for m in seen) == ["a", "b", "c"]
    assert len({m["id"] for m in seen}) == 3, "two requests shared an id"
    for message in reversed(seen):  # the last asked is answered first
        peer.send({"id": message["id"], "ok": True, "who": message["who"]})
    for thread in threads:
        thread.join(10)
    assert answers == {"a": "a", "b": "b", "c": "c"}


def test_an_error_reply_is_a_refusal_with_the_reason_and_its_descriptors_are_closed(
    peer: Peer,
) -> None:
    link = _link(peer)
    spare_r, spare_w = os.pipe()
    outcome: list[BaseException] = []

    def ask() -> None:
        try:
            link.request("start", {}, timeout=10)
        except BaseException as error:
            outcome.append(error)

    thread = threading.Thread(target=ask)
    thread.start()
    request, _ = peer.receive()
    peer.send({"id": request["id"], "ok": False, "error": "no such thing"}, [spare_r])
    thread.join(10)
    os.close(spare_r)  # ours; the one the link received was its own copy
    os.close(spare_w)
    (error,) = outcome
    assert isinstance(error, SupervisorRefused) and error.reason == "no such thing"
    assert "start" in str(error)


def test_descriptors_cross_both_ways(peer: Peer) -> None:
    link = _link(peer)
    sent_r, sent_w = os.pipe()
    replies: list[object] = []

    thread = threading.Thread(
        target=lambda: replies.append(link.request("op", {}, timeout=10, fds=[sent_r]))
    )
    thread.start()
    request, received = peer.receive()
    assert len(received) == 1
    os.write(sent_w, b"to the peer")
    assert os.read(received[0], 64) == b"to the peer"
    back_r, back_w = os.pipe()
    peer.send({"id": request["id"], "ok": True}, [back_r])
    thread.join(10)
    (reply,) = replies
    (fd,) = reply.fds  # type: ignore[attr-defined]
    os.write(back_w, b"to the host")
    assert os.read(fd, 64) == b"to the host"
    for opened in (sent_r, sent_w, *received, back_r, back_w, fd):
        os.close(opened)


def test_a_missed_deadline_calls_unresponsive_once_ends_the_link_and_ignores_the_late_reply(
    peer: Peer,
) -> None:
    called: list[str] = []
    link = _link(peer, unresponsive=lambda: called.append("ended"))
    began = time.monotonic()
    with pytest.raises(SupervisorUnresponsive, match="did not answer 'stuck' within 0.3s"):
        link.request("stuck", {}, timeout=0.3)
    assert 0.25 < time.monotonic() - began < 5.0
    assert called == ["ended"]

    # Ended: the socket is closed, so a request is refused as gone, and the peer sees end-of-file.
    request, _ = peer.receive()
    with pytest.raises(SupervisorGone):
        link.request("again", {}, timeout=1)
    with pytest.raises((BrokenPipeError, ConnectionResetError, OSError)):
        peer.send({"id": request["id"], "ok": True})
    assert called == ["ended"], "unresponsive ran twice"


def test_a_closed_socket_wakes_every_caller_waiting_on_it(peer: Peer) -> None:
    link = _link(peer)
    outcomes: list[str] = []

    def ask() -> None:
        try:
            link.request("op", {}, timeout=30)
        except SupervisorGone:
            outcomes.append("gone")

    threads = [threading.Thread(target=ask) for _ in range(3)]
    for thread in threads:
        thread.start()
    for _ in threads:
        peer.receive()
    began = time.monotonic()
    peer.end.close()  # the supervisor ended
    for thread in threads:
        thread.join(10)
    assert outcomes == ["gone"] * 3 and time.monotonic() - began < 5.0


def test_the_hello_is_waited_for_and_a_socket_that_closes_first_is_gone(peer: Peer) -> None:
    link = _link(peer)
    with pytest.raises(TimeoutError):
        link.wait_hello(0.2)
    peer.hello()
    assert link.wait_hello(5)["protocol"] == 1

    quiet = Peer()
    other = _link(quiet)
    quiet.end.close()
    with pytest.raises(SupervisorGone):
        other.wait_hello(5)


def test_a_reply_nobody_waits_for_and_a_message_it_cannot_read_are_dropped_with_their_fds(
    peer: Peer,
) -> None:
    link = _link(peer)
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(5):
        spare_r, spare_w = os.pipe()
        peer.send({"id": 99999, "ok": True}, [spare_r])  # no such request
        os.close(spare_r)
        os.close(spare_w)
    socket.send_fds(peer.end, [b"not json at all"], [])
    peer.send({"no": "id"})
    # Still serving: a request made after the noise is answered.
    thread_result: list[object] = []
    thread = threading.Thread(
        target=lambda: thread_result.append(link.request("op", {}, timeout=10).fields["x"])
    )
    thread.start()
    request, _ = peer.receive()
    peer.send({"id": request["id"], "ok": True, "x": 1})
    thread.join(10)
    assert thread_result == [1]
    assert until_equal(lambda: len(os.listdir("/proc/self/fd")), before), "descriptors leaked"


def until_equal(read: Callable[[], int], want: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if read() == want:
            return True
        time.sleep(0.02)
    return read() == want


def test_a_link_nobody_holds_closes_its_end(peer: Peer) -> None:
    """The rule decision-191 states: a supervised jail lives as long as the object that holds
    its end. Collected, the link's finalizer closes the socket and the supervisor reads EOF."""

    def make_and_drop() -> None:
        link = _link(peer)
        del link

    make_and_drop()
    gc.collect()
    peer.end.settimeout(10)
    data, _, _, _ = socket.recv_fds(peer.end, 1 << 20, 4)
    assert data == b"", "the supervisor was not given end-of-file"


def test_close_is_idempotent_and_sends_end_of_file(peer: Peer) -> None:
    link = _link(peer)
    link.close()
    link.close()
    data, _, _, _ = socket.recv_fds(peer.end, 1 << 20, 4)
    assert data == b""
    with pytest.raises(SupervisorGone):
        link.request("op", {}, timeout=1)
