"""The `bh-02` command: every run is a session in the TUI; `--resume` continues one.

While the app runs it owns the terminal, so this module says nothing then: lifecycle lines
(`--trace FILE`) go to a file, and a layer file that could not be reloaded is kept and printed
once the app has exited and the terminal is restored. Besides the app it is the only module
that touches the terminal, and only for what has no `output` to go through: option parsing,
a fatal error, and those notes after the run.
"""

import asyncio
import contextlib
import os
import shutil
import sys
from collections.abc import Callable, Iterable, Sequence
from importlib.metadata import entry_points
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TextIO

import click

from bh_02 import sessions
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
from bh_02.outdated import clashes, translated
from cordis.composition import format_layer
from cordis.loader import read_layer

__all__ = ["credential_search", "main"]

_MODEL_HELP = (
    "The model to start on, by name: sonnet (the default), opus, haiku, or one of yours in "
    "~/.config/bh-02/models.toml ($XDG_CONFIG_HOME/bh-02/models.toml); /model lists them."
)
_PATCH_HELP = "A layer file applied over the shipped composition. Repeatable."
_TRACE_HELP = "Append every row's lifecycle event to FILE (the app owns the terminal)."
_PATCH_TYPE = click.Path(exists=True, dir_okay=False, path_type=Path)
_TRACE_TYPE = click.Path(dir_okay=False, writable=True, path_type=Path)
_UPDATED_HEADER = (
    "Rewritten by `bh-02 update-layer` in this bh-02's row names; the original, with its comments, "
    "is {backup}."
)


