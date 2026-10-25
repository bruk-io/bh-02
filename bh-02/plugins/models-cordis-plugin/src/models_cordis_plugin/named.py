"""Named models: which model a name means, on which provider, with what settings.

Two places name models, the second over the first: the models file
(`$XDG_CONFIG_HOME/bh-02/models.toml`, else `~/.config/bh-02/models.toml`, or the row's
`models`), and the row's own `extra` (tables like the file's, which a layer writes): an `extra`
endpoint wins over the file's of the same name. There are no built-in models: every model is one an
endpoint serves, so what a session runs on, and what it spends, is always written down by the person.

The file is one table per endpoint: how to reach a server, and the models it serves, each under
the endpoint's `models`, named `ENDPOINT/MODEL`. The same shape for every provider:

    default = "local/llama"

    [local]
    provider = "openai"                        # or "claude-code"
    base_url = "http://localhost:11434/v1"     # openai: where /chat/completions is
    key = { env = "OPENROUTER_API_KEY" }       # optional: where its key comes from (see below)

    [local.models.llama]
    id = "llama3.2"                            # the provider's own name for the model
    max_tokens = 4096                          # optional (openai), here or on the endpoint
    temperature = 0.2                          # optional (openai), here or on the endpoint

    [work]
    provider = "claude-code"
    base_url = "https://gateway.example/anthropic"   # optional: Claude through this gateway
    key = { cmd = "print-a-token", ttl_ms = 300000 }   # with base_url: Claude Code's apiKeyHelper
    experimental_betas = false                 # optional: false when the gateway refuses them
    models = { opus = { id = "claude-opus-5-5" } }   # the same data, written inline

An endpoint's `key` is one table naming exactly one source, `env` (a variable of bh-02's process
environment), `cmd` (a shell command that prints the key) or `op` (a 1Password reference, read by
`op read`), and, for `cmd` and `op`, an optional `ttl_ms`: how long a printed key is used (`KeySpec`).

A model's table is its endpoint's settings with its own over them (`derived`). `ENDPOINT/ID`, an id
the endpoint's `models` doesn't name, is that id on the endpoint: no server is asked for it. An
openai endpoint with `discover = true` also offers the models its server lists (`discovery.py`),
narrowed by `include`, by glob; `/model` asks the server only when it lists. A claude-code endpoint
with no `base_url` runs on the subscription token, which its `key` says where to get (`env`, `cmd` or
`op`, read when the CLI starts; no `ttl_ms`), and hands it to the Claude Code CLI alone. An endpoint whose
table has a problem names no model: `ENDPOINT/MODEL` is refused with that table's problem, as the
table alone is.

A top-level `default = "NAME"` names the model a new session starts on. The model a session starts
on is chosen, lowest first, by the file's `default`, a layer's model row `default` (the session's own
layer, which `/model` and `--model` write; so a resumed session keeps the model it was on), `--model`
(which writes that layer). A layer that names no model leaves `ModelConfig.default` None, so the
file's counts (`intended`); with neither, no model is chosen, and the model row says what to write
(`chosen`).

A provider can also be `module:attribute`, a factory each model's table is passed to (bh-02's fakes
are one); its tables are its own.

The models file is trusted whole: a factory it names runs in bh-02's own process, a `key` with a `cmd`
or `op` it names runs as the person, and a `key` it names is sent to its `base_url`. So it is not read
when it is in the project, which the model's code can write (`in_project`: bh-02 run from the home
directory, `$XDG_CONFIG_HOME` in the project, a link into it), and `discover` and `key` are read only
from it, never from a layer's `extra`. Wherever a table comes from, an openai endpoint's `key` may not
name the Claude Code token (`withheld`), which is the Claude Code CLI's alone.

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
from models_cordis_plugin.key import TOKEN_VARIABLE, KeySpec

__all__ = [
    "CLAUDE_CODE",
    "DEFAULT_TTL_MS",
    "OPENAI",
    "Intended",
    "ModelConfig",
    "ModelsError",
    "Named",
    "combined",
    "chosen",
    "derived",
    "environ",
    "find",
    "from_file",
    "in_project",
    "intended",
    "key_spec",
    "models_file",
    "named_models",
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
_UNCHOSEN: Final = "nowhere"  # the origin of no default: the models file names none
_FILE_SOURCE: Final = "the models file"
_LAYER_SOURCE: Final = "the model row"
_DEFAULT_KEY: Final = "default"
_EXTRA_SOURCE: Final = "the model row's extra"
_MODELS: Final = "models"
_DISCOVER: Final = "discover"
_INCLUDE: Final = "include"
_KEY: Final = "key"
_BETAS: Final = "experimental_betas"
# What only an endpoint says: which models it has. A model made of it (`derived`) drops them.
_LISTING: Final = frozenset({_MODELS, _DISCOVER, _INCLUDE})
# The keys a model's own table may have, per provider (a factory's tables are its own).
_MODEL_KEYS: Final[Mapping[str, frozenset[str]]] = {
    CLAUDE_CODE: frozenset({"id"}),
    OPENAI: frozenset({"id", "max_tokens", "temperature"}),
}
# The keys an endpoint's table may have, per provider: how to reach it, its models, and the
# settings its models share (each model's own table may set them again).
_ENDPOINT_KEYS: Final[Mapping[str, frozenset[str]]] = {
    CLAUDE_CODE: frozenset({"provider", "base_url", _KEY, _BETAS, _MODELS}),
    OPENAI: frozenset({"provider", "base_url", _KEY, "max_tokens", "temperature", *_LISTING}),
}
# A key's `env` is the name of a variable, never the key itself: a value that isn't such a name is
# never quoted back (an error is shown in the conversation and kept in the session's events).
# Capitals only: a key itself nearly always has lower-case letters (`gsk_...`, `sk-...`), which
# a name with `_` alone would let through.
_ENV_NAME: Final = re.compile(r"[A-Z_][A-Z0-9_]*")
_SOURCES: Final = ("env", "cmd", "op")  # what a `key` table may name; exactly one
_KEY_FIELDS: Final = frozenset({*_SOURCES, "ttl_ms"})
DEFAULT_TTL_MS: Final = 300_000  # how long a printed key is used when `ttl_ms` is unset (Claude Code's own)
_KEY_EXAMPLES: Final = (
    '`key = { env = "OPENROUTER_API_KEY" }`, `key = { cmd = "my-token-helper", ttl_ms = 600000 }` '
    'or `key = { op = "op://vault/item/field" }`'
)
# A model's name under its endpoint: 1 to 200 printable ASCII characters, no space and no `/` (a
# name is `ENDPOINT/MODEL`, split at the first `/`; `/model NAME` takes one word; a layer file holds
# it as TOML, which `format_layer` writes outside ASCII as an escape TOML refuses).
_MODEL_NAME: Final = re.compile(r"[!-.0-~]{1,200}")
_DEFAULTED: Final = (
    'default = "local/MODEL"\n\n[local]\nprovider = "openai"\nbase_url = "https://HOST/v1"\n\n'
    '[local.models.MODEL]\nid = "MODEL ID"'
)
_EXAMPLE: Final = (
    '[NAME]\nprovider = "openai"\nbase_url = "https://HOST/v1"\nkey = { env = "A_VARIABLE" }\n\n'
    '[NAME.models.MODEL]\nid = "MODEL ID"'
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
    None when no layer names one (`intended`: the models file's `default` counts then).
    `models`: the models file, when not the default one. `extra`: endpoints of the row's own, one
    table per name, as in the file. For the claude-code provider: `state`, the directory its
    Claude Code state lives in (the session's `claude/`, which the session layer sets);
    `cwd`, the project Claude
    Code is told it works in (the working directory when unset), which, like the working directory,
    a models file must be outside of (`in_project`)."""

    default: str | None = None
    models: str | None = None
    extra: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    state: str | None = None
    cwd: str | None = None


