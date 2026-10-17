"""A container's supervisor, from the host's side of its start (SPEC.md section 8, decision-203).

The supervisor is the container's PID 1 and its control socket cannot be an inherited descriptor:
through `docker start --attach` the container's descriptors are pipes the containerd shim made, and
`SCM_RIGHTS` and message boundaries, which the protocol needs, do not cross them (measured,
decision-203). So the host binds a `SOCK_SEQPACKET` listener in the channel directory before the
container starts (`bind_rendezvous`), the supervisor connects to it as its first act, and the host
accepts once (`accept_hello`): it requires the peer to be the container's PID 1 by the kernel's own
record of who connected (`SO_PEERCRED`, as the host's pid namespace numbers it, against `docker
inspect`'s `State.Pid`), lets `SupervisorLink` take the connection, and waits for its hello. The
caller then closes the listener and unlinks the path, so nothing listens once the supervisor has
spoken and a process of the jail finds no control socket to dial.

The supervisor's program is written to the jail directory before `docker create`
(`write_source`), which Docker binds read-only: it has no memory-backed bind as `bwrap --ro-bind-data`.

The decisions (`start_verdict`, `peer_refusal`, `container_state`) are pure and read the CLI's own
output; the rest is the shell that makes files and sockets.
"""

import contextlib
import json
import os
import socket
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Final

from brig.run._supervisor_link import SupervisorGone, SupervisorLink
from brig.run._supervisor_program import PROTOCOL, SUPERVISOR_SOURCE

#: How long the supervisor may take to connect and say hello: an interpreter starting, importing
#: and rehearsing, and bwrap's own allowance (`brig.run.host`): a miss is a host too loaded to start
#: a Python.
HELLO_TIMEOUT_S: Final = 60.0

#: How often the container is asked whether it still runs while the accept waits, so a supervisor
#: that died (an interpreter older than 3.9, a kernel without `pidfd_open`) is found in a second and
#: not at the deadline.
_ALIVE_CHECK_S: Final = 1.0

_ACCEPT_SLICE_S: Final = 0.25


class AgentStartFailed(RuntimeError):
    """The supervisor never became the container's agent: it ended before it connected, said
    nothing in time, was not the process that connected, or spoke another protocol. The message
    says which; the caller adds what `docker logs` said."""


class StartVerdict(Enum):
    """What `docker start` and the container's state afterwards say of the command."""

    STARTED = auto()
    NO_INTERPRETER = auto()
    FAILED = auto()


@dataclass(frozen=True, slots=True)
class ContainerState:
    """The parts of `docker inspect`'s `State` a start's verdict reads: `status`, `exit_code`
    (127 where the command was not found, 126 where it is there and cannot be run: Docker's own
    codes), `error` (Docker's message for a container that did not start), and `pid` (the host's pid
    of the container's PID 1, 0 when it is not running)."""

    status: str
    exit_code: int
    error: str
    pid: int


def container_state(stdout: str) -> ContainerState | None:
    """The `State` of the one container `docker inspect` printed, or `None` when it is not that.
    Pure."""
    try:
        (entry,) = json.loads(stdout)
        state = entry["State"]
        status, exit_code, error, pid = (
            state["Status"],
            state["ExitCode"],
            state["Error"],
            state["Pid"],
        )
    except ValueError, KeyError, TypeError:
        return None
    if (
        type(status) is not str
        or type(exit_code) is not int
        or type(error) is not str
        or type(pid) is not int
    ):
        return None
    return ContainerState(status=status, exit_code=exit_code, error=error, pid=pid)


def start_verdict(returncode: int, state: ContainerState | None) -> StartVerdict:
    """What the supervisor's `docker start` came to. A start that returned 0 started. One that
    failed with the container still `created` and its exit code 127 is a command that is not in the
    image (Docker's code for "the contained command could not be found", measured: `/usr/bin/python3`
    and the bare `python3` in an image with none); any other failure, 126 ("cannot be invoked")
    included, is a failure: only a missing interpreter is reason to try `docker exec`. Pure."""
    if returncode == 0:
        return StartVerdict.STARTED
    if state is not None and state.status == "created" and state.exit_code == 127:
        return StartVerdict.NO_INTERPRETER
    return StartVerdict.FAILED


