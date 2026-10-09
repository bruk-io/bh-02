"""The `runner` value over any mechanism: each owner stops its own program on `/release`, a start
ends a release, and each start is told to whoever watches; and the rows that bind it."""

from collections.abc import Mapping, Sequence
from typing import Any

from cordis.loader import resolve
from cordis.testing import drive
from runner_cordis_plugin import UNENFORCED, Runner, Unjailed, release, unconfined


class _Start:
    """A program a `_Mechanism` started: its grades and notice, and whether it was stopped."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.stopped = False

    def report(self) -> Mapping[str, str]:
        return {**UNENFORCED, "fs_read": f"grade {self.n}"}

    def notice(self) -> str:
        return f"notice {self.n}"

    async def stop(self) -> None:
        self.stopped = True


class _Mechanism:
    """What starts programs, numbered; `release` says what it freed and keeps the order it was
    asked in."""

    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.starts: list[_Start] = []

    def report(self) -> Mapping[str, str]:
        return UNENFORCED

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Start:
        self.starts.append(_Start(len(self.starts) + 1))
        return self.starts[-1]

    async def release(self) -> str:
        self.log.append("mechanism")
        return "Nothing holds /w/local.env."


async def test_release_asks_each_owner_to_stop_its_own_then_the_mechanism_and_says_what_each_said() -> None:
    log: list[str] = []
    runner = Runner(_Mechanism(log))

    def owner(name: str, said: str) -> Any:
        async def stop() -> str:
            log.append(name)
            return said

        return stop

    runner.on_release(owner("python", "The Python process is stopped."))
    remove = runner.on_release(owner("gone", "never said"))
    runner.on_release(owner("extensions", ""))  # nothing to say: left out
    remove()
    said = await runner.release()
    assert log == ["python", "extensions", "mechanism"]  # owners first: the mechanism frees what is left
    assert said == "The Python process is stopped. Nothing holds /w/local.env."


async def test_a_start_ends_a_release_and_is_told_to_each_watcher() -> None:
    mechanism = _Mechanism([])
    runner = Runner(mechanism)
    assert runner.report() == UNENFORCED and runner.notice() == ""  # before any start: the mechanism's
    seen: list[int] = []
    stop_watching = runner.on_start(lambda started: seen.append(started.n))  # type: ignore[attr-defined]
    await runner.release()
    assert runner.released()
    await runner.start(["x"], cwd="/w", endpoint="/s")
    assert not runner.released() and seen == [1]
    assert runner.report()["fs_read"] == "grade 1" and runner.notice() == "notice 1"
    stop_watching()
    await runner.start(["y"], cwd="/w", endpoint="/s")
    assert seen == [1] and runner.report()["fs_read"] == "grade 2"  # the last start's


async def test_the_runner_stops_no_program_itself() -> None:
    mechanism = _Mechanism([])
    runner = Runner(mechanism)
    await runner.start(["x"], cwd="/w", endpoint="/s")
    await runner.release()
    assert not mechanism.starts[0].stopped  # its owner registered no stop: it is the owner's


async def test_an_unconfined_runner_holds_nothing_to_release() -> None:
    assert await Unjailed().release() == ""
    effects = await drive(unconfined())
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "runner")]
    runner = effects[0].args[1]
    assert isinstance(runner, Runner) and runner.report() == UNENFORCED


async def test_the_release_row_offers_slash_release_over_the_runner() -> None:
    registered: list[tuple[Mapping[str, Any], Any]] = []

    class Commands:
        def register(self, spec: Mapping[str, Any], run: Any) -> Any:
            registered.append((spec, run))
            return lambda: None

    runner = Runner(_Mechanism([]))
    effects = await drive(release(runner=runner, commands=Commands()))
    assert [e.name for e in effects] == ["acquire"]
    effects[0].args[0](*effects[0].args[1:])
    ((spec, run),) = registered
    assert spec["name"] == "release" and "credential" in spec["help"]
    assert await run("") == "Nothing holds /w/local.env."
    assert await Runner(Unjailed()).release() == ""
    assert resolve("runner:release").inject == {"runner", "commands"}


async def test_nothing_running_and_nothing_held_is_said_so() -> None:
    registered: list[Any] = []

    class Commands:
        def register(self, spec: Mapping[str, Any], run: Any) -> Any:
            registered.append(run)
            return lambda: None

    effects = await drive(release(runner=Runner(Unjailed()), commands=Commands()))
    effects[0].args[0](*effects[0].args[1:])
    assert await registered[0]("") == "Nothing runs in the runner, and it holds nothing."
