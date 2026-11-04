"""The compressor's knobs, in one place, so an eval can turn them over the same tasks.

The defaults are the values the findings were measured with. A knob is set in a TOML file
(`--config knobs.toml`), one at a time (`--set schema.rare=0.15`), or both (the sets win):

    worth_it = 0.9

    [schema]
    rare = 0.15

    [tree]
    max_promoted = 5

    [json_envelope]               # a part of the JSON envelope other than the view's
    samples = "typical"

    [log_envelope]                # and of a log's
    nav = "sed"

The fold's budget and view are not knobs here: each call names them. `label` names a config by
what it changes from the defaults, for reports; `sets` turns one back into `--set` arguments.
"""

import tomllib
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

from compressors.envelope import priority


@dataclass(frozen=True)
class SchemaKnobs:
    """How JSON's shape and its exceptions are worked out (`compressors.schema`)."""

    dominant: float = 0.75  # a value held by this share of rows makes the rows without it exceptions,
    rare: float = 0.1  # when the value they hold instead is at most this share
    key_rare: float = 0.1  # a key in at most this share of rows marks the rows that have it,
    key_common: float = 0.9  # and one in at least this share (but not all) the rows that lack it
    iqr_factor: float = 3.0  # a number beyond this many interquartile ranges of the middle half is an outlier
    min_rows: int = 5  # fewer rows than this and a list is shown as values, not as a schema
    map_min_keys: int = 20  # an object with this many keys of one shape is a collection keyed by them
    values: int = (
        8  # values shown for a field with few of them (the roomiest level; tighter levels show fewer)
    )
    fields: int = 40  # fields shown per collection, keys per plain object
    rows: int = 25  # exception rows shown per collection
    clip: int = 60  # characters of a value shown


@dataclass(frozen=True)
class TreeKnobs:
    """The tree fold of code, XML and outlines (`compressors.tree`)."""

    max_promoted: int = 10  # stand-outs shown per list; the rest are counted in the marker that hides them
    head_children: int = 3  # a list opened partly shows at least its first this many children,
    tail_children: int = 1  # and its last this many
    min_gap: int = 6  # a run of this many plain lines no node covers folds as a leaf of its own
    min_hidden: int = 3  # a node hiding fewer lines than this is shown whole
    max_line_chars: int = 300  # a longer line is clipped
    rare_share: float = 0.1  # a sibling shape held by at most this share of a list stands out,
    dominant: float = 0.6  # when one shape holds at least this share


@dataclass(frozen=True)
class JsonEnvelopeKnobs:
    """Which producer makes each part of a JSON envelope (`compressors.envelope_json`), and the order
    the parts claim the budget in. "" leaves a part to the view's recipe (sample or schema)."""

    shape: str = (
        ""  # fields: every field with its values, counts and ranges; summary: types, few-valued counts
    )
    anomalies: str = ""  # exceptions: every row that breaks the shape; standouts: the stand-out rules; none
    samples: str = ""  # matches: rows holding the query; typical: and one ordinary row; head-tail; none
    nav: str = ""  # jq: a ready query for the broken rows; rows: how to fetch any row; none
    priority: str = "shape,anomalies,nav,samples"


@dataclass(frozen=True)
class LogEnvelopeKnobs:
    """The envelope of a log, or any output read line by line (`compressors.envelope_log`): which
    producer makes each part ("" leaves it to the view's recipe), the order the parts claim the
    budget in, and how its statistics are worked out over line templates."""

    shape: str = ""  # templates: each line template and its count, few-valued holes too; count: totals
    anomalies: str = ""  # rare: rare templates, error words, rare values in a hole; errors: error words; none
    samples: str = ""  # matches: lines with the query; typical: and common templates' first; head-tail; none
    nav: str = ""  # grep: a command per anomaly printing exactly its lines; sed: how to read any lines; none
    priority: str = "shape,anomalies,nav,samples"
    rare: float = 0.01  # a template on at most this share of the lines is rare,
    common: float = 0.5  # when the templates that are not rare cover at least this share
    errors: float = 0.1  # a template holding an error word is an anomaly on at most this share of the lines
    few: int = 6  # a hole holding at most this many values is a field, and its counts are shown
    dominant: float = 0.8  # when one of them is on this share of its template's lines, the lines
    value_rare: float = 0.02  # holding a value on at most this share of them are anomalies
    clip: int = 300  # characters of a line shown, at the roomiest level


@dataclass(frozen=True)
class FoldConfig:
    worth_it: float = 0.9  # a fold that keeps more than this share of the input passes it through instead
    schema: SchemaKnobs = SchemaKnobs()
    tree: TreeKnobs = TreeKnobs()
    json_envelope: JsonEnvelopeKnobs = JsonEnvelopeKnobs()
    log_envelope: LogEnvelopeKnobs = LogEnvelopeKnobs()


