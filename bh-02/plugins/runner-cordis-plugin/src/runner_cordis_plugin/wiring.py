"""The rows: a confined runner (brig) or an unconfined one, bound under `runner`; the rule for
what runs unasked, under `approval`; the grants broker, under `grants`, and `/grants`; and
`/release`."""

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component
from runner_cordis_plugin import allowlist
from runner_cordis_plugin.approval import Approval, Graded
from runner_cordis_plugin.broker import Broker
from runner_cordis_plugin.commands import Listing, grants_command
from runner_cordis_plugin.jail import BrigJail, Granting, Host
from runner_cordis_plugin.policy import BrigConfig
from runner_cordis_plugin.runner import ArgvFor, Runner, Started
from runner_cordis_plugin.unconfined import Unjailed

__all__ = ["approval", "confined", "grant_prompt", "grants", "release", "unconfined"]


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
class _KeyReaders(Protocol):
    """What the confined runner needs of the `models` value (CONTRACTS.md: models): `key_envs()`,
    each variable an endpoint the model row can reach reads as its key, to those endpoints, read
    fresh."""

    def key_envs(self) -> Mapping[str, Sequence[str]]: ...


class _Rechecked:
    """The jail, which first asks `refuse` at each start: the variables the model row's keys read
    change with the layers (another models file, an endpoint added), and the row does not
    reload for that, so a list that was fine when the row came up is checked again."""

    def __init__(self, jail: BrigJail, refuse: Callable[[], None]) -> None:
        self._jail = jail
        self._refuse = refuse

    def report(self) -> Mapping[str, str]:
        return self._jail.report()

    def notice(self) -> str:
        return self._jail.notice()

    async def release(self) -> str:
        return await self._jail.release()

    async def start(self, argv_for: ArgvFor, *, cwd: str) -> Started:
        self._refuse()
        return await self._jail.start(argv_for, cwd=cwd)


@component(provides=("runner",))
async def confined(*, config: BrigConfig, host: Host, models: _KeyReaders, grants: Granting) -> Effects:
    """Fills a `runner` row: `use = "runner:confined"`. A brig jail for each program it starts:
    writes confined to the project, no network, credentials unreadable, graded honestly. Depends
    on `host` so a program can never write the files the running composition is read from, and on
    `grants`, whose value (not its binding) changes with what is granted, so a grant never reloads
    the row: each start reads `grants.granted()`. The
    variables its programs see are the baseline, the names in the person's `runner.toml` and the
    layer's `env` when it sets one (`allowlist`); a list that names a variable a key reads
    (`models.key_envs()`: every endpoint the model row can reach, asked again at each start) is
    refused (`allowlist.Refused`), the row before a jail exists and a start before its jail does.

    Raises:
        Refused: `runner.toml` can't be used, or the list holds a variable a key reads."""
    file = allowlist.location(os.environ, Path.home())
    standing = await asyncio.to_thread(allowlist.read, file, Path.cwd())

    def refuse() -> None:
        allowlist.effective(config, standing, file=file, readers=models.key_envs())

    jailed, note = allowlist.effective(config, standing, file=file, readers=models.key_envs())
    jail = BrigJail(jailed, host, note=note, key_envs=models.key_envs, grants=grants)
    yield bind("runner", Runner(_Rechecked(jail, refuse)))


@component(provides=("runner",))
async def unconfined() -> Effects:
    """Fills a `runner` row with no confinement: `use = "runner:unconfined"` (`--no-jail`). Every
    input, and every extension to load, is then put to the person."""
    yield bind("runner", Runner(Unjailed()))


@component(provides=("grants",))
async def grants(*, host: Host) -> Effects:
    """Fills a `grants` row: `use = "runner:grants"`. The broker of what the person granted the
    jail: a row's `need`, a requester's `ask`, `granted()` (what each start applies), `list` and
    `revoke`. It depends on `host` alone, which the shell pins, so the row never reloads: a grant
    changes the value it bound and not the binding, and so reloads neither `approval` (which
    depends on neither this row nor a requester) nor `runner:confined`."""
    yield bind("grants", Broker(Path(host.grants) if host.grants else None))


@component
async def grant_prompt(*, grants: Listing, commands: _Registrar) -> Effects:
    """Fills a `grant-prompt` row: `use = "runner:grant_prompt"`. `/grants` lists what is granted
    (id, kind, target, answer, scope, who asked and why) and `/grants revoke ID` takes one back,
    for the session or, for an always-grant, the project: the next start no longer applies it."""
    spec = {
        "name": "grants",
        "help": "list what is granted to the jail, or `revoke ID` to take one back",
        "usage": "[revoke ID]",
    }
    yield acquire(commands.register, spec, partial(grants_command, grants))


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
