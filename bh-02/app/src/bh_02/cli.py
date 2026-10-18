"""The `bh-02` command: every run is a session in the TUI; `--resume` continues one.

While the app runs it owns the terminal, so this module says nothing then: lifecycle lines
(`--trace FILE`) go to a file, and a layer file that could not be reloaded, or a session's row log
that stopped being written, is kept and printed once the app has exited and the terminal is
restored. Besides the app it is the only module that touches the terminal, and only for what has no
`output` to go through: option parsing, a fatal error, and those reports after the run.
"""

import asyncio
import contextlib
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from importlib.metadata import entry_points
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TextIO

import click

from bh_02 import sessions, viewing, watching
from bh_02.bootstrap import (
    CREDENTIAL_FILE,
    CompositionError,
    LayerError,
    NotStarted,
    Recoverable,
    code_directories,
    code_packages,
    config_directories,
    credential_files,
    layers,
    memory_directory,
    project_of,
    read_layers,
    run,
    unreadable,
)
from cordis.loader import read_layer

__all__ = ["credential_search", "main"]

_MODEL_HELP = (
    "The model to start on, by name, ENDPOINT/MODEL: one of your endpoints' in "
    "~/.config/bh-02/models.toml ($XDG_CONFIG_HOME/bh-02/models.toml), whose `default` is used "
    "otherwise; /model lists them."
)
_PATCH_HELP = "A layer file applied over the shipped composition. Repeatable."
_TRACE_HELP = "Append every row's lifecycle event to FILE (the app owns the terminal)."
_PATCH_TYPE = click.Path(exists=True, dir_okay=False, path_type=Path)
_TRACE_TYPE = click.Path(dir_okay=False, writable=True, path_type=Path)


