"""Sessions: every interactive run is a directory that can be listed and resumed.

A session is where one conversation lives, outside the project (so a jailed input can't touch
it): `meta.json` (which directory, which stack, when), `session.toml`, the session's own
layer file, `transcript.jsonl`, the conversation (what a resume sends the model again), and
`events.jsonl`, what the ui showed (so a resume shows it again). The session's layer is the
last shipped layer, so everything a run chose (the model, the jail, where the conversation is kept) is
composition, and resuming is booting with that layer again. `/model` edits it the same way:
the layer files stay the only way the running program changes.

A `meta.json` that can't be read (not JSON, a key missing, a value of the wrong type) is a
`Broken` record: listing skips it and says which one it is and what is wrong, so one bad file
never stops the app, `bh-02 sessions` or `--resume`.

`session_layer`, `with_model` and `resume_command` (and the private helpers) are pure; the
rest reads or writes the state directory. `Listing` is the `session` value
(CONTRACTS.md) the shell binds for the status bar.
"""

import datetime
import json
import os
import secrets
import shutil
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, assert_never

from cordis import Row
from cordis.composition import format_layer
from cordis.loader import read_layer
from host_paths import config_home, passes, roots, state_home

__all__ = [
    "Broken",
    "Listing",
    "Session",
    "create",
    "discard",
    "find",
    "listed",
    "pins_model",
    "resume_command",
    "scanned",
    "session_layer",
    "set_model",
    "default_state_root",
    "state_root",
    "with_model",
]

_HEADER = "This session's own layer: written by bh-02 when the session started; /model edits it."
_LAYER = "session.toml"
_META = "meta.json"
TRANSCRIPT = "transcript.jsonl"
_EVENTS = "events.jsonl"
_MODEL_ROW = "model"  # the row whose `default` (the model's name) /model and --model set
_CLAUDE_STATE = (
    "claude"  # the claude-code provider's own state: Claude Code's config, its session, its stderr
)
# The `stack` of a session whose layer records no model, because neither `--model` nor the models
# file's `default` names one, or that default can't be read: it follows the file's default, and the
# model row says what is wrong, or what to write when none is chosen.
_UNPINNED = "default"


@dataclass(frozen=True, slots=True)
class Session:
    """One session: its directory and what it was started as."""

    id: str
    dir: Path
    cwd: str
    stack: str  # the model it started on (an earlier bh-02's: `claude` or `ollama`, its provider)
    created: str
    patches: tuple[str, ...] = ()  # the --patch files it started with (by name)

    @property
    def layer(self) -> Path:
        return self.dir / _LAYER


@dataclass(frozen=True, slots=True)
class Broken:
    """A session record that can't be read: its directory and what is wrong with its meta.json."""

    dir: Path
    why: str

    @property
    def id(self) -> str:
        """The directory's name, which is the id the session was made with."""
        return self.dir.name

    @property
    def message(self) -> str:
        """What to tell the person: which file, what is wrong, and what to do about it."""
        return f"session record {self.dir / _META} can't be read ({self.why}); fix it or remove {self.dir}"


def session_layer(dir: Path, *, model: str | None, no_jail: bool) -> list[Row]:
    """The session's layer: where its conversation and screen history go, what this run chose, and
    what the switch row's /model acts on.

    bh-02's own loop runs over the `model` row, which names its model (`default`, which
    `--model` and /model set): the conversation is the `transcript` row's, kept in the
    session's `transcript.jsonl` (what a resume sends the model again). The model row is
    also told where the claude-code provider keeps its state, the session's `claude/`
    directory (Claude Code's config and session, which a resume continues, and the CLI's
    stderr), whichever model runs first: /model can switch to Claude at any time. (The status
    bar's session id is the `status` row's, read from the `session` value, not written here.)
    The `ui` row is told where to keep what it shows, which it draws again on a resume from
    the last /clear on (the ui hears `cleared` and keeps its own file; /clear writes over only
    the conversation's file, the conversation row finding it from the transcript row's `path`).
    """
    ui = {"history": str(dir / _EVENTS)}
    transcript = dir / TRANSCRIPT
    rows = [
        Row("ui", config=ui),
        Row("transcript", config={"path": str(transcript)}),
        # /model edits this very file
        Row("switch", config={"layer": str(dir / _LAYER), "model_row": _MODEL_ROW}),
    ]
    rows.append(Row(_MODEL_ROW, config={"state": str(dir / _CLAUDE_STATE)}))
    if model is not None:
        rows = with_model(rows, model)
    if no_jail:
        rows.append(Row("runner", "runner:unconfined"))
    return rows