@dataclass(frozen=True, slots=True)
class _ModelsFile:
    """What a models file says: its endpoint tables by name, and its top-level `default` as written
    (None when it has none; TOML has no null, so None is never a value; not checked here: said
    by `chosen` when it is the one in effect)."""

    endpoints: Mapping[str, Mapping[str, Any]]
    default: object = None


@dataclass(frozen=True, slots=True)
class Intended:
    """The model name a session starts on, as written (`name`: not yet checked to be a name), and
    where it was written: `origin`, the models file, a layer, or nowhere (no default: `name` None)."""

    name: object
    origin: str


@dataclass(frozen=True, slots=True)
class Named:
    """A name and what it means: a model (its provider, the provider's id for it, its whole table:
    the provider's settings) or, with `endpoint`, an endpoint (`id` empty, `table` its own, its
    models under `models`), and where it was named."""

    name: str
    provider: str
    id: str
    table: Mapping[str, Any]
    source: str
    endpoint: bool = False


def models_file(explicit: str | None, environ: Mapping[str, str]) -> Path:
    """The models file: `explicit` (the row's `models`), else `$XDG_CONFIG_HOME/bh-02/models.toml`,
    else `~/.config/bh-02/models.toml` (`host_paths.config_home`: a relative value counts as unset)."""
    if explicit:
        return Path(explicit).expanduser()
    return config_home(environ, Path.home()) / "bh-02" / "models.toml"


