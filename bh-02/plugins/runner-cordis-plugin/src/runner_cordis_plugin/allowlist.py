"""The jail's environment allow-list, as the person keeps it (decision-0010): the file
`~/.config/bh-02/runner.toml` (`$XDG_CONFIG_HOME/bh-02/runner.toml`), `env = ["NAME", ...]`, the
variables the jail lets through on top of its baseline (`BASELINE_ENV`).

Read the way the models file is, through `host_paths.passes`: a file in the project, or reached
through a link into it, is one the model's code could have written, so it is not read and the
person is told where to put it. The direction of failure is the narrow one: a file not read leaves
the baseline, never a wider list. A file that can't be read or is not what is described here is
refused (`Refused`), and the jail does not start on it: a typo must not quietly widen or drop the
list.

A layer's runner `config` that sets `env` replaces the file's list; one that omits it takes the
file's (`effective`). Either way, a name that an endpoint's `key = { env = ... }` reads is refused
(`effective`): the jail would hand that key to the model's code. The comparison is the runner's
because it is where both values are visible (the layer's config, and the `host` value, which carries
what the models file's keys read); the models plugin is not imported.
"""

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from host_paths import config_home, passes, roots
from runner_cordis_plugin.jail import BASELINE_ENV, BrigConfig

__all__ = ["FILE", "Refused", "Standing", "effective", "location", "parsed", "read"]

FILE = "runner.toml"
_KEYS = ("env",)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXAMPLE = 'env = ["GITHUB_TOKEN", "AWS_PROFILE"]'


class Refused(ValueError):
    """The allow-list can't be used as it is; the message says what to fix. The jail does not
    start on it."""


@dataclass(frozen=True, slots=True)
class Standing:
    """What the person's file contributes: `names`, the variables it adds to the baseline, and
    `unread`, why it was not read (it is in the project: where to put it instead), else empty."""

    names: tuple[str, ...] = ()
    unread: str = ""


def location(environ: Mapping[str, str], home: Path) -> Path:
    """`$XDG_CONFIG_HOME/bh-02/runner.toml`, else `~/.config/bh-02/runner.toml`
    (`host_paths.config_home`: a relative value counts as unset)."""
    return config_home(environ, home) / "bh-02" / FILE


def parsed(text: str, source: str) -> tuple[str, ...]:
    """The names `text` (the file at `source`) lists, each once, in order.

    Raises:
        Refused: it is not TOML, takes a key other than `env`, or its `env` is not a list of
            variable names.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise Refused(f"{source} is not TOML ({error}); fix it, e.g. `{_EXAMPLE}`, or remove it") from None
    if unknown := sorted(set(data) - set(_KEYS)):
        raise Refused(
            f"{source} has {', '.join(map(repr, unknown))}, which it does not take; it takes "
            f"{', '.join(map(repr, _KEYS))} alone (`{_EXAMPLE}`). Remove the rest"
        )
    names = data.get("env", [])
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise Refused(f"{source}: env must be a list of variable names, e.g. `{_EXAMPLE}`")
    if bad := [name for name in names if not _NAME.fullmatch(name)]:
        raise Refused(
            f"{source}: env names {', '.join(map(repr, bad))}, which are not variable names "
            "(letters, digits and _, not starting with a digit); write the name, never the value"
        )
    return tuple(dict.fromkeys(names))


def read(path: Path, project: Path) -> Standing:
    """What the file at `path` contributes: nothing when there is none, and nothing, with why, when
    reading it passes through `project` (`host_paths.passes`: where the model's code can write).

    Raises:
        Refused: it is there and can't be read, or `parsed` refuses it.
    """
    inside = passes(path, roots(project))
    if inside:
        return Standing(unread=_unread(path, project))
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Standing()
    except OSError as error:
        raise Refused(f"can't read {path} ({error.strerror}); fix it or remove it") from None
    except UnicodeDecodeError:
        raise Refused(f"{path} is not UTF-8 text; fix it or remove it") from None
    return Standing(parsed(text, str(path)))


def _unread(path: Path, project: Path) -> str:
    return (
        f"{path} is not read: it is in the project ({project}) or reached through a link into it, "
        "and the model's code can write there, so it could choose which variables it sees. "
        "The jail passes its baseline only. Keep it outside the project, and not a link into it: "
        "run bh-02 in the project's own directory rather than one that holds your config (such as "
        "your home), or set XDG_CONFIG_HOME to a directory outside it"
    )


def effective(
    config: BrigConfig,
    standing: Standing,
    *,
    file: Path,
    readers: Mapping[str, Sequence[str]],
    models_file: str,
) -> tuple[BrigConfig, str]:
    """The config the jail runs on and a line for the person: the layer's `env` when it sets one
    (it replaces the file's, and the line says so when the file had names), else the baseline
    and the file's names. `readers` is what the models file's keys read, variable to endpoints
    (the `host` value), in `models_file`.

    Raises:
        Refused: a variable in the list that an endpoint's `key = { env = ... }` reads, naming the
            variable, the endpoint and both files.
    """
    note = standing.unread
    if config.env is not None:
        env, where = tuple(config.env), "the `env` of the runner row's config in a layer"
        if standing.names:
            note = (
                f"the layer's runner `env` replaced the list in {file} ({len(standing.names)} names): "
                "only the layer's is passed to the jail"
            )
    else:
        env, where = (*BASELINE_ENV, *standing.names), str(file)
    for name in env:
        if endpoints := readers.get(name):
            raise Refused(
                f"{name} is in {where} and endpoint {', '.join(map(repr, endpoints))} reads it as its "
                f"key (`key = {{ env = {name!r} }}` in {models_file}), which would hand that key to the "
                f"model's code. Remove {name} from {'the layer' if config.env is not None else str(file)}, "
                f"or change the key in {models_file}"
            )
    return replace(config, env=tuple(dict.fromkeys(env))), note
