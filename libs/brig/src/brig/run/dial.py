"""The host's one dial of a reserved socket: a socket, not a link, and its own process answering.

SPEC.md section 10, decision-185 (TASK-0079.33). A reserved socket's path is in
the jail's channel directory, which the jail can write, so a process of the jail
can put a link there to a host socket outside it; a plain `connect` follows the
link and the host speaks its protocol to whatever its user can reach. `dial` is
the only connect `HostRuntime` makes to a reserved socket, for readiness and
for `Process.connect` alike, and it checks twice:

- before connecting, `lstat`: the path is a socket, not a link or anything
  else (`_path_refusal`). A race on its own, so the cheap half;
- after connecting, the peer: the kernel's record of who listens (Linux
  `SO_PEERCRED`, darwin `LOCAL_PEERPID`) is a process in the started process's
  own group, whose leader still holds its recorded identity, read after the
  peer's group so the group's number can't have passed to a stranger
  (`_peer_refusal`). Where Linux offers `SO_PEERPIDFD`, the listener's pidfd
  must be alive before and after the group is read, so a pid reused after its
  listener left can't stand in for it. A platform with no peer reading refuses.

The verdicts are pure; `dial` and `_read_peer` are the shell.
"""

import errno
import os
import signal
import socket
import stat
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from brig.run import _identity


class EndpointRefused(RuntimeError):
    """The host would not dial a reserved socket (decision-185): what is at
    its path is not a socket (a link a process of the jail planted, a file),
    or what answered is not a process of the started process's group, or brig
    can't tell on this platform. Nothing was sent; any connection made was
    closed. `endpoint` is the path, `reason` why."""

    def __init__(self, endpoint: str, reason: str) -> None:
        self.endpoint = endpoint
        self.reason = reason
        super().__init__(
            f"refused to dial {endpoint!r}: {reason}. A process of the jail can write the "
            "channel directory, so the host dials only the started process's own listener"
        )


#: `SO_PEERPIDFD` (Linux 6.5): the listener's pidfd. Python names no constant
#: for it; 77 is its number where `SO_PEERCRED` is 17, the generic numbering
#: (x86_64 and arm64 among it). Elsewhere brig doesn't guess it.
_SO_PEERPIDFD: Final = 77 if getattr(socket, "SO_PEERCRED", None) == 17 else None

#: darwin's `SOL_LOCAL` and `LOCAL_PEERPID` (`<sys/un.h>`): the peer's pid.
_SOL_LOCAL: Final = 0
_LOCAL_PEERPID: Final = 0x002


@dataclass(frozen=True, slots=True)
class _Peer:
    """What the kernel says answered a connect: `pid` as this process's pid
    namespace numbers it (0: it can't), `pgid` its process group (`None`: it
    could not be read, the process has left), and `left`, that its pidfd says
    the listener exited (always `False` where there is no pidfd)."""

    pid: int
    pgid: int | None
    left: bool


def _path_refusal(mode: int) -> str | None:
    """Why the file whose `lstat` mode is `mode` is not dialled, or `None`
    for a socket. Pure."""
    if stat.S_ISSOCK(mode):
        return None
    if stat.S_ISLNK(mode):
        return "it is a symbolic link, which would send the host wherever it points"
    return "it is not a socket"


def _peer_refusal(peer: _Peer | None, *, group: int, leader_holds: bool) -> str | None:
    """Why `peer` is not the started process's own listener, with `group` that
    process's group and `leader_holds` whether its leader held its recorded
    identity when asked after the peer's group was read; `None` when it is.
    `peer` `None`: brig reads no peer on this platform. Pure."""
    if peer is None:
        return f"brig can't read a socket's peer on {sys.platform}, so it can't tell who answers"
    if peer.pid <= 0:
        return "the kernel can't number its listener from here"
    if peer.left or peer.pgid is None:
        return f"its listener (pid {peer.pid}) has left"
    if peer.pgid != group:
        return (
            f"its listener (pid {peer.pid}) is in process group {peer.pgid}, not the "
            f"started process's group {group}"
        )
    if not leader_holds:
        return (
            f"the started process's group leader (pid {group}) no longer holds its recorded "
            "identity, so its group's number can't vouch for the listener"
        )
    return None


