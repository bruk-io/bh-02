"""The rows: the commands broker under `commands`; `jobs`, where commands queue the restarts
they ask for; the operator's commands registered into the broker; and `!`, a shell command,
the prefix claimed in it."""

import functools
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from commands_cordis_plugin.jobs import Jobs
from commands_cordis_plugin.operations import Loader, Operator, Queue
from commands_cordis_plugin.registry import Commands, CommandSpec, Run
from commands_cordis_plugin.shell_command import ShellCommandConfig, run_line
from cordis import Effects, acquire, background, bind, component
from cordis_helpers import perform

__all__ = ["jobs", "operator", "registry", "shell_command"]


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
    """What the jobs row needs of the `output` value: a line told to the person."""

    async def notice(self, message: str) -> None: ...


@component(provides=("jobs",))
async def jobs(*, output: _Notices) -> Effects:
    """Fills a `jobs` row: `use = "commands:jobs"`. The restarts commands queue (`put`), run one
    at a time in this row's own work, a failure told to the person (`output.notice`); and
    whether any is pending (`settled`), which the chat row waits on before it reads a line. It
    depends on `output` alone, which never reloads, so no restart it runs reloads it."""
    value = Jobs(output.notice)
    yield background(perform(value.queue, lambda why: output.notice(why)))
    yield bind("jobs", value)


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
async def operator(*, commands: _Registrar, loader: Loader, jobs: Queue) -> Effects:
    """Fills an `operator` row: `use = "commands:operator"`. /rows, /explain and /restart, over
    the loader that mounted it. A restart is queued in `jobs`, run after the command has
    answered, and one that fails is told to the person there. It depends on neither `model` nor
    `models`, so a composition without them keeps these commands, and a switch never reloads
    it."""
    for spec, run in Operator(loader, jobs).specs:
        yield acquire(commands.register, spec, run)
