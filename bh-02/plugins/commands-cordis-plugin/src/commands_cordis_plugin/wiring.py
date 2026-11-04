"""The rows: the commands broker under `commands`; `jobs`, where commands queue the restarts
they ask for; the operator's commands registered into the broker; and `!`, a shell command,
the prefix claimed in it."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from commands_cordis_plugin.jobs import Jobs
from commands_cordis_plugin.operations import Loader, Operator, Queue
from commands_cordis_plugin.registry import Commands, CommandSpec, Run
from commands_cordis_plugin.shell_command import ShellCommandConfig, run_line
from cordis import Effects, acquire, background, bind, component
from cordis.loader import resolve
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
    depends on `output`, which the ui row binds, so a restart of the ui, of `jobs` itself, or of
    any row it depends on would reload it and cancel the restart it runs: `/restart` refuses
    those rows (the operator's `restart`), and the ui is restarted only by restarting the program."""
    value = Jobs(output.notice)
    yield background(perform(value.queue, lambda why: output.notice(why)))
    yield bind("jobs", value)


@component(provides=("commands",))
async def registry() -> Effects:
    """Fills a `commands` row: `use = "commands:registry"`. Rows register commands into it, and
    rows in a layer claim line prefixes."""
    yield bind("commands", Commands())


@runtime_checkable
class _KeyReaders(Protocol):
    """What the shell-command row needs of the `models` value: `key_envs()`, each variable an
    endpoint the model row can reach reads as its key (CONTRACTS.md: models), read fresh."""

    def key_envs(self) -> Mapping[str, Sequence[str]]: ...


@component
async def shell_command(*, commands: _Claimant, config: ShellCommandConfig, models: _KeyReaders) -> Effects:
    """Fills a `shell-command` row: `use = "commands:shell_command"`. A line starting with `!`
    (`prefix`) runs as a shell command, as the person, in the project (`cwd`), its output
    captured and stopped at its `timeout`; what it printed is shown, and the model reads it with
    the person's next message, so the command's environment lacks the variables the keys of the
    model row's endpoints read (`models.key_envs()`, asked at each command), as it lacks
    `ANTHROPIC_*` and `CLAUDE*`. It claims the prefix in `commands`, which only a layer's row can:
    an extension reaches `commands` through its `register` alone."""
    spec: CommandSpec = {
        "name": "shell",
        "help": "run COMMAND in your shell, here, as you; the model reads its output with your next message",
        "usage": "COMMAND",
    }

    async def run(command: str) -> str | list[dict[str, Any]]:
        return await run_line(command, config=config, withheld=frozenset(models.key_envs()))

    yield acquire(commands.claim, config.prefix, spec, run)


def _declared(use: str) -> tuple[frozenset[str], frozenset[str]] | None:
    """The keys the component a row's `use` names injects and provides; None if it does not resolve."""
    try:
        component = resolve(use)
    except Exception:  # importing a module can raise anything; the loader reports that row itself
        return None
    return component.inject, component.provides


@component
async def operator(*, commands: _Registrar, loader: Loader, jobs: Queue) -> Effects:
    """Fills an `operator` row: `use = "commands:operator"`. /rows, /explain and /restart, over
    the loader that mounted it. A restart is queued in `jobs`, run after the command has
    answered, and one that fails is told to the person there. It depends on neither `model` nor
    `models`, so a composition without them keeps these commands, and a switch never reloads
    it."""
    for spec, run in Operator(loader, jobs, _declared).specs:
        yield acquire(commands.register, spec, run)