def _pidfd_alive(pidfd: int) -> bool:
    """Whether the process `pidfd` refers to still runs (a zombie counts):
    signal 0 delivered or refused for permission."""
    try:
        signal.pidfd_send_signal(pidfd, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _peer_pidfd(sock: socket.socket) -> int | None:
    """The listener's pidfd, or `None` where the kernel has no `SO_PEERPIDFD`.

    Raises:
        ProcessLookupError: the kernel has it and could not give one because
            the listener has left (`ESRCH`, or `EINVAL` from a kernel
            that makes no pidfd for an exited process).
        OSError: anything else the kernel reports.
    """
    if _SO_PEERPIDFD is None:
        return None
    try:
        return int(sock.getsockopt(socket.SOL_SOCKET, _SO_PEERPIDFD))
    except OSError as error:
        if error.errno in (errno.ENOPROTOOPT, errno.EOPNOTSUPP):
            return None
        if error.errno in (errno.ESRCH, errno.EINVAL):
            raise ProcessLookupError(error.errno, "the socket's listener has left") from error
        raise


def _pgid(pid: int) -> int | None:
    """`pid`'s process group, `None` when there is no such process to ask."""
    try:
        return os.getpgid(pid)
    except ProcessLookupError, PermissionError:
        return None


def _read_peer(sock: socket.socket) -> _Peer | None:
    """Who answered `sock`'s connect, as the kernel records it, or `None` on a
    platform brig reads no peer on. On Linux with a pidfd, the listener is
    required alive before and after its group is read (`left` otherwise).

    Raises:
        OSError: the kernel could not report the peer.
    """
    if sys.platform.startswith("linux"):
        pid, _, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        try:
            pidfd = _peer_pidfd(sock)
        except ProcessLookupError:
            return _Peer(pid=pid, pgid=None, left=True)
        try:
            if pidfd is not None and not _pidfd_alive(pidfd):
                return _Peer(pid=pid, pgid=None, left=True)
            pgid = _pgid(pid) if pid > 0 else None
            return _Peer(pid=pid, pgid=pgid, left=pidfd is not None and not _pidfd_alive(pidfd))
        finally:
            if pidfd is not None:
                os.close(pidfd)
    if sys.platform == "darwin":
        pid = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERPID)
        return _Peer(pid=pid, pgid=_pgid(pid) if pid > 0 else None, left=False)
    return None


def dial(
    endpoint: str,
    *,
    group: int,
    leader_pid: int,
    leader_stamp: str,
    lstat: Callable[[str], os.stat_result] = os.lstat,
) -> socket.socket:
    """A connected `AF_UNIX` stream socket to the reserved socket at
    `endpoint`, whose listener is a process of the group `group`, led by
    `leader_pid` holding `leader_stamp` (decision-185). Refuses a path that is
    not a socket before connecting, and closes the connection and refuses when
    the peer is not one of the group's. `lstat` is the path check's seam.

    Raises:
        EndpointRefused: the path is a link or not a socket, or the peer is
            not a process of `group` (or its leader's identity can't vouch for
            it, or brig reads no peer here, or the kernel could not report the
            peer of a connection that succeeded: decision-186).
        OSError: nothing listens there yet (`FileNotFoundError`,
            `ConnectionRefusedError`): only the `lstat` and the `connect`
            raise one.
    """
    reason = _path_refusal(lstat(endpoint).st_mode)
    if reason is not None:
        raise EndpointRefused(endpoint, reason)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(endpoint)
    except BaseException:
        sock.close()
        raise
    try:
        try:
            peer = _read_peer(sock)
        except OSError as error:
            # Something answered; who, the kernel would not say. Not "not
            # yet": a caller polling readiness would wait it out (decision-186).
            raise EndpointRefused(
                endpoint, f"the kernel could not report who listens there ({error})"
            ) from error
        # Asked after the peer's group was read: while the leader holds its
        # identity, its group's number has named this group throughout.
        holds = leader_stamp != _identity.UNKNOWN and _identity.identity_holds(
            leader_pid, leader_stamp
        )
        reason = _peer_refusal(peer, group=group, leader_holds=holds)
    except BaseException:
        sock.close()
        raise
    if reason is not None:
        sock.close()
        raise EndpointRefused(endpoint, reason)
    return sock