def peer_refusal(peer_pid: int, init_pid: int) -> str | None:
    """Why the process that connected to the rendezvous socket is not the container's PID 1, or
    `None` when it is. `peer_pid` is the kernel's number for it in the host's pid namespace
    (`SO_PEERCRED`), `init_pid` `docker inspect`'s `State.Pid`. Pure."""
    if init_pid <= 0:
        return "the container's PID 1 is not known, so the connection cannot be vouched for"
    if peer_pid != init_pid:
        return (
            f"the process that connected is pid {peer_pid}, and the container's PID 1 is {init_pid}"
        )
    return None


def write_source(path: str) -> None:
    """Write the supervisor's program to `path`, mode 0444, created exclusively and not through a
    link: a stale file of an earlier create is removed first, and a link planted at the path is
    removed as the link it is and never followed.

    Raises:
        OSError: the file could not be written.
    """
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(fd, "w", encoding="utf-8") as source:
        source.write(SUPERVISOR_SOURCE)


def bind_rendezvous(path: str) -> socket.socket:
    """A listening `SOCK_SEQPACKET` socket at `path`, mode 0600, for the supervisor to connect to:
    a stale socket of an earlier create is removed first.

    Raises:
        OSError: it could not be bound (a path longer than the kernel allows, a directory that is
            not there).
    """
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        listener.bind(path)
        os.chmod(path, 0o600)
        listener.listen(1)
    except BaseException:
        listener.close()
        raise
    return listener


def release_rendezvous(listener: socket.socket, path: str) -> None:
    """Close the listener and remove its path: after the hello nothing listens."""
    listener.close()
    with contextlib.suppress(OSError):
        os.unlink(path)


def accept_hello(
    listener: socket.socket,
    *,
    init_pid: int,
    alive: Callable[[], bool],
    unresponsive: Callable[[], None],
) -> tuple[SupervisorLink, Mapping[str, Any]]:
    """Accept the supervisor's connection, once, require it to be the container's PID 1, and wait
    for its hello. `alive` asks whether the container still runs (once a second while waiting);
    `unresponsive` is the link's deadline function (`docker rm -f` of the container).

    Raises:
        AgentStartFailed: the container ended first, nothing connected or spoke within
            `HELLO_TIMEOUT_S`, the peer was not PID 1, or the hello names another protocol.
    """
    deadline = time.monotonic() + HELLO_TIMEOUT_S
    next_alive = time.monotonic() + _ALIVE_CHECK_S
    listener.settimeout(_ACCEPT_SLICE_S)
    while True:
        try:
            connection, _ = listener.accept()
            break
        except TimeoutError:
            pass
        now = time.monotonic()
        if now >= next_alive:
            next_alive = now + _ALIVE_CHECK_S
            if not alive():
                raise AgentStartFailed("the container ended before the supervisor connected")
        if now >= deadline:
            raise AgentStartFailed(f"the supervisor did not connect within {HELLO_TIMEOUT_S:.0f}s")
    connection.settimeout(None)
    peer_pid, _, _ = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    refusal = peer_refusal(peer_pid, init_pid)
    if refusal is not None:
        connection.close()
        raise AgentStartFailed(refusal)
    link = SupervisorLink(connection, unresponsive=unresponsive)
    try:
        hello = link.wait_hello(max(1.0, deadline - time.monotonic()))
    except SupervisorGone:
        link.close()
        raise AgentStartFailed(
            "the supervisor's end of the socket closed before it spoke"
        ) from None
    except TimeoutError:
        link.close()
        raise AgentStartFailed(
            f"the supervisor connected and said nothing within {HELLO_TIMEOUT_S:.0f}s"
        ) from None
    if hello.get("protocol") != PROTOCOL:
        link.close()
        raise AgentStartFailed(
            f"it speaks protocol {hello.get('protocol')!r} and this brig speaks {PROTOCOL}"
        )
    return link, hello


def missing_interpreter_reason(interpreter: str | None, image: str) -> str:
    """The sentence a record keeps of why a container's processes are started with `docker exec`:
    the interpreter the supervisor was to run under is not in the image (`docker start` answered
    127), or none was named. Pure."""
    if interpreter is None:
        return (
            f"the `oci` mechanism names no interpreter for the image {image!r} "
            "(Oci(interpreter=None)), so brig's supervisor was not tried"
        )
    return (
        f"the image {image!r} has no {interpreter!r}: `docker start` of brig's supervisor "
        "answered that the command was not found (exit code 127)"
    )