def pins_model(rows: Sequence[Row]) -> bool:
    """Whether a layer composed after a session's (a `--patch` file) sets the model row's config:
    a layer replaces a row's config whole, so its `default` wins over the one `--model` and
    `/model` record in the session's layer."""
    return any(row.id == _MODEL_ROW and row.config is not None for row in rows)


def with_model(rows: Sequence[Row], model: str) -> list[Row]:
    """`rows` with the model named on the row that chooses it (the model row's `default`),
    keeping that row's other config."""
    target = _MODEL_ROW
    out = [r for r in rows if r.id != target]
    current = next((r for r in rows if r.id == target), Row(target))
    return [*out, Row(target, current.use, {**(current.config or {}), "default": model}, current.disabled)]


def state_root() -> Path:
    """`$XDG_STATE_HOME/bh-02/sessions`, else the default (`default_state_root`); a relative
    value counts as unset (`host_paths.state_home`)."""
    return state_home(os.environ, Path.home()) / "bh-02" / "sessions"


def _models_file() -> Path:
    """`$XDG_CONFIG_HOME/bh-02/models.toml`, else `~/.config/bh-02/models.toml`: the models file
    the model row reads when its config names no other (the models plugin resolves it the same way,
    through `host_paths.config_home`)."""
    return config_home(os.environ, Path.home()) / "bh-02" / "models.toml"


def _pinned(file: str | OSError | UnicodeDecodeError | None) -> str | None:
    """The model a new session's layer records from the models file (`file`: its text; None when there
    is none, or it is not read; the error when it can't be read or is not UTF-8 text): the file's
    `default` when that is a name (a non-empty string; the model row says so if it names no model).
    None, no model recorded, when there is no file or it names no default (there are no built-in
    models: the row says what to write), and when the model row has something to say about the file:
    it can't be read, is not UTF-8 text or TOML, holds a key that is no table, or its `default` is no
    name (TASK-0087: the row stays `Unusable` and says what to write). The same rule as
    `models_cordis_plugin.named.parsed` and `standing`, which the app test of the two sides holds them
    to: a `default` that is a table is an endpoint named `default`, not the setting."""
    match file:
        case None:
            return None
        case OSError() | UnicodeDecodeError():
            return None
        case str():
            pass
        case _ as unreachable:
            assert_never(unreachable)
    try:
        data = tomllib.loads(file)
    except tomllib.TOMLDecodeError:
        return None
    declared: object = None
    for name, value in data.items():
        if isinstance(value, dict):
            continue  # an endpoint's table
        if name != "default":
            return None  # a key that is no table
        declared = value
    if declared is None:
        return None
    return declared if isinstance(declared, str) and declared else None


def default_state_root() -> Path:
    """`~/.local/state/bh-02/sessions`: where sessions live when `XDG_STATE_HOME` is not set,
    so a run with it set still keeps a jailed input out of a default run's sessions."""
    return Path.home() / ".local" / "state" / "bh-02" / "sessions"


def create(root: Path, cwd: str, *, model: str | None, no_jail: bool, patches: Sequence[str] = ()) -> Session:
    """A new session directory, its metadata and its layer, written before anything boots.

    The model it starts on is `--model`'s name, else the models file's `default` when that is a
    name (`_pinned`); the layer records it (as `--model` does), so a resume keeps it whatever the
    file says later. When there is neither, or the file can't be read, is not TOML or has a `default`
    that is no name, the layer records none and the model row says what is wrong or what to write;
    the session's `stack` is then `default`. Otherwise its `stack` is that model, and
    `patches` the names of the `--patch` files it started with: the listing shows both, since
    a patch can replace the model row. A resume with other patches keeps these.
    """
    file: str | OSError | UnicodeDecodeError | None = None
    # As the model row reads the file, it is trusted only outside the project, where the model's
    # code can write: a file in it, by its path or the links on the way, gives no default. The roots
    # are the row's: the working directory, and the session's directory, which is the same one in a
    # real run. (The row's own `cwd` is only a layer's, and a layer that sets the model row replaces
    # the one written here whole: `pins_model`.)
    if not model and not any(passes(_models_file(), roots(Path(where))) for where in {cwd, os.getcwd()}):
        try:
            file = _models_file().read_text(encoding="utf-8")
        except FileNotFoundError:
            pass  # no file: no user models, no default
        except (OSError, UnicodeDecodeError) as error:
            file = error  # the model row says it can't read the file, or that it is not UTF-8 text
    pinned = model or _pinned(file)
    stack = pinned or _UNPINNED
    now = datetime.datetime.now()
    sid = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    # To the microsecond, so two sessions started in the same second still list newest first.
    session = Session(sid, root / sid, cwd, stack, now.isoformat(timespec="microseconds"), tuple(patches))
    session.dir.mkdir(parents=True)
    meta: dict[str, Any] = {"id": sid, "cwd": cwd, "stack": stack, "created": session.created}
    if patches:
        meta["patches"] = list(patches)
    (session.dir / _META).write_text(json.dumps(meta, indent=2) + "\n")
    rows = session_layer(session.dir, model=pinned, no_jail=no_jail)
    session.layer.write_text(format_layer(rows, _HEADER))
    return session


