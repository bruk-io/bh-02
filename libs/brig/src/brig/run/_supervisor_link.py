"""The host's end of a supervisor's control socket (SPEC.md section 8, decision-191).

A supervised jail's PID 1 holds the other end of a `SOCK_SEQPACKET` socketpair the host made
before it started anything. Every start, signal, wait and stop of a process of the jail is a
request on it: one JSON object per message, descriptors by `SCM_RIGHTS`, each request numbered and
each reply carrying the number back, so several callers' requests are in flight at once and a
reply finds its own caller (`SupervisorLink.request`).

**A request has a host-side deadline, and a deadline missed ends the jail.** A supervisor that
does not answer is spinning, wedged or hostile, and law 7 says control must not require its
cooperation: the link calls the `unresponsive` function its owner gave it (`HostRuntime`'s
teardown of the supervisor's group, SPEC.md section 9's ladder), closes the socket, and raises
`SupervisorUnresponsive` to the caller. The same close is what `Jail.destroy` does first: the
supervisor reads end-of-file on its end and ends everything it holds, which is how a jail ends
when the host that made it dies, too (the kernel closes the socket).

**A class, because it owns a resource with a lifecycle**: a socket, a reader thread that is the
only thing that reads it, and the requests in flight. The thread holds the `_Wire`, never the
link, so a link nobody holds is collected, its finalizer closes the socket, and the jail ends,
which is the rule: a supervised jail lives as long as the object that holds its end.
"""

import contextlib
import itertools
import json
import os
import socket
import threading
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

#: The largest message either side sends or reads; the supervisor's own limit is the same.
MAX_MESSAGE: Final = 1 << 20

#: The most descriptors one message carries (a start's three stdio files, a pidfd).
MAX_FDS: Final = 4


class SupervisorGone(RuntimeError):
    """The control socket is closed: the supervisor ended, or the jail was destroyed, or this
    link was closed. What a request was waiting for will not come."""


class SupervisorUnresponsive(RuntimeError):
    """The supervisor did not answer a request within its host-side deadline, so the jail was
    destroyed (SPEC.md section 8, decision-191): a supervisor that does not answer is spinning,
    wedged or hostile, and ending it does not wait on it. Every process of the jail is gone
    or is being ended; `Jail.destroy` reports what ended."""


class SupervisorRefused(RuntimeError):
    """The supervisor answered a request with an error: `reason` is what it said. The jail is
    unharmed; the request did nothing."""

    def __init__(self, op: str, reason: str) -> None:
        self.op = op
        self.reason = reason
        super().__init__(f"the supervisor refused {op!r}: {reason}")


@dataclass(frozen=True, slots=True)
class Reply:
    """A successful reply: its fields, and the descriptors it carried (the caller owns and
    closes them)."""

    fields: Mapping[str, Any]
    fds: tuple[int, ...] = ()


@dataclass(slots=True)
class _Pending:
    """A request in flight: set once, by the reader thread."""

    arrived: threading.Event = field(default_factory=threading.Event)
    message: Mapping[str, Any] | None = None
    fds: tuple[int, ...] = ()


