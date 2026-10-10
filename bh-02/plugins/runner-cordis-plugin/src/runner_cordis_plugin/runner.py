"""The `runner` value: what starts the programs that run the model's code, and `/release`.

A runner starts a program (the Python process, the extensions process) through a mechanism: a
brig jail (`jail.BrigJail`, `runner:confined`) or none (`unconfined.Unjailed`,
`runner:unconfined`). This adds what is the same whichever it is:

- Each owner holds its own start. The row that starts a program is the one that stops it: on
  `/release` the runner asks each owner that registered (`on_release`) to stop its own process
  and say what it stopped, then has the mechanism let go of what it holds on the host (on Linux,
  the placeholders where bh-02 looks for its credential). The runner never stops another row's
  program.
- A release ends with the next start, whoever starts: while `released()`, an owner that would
  start only to keep something warm (the extensions process) waits, and one the person asked for
  (an input, a change the model made) starts, ending it.
- The grades of each start are reported to whoever watches (`on_start`): the status bar's
  field, and an owner waiting for a release to end.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable

from cordis_helpers import Hooks

__all__ = ["Mechanism", "Runner", "Started"]


@runtime_checkable
class Started(Protocol):
    """A program a runner started: what its own start is (its grades, and what the person should
    know of it), and how to stop it."""

    def report(self) -> Mapping[str, str]: ...
    def notice(self) -> str: ...
    async def stop(self) -> None: ...


@runtime_checkable
class Mechanism(Protocol):
    """What starts a program: a brig jail, or nothing at all. `release` lets go of what it holds
    on the host once no program of its runs, and says what that freed."""

    def report(self) -> Mapping[str, str]: ...
    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Started: ...
    async def release(self) -> str: ...


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
        """What the person should know of the last start ("" before any, or when nothing)."""
        return self._last.notice() if self._last is not None else ""

    def released(self) -> bool:
        """Whether `/release` has stopped what runs and nothing has started since."""
        return self._released

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Started:
        """Start `argv` in `cwd`, listening on `endpoint`; tell each watcher (`on_start`). A start
        ends a release, before anything waits."""
        self._released = False
        started = await self._mechanism.start(argv, cwd=cwd, endpoint=endpoint)
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