def read_models(path: Path) -> str | None:
    """The models file's text, or None when there is none (no file is no user models).

    Raises:
        ModelsError: the file is there but can't be read, or is not UTF-8 text.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ModelsError(
            "models_file", f"can't read the models file {path} ({error.strerror}); fix it or remove it"
        ) from None
    except UnicodeDecodeError:
        raise ModelsError(
            "models_file", f"the models file {path} is not UTF-8 text; fix it or remove it"
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
        "code can write, and a models file the model wrote could run code as you (a `key` with a `cmd`, "
        "a `module:attribute` provider) or send a key to a server of its choosing. Keep your "
        "models file outside the project, and not a link into it: run bh-02 in the project's own "
        "directory rather than one that holds your config (such as your home), or set "
        "XDG_CONFIG_HOME (or the model row's `models`) to a directory outside it. Until then only "
        "the model row's `extra` is offered"
    )


def environ() -> Mapping[str, str]:
    """The process environment, for `models_file`."""
    return os.environ


def parsed(text: str | None, source: str) -> _ModelsFile:
    """The models file's endpoint tables, by name, and its `default`: empty for no file. A
    `[default]` table is an endpoint named `default`.

    Raises:
        ModelsError: the file is not TOML, or holds something other than one table per endpoint
            (and a `default`).
    """
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
                f"the models file {source}: {name!r} is not a table; each endpoint is one, e.g.\n{_EXAMPLE}",
            )
    return _ModelsFile(tables, default)


def standing(from_file: object) -> Intended:
    """The default below any layer: the models file's `default` when it has one, else none."""
    if from_file is None:
        return Intended(None, _UNCHOSEN)
    return Intended(from_file, _FILE_SOURCE)


