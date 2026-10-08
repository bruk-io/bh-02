"""Named models: which model a name means, on which provider, with what settings.

Three places name models, each over the last: the built-ins (`sonnet`, `opus`, `haiku`,
Claude through Claude Code), the models file (`$XDG_CONFIG_HOME/bh-02/models.toml`, else
`~/.config/bh-02/models.toml`, or the row's `models`), and the row's own `extra` (a table
like the file's, which a migrated layer writes). A later place wins: an `extra` model over
the file's of the same name, and a user's model over a built-in (allowed, and noted as
shadowing it). The file is one table per model:

    [llama]
    provider = "openai"                        # or "claude-code"
    id = "llama3.2"                            # the provider's own name for the model
    base_url = "http://localhost:11434/v1"     # openai only: where /chat/completions is
    key = "OPENROUTER_API_KEY"                 # openai only, optional: a line of local.env
    max_tokens = 4096                          # optional
    temperature = 0.2                          # optional

A provider can also be `module:attribute`, a factory the model's table is passed to (bh-02's
fakes are one); its table is its own.

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

from cordis_helpers import config_home, walked
from models_cordis_plugin.claude_code.credential import TOKEN_VARIABLE

__all__ = [
    "BUILT_IN",
    "CLAUDE_CODE",
    "OPENAI",
    "ModelConfig",
    "ModelsError",
    "Named",
    "combined",
    "chosen",
    "environ",
    "in_project",
    "key_name",
    "models_file",
    "parsed",
    "problem",
    "read_models",
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
_BUILT_IN_SOURCE: Final = "built in"
_EXTRA_SOURCE: Final = "the model row's extra"
# The keys a model's table may have, per provider (a factory's table is its own).
_KEYS: Final[Mapping[str, frozenset[str]]] = {
    CLAUDE_CODE: frozenset({"provider", "id"}),
    OPENAI: frozenset({"provider", "id", "base_url", "key", "max_tokens", "temperature"}),
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
    """The `model` row's config. `default`: the model's name (`/model` and `--model` set it).
    `models`: the models file, when not the default one. `extra`: models of the row's own, one
    table per name, as in the file. For the claude-code provider: `state`, the directory its
    Claude Code state lives in (the session's `claude/`, which the session layer sets);
    `env_file`, where `local.env` is (found above the install when unset; the openai provider
    reads a model's `key` there too); `cwd`, the project Claude Code is told it works in (the
    working directory when unset), which, like the working directory, a models file must be
    outside of (`in_project`)."""

    default: str = "sonnet"
    models: str | None = None
    extra: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    state: str | None = None
    env_file: str | None = None
    cwd: str | None = None


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
    else `~/.config/bh-02/models.toml`."""
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
    `cordis_helpers.walked`, as the context files and the kernel's startup files are walked), it is
    under the root as named or as resolved; a link the model could repoint, or a directory it could
    swap for one, would choose what is read. None when it is outside. Whether the file is there
    does not matter: the model could write one."""
    named = Path(os.path.normpath(path.absolute()))
    roots = (Path(os.path.normpath(root.absolute())), root.resolve())
    inside = [p for p in (named, *walked(path.absolute())) if any(p.is_relative_to(r) for r in roots)]
    if not inside:
        return None
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


def parsed(text: str | None, source: str) -> dict[str, Mapping[str, Any]]:
    """The models file's tables, by name: `{}` for no file. A file that is not TOML, or holds
    something other than one table per model, is a `ModelsError` naming it."""
    if text is None:
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ModelsError("models_file", f"the models file {source} is not TOML ({error}); fix it") from None
    for name, table in data.items():
        if not isinstance(table, dict):
            raise ModelsError(
                "models_file",
                f"the models file {source}: {name!r} is not a table; each model is one, e.g.\n{_EXAMPLE}",
            )
    return data


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
    if not named.id:
        return f'{where} names no model id; give it `id = "..."`, the provider\'s own name for the model'
    if named.provider == OPENAI:
        return _openai_problem(named, where)
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


def chosen(name: object, models: Sequence[Named], source: str, refused: str | None = None) -> Named:
    """The model `name` means, or a `ModelsError` saying what to do: no such name (the models
    there are, and where to add one, or why the models file is not read: `refused`, which
    `in_project` says), or a table with a problem."""
    if not isinstance(name, str) or not name:
        raise ModelsError(
            "model_config",
            f"the model row's default is {name!r}, not a model's name; give it one, like "
            '`default = "sonnet"`, or remove it',
        )
    found = next((named for named in models if named.name == name), None)
    if found is None:
        names = ", ".join(named.name for named in models)
        add = refused or (
            f"to add {name!r}, give it a table in the models file {source}:\n{_EXAMPLE.replace('NAME', name)}"
        )
        raise ModelsError(
            "unknown_model",
            f"no model named {name!r}; the models are {names}. /model NAME switches to one; {add}",
        )
    if (why := problem(found)) is not None:
        raise ModelsError("model_config", why)
    return found