def _model_name(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    """`--model`'s name, refused unless it is UTF-8: argv bytes that are not UTF-8 arrive as a lone
    surrogate, which no layer can hold, so it is refused here, before a session is made for it."""
    if value is not None:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise click.BadParameter(
                f"{value!r} is not valid UTF-8; write the model's name in UTF-8", ctx=ctx, param=param
            ) from None
    return value


@click.group(invoke_without_command=True)
@click.option("--model", default=None, callback=_model_name, help=_MODEL_HELP)
@click.option("--patch", "patches", multiple=True, type=_PATCH_TYPE, help=_PATCH_HELP)
@click.option("--trace", default=None, type=_TRACE_TYPE, metavar="FILE", help=_TRACE_HELP)
@click.option(
    "--no-jail",
    is_flag=True,
    help="Run the model's code unjailed, with your own permissions; every input asks.",
)
@click.option(
    "--resume",
    is_flag=False,
    flag_value="",
    default=None,
    metavar="[ID]",
    help="Continue this directory's newest session, or the one named: its id, the start of it, or its "
    "last part (the status bar's short id; `bh-02 sessions` lists them).",
)
@click.pass_context
def main(
    ctx: click.Context,
    model: str | None,
    patches: Sequence[Path],
    trace: Path | None,
    no_jail: bool,
    resume: str | None,
) -> None:
    """A coding agent in a terminal app. The model acts in Python, through the python tool, in a
    persistent Python process inside a jail. Its models are the endpoints in the models file: Claude
    through Claude Code (on the Claude subscription, with the CLAUDE_CODE_OAUTH_TOKEN in local.env
    that `claude setup-token` makes, or through a gateway), and any OpenAI-compatible model. Every
    run is a session that `--resume` continues."""
    if ctx.invoked_subcommand is not None:
        return
    with contextlib.ExitStack() as holding:  # the session is held until the run is over
        try:
            read_layers(patches)  # before a session is made for a run that can't start
            _no_pinned_model(model, patches)
            session = _session(resume, model=model, no_jail=no_jail, patches=patches, holding=holding)
        except (LayerError, sessions.Held) as error:
            click.echo(f"error: {error.message}", err=True)
            sys.exit(1)
        # the status bar shows the session's id from here, marked as resumed on a resume
        listing = sessions.Listing(str(sessions.state_root()), session.id, resume is not None)
        code, started = _run([*layers(), session.layer, *patches], trace, listing, session.row_log)
    if not started and resume is None:
        sessions.discard(session)  # a run that never came up made no session worth listing
    else:
        if started:
            newest = sessions.listed(sessions.state_root(), str(Path.cwd()))[:1]
            newest_id = newest[0].id if newest else None
            how = sessions.resume_command(session.stack, None if session.id == newest_id else session.id)
            farewell = f"session {session.id}  ({how} to continue it)"
        else:  # a resume that did not come up: it would fail the same way until something changes
            farewell = _not_resumable(session)
        with contextlib.suppress(OSError):  # the terminal has gone (its window closed): nobody to tell
            click.echo(click.style(farewell, dim=True), err=True)
    sys.exit(code)


def _not_resumable(session: sessions.Session) -> str:
    """What to say of a resumed session that did not come up, in place of the offer to resume it
    (which would fail the same way): it was kept, and the layer to change is the one the error
    above names, this session's own or a `--patch` file."""
    return (
        f"session {session.id}  did not start and is kept as it was; change what the error above "
        f"names, in this session's own layer ({session.layer}) or in a --patch file"
    )


def _no_pinned_model(model: str | None, patches: Sequence[Path]) -> None:
    """Raise `LayerError` for `--model` with a `--patch` file that sets the model row's config,
    which replaces the session layer's whole: the model it names would run, not `--model`'s."""
    pinning = [patch for patch in patches if sessions.pins_model(read_layer(str(patch)))]
    if model is None or not pinning:
        return
    raise LayerError(
        f"--model {model} would not take effect: {pinning[0]} sets the model row's config, which "
        "replaces the one --model writes whole. Drop --model and set `default` in that file's model "
        f'row (`config = {{ default = "{model}", ... }}`), or remove the model row\'s config from it'
    )


@main.command("sessions")
def sessions_command() -> None:
    """List this directory's sessions, newest first: each one's id, when it started, the model
    it started on and any `--patch` files it started with, which may have replaced the model.
    A record that can't be read is skipped, and named on stderr."""
    found, broken = sessions.scanned(sessions.state_root(), str(Path.cwd()))
    if not found and not broken:
        click.echo("no sessions in this directory yet", err=True)
    for session in found:
        patched = f"  patched: {', '.join(session.patches)}" if session.patches else ""
        click.echo(f"{session.id}  {session.created[:19]}  {session.stack}{patched}")  # to the second
    for record in broken:
        click.echo(f"warning: skipped {record.message}", err=True)


@main.command("check-examples")
@click.argument(
    "files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def check_examples_command(files: Sequence[Path]) -> None:
    """Check the docstrings of the functions and classes startup files tell for an example in each
    (a doctest block, or a `::` literal block) and for doctest blocks that parse, each with a blank
    line before it. It reads each FILE and runs none of its code, needs no session and no model, and
    exits 1 on a finding, 0 on none and 2 when it can't check a file. ruff checks the rest of the
    convention (`ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 FILE`), and mypy the
    types, with `mypy --strict --config-file= FILE`."""
    program = _check_program()
    sys.exit(subprocess.run([sys.executable, "-I", str(program), *map(str, files)], check=False).returncode)


def _check_program() -> Path:
    """The python plugin's `startup_check.py`, found by the plugin's name (`code_directories`, which
    imports nothing): the app does not import a plugin, and the program is run by path, as the
    Python process runs it in the jail."""
    for directory in code_directories(("python_cordis_plugin",)):
        program = Path(directory) / "startup_check.py"
        if program.is_file():
            return program
    raise click.ClickException("the python plugin is not installed, so there is no example rule to run")


@main.command("watch")
@click.argument("session")
@click.argument("agent")
@click.option("--once", is_flag=True, help="Print what the log holds now and stop, instead of following it.")
def watch_command(session: str, agent: str, once: bool) -> None:
    """Follow one sub-agent's event log, read-only: SESSION is a session's id (`bh-02 sessions`)
    and AGENT the agent's name (`/agents` in the session says the command, such as
    `bh-02 watch 20261012-091500-ab12 general-1`). Stops when the agent ends; Ctrl-C leaves it
    sooner. Nothing is written, and only names bh-02 made are accepted."""
    try:
        for chunk in watching.watched(sessions.state_root(), session, agent, follow=not once):
            click.echo(chunk, nl=False)
    except watching.Refused as error:
        click.echo(f"error: {error.message}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo(err=True)


@main.command("trajectory")
@click.argument("session_id", metavar="[ID]", required=False)
@click.option(
    "--follow", "-f", is_flag=True, help="Keep reading the files and print what is new, until Ctrl-C."
)
def trajectory_command(session_id: str | None, follow: bool) -> None:
    """Print a session laid out in time, read-only: each reply, its steps (model, time to first
    chunk, generation time, speed, usage, cost), their calls (answer, wait, run time), the
    sub-agents they started and the rows that reloaded, with times in your local time. ID is the
    session as `--resume` takes it (its id, the start of it or its last part; `bh-02 sessions` lists
    them), the newest in this directory when left out. Nothing is written, and the files are read
    through no link."""
    root = sessions.state_root()
    found = sessions.chosen(
        sessions.find(root, str(Path.cwd()), session_id or None), session_id or "", "show"
    )
    if isinstance(found, str):
        raise click.UsageError(found)
    try:
        for line in viewing.shown(root, found.dir.name, follow=follow):
            click.echo(line)
    except watching.Refused as error:
        click.echo(f"error: {error.message}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo(err=True)


def _session(
    resume: str | None,
    *,
    model: str | None,
    no_jail: bool,
    patches: Sequence[Path],
    holding: contextlib.ExitStack,
) -> sessions.Session:
    """A new session, its layer written before anything boots, or the one `--resume` names. Either
    is held (`sessions.held`) in `holding`, which keeps it for the run; a resumed one is held before
    its layer is read or rewritten, so a session another bh-02 is running is refused (`Held`) with
    nothing of it touched.
    """
    root, cwd = sessions.state_root(), str(Path.cwd())
    if resume is None:
        names = [patch.name for patch in patches]
        made = sessions.create(root, cwd, model=model, no_jail=no_jail, patches=names)
        holding.enter_context(sessions.held(made))
        return made
    found = sessions.chosen(sessions.find(root, cwd, resume or None), resume, "resume")
    if isinstance(found, str):
        raise click.UsageError(found)
    holding.enter_context(sessions.held(found))
    read_layers([found.layer])  # a hand-edited session.toml: one line, before /model rewrites it
    if no_jail:
        raise click.UsageError("a resumed session keeps the jail it started with")
    if model is not None:
        sessions.set_model(found, model)
    return found


def _run(
    layers: Iterable[str | Path | Traversable],
    trace: Path | None,
    listing: sessions.Listing,
    row_log: Path,
) -> tuple[int, bool]:
    """Run the composition; return the exit code, and whether it came up at all. Reports
    kept during the run print after it. `row_log` is the file the session's row reloads go to."""
    reports: list[str] = []
    with contextlib.ExitStack() as stack:
        traced = stack.enter_context(trace.open("a")) if trace is not None else None
        listen = _writer(traced, "") if traced is not None else None
        reported = _writer(traced, "report: ") if traced is not None else None

        def report(line: str) -> None:
            reports.append(line)
            if reported is not None:
                reported(line)

        code, started = _launch(layers, listen, report, listing, row_log)
    for line in reports:
        click.echo(f"error: {line}", err=True)
    return code, started


def _launch(
    layers: Iterable[str | Path | Traversable],
    trace: Callable[[str], None] | None,
    report: Callable[[str], None],
    listing: sessions.Listing,
    row_log: Path,
) -> tuple[int, bool]:
    """Run to the end; return the exit code and whether the composition came up. A failure
    the person should see is printed (the terminal is theirs again by then) and becomes exit
    code 1. A bug propagates as itself."""
    # where the credential may be: where the model rows look for it, beside the project; and the
    # sessions' state, where each session's Claude Code child keeps its config and messaging peer
    # token (this run's, and the default one when `XDG_STATE_HOME` moves this run's elsewhere):
    # no jailed input may read any of them. Another state root, of a run with another
    # `XDG_STATE_HOME`, is not known here. And bh-02's configuration (this run's and the default
    # one), whose files the host reads and trusts: no jailed input may write there. And where
    # bh-02 runs its own code from, every package a layer may name as installed: every jail reads
    # it (the extensions process imports cordis), and no jailed input may write it. And the
    # project's auto memory directory, made here so the jail can let an input write it.
    credentials = credential_search()
    states = [listing.root, str(sessions.default_state_root())] if listing.root else []
    beside = [Path.cwd() / CREDENTIAL_FILE]
    secrets = unreadable(credentials, beside, (str(Path(state).resolve()) for state in states))
    trusted = config_directories(os.environ, Path.home())
    code = code_directories(code_packages(ep.module for ep in entry_points(group="cordis.plugins")))
    memory = memory_directory(project_of(Path.cwd().resolve()), os.environ, Path.home())
    Path(memory).mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        asyncio.run(
            run(
                layers,
                trace=trace,
                report=report,
                row_log=row_log,
                session=listing,
                credentials=credentials,
                secrets=secrets,
                trusted=trusted,
                code=code,
                auto_memory=memory,
            )
        )
    except CompositionError as error:
        click.echo(f"error: {error.message}", err=True)
        return 1, not isinstance(error, NotStarted | LayerError)
    except Exception as error:
        if not isinstance(error, Recoverable):
            raise
        click.echo(f"error: {error.message}", err=True)
        return 1, True
    except KeyboardInterrupt:
        click.echo(err=True)
    return 0, True


def credential_search() -> tuple[str, ...]:
    """Where the model rows look for bh-02's `local.env`, nearest first: above bh-02's own
    install and above its environment, so the workspace's own is found from any working
    directory. The one list: the model rows read the first that is a file (the `host`
    value's `credentials`), and every one is a secret the jail keeps an input from reading,
    writing or creating. Not the project's own `local.env`: a project's may hold anything."""
    return credential_files([Path(__file__).resolve(), Path(sys.prefix).resolve()])


def _writer(file: TextIO, prefix: str) -> Callable[[str], None]:
    """Append each line to `file` at once, so a trace survives a crash."""

    def write(line: str) -> None:
        file.write(f"{prefix}{line}\n")
        file.flush()

    return write