def intended(layer: object, below: Intended) -> Intended:
    """The model a session starts on: a layer's model row `default` when it has one (None when no
    layer names a model), else `below` (`standing`). A
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
    """Every endpoint: the models file's (`files`, read from `source`), then the row's `extra`; a
    later endpoint of the same name replaces an earlier one, in its place.

    Raises:
        ModelsError: `extra` is not a table of tables.
    """
    if not isinstance(extra, Mapping):
        raise ModelsError(
            "model_config",
            f"{_EXTRA_SOURCE} is {type(extra).__name__}, not a table of endpoints; give it one table "
            "per endpoint, as in the models file, or remove it",
        )
    for name, table in extra.items():
        if not isinstance(table, Mapping):
            raise ModelsError(
                "model_config",
                f"{_EXTRA_SOURCE}: {name!r} is not a table; each endpoint is one, e.g. "
                f'`{name} = {{ provider = "openai", base_url = "https://HOST/v1", '
                'models = { MODEL = { id = "MODEL ID" } } }`',
            )
    out: dict[str, Named] = {}
    for where, tables in ((source, files), (_EXTRA_SOURCE, extra)):
        for name, table in tables.items():
            out[name] = _named(str(name), table, where, endpoint=True)
    return list(out.values())


def _named(name: str, table: Mapping[str, Any], source: str, *, endpoint: bool = False) -> Named:
    provider, model = table.get("provider"), table.get("id")
    return Named(
        name,
        provider if isinstance(provider, str) else "",
        model if isinstance(model, str) and not endpoint else "",
        dict(table),
        source,
        endpoint,
    )


def _article(provider: str) -> str:
    """The article before a provider's name in a message: 'an' before a vowel ('an openai endpoint'),
    else 'a' ('a claude-code endpoint'). The built-in names are lowercase, and a factory never reaches it."""
    return "an" if provider.startswith(("a", "e", "i", "o", "u")) else "a"


def problem(named: Named) -> str | None:
    """What is wrong with a model's or an endpoint's table, said so the person can fix it; None when
    nothing is. An endpoint's problem is its own or any of its models'."""
    kind = "endpoint" if named.endpoint else "model"
    where = f"{kind} {named.name!r} ({named.source})"
    if not named.provider:
        return (
            f'{where} names no provider; give it `provider = "{OPENAI}"` (an OpenAI-compatible '
            f'endpoint) or `provider = "{CLAUDE_CODE}"` (Claude through Claude Code)'
        )
    factory = named.provider not in _PROVIDERS
    if factory and ":" not in named.provider:
        known = " or ".join(map(repr, _PROVIDERS))
        return f"{where}: provider {named.provider!r} is not one bh-02 has; use {known}"
    if named.endpoint:
        return _endpoint_problem(named, where, factory=factory)
    if factory:
        return None  # a factory (`module:attribute`), whose tables are its own
    allowed = _ENDPOINT_KEYS[named.provider] - _LISTING | _MODEL_KEYS[named.provider]
    if unknown := sorted(set(named.table) - allowed):
        return (
            f"{where}: {', '.join(unknown)} is not a setting of {_article(named.provider)} "
            f"{named.provider} model"
        )
    if not named.id:
        return f'{where} names no model id; give it `id = "..."`, the provider\'s own name for the model'
    return _settings_problem(named, where)


def _endpoint_problem(named: Named, where: str, *, factory: bool) -> str | None:
    """What is wrong with an endpoint's table, or one of its models', or None."""
    table = named.table
    if "/" in named.name:
        return (
            f"{where}: an endpoint's name may not hold '/': its models are named ENDPOINT/MODEL, split "
            "at the first '/'. Rename the table"
        )
    if (why := _models_problem(named, where, factory=factory)) is not None:
        return why
    if factory:
        return None
    if unknown := sorted(set(table) - _ENDPOINT_KEYS[named.provider]):
        allowed = ", ".join(sorted(_ENDPOINT_KEYS[named.provider]))
        return (
            f"{where}: {', '.join(unknown)} is not a setting of {_article(named.provider)} "
            f"{named.provider} endpoint; it takes {allowed}"
        )
    if named.source == _EXTRA_SOURCE and (said := sorted({_DISCOVER, _KEY} & set(table))):
        return (
            f"{where}: {' and '.join(said)} is read only from the models file, never from a layer: it "
            "makes bh-02 trust the table (ask a server what it lists, send a key to a server, run a "
            f"command as you). Move this table to the models file, or remove {' and '.join(said)}"
        )
    if named.provider == OPENAI and (why := _discover_problem(named, where)) is not None:
        return why
    if not table.get(_MODELS) and table.get(_DISCOVER) is not True:
        how = " or `discover = true` to offer what its server lists" if named.provider == OPENAI else ""
        return f'{where} names no models; give it one, `[{named.name}.models.MODEL]` with `id = "..."`{how}'
    if (why := _settings_problem(named, where)) is not None:
        return why
    for model in _model_names(table):
        if (why := problem(derived(named, model, checked=False))) is not None:
            return why
    return None


def _models_problem(named: Named, where: str, *, factory: bool) -> str | None:
    """What is wrong with an endpoint's `models` as a table of models, or None."""
    models = named.table.get(_MODELS, {})
    if not isinstance(models, dict):
        return (
            f"{where}: models must be a table of models, one per name, like "
            f'`[{named.name}.models.MODEL]` with `id = "..."`'
        )
    for model, table in models.items():
        if not _MODEL_NAME.fullmatch(model):
            return (
                f"{where}: {model!r} can't name a model: a model's name is 1 to 200 printable ASCII "
                "characters, with no space and no '/'. Rename it"
            )
        if not isinstance(table, dict):
            return (
                f'{where}: models.{model} is not a table; give it one, `{model} = {{ id = "..." }}`, '
                f"or `[{named.name}.models.{model}]` with its id"
            )
        if factory:
            continue
        if unknown := sorted(set(table) - _MODEL_KEYS[named.provider]):
            allowed = ", ".join(sorted(_MODEL_KEYS[named.provider]))
            return (
                f"{where}: {', '.join(unknown)} is not a setting of {_article(named.provider)} "
                f"{named.provider} model ({named.name}/{model}); a model takes {allowed}, "
                "and its endpoint the rest"
            )
        if not isinstance(table.get("id"), str) or not table["id"]:
            return (
                f'{where}: model {model!r} names no id; give it `id = "..."`, the provider\'s own name '
                "for the model"
            )
    return None


