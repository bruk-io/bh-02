"""Named models: which model a name means, on which provider, with what settings.

Three places name models, each over the last: the built-ins (`sonnet`, `opus`, `haiku`,
Claude through Claude Code), the models file (`$XDG_CONFIG_HOME/bh-02/models.toml`, else
`~/.config/bh-02/models.toml`, or the row's `models`), and the row's own `extra` (a table
like the file's, which a migrated layer writes). A later place wins: an `extra` model over
the file's of the same name, and a user's model over a built-in (allowed, and marked as
shadowing it). The file is one table per model:

    [llama]
    provider = "openai"                        # or "claude-code"
    id = "llama3.2"                            # the provider's own name for the model
    base_url = "http://localhost:11434/v1"     # openai only: where /chat/completions is
    key = "OPENROUTER_API_KEY"                 # openai only, optional: a line of local.env
    max_tokens = 4096                          # optional
    temperature = 0.2                          # optional

A top-level `default = "NAME"` above the tables names the model a new session starts on. The
model a session starts on is chosen, lowest first, by the built-in `sonnet`, the file's `default`,
a layer's model row `default` (the session's own layer, which `/model` and `--model` write; so a
resumed session keeps the model it was on), `--model` (which writes that layer). A layer that
names no model leaves `ModelConfig.default` None, so the file's counts; one that names `sonnet`
chooses it (`intended`).

A provider can also be `module:attribute`, a factory the model's table is passed to (bh-02's
fakes are one); its table is its own.

An openai table with `discover = true` is an endpoint, not a model: it names the models its server
lists, `ENDPOINT/ID`, split at the first `/` (`find`). Such a name needs no network to mean what it
says (`find` derives the model from the endpoint's table); the server is asked only when `/model`
lists (`discovery.py`). `include` narrows what is listed, by glob. Endpoints come only from the
models file, which is why a layer's `extra` may not hold one. An endpoint whose table has a problem
names no model: `ENDPOINT/ID` is refused with that table's problem, as the table alone is.

The models file is trusted whole: a factory it names runs in bh-02's own process, and a `key`
it names is sent to its `base_url`. So it is not read when it is in the project, which the
model's code can write (`in_project`: bh-02 run from the home directory, `$XDG_CONFIG_HOME` in
the project, a link into it). And wherever a table comes from, an `openai` model's `key` may
not name the Claude Code token (`withheld`), which is the Claude Code CLI's alone.

Everything here is pure but `models_file`, which reads the environment, `read_models`, which
reads the file, and `in_project`, which follows the file's links.
"""

import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from host_paths import config_home, passes, roots
from models_cordis_plugin.claude_code.credential import TOKEN_VARIABLE

__all__ = [
    "BUILT_IN",
    "CLAUDE_CODE",
    "OPENAI",
    "Intended",
    "ModelConfig",
    "ModelsError",
    "Named",
    "combined",
    "chosen",
    "derived",
    "endpoint",
    "environ",
    "find",
    "from_file",
    "in_project",
    "intended",
    "key_name",
    "models_file",
    "not_a_model",
    "parsed",
    "problem",
    "read_models",
    "said_names",
    "standing",
    "withheld",
]

CLAUDE_CODE: Final = "claude-code"
OPENAI: Final = "openai"
_PROVIDERS: Final = (CLAUDE_CODE, OPENAI)
BUILT_IN: Final[Mapping[str, Mapping[str, Any]]] = {
    "sonnet": {"provider": CLAUDE_CODE, "id": "sonnet"},
    "opus": {"provider": CLAUDE_CODE, "id": "opus"},
    "haiku": {"provider": CLAUDE_CODE, "id": "haiku"},
}
_BUILT_IN_DEFAULT: Final = "sonnet"
_BUILT_IN_SOURCE: Final = "built in"
_FILE_SOURCE: Final = "the models file"
_LAYER_SOURCE: Final = "the model row"
_DEFAULT_KEY: Final = "default"
_EXTRA_SOURCE: Final = "the model row's extra"
_DISCOVER: Final = "discover"
_INCLUDE: Final = "include"
# The keys a model's table may have, per provider (a factory's table is its own).
_KEYS: Final[Mapping[str, frozenset[str]]] = {
    CLAUDE_CODE: frozenset({"provider", "id"}),
    OPENAI: frozenset(
        {"provider", "id", "base_url", "key", "max_tokens", "temperature", _DISCOVER, _INCLUDE}
    ),
}
# A key is the name of a local.env line, never the key itself: a value that isn't such a name is
# never quoted back (an error is shown in the conversation and kept in the session's events).
# Capitals only: a key itself nearly always has lower-case letters (`gsk_...`, `sk-...`), which
# a name with `_` alone would let through.
_KEY_NAME: Final = re.compile(r"[A-Z_][A-Z0-9_]*")
_EXAMPLE: Final = (
    '[NAME]\nprovider = "openai"\nid = "MODEL ID"\nbase_url = "https://HOST/v1"\nkey = "LINE_IN_LOCAL_ENV"'
)


