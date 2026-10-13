"""The jail's own hold on its tether (decision-167, made per start by decision-181).

`create` takes the read end of a pipe whose write end the embedder keeps. Every
process the jail starts is tethered to it: its exit wrapper starts a watcher on
that read end, in the process's own group, before the workload, and the watcher
ends the group once every write end is closed. So the jail needs the read end
for as long as it can start anything, while the embedder may close its own copy
once `create` returns, as it could after `launch` before.

`HeldTether` is that hold: a duplicate of the read end, not inheritable, held in
memory and never in a record (an fd does not serialize). Each start passes it to
its own wrapper alone (`pass_fds`), and the wrapper hands it to its watcher and
closes its own copy, as decision-167's wrapper did. The duplicate is closed when
the last in-memory holder is collected (`weakref.finalize`), never by `destroy`,
so ending a jail changes nothing about what a later start does.
"""

import os
import select
import weakref


class TetherClosed(RuntimeError):
    """A start was refused because the jail's tether has ended: every write
    end is closed (the embedder closed it, or died), or the jail's own hold on
    it was released. A process started now would be ended by its watcher at
    once, or run untethered, so nothing is started (decision-181)."""


def _at_eof(fd: int) -> bool:
    """Whether reading `fd`, a pipe's read end, would return end-of-file now.

    Polled with no wait; a pending byte is read and dropped (the tether carries
    no data: its watchers read and drop whatever is written). Never blocks,
    and never sets `O_NONBLOCK`, which is shared with every watcher holding the
    same pipe and would turn their blocking read into an error, and so a kill."""
    if hasattr(select, "poll"):
        poller = select.poll()
        poller.register(fd, select.POLLIN)
        if not poller.poll(0):
            return False
    elif not select.select([fd], [], [], 0)[0]:
        return False
    return os.read(fd, 512) == b""


class HeldTether:
    """A jail's duplicate of its tether's read end, alive while it is held.

    A class because it owns a resource with a lifecycle: the fd, closed once,
    when the holder is collected or `release` is called."""

    def __init__(self, fd: int) -> None:
        """Duplicate `fd` (the tether's read end), not inheritable.

        Raises:
            OSError: `fd` is not an open descriptor.
        """
        self._fd = os.dup(fd)
        self._finalizer = weakref.finalize(self, os.close, self._fd)

    def fd(self) -> int:
        """The read end to hand to a start's wrapper.

        Raises:
            TetherClosed: the tether is at end-of-file, or this hold was released.
        """
        if not self._finalizer.alive:
            raise TetherClosed("the jail's hold on its tether was released; nothing is started")
        if _at_eof(self._fd):
            raise TetherClosed(
                "the jail's tether has ended (every write end is closed: the embedder "
                "closed it or died), so a process started now would be killed at once; "
                "nothing is started. Create a new jail with a live tether"
            )
        return self._fd

    def release(self) -> None:
        """Close the duplicate now. Idempotent."""
        self._finalizer()