@click.group(invoke_without_command=True)
@click.option("--model", default=None, help=_MODEL_HELP)
@click.option("--patch", "patches", multiple=True, type=_PATCH_TYPE, help=_PATCH_HELP)
@click.option("--trace", default=None, type=_TRACE_TYPE, metavar="FILE", help=_TRACE_HELP)
@click.option(
    "--no-jail", is_flag=True, help="Run the kernel unjailed, with your own permissions; every input asks."
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
    persistent kernel inside a jail. Claude is reached through Claude Code on the Claude
    subscription, with the CLAUDE_CODE_OAUTH_TOKEN in local.env (`claude setup-token` makes
    one); any OpenAI-compatible model can be added to the models file. Every run is a session
    that `--resume` continues."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        read_layers(patches)  # before a session is made for a run that can't start
        _no_outdated_rows(patches)
        _no_pinned_model(model, patches)
        session = _session(resume, model=model, no_jail=no_jail, patches=patches)
    except LayerError as error:
        click.echo(f"error: {error.message}", err=True)
        sys.exit(1)
    # the status bar shows the session's id from here, marked as resumed on a resume
    listing = sessions.Listing(str(sessions.state_root()), session.id, resume is not None)
    code, started = _run([*layers(), session.layer, *patches], trace, listing)
    if not started and resume is None:
        sessions.discard(session)  # a run that never came up made no session worth listing
    else:
        newest = sessions.listed(sessions.state_root(), str(Path.cwd()))[:1]
        newest_id = newest[0].id if newest else None
        how = sessions.resume_command(session.stack, None if session.id == newest_id else session.id)
        with contextlib.suppress(OSError):  # the terminal has gone (its window closed): nobody to tell
            click.echo(click.style(f"session {session.id}  ({how} to continue it)", dim=True), err=True)
    sys.exit(code)


def _no_outdated_rows(patches: Sequence[Path]) -> None:
    """Raise `LayerError` for `--patch` files naming rows this bh-02 renamed or no longer has:
    each such row, what to change, and how. `bh-02 update-layer` rewrites a file, except one
    with rows it cannot fold together (`clashes`), which is fixed by hand first."""
    stale = {patch: changes for patch in patches if (changes := translated(read_layer(str(patch)))[1])}
    if not stale:
        return
    lines = [f"  {patch}: {change}" for patch, changes in stale.items() for change in changes]
    by_hand = {patch: len(clashes(read_layer(str(patch)))) for patch in stale}
    rewritable = [patch for patch in stale if not by_hand[patch]]
    if rewritable:
        commands = " and ".join(f"`bh-02 update-layer {patch}`" for patch in rewritable)
        lines.append(f"run {commands} to rewrite it (the original is kept beside it as .bak), then run again")
    for patch, count in by_hand.items():
        if not count:
            continue
        rest = f", then `bh-02 update-layer {patch}` for the rest" if len(stale[patch]) > count else ""
        lines.append(
            f"fold the clashing rows in {patch} together by hand (update-layer leaves which one "
            f"wins to you){rest}, then run again"
        )
    raise LayerError("a --patch file names rows this bh-02 renamed or no longer has:\n" + "\n".join(lines))


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


@main.command("update-layer")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def update_layer_command(file: Path) -> None:
    """Rewrite a layer file (a --patch file) that names rows this bh-02 renamed or no longer
    has, in today's names, and say what changed. The original is kept as FILE.bak (with its
    comments, which the rewrite does not carry over; an earlier FILE.bak is replaced, and the
    output says so). A file already up to date is left as it
    is, so running it again changes nothing. A file with a renamed row whose new id it already
    has (both `llm` and `loop`) is refused, unchanged: which one wins is the person's call."""
    try:
        read_layers([file])
    except LayerError as error:
        click.echo(f"error: {error.message}", err=True)
        sys.exit(1)
    if by_hand := clashes(read_layer(str(file))):
        click.echo(f"error: {file} has rows update-layer cannot fold together for you:", err=True)
        for clash in by_hand:
            click.echo(f"  {file}: {clash}", err=True)
        click.echo("nothing was rewritten; fix those by hand, then run it again", err=True)
        sys.exit(1)
    rows, changes = translated(read_layer(str(file)))
    if not changes:
        click.echo(f"{file} is up to date: nothing to change")
        return
    backup = file.with_name(f"{file.name}.bak")
    replaced = backup.exists()
    shutil.copyfile(file, backup)
    file.write_text(format_layer(rows, _UPDATED_HEADER.format(backup=backup.name)))
    for change in changes:
        click.echo(f"{file}: {change}")
    click.echo(f"rewritten; the original, with its comments, is {backup}")
    if sessions.pins_model(rows):
        click.echo(
            f"note: {file} sets the model row's config, so while it is a --patch it chooses the model: "
            "--model is refused and /model can't switch. To switch freely, move its models to the "
            f"models file ({sessions.models_file()}) and remove the model row from it"
        )
    if replaced:
        click.echo(f"note: {backup} was there already, from an earlier run; it now holds this run's original")


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


def _session(
    resume: str | None, *, model: str | None, no_jail: bool, patches: Sequence[Path]
) -> sessions.Session:
    """A new session, or the one `--resume` names, its layer written (or brought up to date)
    before anything boots."""
    root, cwd = sessions.state_root(), str(Path.cwd())
    if resume is None:
        names = [patch.name for patch in patches]
        return sessions.create(root, cwd, model=model, no_jail=no_jail, patches=names)
    candidates = sessions.find(root, cwd, resume or None)
    if not candidates and not resume:
        raise click.UsageError("no sessions in this directory yet; run bh-02 to start one")
    if not candidates:
        raise click.UsageError(f"no session {resume!r} in this directory; `bh-02 sessions` lists them")
    if len(candidates) > 1:
        ids = ", ".join(s.id for s in candidates)
        raise click.UsageError(
            f"{resume!r} matches {len(candidates)} sessions' ids ({ids}); give more of one"
        )
    (found,) = candidates
    if isinstance(found, sessions.Broken):
        raise click.UsageError(f"can't resume {found.id}: {found.message}")
    read_layers([found.layer])  # a hand-edited session.toml: one line, before /model rewrites it
    if (why := sessions.retired(read_layer(str(found.layer)))) is not None:
        raise LayerError(f"can't resume {found.id}: {why}; start a new session with `uv run bh-02`")
    if by_hand := clashes(read_layer(str(found.layer))):  # only a hand edit writes both names
        raise LayerError(
            f"can't resume {found.id}: {found.layer} has rows it cannot fold together for you:\n"
            + "\n".join(f"  {clash}" for clash in by_hand)
            + "\nfix that file by hand, then resume again"
        )
    if no_jail:
        raise click.UsageError("a resumed session keeps the jail it started with")
    sessions.update(found)
    if model is not None:
        sessions.set_model(found, model)
    return found


def _run(
    layers: Iterable[str | Path | Traversable],
    trace: Path | None,
    listing: sessions.Listing,
) -> tuple[int, bool]:
    """Run the composition; return the exit code, and whether it came up at all. Reports
    kept during the run print after it."""
    reports: list[str] = []
    with contextlib.ExitStack() as stack:
        traced = stack.enter_context(trace.open("a")) if trace is not None else None
        listen = _writer(traced, "") if traced is not None else None
        noted = _writer(traced, "report: ") if traced is not None else None

        def report(line: str) -> None:
            reports.append(line)
            if noted is not None:
                noted(line)

        code, started = _launch(layers, listen, report, listing)
    for line in reports:
        click.echo(f"error: {line}", err=True)
    return code, started


def _launch(
    layers: Iterable[str | Path | Traversable],
    trace: Callable[[str], None] | None,
    report: Callable[[str], None],
    listing: sessions.Listing,
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
    # it (the extensions' worker imports cordis), and no jailed input may write it. And the
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
                sessions=listing,
                credentials=credentials,
                secrets=secrets,
                trusted=trusted,
                code=code,
                memory=memory,
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
    directory. The one list: the model rows read the first that is a file (the `layers`
    value's `credentials`), and every one is a secret the jail keeps an input from reading,
    writing or creating. Not the project's own `local.env`: a project's may hold anything."""
    return credential_files([Path(__file__).resolve(), Path(sys.prefix).resolve()])


def _writer(file: TextIO, prefix: str) -> Callable[[str], None]:
    """Append each line to `file` at once, so a trace survives a crash."""

    def write(line: str) -> None:
        file.write(f"{prefix}{line}\n")
        file.flush()

    return write
