"""Sessions: every interactive run is a directory that can be listed and resumed.

A session is where one conversation lives, outside the project (so a jailed input can't touch
it): `meta.json` (which directory, which stack, when), `session.toml`, the session's own
layer file, `transcript.jsonl`, the loop's history (what a resume sends the model again), and
`events.jsonl`, what the ui showed (so a resume shows it again). The session's layer is the
last shipped layer, so everything a run chose (the model, the jail, where history goes) is
composition, and resuming is booting with that layer again. `/model` edits it the same way:
the layer files stay the only way the running program changes.

A `meta.json` that can't be read (not JSON, a key missing, a value of the wrong type) is a
`Broken` record: listing skips it and says which one it is and what is wrong, so one bad file
never stops the app, `bh-02 sessions` or `--resume`. A session whose layer still names the
Claude Agent SDK stack bh-02 no longer has is `retired`: it lists, but can't be resumed.

`session_layer`, `with_model`, `retired` and `resume_command` (and the private helpers) are
pure; the rest reads or writes the state directory. `Listing` is the `sessions` value
(CONTRACTS.md) the shell binds for the status bar.
"""

import datetime
import json
import os
import secrets
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from bh_02.outdated import translated
from cordis import Row
from cordis.composition import format_layer
from cordis.loader import read_layer

