"""A jail's channel directory as a runtime hands it out: reserve a socket, say where the host
dials it, dial it (SPEC.md section 10, decision-184, decision-185, decision-196).

Every runtime whose processes share a socket namespace with the host answers these four the same way
(`HostRuntime`, `OciRuntime`): the reserved socket is a file in `<jail_dir>/chan`, which the host
dials at the path the process binds, or at the directory of its own when the process has a mount
namespace, through the one verified dial (`brig/run/dial.py`). They are here so that a second
runtime does not carry a copy of the first's.
"""

import socket

from brig.run import _records
from brig.run.dial import dial
from brig.run.runtime import (
    JailRecord,
    ProcessRecord,
    Reservation,
    channel_dir_of,
    reserved_socket,
    socket_endpoint,
)


def reserve(jail: JailRecord, channel: str) -> Reservation:
    """A fresh socket in `jail`'s channel directory, under the jail directory resolved, as the
    mechanisms grant it (decision-184): its name 16 hex characters from `secrets` and `.sock`,
    never reused. The host shares the jail's paths, so the host dials the path the process binds,
    unless the jail's processes have mount namespaces of their own, where it is the directory the
    process sees over the channel directory (decision-196)."""
    path = reserved_socket(channel_dir_of(jail), _records.new_id())
    private = jail.namespaces is not None and jail.namespaces.held
    return Reservation(
        channel=channel, bound_path=path, endpoint=socket_endpoint(path, namespaces=private)
    )


def endpoint_of(process: ProcessRecord) -> str | None:
    """The path to dial `process`'s socket at: the one it binds, which the host shares
    (decision-184), or the one in the directory of its own when it has a mount namespace
    (decision-196). `None` for a process started with no channel."""
    if process.bound_path is None:
        return None
    return socket_endpoint(process.bound_path, namespaces=process.namespaces)


def connect_to(process: ProcessRecord) -> socket.socket:
    """A connected socket to `process`'s reserved socket (decision-185): refused before connecting
    when its path is a link or not a socket, and closed and refused after when its listener is not
    a process of `process`'s group led by its recorded leader (`brig/run/dial.py`).

    Raises:
        ValueError: `process` was started with no channel.
        EndpointRefused: the path is a link or not a socket, or the peer is not `process`'s own.
        OSError: nothing listens there yet.
    """
    endpoint = endpoint_of(process)
    if endpoint is None:
        raise ValueError(f"process {process.id} was started with no channel to connect to")
    return dial(
        endpoint, group=process.pgid, leader_pid=process.pid, leader_stamp=process.start_time
    )


def is_ready(process: ProcessRecord) -> bool:
    """Whether `connect_to` `process`'s socket succeeds now, closed at once; never whether the path
    exists (SPEC.md section 10). `False` for a process with no channel and while nothing listens.

    Raises:
        EndpointRefused: what is at its socket is not its own listener (decision-185), or the
            kernel could not say who listens there (decision-186): only "nothing listens yet"
            reads `False`.
    """
    if process.bound_path is None:
        return False
    try:
        connect_to(process).close()
    except OSError:
        return False
    return True
