"""The rows: the commands broker under `commands`; the operator's commands registered into it;
and `!`, a shell command, the prefix claimed in it."""

import asyncio
import functools
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from commands_cordis_plugin.operations import Loader, Operator, unfinished
from commands_cordis_plugin.registry import Commands, CommandSpec, Run
from commands_cordis_plugin.shell_command import ShellCommandConfig, run_line
from cordis import Effects, acquire, background, bind, component
from cordis_helpers import Job, perform

__all__ = ["operator", "registry", "shell_command"]


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value."""

    def register(self, spec: CommandSpec, run: Run) -> Callable[[], None]: ...


@runtime_checkable
class _Claimant(Protocol):
    """What a row that takes the lines starting with a prefix needs of the `commands` value."""

    def claim(self, prefix: str, spec: CommandSpec, run: Run) -> Callable[[], None]: ...


@runtime_checkable
class _Notices(Protocol):
    """What the operator needs of the `output` value: a line told to the person."""

    async def notice(self, message: str) -> None: ...


@component(provides=("commands",))
async def registry() -> Effects:
    """Fills a `commands` row: `use = "commands:registry"`. Rows register commands into it, and
    rows in a layer claim line prefixes."""
    yield bind("commands", Commands())


@component
async def shell_command(*, commands: _Claimant, config: ShellCommandConfig) -> Effects:
    """Fills a `shell-command` row: `use = "commands:shell_command"`. A line starting with `!`
    (`prefix`) runs as a shell command, as the person, in the project (`cwd`), its output
    captured and stopped at its `timeout`; what it printed is shown, and the model reads it with
    the person's next message. It claims the prefix in `commands`, which only a layer's row can:
    an extension reaches `commands` through its `register` alone."""
    spec: CommandSpec = {
        "name": "shell",
        "help": "run COMMAND in your shell, here, as you; the model reads its output with your next message",
        "usage": "COMMAND",
    }
    yield acquire(commands.claim, config.prefix, spec, functools.partial(run_line, config=config))


@component
async def operator(*, commands: _Registrar, loader: Loader, output: _Notices) -> Effects:
    """Fills an `operator` row: `use = "commands:operator"`. /rows, /explain and /restart, over
    the loader that mounted it. Its restarts are its own background work, run after the command
    has answered, so one that fails is told to the person (`output.notice`). It depends on
    neither `model` nor `models`, so a composition without them keeps these commands, and a
    switch never reloads it."""
    jobs: asyncio.Queue[Job] = asyncio.Queue()
    yield background(perform(jobs, lambda why: output.notice(unfinished(why))))
    for spec, run in Operator(loader, jobs).specs:
        yield acquire(commands.register, spec, run)