def set_model(session: Session, model: str) -> None:
    """Choose the model for a session from now on, in its layer (so a resume keeps it)."""
    rows = with_model(read_layer(session.layer), model)
    session.layer.write_text(format_layer(rows, _HEADER))


def listed(root: Path, cwd: str) -> list[Session]:
    """This directory's sessions, newest first; a record that can't be read is left out."""
    return scanned(root, cwd)[0]


def scanned(root: Path, cwd: str) -> tuple[list[Session], list[Broken]]:
    """This directory's sessions, newest first, and the records that can't be read.

    A broken record is one whose meta.json is not JSON, lacks a key, or has a value of the
    wrong type; one whose `cwd` can't be read may be any directory's, so it is reported here
    too. A meta.json that vanishes while listing (a session another run is discarding) is
    neither: a race is not a broken file.
    """
    found: list[Session] = []
    broken: list[Broken] = []
    for meta in sorted(root.glob(f"*/{_META}")) if root.is_dir() else []:
        try:
            content = meta.read_bytes()
        except OSError:
            continue
        match _record(content, meta.parent, cwd):
            case Session() as session:
                found.append(session)
            case Broken() as record:
                broken.append(record)
    return _newest(found), broken


def _record(content: bytes, dir: Path, cwd: str) -> Session | Broken | None:
    """The session a meta.json describes, `Broken` saying what is wrong with it, or None when
    it is another directory's."""
    try:
        data = json.loads(content)
    except ValueError as error:
        return Broken(dir, f"not JSON: {error}")
    if not isinstance(data, dict):
        return Broken(dir, "not a JSON object")
    if not isinstance(data.get("cwd"), str):
        return Broken(dir, "`cwd` is missing or not a string")
    if data["cwd"] != cwd:
        return None
    for key in ("id", "stack", "created"):
        if not isinstance(data.get(key), str) or not data[key]:
            return Broken(dir, f"`{key}` is missing, empty or not a string")
    patches = data.get("patches", [])
    if not isinstance(patches, list) or not all(isinstance(p, str) for p in patches):
        return Broken(dir, "`patches` is not a list of file names")
    return Session(data["id"], dir, cwd, data["stack"], data["created"], tuple(patches))


def discard(session: Session) -> None:
    """Remove a session's directory: a run that never started leaves nothing to resume."""
    shutil.rmtree(session.dir, ignore_errors=True)


def _newest(sessions: Sequence[Session]) -> list[Session]:
    return sorted(sessions, key=lambda s: s.created, reverse=True)


class _Named(Protocol):
    @property
    def id(self) -> str: ...


def _matching[T: _Named](sessions: Sequence[T], sid: str) -> list[T]:
    """The sessions `sid` names: the one whose id it is, else every one whose id starts with
    it, else every one whose id ends with it (the short id the status bar shows)."""
    exact = [s for s in sessions if s.id == sid]
    return (
        exact or [s for s in sessions if s.id.startswith(sid)] or [s for s in sessions if s.id.endswith(sid)]
    )


def find(root: Path, cwd: str, sid: str | None) -> list[Session | Broken]:
    """The sessions a resume could mean: the newest readable one for this directory when `sid`
    is None, else those `sid` names (an id, a prefix of one, or its end, as the status bar's
    short id), a broken record among them, so a resume of it can say what is wrong. More than
    one is ambiguous."""
    sessions, broken = scanned(root, cwd)
    if sid is None:
        return [*sessions[:1]]
    return _matching([*sessions, *broken], sid)


def resume_command(stack: str, session_id: str | None = None) -> str:
    """The command that continues a session (the newest when `session_id` is None), whatever
    it runs on (`stack`): the model row reads any credential from `local.env` itself."""
    return "uv run bh-02 --resume" if session_id is None else f"uv run bh-02 --resume {session_id}"


@dataclass(frozen=True, slots=True)
class Listing:
    """The `session` value (CONTRACTS.md): the running session, which the status bar shows.

    `current` is its id, empty when the composition runs without a session (as tests boot
    one); `resumed`: it was continued (`--resume`), which the status bar marks. `root` is the
    state directory the sessions are kept in, empty without one: the command line names it
    among what no jailed input may read.
    """

    root: str = ""
    current: str = ""
    resumed: bool = False