def _model_names(table: Mapping[str, Any]) -> list[str]:
    """The names an endpoint's `models` gives, as written (empty when it has none or no table)."""
    models = table.get(_MODELS)
    return list(models) if isinstance(models, dict) else []


def named_models(host: Named) -> list[Named]:
    """The models an endpoint's `models` names, in the order written, each as `derived` makes it;
    none when it has a problem (`problem` says what)."""
    if problem(host) is not None:
        return []
    return [derived(host, model, checked=False) for model in _model_names(host.table)]


def _discover_problem(named: Named, where: str) -> str | None:
    """What is wrong with an openai endpoint's `discover` and `include`, or None."""
    table = named.table
    discover = table.get(_DISCOVER)
    if _DISCOVER in table and not isinstance(discover, bool):
        return f"{where}: discover must be true or false"
    if _INCLUDE in table and discover is not True:
        return (
            f"{where}: include narrows the models an endpoint's server lists; add `discover = true`, or "
            "remove include"
        )
    patterns = table.get(_INCLUDE)
    if _INCLUDE in table and not (
        isinstance(patterns, list)
        and patterns
        and all(isinstance(pattern, str) and pattern for pattern in patterns)
    ):
        return f'{where}: include must be a list of patterns, like `include = ["qwen*"]`'
    return None


def _settings_problem(named: Named, where: str) -> str | None:
    """What is wrong with how a model or endpoint is reached, and with its settings, or None."""
    table = named.table
    url = table.get("base_url")
    if named.provider == OPENAI and (not isinstance(url, str) or not url):
        return (
            f"{where} names no base_url; give it the endpoint's base, the part before "
            '/chat/completions (e.g. `base_url = "https://api.openai.com/v1"`, '
            '`"http://localhost:11434/v1"` for Ollama)'
        )
    if url is not None and (bad := _url_problem(url)) is not None:
        return f'{where}: base_url {url!r} {bad}; e.g. `base_url = "https://api.openai.com/v1"`'
    if (why := _key_problem(named, where)) is not None:
        return why
    tokens = table.get("max_tokens")
    if tokens is not None and not _whole(tokens):
        return f"{where}: max_tokens must be a whole number above 0"
    heat = table.get("temperature")
    if heat is not None and (not isinstance(heat, int | float) or isinstance(heat, bool)):
        return f"{where}: temperature must be a number"
    betas = table.get(_BETAS)
    if betas is not None and not isinstance(betas, bool):
        return f"{where}: experimental_betas must be true or false"
    return None


def _key_problem(named: Named, where: str) -> str | None:
    """What is wrong with how a model or endpoint gets its key (`key`: `_read_key`), or None. A
    claude-code one with a `base_url` (a gateway) needs a `key` of `cmd` or `op`, which the Claude
    Code CLI runs: bh-02 never holds that key, so an `env` is refused. One without runs on the
    subscription token its `key` gives (any source; bh-02 reads it when the CLI starts, so no `ttl_ms`)."""
    table = named.table
    key = table.get(_KEY)
    spec = None
    if _KEY in table:
        read = _read_key(key)
        if isinstance(read, str):
            return f"{where}: {read}"
        spec = read
    if named.provider != CLAUDE_CODE and (why := withheld(named)) is not None:
        return why
    if named.provider == CLAUDE_CODE:
        if spec is not None and spec.source == "env" and "base_url" in table:
            return (
                f"{where}: a gateway's key can't be an env: the Claude Code CLI gets it by running a "
                "command, and bh-02 never holds it. Give the command that prints it, "
                '`key = { cmd = "my-token-helper" }`, or `key = { op = "op://vault/item/field" }`'
            )
        if "base_url" in table and spec is None:
            return (
                f"{where}: a gateway needs both base_url (where Claude Code sends its requests) and "
                "key (the command that prints its key, Claude Code's apiKeyHelper), like "
                '`key = { cmd = "my-token-helper", ttl_ms = 300000 }`; give both, or neither, which '
                "uses the subscription token"
            )
        if "base_url" not in table and spec is not None and spec.ttl_ms is not None:
            return (
                f"{where}: key.ttl_ms is for a gateway's key, which Claude Code runs again when it is up; "
                "bh-02 reads the subscription token each time it starts the Claude Code CLI, so remove ttl_ms"
            )
        if _BETAS in table and "base_url" not in table:
            return f"{where}: experimental_betas is for a gateway; add base_url and key, or remove it"
    return None