class ModelsError(Exception):
    """A model that can't be used, said for the person (CONTRACTS.md: Errors): the `model`
    contract's recoverable error."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """The `model` row's config. `default`: the model's name (`/model` and `--model` set it);
    None when no layer names one, which is not the same as naming `sonnet` (`intended`: the
    models file's `default` counts then).
    `models`: the models file, when not the default one. `extra`: models of the row's own, one
    table per name, as in the file. For the claude-code provider: `state`, the directory its
    Claude Code state lives in (the session's `claude/`, which the session layer sets);
    `env_file`, where `local.env` is (found above the install when unset; the openai provider
    reads a model's `key` there too); `cwd`, the project Claude Code is told it works in (the
    working directory when unset), which, like the working directory, a models file must be
    outside of (`in_project`)."""

    default: str | None = None
    models: str | None = None
    extra: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    state: str | None = None
    env_file: str | None = None
    cwd: str | None = None


@dataclass(frozen=True, slots=True)
class _ModelsFile:
    """What a models file says: its model tables by name, and its top-level `default` as written
    (None when it has none; TOML has no null, so None is never a value; not checked here: said
    by `chosen` when it is the one in effect)."""

    models: Mapping[str, Mapping[str, Any]]
    default: object = None


@dataclass(frozen=True, slots=True)
class Intended:
    """The model name a session starts on, as written (`name`: not yet checked to be a name), and
    where it was written: `origin`, the built-in default, the models file, or a layer."""

    name: object
    origin: str


@dataclass(frozen=True, slots=True)
class Named:
    """One model a name means: its provider, the provider's id for it, its whole table (the
    provider's settings), where it was named, and whether it shadows a built-in."""

    name: str
    provider: str
    id: str
    table: Mapping[str, Any]
    source: str
    shadows: bool = False


def models_file(explicit: str | None, environ: Mapping[str, str]) -> Path:
    """The models file: `explicit` (the row's `models`), else `$XDG_CONFIG_HOME/bh-02/models.toml`,
    else `~/.config/bh-02/models.toml` (`host_paths.config_home`: a relative value counts as unset)."""
    if explicit:
        return Path(explicit).expanduser()
    return config_home(environ, Path.home()) / "bh-02" / "models.toml"


def read_models(path: Path) -> str | None:
    """The models file's text, or None when there is none (no file is no user models)."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ModelsError(
            "models_file", f"can't read the models file {path} ({error.strerror}); fix it or remove it"
        ) from None


def in_project(path: Path, root: Path) -> str | None:
    """Why the models file `path` is not read, said so the person can fix it: it is in the project
    `root`, which the model's code can write. It is the project's when, as named or anywhere reading
    it goes (each directory and link on the way, links followed, to where it ends:
    `host_paths.passes`, as memory files outside the project and the python row's startup files are
    walked), it is under the root as named or as resolved; a link the model could repoint, or a
    directory it could swap for one, would choose what is read. None when it is outside. Whether
    the file is there does not matter: the model could write one."""
    inside = passes(path, roots(root))
    if not inside:
        return None
    named = Path(os.path.normpath(path.absolute()))
    return _refused(path, root, "" if inside[0] == named else f" as its links lead ({inside[-1]})")


def _refused(path: Path, root: Path, how: str) -> str:
    return (
        f"the models file {path} is not read: it is in the project ({root}){how}, which the model's "
        "code can write, and a models file the model wrote could run code in bh-02's own process (a "
        "`module:attribute` provider) or send a local.env key to a server of its choosing. Keep your "
        "models file outside the project, and not a link into it: run bh-02 in the project's own "
        "directory rather than one that holds your config (such as your home), or set "
        "XDG_CONFIG_HOME (or the model row's `models`) to a directory outside it. Until then only "
        "the built-in models and the model row's `extra` are offered"
    )


def environ() -> Mapping[str, str]:
    """The process environment, for `models_file`."""
    return os.environ


def parsed(text: str | None, source: str) -> _ModelsFile:
    """The models file's tables, by name, and its `default`: empty for no file. A file that is not
    TOML, or holds something other than one table per model (and a `default`), is a
    `ModelsError` naming it. A `[default]` table is a model named `default`."""
    if text is None:
        return _ModelsFile({})
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ModelsError("models_file", f"the models file {source} is not TOML ({error}); fix it") from None
    default = None
    tables: dict[str, Mapping[str, Any]] = {}
    for name, table in data.items():
        if isinstance(table, dict):
            tables[name] = table
        elif name == _DEFAULT_KEY:
            default = table
        else:
            raise ModelsError(
                "models_file",
                f"the models file {source}: {name!r} is not a table; each model is one, e.g.\n{_EXAMPLE}",
            )
    return _ModelsFile(tables, default)


def standing(from_file: object) -> Intended:
    """The default below any layer: the models file's `default` when it has one, else `sonnet`."""
    if from_file is None:
        return Intended(_BUILT_IN_DEFAULT, _BUILT_IN_SOURCE)
    return Intended(from_file, _FILE_SOURCE)


def intended(layer: object, below: Intended) -> Intended:
    """The model a session starts on: a layer's model row `default` when it has one (None when no
    layer names a model, which `sonnet` named in a layer is not), else `below` (`standing`). A
    layer's default that is the models file's own default is the file's (`from_file`): a new
    session's layer records it from there at the start (`bh_02.sessions.create`), so an error
    about it says the file's default is the cause."""
    if layer is None or (layer == below.name and from_file(below)):
        return below
    return Intended(layer, _LAYER_SOURCE)


def from_file(wanted: Intended) -> bool:
    """Whether `wanted` was written as the models file's `default`."""
    return wanted.origin == _FILE_SOURCE


def combined(
    files: Mapping[str, Mapping[str, Any]], source: str, extra: Mapping[str, Mapping[str, Any]]
) -> list[Named]:
    """Every named model: the built-ins, then the models file's (`files`, read from `source`),
    then the row's `extra`; a later one of the same name replaces an earlier one, in its
    place, and a user's model named like a built-in is marked as shadowing it."""
    if not isinstance(extra, Mapping):
        raise ModelsError(
            "model_config",
            f"{_EXTRA_SOURCE} is {type(extra).__name__}, not a table of models; give it one table "
            "per model, as in the models file, or remove it",
        )
    for name, table in extra.items():
        if not isinstance(table, Mapping):
            raise ModelsError(
                "model_config",
                f"{_EXTRA_SOURCE}: {name!r} is not a table; each model is one, e.g. "
                f'`{name} = {{ provider = "openai", id = "MODEL ID", base_url = "https://HOST/v1" }}`',
            )
    out: dict[str, Named] = {name: _named(name, table, _BUILT_IN_SOURCE) for name, table in BUILT_IN.items()}
    for where, tables in ((source, files), (_EXTRA_SOURCE, extra)):
        for name, table in tables.items():
            out[name] = _named(str(name), table, where, shadows=name in BUILT_IN)
    return list(out.values())


def _named(name: str, table: Mapping[str, Any], source: str, *, shadows: bool = False) -> Named:
    provider, model = table.get("provider"), table.get("id")
    return Named(
        name,
        provider if isinstance(provider, str) else "",
        model if isinstance(model, str) else "",
        dict(table),
        source,
        shadows,
    )


def problem(named: Named) -> str | None:
    """What is wrong with a model's table, said so the person can fix it; None when nothing is."""
    where = f"model {named.name!r} ({named.source})"
    if not named.provider:
        return (
            f'{where} names no provider; give it `provider = "{OPENAI}"` (an OpenAI-compatible '
            f'endpoint) or `provider = "{CLAUDE_CODE}"` (Claude through Claude Code)'
        )
    if named.provider not in _PROVIDERS:
        if ":" in named.provider:
            return None  # a factory (`module:attribute`), whose table is its own
        known = " or ".join(map(repr, _PROVIDERS))
        return f"{where}: provider {named.provider!r} is not one bh-02 has; use {known}"
    if unknown := sorted(set(named.table) - _KEYS[named.provider]):
        allowed = ", ".join(sorted(_KEYS[named.provider]))
        return (
            f"{where}: {', '.join(unknown)} is not a setting of a {named.provider} model; it takes {allowed}"
        )
    if named.provider == OPENAI and (why := _discover_problem(named, where)) is not None:
        return why
    if not named.id and not endpoint(named):
        return f'{where} names no model id; give it `id = "..."`, the provider\'s own name for the model'
    if named.provider == OPENAI:
        return _openai_problem(named, where)
    return None


def endpoint(named: Named) -> bool:
    """Whether `named` is an endpoint, a table that names the models its server lists
    (`discover = true` on an openai table of the models file), not a model. A table of the
    row's `extra` is never one: endpoints come only from the trusted models file (`problem`)."""
    return named.provider == OPENAI and named.table.get(_DISCOVER) is True and named.source != _EXTRA_SOURCE


def _discover_problem(named: Named, where: str) -> str | None:
    """What is wrong with an openai table's `discover` and `include`, or None."""
    table = named.table
    discover = table.get(_DISCOVER)
    if _DISCOVER in table and not isinstance(discover, bool):
        return f"{where}: discover must be true or false"
    if _INCLUDE in table and discover is not True:
        return (
            f"{where}: include narrows the models an endpoint lists; add `discover = true`, or remove include"
        )
    if discover is not True:
        return None
    if named.source == _EXTRA_SOURCE:
        return (
            f"{where}: discover is read only from the models file, never from a layer: an endpoint is "
            "trusted whole, as its table in the models file is. Move this table there, or remove discover"
        )
    if "/" in named.name:
        return (
            f"{where}: an endpoint's name may not hold '/': its models are named ENDPOINT/ID, split at "
            "the first '/'. Rename the table"
        )
    if "id" in table:
        return (
            f"{where}: an endpoint names no id, it lists its models (named {named.name}/ID). Remove id, "
            "or remove discover for a single model"
        )
    patterns = table.get(_INCLUDE)
    if _INCLUDE in table and not (
        isinstance(patterns, list)
        and patterns
        and all(isinstance(pattern, str) and pattern for pattern in patterns)
    ):
        return f'{where}: include must be a list of patterns, like `include = ["qwen*"]`'
    return None


def _openai_problem(named: Named, where: str) -> str | None:
    """What is wrong with an openai model's settings, or None."""
    url = named.table.get("base_url")
    if not isinstance(url, str) or not url:
        return (
            f"{where} names no base_url; give it the endpoint's base, the part before "
            '/chat/completions (e.g. `base_url = "https://api.openai.com/v1"`, '
            '`"http://localhost:11434/v1"` for Ollama)'
        )
    if (bad := _url_problem(url)) is not None:
        return f'{where}: base_url {url!r} {bad}; e.g. `base_url = "https://api.openai.com/v1"`'
    key = named.table.get("key")
    if key is not None and key_name(key) is None:
        return (
            f"{where}: key must name a line of local.env (capitals, digits and _, like "
            '`key = "OPENAI_API_KEY"`), not hold the key itself; put the key in local.env as '
            "`OPENAI_API_KEY=<the key>` and name that line here"
        )
    if (why := withheld(named)) is not None:
        return why
    tokens = named.table.get("max_tokens")
    if tokens is not None and (not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0):
        return f"{where}: max_tokens must be a whole number above 0"
    heat = named.table.get("temperature")
    if heat is not None and (not isinstance(heat, int | float) or isinstance(heat, bool)):
        return f"{where}: temperature must be a number"
    return None


def _url_problem(url: str) -> str | None:
    """What is wrong with a base_url as a URL (said after it), or None."""
    try:
        parts = urlsplit(url)
        _ = parts.port  # reading it checks it: a port not a number, or out of range, is a ValueError
    except ValueError as error:
        return f"is not a URL ({error})"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "is not an http(s) URL with a host"
    return None


def withheld(named: Named) -> str | None:
    """Why `named`'s key is never sent: it names the Claude Code token, which bh-02 hands to the
    Claude Code CLI alone, never to an endpoint; None when it names another line, or none."""
    if named.table.get("key") != TOKEN_VARIABLE:
        return None
    return (
        f"model {named.name!r} ({named.source}): key may not name {TOKEN_VARIABLE}, the Claude Code "
        "token: bh-02 gives it to the Claude Code CLI alone and never sends it to an endpoint "
        "(whoever holds it can use your subscription). Name the local.env line of this endpoint's "
        "own key (add one as `ITS_API_KEY=<the key>`), or use sonnet, opus or haiku for Claude"
    )


def key_name(key: object) -> str | None:
    """`key` when it is the name of a local.env line (`OPENAI_API_KEY`: capitals, digits, `_`);
    None for anything else, which may be the key itself and so is never quoted."""
    return key if isinstance(key, str) and _KEY_NAME.fullmatch(key) else None


def derived(host: Named, model_id: str) -> Named:
    """The model `ENDPOINT/ID` means: the endpoint's table (its provider, `base_url`, `key` and
    settings) with `model_id` as the model's, named as the person writes it. Nothing is asked of the
    server: an id it lacks is the first step's 404. A table with a problem (`problem`) means no model:
    `host` itself comes back, which `not_a_model` refuses with that problem, so the person is told
    which table to fix and what to write, and no model is made of a table bh-02 calls broken."""
    if problem(host) is not None:
        return host
    table = {k: v for k, v in host.table.items() if k not in (_DISCOVER, _INCLUDE)}
    return Named(f"{host.name}/{model_id}", OPENAI, model_id, {**table, "id": model_id}, host.source)


def find(name: object, models: Sequence[Named]) -> Named | None:
    """The model `name` means, or None: the table of that name, else `ENDPOINT/ID` for an
    endpoint (`derived`: the endpoint's own table when that has a problem), split at the first `/`
    so an id may hold more of them, and `:`. Pure: no server is asked."""
    if not isinstance(name, str):
        return None
    exact = next((named for named in models if named.name == name), None)
    if exact is not None:
        return exact
    host_name, slash, model_id = name.partition("/")
    if not slash or not model_id:
        return None
    host = next((named for named in models if named.name == host_name and endpoint(named)), None)
    return None if host is None else derived(host, model_id)


def not_a_model(found: Named) -> str | None:
    """Why `found` can't be the model row's model, said so the person can fix it: its table has a
    problem (`problem`: an endpoint's too, which resolves no model of it), or it is an endpoint,
    which lists models and is none; None when it can be."""
    if (why := problem(found)) is not None:
        return why
    if endpoint(found):
        return (
            f"{found.name!r} ({found.source}) is an endpoint, which lists models and is none itself; "
            f"name one of them, {found.name}/ID: /model lists them"
        )
    return None


def said_names(models: Sequence[Named]) -> str:
    """The models there are, for a message: each model's name, then, when there are endpoints,
    that a name may be `ENDPOINT/ID` for one."""
    names = ", ".join(named.name for named in models if not endpoint(named))
    hosts = ", ".join(named.name for named in models if endpoint(named))
    return names + (f"; or ENDPOINT/ID, for an endpoint ({hosts})" if hosts else "")


def chosen(
    name: object,
    models: Sequence[Named],
    source: str,
    refused: str | None = None,
    origin: str = _LAYER_SOURCE,
) -> Named:
    """The model `name` means, or a `ModelsError` saying what to do: no such name (the models
    there are, and where to add one, or why the models file is not read: `refused`, which
    `in_project` says), or a table with a problem. `origin`: where `name` was written
    (`Intended.origin`), said when it is the models file's `default`."""
    from_file = origin == _FILE_SOURCE
    if not isinstance(name, str) or not name:
        who = f"the default in the models file {source}" if from_file else "the model row's default"
        raise ModelsError(
            "models_file" if from_file else "model_config",
            f'{who} is {name!r}, not a model\'s name; give it one, like `default = "sonnet"`, or remove it',
        )
    found = find(name, models)
    if found is None:
        names = said_names(models)
        add = refused or (
            f"to add {name!r}, give it a table in the models file {source}:\n{_EXAMPLE.replace('NAME', name)}"
        )
        which = f", the default in the models file {source}" if from_file else ""
        raise ModelsError(
            "unknown_model",
            f"no model named {name!r}{which}; the models are {names}. /model NAME switches to one; {add}",
        )
    if (why := not_a_model(found)) is not None:
        raise ModelsError("model_config", why)
    return found
