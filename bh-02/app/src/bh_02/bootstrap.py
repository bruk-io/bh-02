"""Boot a composition and run it until the chat row's own work is done, then unwind."""

import asyncio
import contextlib
import os
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol, runtime_checkable

from bh_02.sessions import Listing
from cordis import Booted, Effects, Inspection, Row, Runtime, bind, boot, component, enter
from cordis.loader import read_layer

__all__ = [
    "CREDENTIAL_FILE",
    "CompositionError",
    "LayerError",
    "NotStarted",
    "Recoverable",
    "config_directories",
    "credential_files",
    "memory_directory",
    "project_of",
    "unreadable",
    "layers",
    "read_layers",
    "run",
]


@runtime_checkable
class Recoverable(Protocol):
    """A failure the chat row lets through that the person should see (CONTRACTS.md: loop errors)."""

    kind: str
    message: str


@runtime_checkable
class _ChatDone(Awaitable[None], Protocol):
    """The shape `_await_chat` needs of `done` (CONTRACTS.md): awaitable, and able to say
    whether it was itself cancelled. Not `asyncio.Task` directly: a parameterized generic
    is not a class cordis can use as a contract (`isinstance` refuses one), so a Protocol
    of bh-02's own is the same move every other consumer in this codebase already makes.
    """

    def cancelled(self) -> bool: ...


@component
async def harness(*, done: _ChatDone) -> Effects:
    """Exists only to declare bh-02's own dependency on `done` (CONTRACTS.md), mounted as an
    extra row by `run()`. Its presence and shape are then checked the way any component's
    dependency is: `unsatisfiable()` before any effect runs, `check_contract` at commit,
    and a `harness` row that never activates is just another row `_raise_if_stalled`
    already reports — no bespoke check in the bootstrap itself.
    """
    yield enter(contextlib.nullcontext())


@dataclass(frozen=True, slots=True)
class _LayerFiles:
    """The composition's own files (CONTRACTS.md: layers): every layer the loader is watching
    (`paths`), where the model rows look for the credential file, nearest first
    (`credentials`), what no input may read (`secrets`): every one of `credentials`, the
    `local.env` beside and above the project, and the sessions' state (Claude Code's own config
    and tokens), and bh-02's configuration directories (`trusted`), whose files the host reads
    and trusts; and the project's auto memory directory (`memory`), which the model writes and
    the memory rows read. The jail keeps an input from rewriting the first and from reading the
    secrets, from writing or creating any secret under a root it may write, and from writing in
    a configuration directory under one; and lets it write the memory directory."""

    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    memory: str = ""


# The file bh-02's credentials live in (CLAUDE_CODE_OAUTH_TOKEN, and any key a model names),
# read by the model row.
CREDENTIAL_FILE = "local.env"


def credential_files(anchors: Iterable[Path]) -> tuple[str, ...]:
    """`local.env` in every directory above each anchor, nearest first, resolved anchors in.
    Above bh-02's installed package and its environment, that is where the model rows look for
    the credential (the `layers` value's `credentials`), so from any working directory the
    workspace's own `local.env` is among them."""
    found = (str(parent / CREDENTIAL_FILE) for anchor in anchors for parent in anchor.parents)
    return tuple(dict.fromkeys(found))


def unreadable(credentials: Iterable[str], anchors: Iterable[Path], states: Iterable[str]) -> tuple[str, ...]:
    """What no jailed input may read (the `layers` value's `secrets`): every place the model rows
    look for the credential (`credentials`, all of them, so none can be planted), the
    `local.env` above each of `anchors` (the project's, beside it), and `states`, the sessions'
    state directories (this run's and the default one), where each session's Claude Code child
    keeps its config and messaging peer token. An empty state (a composition booted without
    sessions) adds nothing."""
    found = (*credentials, *credential_files(anchors), *(state for state in states if state))
    return tuple(dict.fromkeys(found))


def config_directories(environ: Mapping[str, str], home: Path) -> tuple[str, ...]:
    """bh-02's configuration directories of the person's (the `layers` value's `trusted`): this
    run's (`$XDG_CONFIG_HOME/bh-02`, else `~/.config/bh-02`) and the default one, which a run
    without the variable reads, each as named and as it resolves (a link into a dotfiles
    repository). The host reads what is there and trusts it (the models file, and the person's
    startup file, whose text it hands to the model's REPL), so no jailed
    input may write there: a session run from the home directory would otherwise choose what
    every later one reads."""
    default = home / ".config"
    named = (
        Path(os.path.normpath(Path(base, "bh-02").absolute()))
        for base in (environ.get("XDG_CONFIG_HOME") or default, default)
    )
    return tuple(dict.fromkeys(str(path) for each in named for path in (each, each.resolve())))