def _read_key(key: object) -> KeySpec | str:
    """A `key` table as the `KeySpec` it says, or what is wrong with it (said after the table's
    `where`, and never quoting its values: a key written here as text may be the key itself)."""
    if not isinstance(key, Mapping):
        return (
            "key must be a table saying where the key comes from, never the key itself or a name; "
            f"write {_KEY_EXAMPLES}"
        )
    if unknown := sorted(set(key) - _KEY_FIELDS):
        return (
            f"key has {', '.join(map(str, unknown))}, which a key does not take; it takes exactly one of "
            f"env, cmd or op, and ttl_ms with cmd or op: {_KEY_EXAMPLES}"
        )
    given = [source for source in _SOURCES if source in key]
    if not given:
        return f"key names no source; give exactly one of env, cmd or op: {_KEY_EXAMPLES}"
    if len(given) > 1:
        return f"key gives {' and '.join(given)}; give exactly one of env, cmd or op: {_KEY_EXAMPLES}"
    source = given[0]
    value = key[source]
    ttl = key.get("ttl_ms")
    if not isinstance(value, str) or not value.strip():
        return f"key.{source} must be {_SOURCE_IS[source]}"
    if source == "env" and not _ENV_NAME.fullmatch(value):
        return f"key.env must be {_SOURCE_IS['env']}, not hold the key itself"
    if source == "op" and not value.startswith("op://"):
        return f"key.op must be {_SOURCE_IS['op']}"
    if "ttl_ms" in key and source == "env":
        return (
            "key.ttl_ms says how long a printed key is used; an env key is read from bh-02's "
            "environment on every request, so remove ttl_ms (or give cmd or op)"
        )
    if "ttl_ms" in key and not _whole(ttl):
        return "key.ttl_ms must be a whole number of milliseconds above 0"
    return KeySpec(source, value, ttl if isinstance(ttl, int) else None)


_SOURCE_IS: Final[Mapping[str, str]] = {
    "env": 'the name of an environment variable (capitals, digits and _, like `env = "OPENAI_API_KEY"`)',
    "cmd": 'a command that prints a key, like `cmd = "my-token-helper"`',
    "op": 'a 1Password reference starting op://, like `op = "op://vault/item/field"`',
}


def key_spec(key: object) -> KeySpec | None:
    """The `KeySpec` a `key` table says; None when there is no key or it is not a valid one
    (`problem` says what is wrong first, so a provider only sees a valid one)."""
    read = _read_key(key) if key is not None else None
    return read if isinstance(read, KeySpec) else None


