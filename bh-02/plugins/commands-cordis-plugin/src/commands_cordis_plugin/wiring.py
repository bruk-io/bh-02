"""The rows: the commands broker under `commands`; the operator's commands registered into it;
and `!`, a shell command, the prefix claimed in it."""

import asyncio
import functools
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from commands_cordis_plugin.operations import Loader, Models, Operator, OperatorConfig
from commands_cordis_plugin.registry import Commands, CommandSpec, Run
from commands_cordis_plugin.shell_command import ShellCommandConfig, run_line
from cordis import Effects, Row, acquire, background, bind, component
from cordis.composition import format_layer
from cordis.loader import Loader as _Mounting
from cordis.loader import read_layer
from cordis_helpers import Job, perform

__all__ = ["operator", "registry", "set_model", "shadowing", "shell_command"]


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value."""

    def register(self, spec: CommandSpec, run: Run) -> Callable[[], None]: ...


@runtime_checkable
class _Claimant(Protocol):
    """What a row that takes the lines starting with a prefix needs of the `commands` value."""

    def claim(self, prefix: str, spec: CommandSpec, run: Run) -> Callable[[], None]: ...


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
async def operator(
    *, commands: _Registrar, loader: Loader, models: Models, config: OperatorConfig
) -> Effects:
    """Fills an `operator` row: `use = "commands:operator"`. /rows, /explain, /restart, /clear
    and /model, over the loader that mounted it and the `models` there are. Its restarts are its
    own background work. It depends on `models`, not `model`, so a switch never reloads it."""
    jobs: asyncio.Queue[Job] = asyncio.Queue()
    failures: list[str] = []
    yield background(perform(jobs, failures.append))
    files = [str(path) for path in loader.config.layers] if isinstance(loader, _Mounting) else []
    for spec, run in Operator(
        loader, models, config, jobs, set_model, lambda layer, rid: shadowing(files, layer, rid)
    ).specs:
        yield acquire(commands.register, spec, run)


def set_model(layer: str, rid: str, model: str) -> None:
    """Name `model` as row `rid`'s `default` in the layer file `layer`, keeping the rest of its
    config (the model row's `default` is the model's name)."""
    rows = read_layer(layer)
    current = next((r for r in rows if r.id == rid), Row(rid))
    kept = [r for r in rows if r.id != rid]
    chosen = Row(rid, current.use, {**(current.config or {}), "default": model}, current.disabled)
    Path(layer).write_text(format_layer([*kept, chosen], "This session's own layer; /model edits it."))


def shadowing(files: Sequence[str], layer: str, rid: str) -> str | None:
    """The first of the layer `files` composed after `layer` that sets row `rid`'s config, which
    replaces the config `layer` gives it whole (a `--patch` naming the model row, over the
    session's layer that /model edits); None when none does. A file that can't be read is
    skipped: the loader reports it."""
    mine = Path(layer).resolve()
    at = next((n for n, path in enumerate(files) if Path(path).resolve() == mine), None)
    for path in files[at + 1 :] if at is not None else []:
        try:
            rows = read_layer(path)
        except OSError, ValueError:
            continue
        if any(row.id == rid and row.config is not None for row in rows):
            return path
    return None