def project_of(cwd: Path) -> Path:
    """The project auto memory belongs to, as Claude Code finds it: the git repository `cwd` is
    in (a worktree's main repository, so every worktree shares one), else `cwd` itself. Read from
    `.git` with no subprocess: a directory is a repository's own, a file a worktree's
    (`gitdir: ...`, whose `commondir` names the main repository's `.git`)."""
    for here in (cwd, *cwd.parents):
        git = here / ".git"
        if git.is_dir():
            return here
        if git.is_file():
            try:
                line = git.read_text(errors="replace")[:4096].splitlines()[0]
                gitdir = (here / line.removeprefix("gitdir:").strip()).resolve()
                common = (gitdir / (gitdir / "commondir").read_text().strip()).resolve()
            except OSError, IndexError:
                return here
            return common.parent if common.name == ".git" else here
    return cwd


def memory_directory(project: Path, environ: Mapping[str, str], home: Path) -> str:
    """Where the project's auto memory is kept (the `layers` value's `memory`):
    `$XDG_STATE_HOME/bh-02/projects/<project>/memory`, else under `~/.local/state`, as Claude
    Code keeps it under `~/.claude/projects/<project>/memory`: machine-local, never in the
    repository. `<project>` is the project's absolute path, every character but a letter or a
    digit a `-` (`/home/me/app` is `-home-me-app`), as Claude Code names it."""
    state = Path(environ.get("XDG_STATE_HOME") or home / ".local" / "state")
    return str(state / "bh-02" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project)) / "memory")


@component(provides=("layers",))
async def layer_files(*, config: _LayerFiles) -> Effects:
    """Binds the layer files `run()` was given, mounted by `run()` as a row of its own, so a
    jail can keep an input from rewriting the program it runs in."""
    yield bind("layers", config)


@component(provides=("sessions",))
async def session_list(*, config: Listing) -> Effects:
    """Binds the running session (CONTRACTS.md: sessions), mounted by `run()` as a row of its
    own, so the status bar can show its id without knowing where sessions live."""
    yield bind("sessions", config)


class CompositionError(Exception):
    """A row that never started, or left and took the work with it, with cordis's diagnosis."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LayerError(CompositionError):
    """A layer file that could not be read at launch: missing, not TOML, or not rows."""


class NotStarted(CompositionError):
    """A composition that never came up (a row that never started): the run did nothing."""


def _layer_problem(path: str, error: Exception) -> str:
    """What to tell the person about a layer file `read_layer` refused, naming it once."""
    match error:
        case OSError():
            why = error.strerror or str(error)
        case _:
            why = str(error).removeprefix(f"{path}: ")
    return f"{path}: {why}; fix the file or drop it"


def read_layers(paths: Iterable[str | Path | Traversable]) -> None:
    """Read every layer file once before anything boots; raise `LayerError` for the first that
    can't be read, so a broken file is one line and not a traceback from inside the loader."""
    for path in paths:
        try:
            read_layer(str(path))
        except (OSError, ValueError) as error:
            raise LayerError(_layer_problem(str(path), error)) from None


def layers() -> list[Traversable]:
    """The shipped layers: the harness (`bh-02.toml`). Every later file is a patch over it, so
    a session's own layer and a user's `--patch` compose the same way whichever model runs."""
    return [resources.files("bh_02") / "bh-02.toml"]


