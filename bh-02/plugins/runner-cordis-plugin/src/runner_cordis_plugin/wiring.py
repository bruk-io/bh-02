"""The rows: a confined runner (brig) or an unconfined one, bound under `runner`; the rule for
what runs unasked, under `approval`; and `/release`."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component
from runner_cordis_plugin.approval import Approval, Graded
from runner_cordis_plugin.jail import BrigConfig, BrigJail, Layers
from runner_cordis_plugin.runner import Runner
from runner_cordis_plugin.unconfined import Unjailed

__all__ = ["approval", "confined", "release", "unconfined"]


@runtime_checkable
class _Releasing(Protocol):
    """What `/release` needs of the `runner` value (CONTRACTS.md: runner)."""

    async def release(self) -> str: ...


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value (CONTRACTS.md: commands)."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@component(provides=("runner",))
async def confined(*, config: BrigConfig, layers: Layers) -> Effects:
    """Fills a `runner` row: `use = "runner:confined"`. A brig jail for each program it starts:
    writes confined to the project, no network, credentials unreadable, graded honestly. Depends
    on `layers` so a program can never write the files the running composition is read from."""
    yield bind("runner", Runner(BrigJail(config, layers)))


@component(provides=("runner",))
async def unconfined() -> Effects:
    """Fills a `runner` row with no confinement: `use = "runner:unconfined"` (`--no-jail`). Every
    input, and every extension to load, is then put to the person."""
    yield bind("runner", Runner(Unjailed()))


@component(provides=("approval",))
async def approval(*, runner: Graded) -> Effects:
    """Fills an `approval` row: `use = "runner:approval"`. The rule for what runs unasked: what
    runs in the runner, when the runner confines it. Asking the person is the asker's (the loop,
    the extensions row), through `output.confirm`. Depends on the runner alone, so `/clear` (a new
    Python process) leaves it up. It runs in bh-02's own process: only a layer replaces it."""
    yield bind("approval", Approval(runner))


@component
async def release(*, runner: _Releasing, commands: _Registrar) -> Effects:
    """Fills a `release` row: `use = "runner:release"`. `/release` asks each row that started a
    program in the runner to stop its own (the Python process, the extensions' worker), then has
    the runner let go of what it holds on the host (on Linux, where bh-02 looks for its
    credential) until the next start: the way to add a credential mid-session."""

    async def run(args: str) -> str:
        return await runner.release() or "Nothing runs in the runner, and it holds nothing."

    spec = {
        "name": "release",
        "help": "stop what runs in the runner until the next input (to add your credential)",
        "usage": "",
    }
    yield acquire(commands.register, spec, run)
