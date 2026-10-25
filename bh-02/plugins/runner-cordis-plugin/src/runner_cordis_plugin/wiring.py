"""The rows: a confined runner (brig) or an unconfined one, bound under `runner`; the rule for
what runs unasked, under `approval`; and `/release`."""

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component
from runner_cordis_plugin import allowlist
from runner_cordis_plugin.approval import Approval, Graded
from runner_cordis_plugin.jail import BrigConfig, BrigJail, Host
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


@runtime_checkable
class _Keyed(Host, Protocol):
    """The `host` value with what the models file's keys read (CONTRACTS.md: host): `key_envs`,
    each variable an endpoint's `key = { env = ... }` reads, to the endpoints that read it, and
    `models_file`, the file they were read from."""

    @property
    def key_envs(self) -> Mapping[str, Sequence[str]]: ...
    @property
    def models_file(self) -> str: ...


@component(provides=("runner",))
async def confined(*, config: BrigConfig, host: _Keyed) -> Effects:
    """Fills a `runner` row: `use = "runner:confined"`. A brig jail for each program it starts:
    writes confined to the project, no network, credentials unreadable, graded honestly. Depends
    on `host` so a program can never write the files the running composition is read from. The
    variables its programs see are the baseline, the names in the person's `runner.toml` and the
    layer's `env` when it sets one (`allowlist`); a list that is refused (`allowlist.Refused`)
    stops this row before a jail exists.

    Raises:
        Refused: `runner.toml` can't be used, or the list holds a variable a key reads."""
    file = allowlist.location(os.environ, Path.home())
    standing = await asyncio.to_thread(allowlist.read, file, Path.cwd())
    jailed, note = allowlist.effective(
        config, standing, file=file, readers=host.key_envs, models_file=host.models_file
    )
    yield bind("runner", Runner(BrigJail(jailed, host, note=note)))


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
    program in the runner to stop its own (the Python process, the extensions process), then has
    the runner let go of what it holds on the host (on Linux, the empty directories it keeps in place
    of write-denied paths that do not exist yet, such as `.envrc`) until the next start: the way to
    create one of those mid-session."""

    async def run(args: str) -> str:
        return await runner.release() or "Nothing runs in the runner, and it holds nothing."

    spec = {
        "name": "release",
        "help": "stop what runs in the runner until the next input (to create a path the jail holds)",
        "usage": "",
    }
    yield acquire(commands.register, spec, run)