__all__ = [
    "Broken",
    "Listing",
    "Session",
    "create",
    "discard",
    "find",
    "listed",
    "models_file",
    "pins_model",
    "resume_command",
    "retired",
    "scanned",
    "session_layer",
    "set_model",
    "default_state_root",
    "state_root",
    "update",
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
_DEFAULT_MODEL = "sonnet"  # what the model row names when no layer says (models:model's default)
# What an earlier bh-02 called the model row, and its Ollama stack (`--ollama`, gone): a
# session started on that stack had the Ollama row from a shipped layer, not its own.
_OLD_MODEL_ROW = "completion"
_OLLAMA_STACK = "ollama"
_OLLAMA = "ollama:completion"


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
    """The session's layer: where its history goes, what this run chose, and what the
    operator's /model and /clear act on.

    bh-02's own loop runs over the `model` row, which names its model (`default`, which
    `--model` and /model set): the conversation is the `transcript` row's, kept in the
    session's `transcript.jsonl` (what a resume sends the model again). The model row is
    also told where the claude-code provider keeps its state, the session's `claude/`
    directory (Claude Code's config and session, which a resume continues, and the CLI's
    stderr), whichever model runs first: /model can switch to Claude at any time. (The status
    bar's session id is the `status` row's, read from the `sessions` value, not written here.)
    The `ui` row is told where to keep what it shows, which it draws again on a resume from
    the last /clear on (the ui hears `cleared` and keeps its own file; /clear empties only the
    model's history).
    """
    ui = {"history": str(dir / _EVENTS)}
    history = dir / TRANSCRIPT
    rows = [
        Row("ui", config=ui),
        Row("transcript", config={"path": str(history)}),
        # /model edits this very file; /clear empties the model's history before starting afresh
        Row(
            "operator", config={"layer": str(dir / _LAYER), "model_row": _MODEL_ROW, "forget": [str(history)]}
        ),
    ]
    rows.append(Row(_MODEL_ROW, config={"state": str(dir / _CLAUDE_STATE)}))
    if model is not None:
        rows = with_model(rows, model)
    if no_jail:
        rows.append(Row("jail", "kernel:unjailed"))
    return rows


def pins_model(rows: Sequence[Row]) -> bool:
    """Whether a layer composed after a session's (a `--patch` file) sets the model row's config:
    a layer replaces a row's config whole, so its `default` wins over the one `--model` and
    `/model` record in the session's layer."""
    return any(row.id == _MODEL_ROW and row.config is not None for row in rows)


def retired(rows: Sequence[Row]) -> str | None:
    """Why a session's layer can't run any more, or None when it can.

    The first Claude stack let Claude Code run its own loop (`claude-agent-sdk:*`, an `llm` row
    with a `session_file` and `stderr_log`): its conversation lived in Claude Code alone, with no
    transcript bh-02 could continue it from. (Sessions from the Messages API stack, which named
    `anthropic:completion`, are not retired: `_updated` moves them to the model row.)
    """
    for row in rows:
        if row.use is not None and row.use.startswith("claude-agent-sdk:"):
            return f"its layer names {row.use}, which bh-02 no longer has"
        if row.id == "llm" and {"session_file", "stderr_log"} & set(row.config or {}):
            return "it ran on the Claude Agent SDK stack, whose conversation bh-02 can no longer continue"
    return None


# What a session layer written earlier said that the shipped layers now say better: a
# `model_status` row naming its row (the model row was `completion` then), which replaced the
# shipped config (and its `default`, the model the status bar names when none is chosen) with
# one that has no default.
_SUPERSEDED = (Row("model_status", config={"row": _OLD_MODEL_ROW}),)
# Claude through Anthropic's Messages API (`anthropic:completion`) became Claude through Claude
# Code (`claude-code:completion`), now a provider of the model row; of that row's config only
# the model carries over (`outdated` names it as the model row's `default`).
_RETIRED_COMPLETION = "anthropic:completion"
_COMPLETION = "claude-code:completion"
_CARRIED = frozenset({"model", "state", "env_file", "cwd"})


def _updated(rows: Sequence[Row], dir: Path, stack: str) -> list[Row]:
    """A session's layer as a session started now would have it: without the rows an earlier
    bh-02 wrote that the shipped layers now say better, in today's names (`outdated`: rows
    renamed, the status-bar rows made one, rows bh-02 no longer has dropped, its `session` row
    among them, the model row's providers moved into `models:model`), a completion row that
    named the Messages API naming Claude Code first (its API-only settings dropped), a session
    of the Ollama stack given the Ollama row its shipped layer gave it (a layer bh-02 no longer
    has), and the model row's `state` in the session's directory."""
    pre: list[Row] = []
    for row in rows:
        if row in _SUPERSEDED:
            continue  # superseded first: translated, it would become a `status` row
        if row.id == _OLD_MODEL_ROW and row.use == _RETIRED_COMPLETION:
            config = {k: v for k, v in (row.config or {}).items() if k in _CARRIED}
            row = Row(row.id, _COMPLETION, config, row.disabled)
        elif row.id == _OLD_MODEL_ROW and row.use is None and stack == _OLLAMA_STACK:
            row = Row(row.id, _OLLAMA, row.config, row.disabled)  # --ollama --model: the row's model
        pre.append(row)
    ids = {row.id for row in pre}
    if stack == _OLLAMA_STACK and not ids & {_OLD_MODEL_ROW, _MODEL_ROW}:
        pre.append(Row(_OLD_MODEL_ROW, _OLLAMA))  # the Ollama row `ollama.toml` gave it
    current, _ = translated(pre)
    out: list[Row] = []
    for row in current:
        if row.id == _MODEL_ROW and row.use in (None, "models:model") and "state" not in (row.config or {}):
            row = Row(
                row.id, row.use, {**(row.config or {}), "state": str(dir / _CLAUDE_STATE)}, row.disabled
            )
        out.append(row)
    if not any(row.id == _MODEL_ROW for row in out):
        out.append(Row(_MODEL_ROW, config={"state": str(dir / _CLAUDE_STATE)}))
    return out


def update(session: Session) -> None:
    """Rewrite a session's layer as `_updated` says, if that changes it (before a resume)."""
    rows = read_layer(session.layer)
    if (fresh := _updated(rows, session.dir, session.stack)) != rows:
        session.layer.write_text(format_layer(fresh, _HEADER))


def with_model(rows: Sequence[Row], model: str) -> list[Row]:
    """`rows` with the model named on the row that chooses it (the model row's `default`),
    keeping that row's other config."""
    target = _MODEL_ROW
    out = [r for r in rows if r.id != target]
    current = next((r for r in rows if r.id == target), Row(target))
    return [*out, Row(target, current.use, {**(current.config or {}), "default": model}, current.disabled)]


def state_root() -> Path:
    """`$XDG_STATE_HOME/bh-02/sessions`, else the default (`default_state_root`)."""
    if base := os.environ.get("XDG_STATE_HOME"):
        return Path(base) / "bh-02" / "sessions"
    return default_state_root()


def models_file() -> Path:
    """`$XDG_CONFIG_HOME/bh-02/models.toml`, else `~/.config/bh-02/models.toml`: the models file
    the model row reads when its config names no other (the models plugin resolves it the same way)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "bh-02" / "models.toml"


def default_state_root() -> Path:
    """`~/.local/state/bh-02/sessions`: where sessions live when `XDG_STATE_HOME` is not set,
    so a run with it set still keeps a jailed input out of a default run's sessions."""
    return Path.home() / ".local" / "state" / "bh-02" / "sessions"


def create(root: Path, cwd: str, *, model: str | None, no_jail: bool, patches: Sequence[str] = ()) -> Session:
    """A new session directory, its metadata and its layer, written before anything boots.

    Its `stack` is the model it was started on (`--model`'s name, else the default), and
    `patches` the names of the `--patch` files it started with: the listing shows both, since
    a patch can replace the model row. A resume with other patches keeps these.
    """
    stack = model or _DEFAULT_MODEL
    now = datetime.datetime.now()
    sid = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    # To the microsecond, so two sessions started in the same second still list newest first.
    session = Session(sid, root / sid, cwd, stack, now.isoformat(timespec="microseconds"), tuple(patches))
    session.dir.mkdir(parents=True)
    meta: dict[str, Any] = {"id": sid, "cwd": cwd, "stack": stack, "created": session.created}
    if patches:
        meta["patches"] = list(patches)
    (session.dir / _META).write_text(json.dumps(meta, indent=2) + "\n")
    rows = session_layer(session.dir, model=model, no_jail=no_jail)
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
    """The `sessions` value (CONTRACTS.md): the running session, which the status bar shows.

    `current` is its id, empty when the composition runs without a session (as tests boot
    one); `resumed`: it was continued (`--resume`), which the status bar marks. `root` is the
    state directory the sessions are kept in, empty without one: the command line names it
    among what no jailed input may read.
    """

    root: str = ""
    current: str = ""
    resumed: bool = False