class _Wire:
    """The socket and what is in flight on it, shared by the link and its reader thread."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.send_lock = threading.Lock()
        self.lock = threading.Lock()
        self.pending: dict[int, _Pending] = {}
        self.ids = itertools.count(1)
        self.closed = False
        self.hello: Mapping[str, Any] | None = None
        self.hello_arrived = threading.Event()

    def close(self) -> None:
        """Shut the socket down, which wakes the reader and gives the supervisor its
        end-of-file, then close it; every request in flight is answered `SupervisorGone`.
        Idempotent."""
        with self.lock:
            if self.closed:
                return
            self.closed = True
            waiting = list(self.pending.values())
            self.pending.clear()
        with contextlib.suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        for pending in waiting:
            pending.arrived.set()
        self.hello_arrived.set()

    def read_loop(self) -> None:
        """The only reader: each message to the request it answers, until end-of-file."""
        try:
            while True:
                try:
                    data, fds, flags, _ = socket.recv_fds(self.sock, MAX_MESSAGE, MAX_FDS)
                except OSError:
                    return
                for fd in fds:
                    os.set_inheritable(fd, False)
                if not data:
                    return
                self._deliver(data, tuple(fds), flags)
        finally:
            self.close()

    def _deliver(self, data: bytes, fds: tuple[int, ...], flags: int) -> None:
        """Hand one message to whoever waits for it; close its descriptors when nobody does
        (a reply that came after its request's deadline, or a message the host cannot read)."""
        message: Any = None
        if not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            try:
                message = json.loads(data)
            except ValueError:
                message = None
        if isinstance(message, dict) and "hello" in message:
            self.hello = message
            self.hello_arrived.set()
            _close_all(fds)
            return
        request_id = message.get("id") if isinstance(message, dict) else None
        with self.lock:
            pending = self.pending.pop(request_id, None) if isinstance(request_id, int) else None
        if pending is None or not isinstance(message, dict):
            _close_all(fds)
            return
        pending.message, pending.fds = message, fds
        pending.arrived.set()


def _close_all(fds: Sequence[int]) -> None:
    for fd in fds:
        with contextlib.suppress(OSError):
            os.close(fd)


class SupervisorLink:
    """A supervisor's control socket, from the host's side: `request` and `close`."""

    def __init__(self, sock: socket.socket, *, unresponsive: Callable[[], None]) -> None:
        """Start reading `sock`, the host's end of the socketpair. `unresponsive` ends the
        jail without the supervisor's help (`HostRuntime`'s teardown of its group); it is
        called once, when a request's deadline passes."""
        self._wire = _Wire(sock)
        self._unresponsive = unresponsive
        self._escalated = threading.Event()
        self.statuses: dict[str, int] = {}
        """What `wait` has learned of each process, by id, so a status survives the jail's
        end."""
        threading.Thread(
            target=self._wire.read_loop, name="brig-supervisor-link", daemon=True
        ).start()
        self._finalizer = weakref.finalize(self, self._wire.close)

    def wait_hello(self, timeout: float) -> Mapping[str, Any]:
        """The supervisor's greeting, once it has imported everything and can take requests.

        Raises:
            SupervisorGone: the socket closed before it spoke (it failed to start).
            TimeoutError: it did not speak within `timeout` seconds.
        """
        if not self._wire.hello_arrived.wait(timeout):
            raise TimeoutError(f"the supervisor said nothing within {timeout}s")
        hello = self._wire.hello
        if hello is None:
            raise SupervisorGone("the supervisor's end of the socket closed before it spoke")
        return hello

    def request(
        self,
        op: str,
        fields: Mapping[str, Any],
        *,
        timeout: float,
        fds: Sequence[int] = (),
    ) -> Reply:
        """Send `op` with `fields` (and `fds`, by `SCM_RIGHTS`) and wait for its reply, at
        most `timeout` seconds. Many threads may call this at once.

        Raises:
            SupervisorGone: the socket is closed, or closed while this waited.
            SupervisorUnresponsive: no reply within `timeout`; the jail was destroyed.
            SupervisorRefused: the supervisor answered with an error.
        """
        wire = self._wire
        pending = _Pending()
        with wire.lock:
            if wire.closed:
                raise SupervisorGone(f"the supervisor's socket is closed; {op!r} was not sent")
            request_id = next(wire.ids)
            wire.pending[request_id] = pending
        data = json.dumps({**fields, "id": request_id, "op": op}).encode()
        try:
            with wire.send_lock:
                socket.send_fds(wire.sock, [data], list(fds))
        except OSError as error:
            wire.close()
            raise SupervisorGone(f"sending {op!r} to the supervisor failed: {error}") from error
        if not pending.arrived.wait(timeout):
            with wire.lock:
                wire.pending.pop(request_id, None)
            if not pending.arrived.is_set():
                self._escalate(op, timeout)
        message = pending.message
        if message is None:
            raise SupervisorGone(f"the supervisor's socket closed while {op!r} was waiting")
        if message.get("ok") is not True:
            _close_all(pending.fds)
            raise SupervisorRefused(op, str(message.get("error", "no reason given")))
        return Reply(fields=message, fds=pending.fds)

    def _escalate(self, op: str, timeout: float) -> None:
        """A deadline missed: end the jail without the supervisor, once, and say so.

        Raises:
            SupervisorUnresponsive: always, naming the request and the deadline.
        """
        if not self._escalated.is_set():
            self._escalated.set()
            try:
                self._unresponsive()
            finally:
                self._wire.close()
        raise SupervisorUnresponsive(
            f"the supervisor did not answer {op!r} within {timeout}s, so the jail was destroyed "
            "without it (law 7: control must not require cooperation); everything in it is "
            "gone or being ended, and `Jail.destroy` reports what ended"
        )

    def close(self) -> None:
        """Close the host's end of the socket: the supervisor reads end-of-file and ends
        everything it holds. Idempotent."""
        self._finalizer()