async def run(
    layers: Iterable[str | Path | Traversable],
    overrides: Iterable[Row] = (),
    *,
    trace: Callable[[str], None] | None = None,
    report: Callable[[str], None] | None = None,
    sessions: Listing | None = None,
    credentials: Iterable[str] = (),
    secrets: Iterable[str] = (),
    trusted: Iterable[str] = (),
    memory: str = "",
) -> None:
    """Boot, wait for the chat row's own work to end (CONTRACTS.md: `done`), then unwind.

    Every layer is read once first: one that can't be read is a `LayerError` naming it.

    Adds three rows of its own after `overrides`, pinned on: `layers`, which binds the layer
    files' paths, `credentials`, where the model rows look for the credential file (none: a
    composition booted without them finds no credential unless its model row names an
    `env_file`), `secrets`, where the credential file may be and the sessions' state
    (CONTRACTS.md: layers; the jail denies an input both), `trusted`, bh-02's configuration
    directories (`config_directories`; the jail denies an input writing there), and `memory`,
    the project's auto memory directory (`memory_directory`; the jail lets an input write it,
    and none when empty), `sessions`, which binds this
    directory's sessions and the running one (`sessions`; the default lists none), and
    `harness`, whose only job is to declare bh-02's dependency on `done`, so a chat row that
    never binds it is an ordinary "waiting on" stall and a `done` of the wrong shape is an
    ordinary contract violation -- both diagnosed by cordis itself, not by this function.

    A row that never starts, or that leaves mid-run and takes the work with it, is reported
    with cordis's own diagnosis rather than a silent exit. An exception from the work itself
    (the ui's `ui_crashed`, reaching the command line through the chat row's `done`) propagates
    as it is. This waits on the chat row's own `done` binding, not `Runtime.idle()`: idle() is
    process-wide, so a provider with background work of its own (a heartbeat, a reconnect
    loop) would otherwise keep this running after the chat row itself is done -- and, for the
    same reason, that provider's own background work failing is not fatal to this function
    either: only the chat row's own `done` and the rows `_raise_if_stalled` checks (never-started
    or newly-inactive rows) can end a run early. A background failure elsewhere stays visible
    in `status()`/`explain()`, not surfaced here. `trace` sees every lifecycle event (reload,
    active, bind, unbind, unloading, ...) as one line, from the first row on; `report` hears
    about a layer file that changed but could not be reloaded.

    The layer files are watched while the program runs: edit one and the composition reshapes
    itself.
    """
    paths = [str(layer) for layer in layers]
    read_layers(paths)
    rt = Runtime()
    if trace is not None:
        rt.listeners.append(lambda event: trace(str(event)))
    watched = {
        "paths": [str(Path(path).resolve()) for path in paths],
        "credentials": list(credentials),
        "secrets": list(secrets),
        "trusted": list(trusted),
        "memory": memory,
    }
    booted: Booted = await boot(
        paths,
        [
            *overrides,
            # bh-02's own rows, after every layer and pinned on, so no layer can take them away
            Row("harness", "bh_02.bootstrap:harness", disabled=False),
            Row("layers", "bh_02.bootstrap:layer_files", config=watched, disabled=False),
            Row(
                "sessions",
                "bh_02.bootstrap:session_list",
                config=asdict(sessions or Listing()),
                disabled=False,
            ),
        ],
        rt,
        report=report,
    )
    try:
        _raise_if_stalled(booted, "could not start", NotStarted)
        await _await_chat(booted)
        _raise_if_stalled(booted, "stopped early")
    finally:
        await booted.runtime.shutdown()


async def _await_chat(booted: Booted) -> None:
    """Wait for the chat row's `done` task, not every fiber's background work.

    `harness` (mounted alongside every composition `run()` boots) declares `done` as its
    own dependency, so by the time `_raise_if_stalled(booted, "could not start")` has
    passed, cordis has already confirmed it is bound and shaped right: nothing left to
    check here but the wait itself.

    A CancelledError raised *because that task was itself cancelled* means the chat row's own
    fiber deactivated and cancelled its own task through the ordinary undo path. Usually it
    comes straight back: a dependency was *replaced* (the model reloaded by a layer edit, a
    `/model`, a `/clear`), the chat row reloaded against it, and it bound a new `done`, which is
    then followed. If no new `done` appears once the runtime settles, the chat row stopped, for
    `_raise_if_stalled("stopped early")` to diagnose next. A CancelledError reaching this
    `await` any other way (this coroutine itself was cancelled, e.g. by an external
    shutdown) is not the task's and must propagate. Any other exception is the work's own
    and propagates as `idle()` used to re-raise it.
    """
    task: _ChatDone = booted.runtime.root.get("done")
    while True:
        try:
            await task
            break  # the chat row finished its own work
        except asyncio.CancelledError:
            if not task.cancelled():
                raise
        await booted.runtime.settle()
        following: _ChatDone | None = booted.runtime.root.get("done")
        if following is None or following is task:
            break  # stopped, and not restarted
        task = following
    await booted.runtime.settle()


def _raise_if_stalled(booted: Booted, what: str, error: type[CompositionError] = CompositionError) -> None:
    """Fail (`error`) with what cordis knows about every row that is not ACTIVE, or return
    quietly. A loader that never came up (a layer that can't be read or composed) is its own
    diagnosis."""
    if booted.loader is None:
        raise error(f"{what}:\n{Inspection(booted.runtime).explain('loader')}")
    stalled = {row: state for row, state in booted.loader.status().items() if _is_stalled(state)}
    if not stalled:
        return
    view = Inspection(booted.runtime)
    # a row with a fiber gets cordis's diagnosis; a row without one (unresolved) gets its status
    lines = [
        view.explain(row) if view.fiber(row) is not None else f"{row}: {state}"
        for row, state in stalled.items()
    ]
    raise error(f"{what}:\n" + "\n".join(lines))


def _is_stalled(state: str) -> bool:
    """A row that should be running and is not.

    `disabled` is a choice, not a stall. A row whose *background* work died
    (`Loader.describe`'s "active, work failed: ..." — task-0005) is not a stall either: the
    fiber is still ACTIVE, its setup and binds still stand (cordis/README.md), and that
    failure reaches `run()` through the chat row's own `done` await, not through this check.
    Without this, a fast failure can race `_raise_if_stalled("could not start")` and get
    reported as a composition error instead of the Recoverable failure it actually is.
    """
    return state not in ("active", "disabled") and not state.startswith("active, work failed")
