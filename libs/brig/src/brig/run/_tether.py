"""The jail's own hold on its tether (decision-167, made per start by decision-181), and the
lifeline a supervised jail with no tether gives its helpers (decision-199).

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

`HeldLifeline` is the tether a supervised jail has no use for and its helpers still need: a
supervised jail's processes end with the socket its supervisor reads (decision-191), a socket
no helper can watch without holding the end that would keep it open. It is a pipe the jail
makes, whose write end it alone holds: the kernel closes that end when the creating process
dies, and the jail's collection closes it, which is exactly when the socket closes.
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

        The tether is at end-of-file once every write end is closed: a copy that a child
        forked by another thread still holds, before its exec, keeps it open for a moment,
        and a start made then is not refused (SPEC.md section 8, TASK-0079.25 point 2).

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


def _close_both(read_end: int, write_end: int) -> None:
    os.close(read_end)
    os.close(write_end)


class HeldLifeline:
    """A pipe whose write end only this object holds, for the helpers of a supervised jail with
    no tether (decision-199): each helper's watcher reads the other end and ends the helper's
    group once this one is closed.

    A class because it owns a resource with a lifecycle: both ends, closed once, when the
    holder is collected (the kernel closes them if the process dies first). Neither end is
    inheritable, so a start passes the read end to its own wrapper alone (`pass_fds`) and
    nothing else ever holds the write end.
    """

    def __init__(self) -> None:
        """Make the pipe.

        Raises:
            OSError: no descriptor could be made.
        """
        self._read, write_end = os.pipe()
        weakref.finalize(self, _close_both, self._read, write_end)

    def fd(self) -> int:
        """The read end, to hand to a helper's wrapper."""
        return self._read
