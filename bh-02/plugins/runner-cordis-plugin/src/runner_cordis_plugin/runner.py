"""The `runner` value: what starts the programs that run the model's code, and `/release`.

A runner starts a program (the Python process, the extensions process) through a mechanism: a
brig jail (`jail.BrigJail`, `runner:confined`) or none (`unconfined.Unjailed`,
`runner:unconfined`). This adds what is the same whichever it is:

- Each owner holds its own start. The row that starts a program is the one that stops it: on
  `/release` the runner asks each owner that registered (`on_release`) to stop its own process
  and say what it stopped, then has the mechanism let go of what it holds on the host (on Linux,
  the placeholders it holds in place of write-denied paths that do not exist yet). The runner never
  stops another row's program.
- A release ends with the next start, whoever starts: while `released()`, an owner that would
  start only to keep something warm (the extensions process) waits, and one the person asked for
  (an input, a change the model made) starts, ending it.
- The grades of each start are reported to whoever watches (`on_start`): the status bar's
  field, and an owner waiting for a release to end.
"""

import shutil
import socket
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from cordis_helpers import Hooks

__all__ = ["Mechanism", "Runner", "Started", "reserved_endpoint", "unreserve_endpoint"]


@runtime_checkable
class Started(Protocol):
    """A program a runner started: what its own start is (its grades, and what the person should
    know of it), and how to stop it."""

    @property
    def endpoint(self) -> str:
        """The Unix socket the program listens on: the one the runner chose for this start. It is
        for the program's argv alone; an owner never dials it (`connection` is the way in)."""
        ...

    @property
    def connection(self) -> socket.socket:
        """The runner's own connected, blocking stream socket to the program, made when it was
        ready. The owner takes it (`asyncio.open_unix_connection(sock=...)`) and closes it; `stop`
        closes it too. Never dial `endpoint`: a jailed program can swap its socket for a link to
        another one. A second connection means a new start."""
        ...

    def interrupt(self) -> bool:
        """Ask the program to stop what it is running (an input); whether it was running."""
        ...

    def ended(self) -> str:
        """Why the jail ended the program itself, for the person; "" when it did not."""
        ...

    def report(self) -> Mapping[str, str]: ...
    def notice(self) -> str: ...

    def reads(self) -> tuple[str, ...]:
        """The trees it can read when that is all it can read; empty when it reads everything
        but what it hides, or is no jail."""
        ...

    def writes(self) -> tuple[str, ...]:
        """The directories it may write but a scratch directory of its own; empty when it
        confines no writes."""
        ...

    async def stop(self) -> None: ...


@runtime_checkable
class Mechanism(Protocol):
    """What starts a program: a brig jail, or nothing at all. `release` lets go of what it holds
    on the host once no program of its runs, and says what that freed."""

    def report(self) -> Mapping[str, str]: ...
    def notice(self) -> str: ...
    async def start(self, argv_for: ArgvFor, *, cwd: str, owner: str) -> Started: ...
    async def release(self) -> str: ...


type ArgvFor = Callable[[str], Sequence[str]]
type Release = Callable[[], Awaitable[str]]
type Watch = Callable[[Started], None]


class Runner:
    """Implements `runner` (CONTRACTS.md: runner) over one mechanism."""

    def __init__(self, mechanism: Mechanism) -> None:
        self._mechanism = mechanism
        self._released = False
        self._last: Started | None = None
        self._releases: Hooks[Release] = Hooks()
        self._starts: Hooks[Watch] = Hooks()

    def report(self) -> Mapping[str, str]:
        """The grades of the last start (before any, the mechanism's own)."""
        return self._last.report() if self._last is not None else self._mechanism.report()

    def notice(self) -> str:
        """What the person should know of the last start (before any, the mechanism's own: that it
        can jail nothing here); "" when nothing."""
        return self._last.notice() if self._last is not None else self._mechanism.notice()

    def released(self) -> bool:
        """Whether `/release` has stopped what runs and nothing has started since."""
        return self._released

    async def start(self, argv_for: ArgvFor, *, cwd: str, owner: str) -> Started:
        """Start the program `argv_for(endpoint)` in `cwd`, listening on the endpoint the runner
        chose for it (`started.endpoint`, handed to `argv_for` before anything starts); tell each
        watcher (`on_start`). `owner` is the row that starts it (`python`, `extensions`): a
        connection the program makes that is refused is asked as its input. A start ends a release,
        before anything waits."""
        self._released = False
        started = await self._mechanism.start(argv_for, cwd=cwd, owner=owner)
        self._last = started
        for watch in tuple(self._starts):
            watch(started)
        return started

    def on_release(self, stop: Release) -> Callable[[], None]:
        """Have `stop()` asked on `/release`: an owner stops its own process and returns what the
        person is told of it ('' for nothing). Returns its remover."""
        return self._releases.add(stop)

    def on_start(self, watch: Watch) -> Callable[[], None]:
        """Have `watch(started)` told of each start, after it. Returns its remover."""
        return self._starts.add(watch)

    async def release(self) -> str:
        """`/release`: each owner stops its own process (`on_release`), then the mechanism lets
        go of what it holds on the host; what each says, in that order. The runner is then
        `released` until its next start."""
        self._released = True  # before anything waits: from here on, an owner that waits starts nothing
        said = [await stop() for stop in tuple(self._releases)]
        said.append(await self._mechanism.release())
        return " ".join(part for part in said if part)


def reserved_endpoint() -> str:
    """A socket path for one start, in a directory of its own that only that start uses: short
    (a Unix socket path must fit in about 100 bytes) and under `/tmp`, which a jail may be given
    to write. A mechanism reserves it before the program's command is built, and gives the
    directory back with `unreserve_endpoint` once the program is stopped."""
    return str(Path(tempfile.mkdtemp(prefix="bh-s-", dir="/tmp"), "k.sock"))


def unreserve_endpoint(endpoint: str) -> None:
    """Remove the directory `reserved_endpoint` made for `endpoint`, with whatever is in it."""
    shutil.rmtree(Path(endpoint).parent, ignore_errors=True)