def _whole(value: object) -> bool:
    """Whether `value` is a whole number above 0 (a TOML `true` is no number)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _url_problem(url: object) -> str | None:
    """What is wrong with a base_url as a URL (said after it), or None."""
    if not isinstance(url, str):
        return "is not text"
    try:
        parts = urlsplit(url)
        _ = parts.port  # reading it checks it: a port not a number, or out of range, is a ValueError
    except ValueError as error:
        return f"is not a URL ({error})"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "is not an http(s) URL with a host"
    return None


def withheld(named: Named) -> str | None:
    """Why `named`'s key is never sent: it reads the Claude Code token, which bh-02 hands to the
    Claude Code CLI alone, never to an endpoint; None when it reads another variable, or none."""
    spec = key_spec(named.table.get(_KEY))
    if spec is None or spec.source != "env" or spec.value != TOKEN_VARIABLE:
        return None
    return (
        f"{named.name!r} ({named.source}): key may not read {TOKEN_VARIABLE}, the Claude Code "
        "token: bh-02 gives it to the Claude Code CLI alone and never sends it to an endpoint "
        "(whoever holds it can use your subscription). Name the variable of this endpoint's "
        'own key (`key = { env = "ITS_API_KEY" }`), or use a claude-code endpoint for Claude'
    )


def derived(host: Named, model: str, *, checked: bool = True) -> Named:
    """The model `ENDPOINT/MODEL` means: the endpoint's table (its provider, how it is reached, the
    settings its models share) with the model's own over it: the table its `models` gives `model`,
    else `model` as the provider's id (an id the endpoint's `models` doesn't name). Nothing is asked
    of the server: an id it lacks is the first step's error. With `checked`, a table with a problem
    (`problem`) means no model: `host` itself comes back, which `not_a_model` refuses with that
    problem, so the person is told which table to fix and what to write."""
    if checked and problem(host) is not None:
        return host
    shared = {k: v for k, v in host.table.items() if k not in _LISTING}
    models = host.table.get(_MODELS)
    own = models.get(model) if isinstance(models, dict) else None
    table = {**shared, **own} if isinstance(own, dict) else {**shared, "id": model}
    model_id = table.get("id")
    return Named(
        f"{host.name}/{model}",
        host.provider,
        model_id if isinstance(model_id, str) else "",
        table,
        host.source,
    )


def find(name: object, models: Sequence[Named]) -> Named | None:
    """What `name` means, or None: the endpoint of that name, else
    `ENDPOINT/MODEL` (`derived`: the endpoint's own table when that has a problem), split at the
    first `/` so an id may hold more of them, and `:`. Pure: no server is asked."""
    if not isinstance(name, str):
        return None
    exact = next((named for named in models if named.name == name), None)
    if exact is not None:
        return exact
    host_name, slash, model = name.partition("/")
    if not slash or not model:
        return None
    host = next((named for named in models if named.name == host_name and named.endpoint), None)
    return None if host is None else derived(host, model)


def not_a_model(found: Named) -> str | None:
    """Why `found` can't be the model row's model, said so the person can fix it: its table has a
    problem (`problem`: an endpoint's too, which resolves no model of it), or it is an endpoint,
    which serves models and is none; None when it can be."""
    if (why := problem(found)) is not None:
        return why
    if found.endpoint:
        names = ", ".join(named.name for named in named_models(found))
        return (
            f"{found.name!r} ({found.source}) is an endpoint, which serves models and is none itself; "
            f"name one of them, {found.name}/MODEL" + (f" ({names})" if names else ": /model lists them")
        )
    return None


def said_names(models: Sequence[Named]) -> str:
    """The models there are, for a message: each model an endpoint names, then, when there are
    endpoints, that a name may be `ENDPOINT/ID` for one; `none` when there are none."""
    names = [model.name for named in models if named.endpoint for model in named_models(named)]
    hosts = ", ".join(named.name for named in models if named.endpoint)
    listed = ", ".join(names) or "none"
    return listed + (f"; or ENDPOINT/ID, an id on an endpoint ({hosts})" if hosts else "")


def chosen(
    name: object,
    models: Sequence[Named],
    source: str,
    refused: str | None = None,
    origin: str = _LAYER_SOURCE,
) -> Named:
    """The model `name` means. `origin`: where `name` was written (`Intended.origin`), said when it
    is the models file's `default`.

    Raises:
        ModelsError: `name` is no name, no model has it (the models there are, and where to add one,
            or why the models file is not read: `refused`, which `in_project` says), or its table has
            a problem.
    """
    from_file = origin == _FILE_SOURCE
    if name is None and origin == _UNCHOSEN:
        add = refused or f"add an endpoint and a `default` to the models file {source}, e.g.\n{_DEFAULTED}"
        raise ModelsError(
            "unknown_model",
            "no model is chosen: neither --model, /model nor the models file's `default` names one; the "
            f"models are {said_names(models)}. /model NAME switches to one; {add}",
        )
    if not isinstance(name, str) or not name:
        who = f"the default in the models file {source}" if from_file else "the model row's default"
        raise ModelsError(
            "models_file" if from_file else "model_config",
            f"{who} is {name!r}, not a model's name; give it one, like "
            '`default = "local/llama"`, or remove it',
        )
    found = find(name, models)
    if found is None:
        names = said_names(models)
        add = refused or (f"to add a model, give it an endpoint in the models file {source}:\n{_EXAMPLE}")
        which = f", the default in the models file {source}" if from_file else ""
        raise ModelsError(
            "unknown_model",
            f"no model named {name!r}{which}; the models are {names}. /model NAME switches to one; {add}",
        )
    if (why := not_a_model(found)) is not None:
        raise ModelsError("model_config", why)
    return found