DEFAULT = FoldConfig()
_SECTIONS = {
    "schema": SchemaKnobs,
    "tree": TreeKnobs,
    "json_envelope": JsonEnvelopeKnobs,
    "log_envelope": LogEnvelopeKnobs,
}
# The knobs that name a producer: the names each takes (each format's `compressors.envelope_*` holds
# its producers). "" is the view's.
CHOICES = {
    "json_envelope.shape": ("", "fields", "summary"),
    "json_envelope.anomalies": ("", "exceptions", "standouts", "none"),
    "json_envelope.samples": ("", "matches", "typical", "head-tail", "none"),
    "json_envelope.nav": ("", "jq", "rows", "none"),
    "log_envelope.shape": ("", "templates", "count"),
    "log_envelope.anomalies": ("", "rare", "errors", "none"),
    "log_envelope.samples": ("", "matches", "typical", "head-tail", "none"),
    "log_envelope.nav": ("", "grep", "sed", "none"),
}


def _knob_names() -> list[str]:
    top = [f.name for f in fields(FoldConfig) if f.name not in _SECTIONS]
    return top + [f"{s}.{f.name}" for s, cls in _SECTIONS.items() for f in fields(cls)]


def _typed(name: str, default: Any, value: Any) -> Any:
    """`value` as the type of the knob's default.

    Raises:
        ValueError: it is not a value of that type.
    """
    kind = type(default)
    if name in CHOICES and value not in CHOICES[name]:
        names = ", ".join(c or '"" (the view\'s)' for c in CHOICES[name])
        raise ValueError(f"{name} is one of {names}; not {value!r}")
    if name.endswith("_envelope.priority"):
        priority(str(value))  # names each part once, or raises
    if isinstance(value, str):
        try:
            value = kind(value)
        except ValueError:
            raise ValueError(f"{name} takes a {kind.__name__}, not {value!r}") from None
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if type(value) is not kind:
        raise ValueError(f"{name} takes a {kind.__name__}, not {value!r}")
    return value


def with_values(config: FoldConfig, values: dict[str, Any]) -> FoldConfig:
    """`config` with knobs set by dotted name (`"schema.rare": 0.15`).

    Raises:
        ValueError: a name is no knob, or a value is not of the knob's type.
    """
    top: dict[str, Any] = {}
    sections: dict[str, dict[str, Any]] = {}
    for name, value in values.items():
        section, _, key = name.rpartition(".")
        if name not in _knob_names():
            raise ValueError(f"no knob {name!r}; the knobs are: {', '.join(_knob_names())}")
        if section:
            default = getattr(getattr(DEFAULT, section), key)
            sections.setdefault(section, {})[key] = _typed(name, default, value)
        else:
            top[key] = _typed(name, getattr(DEFAULT, key), value)
    for section, changes in sections.items():
        top[section] = replace(getattr(config, section), **changes)
    return replace(config, **top)


def with_sets(config: FoldConfig, sets: list[str]) -> FoldConfig:
    """`config` with `--set` arguments applied (`schema.rare=0.15`).

    Raises:
        ValueError: a set is not NAME=VALUE, names no knob, or its value is of the wrong type.
    """
    values = {}
    for s in sets:
        name, eq, value = s.partition("=")
        if not eq:
            raise ValueError(f"--set takes NAME=VALUE, such as schema.rare=0.15; not {s!r}")
        values[name.strip()] = value.strip()
    return with_values(config, values)


def load(path: str | Path) -> FoldConfig:
    """The config a TOML file sets (the defaults for every knob it leaves out). A file that cannot be
    read raises OSError, from reading it.

    Raises:
        ValueError: it is not TOML, or it sets something that is no knob or a value of the wrong type.
    """
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path}: not TOML: {e}") from None
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            flat |= {f"{key}.{k}": v for k, v in value.items()}
        else:
            flat[key] = value
    return with_values(DEFAULT, flat)


def changes(config: FoldConfig) -> dict[str, Any]:
    """The knobs `config` sets differently from the defaults, by dotted name."""
    now, default = asdict(config), asdict(DEFAULT)
    out = {k: v for k, v in now.items() if k not in _SECTIONS and v != default[k]}
    for section in _SECTIONS:
        out |= {f"{section}.{k}": v for k, v in now[section].items() if v != default[section][k]}
    return out


def label(config: FoldConfig) -> str:
    """A config's name in a report: what it changes, or "defaults"."""
    return ", ".join(f"{k}={v}" for k, v in changes(config).items()) or "defaults"


def sets(config: FoldConfig) -> list[str]:
    """The `--set` arguments that make `config` from the defaults."""
    return [f"{k}={v}" for k, v in changes(config).items()]
