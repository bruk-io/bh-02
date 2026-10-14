"""A composition as values: rows, layers, and the plan that turns one into another.

A composition is a list of rows. Each row names a component (`use`), carries its config,
and can be disabled. Layers apply in order to an empty list: a row whose id is new inserts,
a row whose id exists replaces that row's `config`, `use` or `disabled`. That is how a
shipped composition stays replaceable without a fork.

    [[plugin]]
    id = "llm"
    use = "my_app.llm:claude_backend"     # module:attribute, or plugin:component by entry point
    config = { model = "sonnet" }

This module imports nothing from cordis and touches nothing: parsing, composing and
planning are functions from values to values. `cordis.loader` reads the files, resolves the
names and mounts the rows.
"""

import json
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class Row:
    """One line of a layer. In a patch layer, a field left out keeps the value below it."""

    id: str
    use: str | None = None
    config: Mapping[str, Any] | None = None
    disabled: bool | None = None


@dataclass(frozen=True, slots=True)
class Entry:
    """A composed row: what the loader mounts."""

    id: str
    use: str
    config: Mapping[str, Any] = field(default_factory=dict)
    disabled: bool = False


def compose(layers: Iterable[Iterable[Row]]) -> list[Entry]:
    """Apply layers in order to an empty list. Insertion order is kept; it carries no meaning."""
    rows: dict[str, Entry] = {}
    for layer in layers:
        for row in layer:
            existing = rows.get(row.id)
            if existing is None:
                if row.use is None:
                    raise ValueError(
                        f"row {row.id!r} inserts a new plugin but gives no `use`; a patch row can "
                        f"only change a row some layer below it already added"
                    )
                rows[row.id] = Entry(row.id, row.use, dict(row.config or {}), bool(row.disabled))
                continue
            rows[row.id] = Entry(
                row.id,
                row.use if row.use is not None else existing.use,
                dict(row.config) if row.config is not None else existing.config,
                row.disabled if row.disabled is not None else existing.disabled,
            )
    return list(rows.values())


def parse_layer(text: str, source: str = "<layer>") -> list[Row]:
    """A layer's text: `[[plugin]]` tables with id, use, config, disabled. `source` names it in errors."""
    data = tomllib.loads(text)
    plugins = data.get("plugin", [])
    if not isinstance(plugins, list) or not all(isinstance(raw, dict) for raw in plugins):
        raise ValueError(
            f"{source}: 'plugin' is {_toml_kind(plugins)}; write each row as a [[plugin]] "
            f"table (double brackets), one per row"
        )
    rows = []
    for raw in plugins:
        if unknown := set(raw) - {"id", "use", "config", "disabled"}:
            raise ValueError(
                f"{source}: row {raw.get('id', '?')!r} has unknown fields {sorted(unknown)}; "
                f"a row is id, use, config, disabled"
            )
        _check_row(raw, source)
        rows.append(Row(raw["id"], raw.get("use"), raw.get("config"), raw.get("disabled")))
    return rows


# A row's fields, the TOML each must be, and how to write one.
_FIELDS: dict[str, tuple[type, str]] = {
    "id": (str, 'a string: id = "llm"'),
    "use": (str, 'a string: use = "plugin:component" or "module:attribute"'),
    "config": (dict, 'a table: config = { model = "sonnet" }'),
    "disabled": (bool, "true or false: disabled = true"),
}


def _check_row(raw: Mapping[str, Any], source: str) -> None:
    """Refuse a row with no id, or whose fields are not the TOML they must be, saying what to write."""
    if "id" not in raw:
        use = f" (use = {json.dumps(raw['use'])})" if isinstance(raw.get("use"), str) else ""
        raise ValueError(f"{source}: a [[plugin]] row{use} has no 'id'; add id = \"...\" naming it")
    for name, (kind, how) in _FIELDS.items():
        if name in raw and not isinstance(raw[name], kind):
            row = raw["id"] if isinstance(raw.get("id"), str) else "?"
            raise ValueError(f"{source}: row {row!r}: {name!r} is {_toml_kind(raw[name])}; it must be {how}")


def _toml_kind(value: object) -> str:
    """What a TOML value is, in TOML's words: `[plugin]` reads as one table, not an array of them."""
    match value:
        case bool():
            return f"a boolean ({str(value).lower()})"
        case int() | float():
            return f"a number ({value!r})"
        case str():
            return f"a string ({json.dumps(value)})"
        case dict():
            return "one table ([plugin], single brackets)" if value else "an empty table"
        case list():
            return "an array of values (plugin = [...])"
    return type(value).__name__


def format_layer(rows: Iterable[Row], header: str = "") -> str:
    """The text of a layer holding `rows`: `parse_layer`'s inverse, for a program that writes
    the layer files it runs from (a session's own layer, a `/model` command). `header` is a
    comment block put first; comments already in a file are not kept.

    Every string (an id, a `use`, a config key or value, however nested) is written as a TOML
    basic string of printable ASCII: a quote, a backslash and a control character get their
    backslash escape, and any other character outside printable ASCII is a `\\uXXXX` escape
    (`\\UXXXXXXXX` above U+FFFF, which is one escape, not the surrogate pair JSON would write
    and TOML refuses). So the text reads back as the same strings whatever encoding the file is
    written with.

    Raises:
        TypeError: A config value is not a string, number, bool, mapping, list or tuple.
        ValueError: A string holds a lone surrogate (half of a character, which is what bytes
            that are not UTF-8 decode to): no TOML string can, so it is refused here, not
            written as a layer `parse_layer` can't read.
    """
    parts = [f"# {line}".rstrip() for line in header.splitlines()]
    for row in rows:
        lines = ["[[plugin]]", f"id = {_toml(row.id)}"]
        if row.use is not None:
            lines.append(f"use = {_toml(row.use)}")
        if row.config is not None:
            lines.append(f"config = {_toml(row.config)}")
        if row.disabled is not None:
            lines.append(f"disabled = {_toml(row.disabled)}")
        parts.append("\n" + "\n".join(lines))
    return "\n".join(parts).lstrip("\n") + "\n"


def _toml(value: object) -> str:
    """One TOML value, inline: what a row's fields and config hold."""
    match value:
        case bool():
            return "true" if value else "false"
        case int() | float():
            return repr(value)
        case str():
            return _toml_string(value)
        case Mapping():
            return "{ " + ", ".join(f"{_toml_string(str(k))} = {_toml(v)}" for k, v in value.items()) + " }"
        case list() | tuple():
            return "[" + ", ".join(_toml(v) for v in value) + "]"
    raise TypeError(f"a layer can't hold a {type(value).__name__}: {value!r}")


# The characters a TOML basic string spells with a short escape; every other one of printable
# ASCII (space to `~`) is written as it is.
_SHORT_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _toml_string(text: str) -> str:
    """`text` as a TOML basic string, in printable ASCII only (see `format_layer`).

    JSON's own string would not do: it writes a character above U+FFFF as a surrogate pair, which
    TOML refuses in an escape (it takes Unicode scalar values only).

    Raises:
        ValueError: `text` holds a lone surrogate, which no TOML string can.
    """
    if (half := next((c for c in text if "\ud800" <= c <= "\udfff"), None)) is not None:
        raise ValueError(
            f"a layer can't hold {text!r}: {half!r} is half of a character (a surrogate), which no TOML "
            f"string can hold; bytes that are not UTF-8 decode to one, so write it in UTF-8"
        )
    return '"' + "".join(map(_written, text)) + '"'


def _written(char: str) -> str:
    """One character of a TOML basic string: itself when it is printable ASCII, else an escape."""
    if char in _SHORT_ESCAPES:
        return _SHORT_ESCAPES[char]
    if " " <= char <= "~":
        return char
    code = ord(char)
    return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"


@dataclass(frozen=True, slots=True)
class Unmount:
    """A step of a plan: retire the row `id`, because it was removed or is about to be replaced."""

    id: str
    reason: Literal["removed", "changed"]


@dataclass(frozen=True, slots=True)
class Mount:
    """A step of a plan: mount `entry`, which is new or replaces a row unmounted just before."""

    entry: Entry


type Plan = tuple[Unmount | Mount, ...]


def plan(current: Mapping[str, Entry], desired: Iterable[Entry]) -> Plan:
    """What turns the rows mounted now into the rows wanted, in the order it must happen.

    A row whose entry is unchanged is not in the plan. Every unmount precedes every mount:
    a replacement binds the same keys as the row it replaces, and `bind` refuses a key
    another fiber still holds, so nothing may be mounted while any outgoing row (removed,
    or changed, or one whose key moved to a different id) is still up.
    """
    wanted = {e.id: e for e in desired}
    unmounts: list[Unmount | Mount] = [Unmount(rid, "removed") for rid in current if rid not in wanted]
    mounts: list[Unmount | Mount] = []
    for rid, entry in wanted.items():
        if rid in current and current[rid] == entry:
            continue
        if rid in current:
            unmounts.append(Unmount(rid, "changed"))
        mounts.append(Mount(entry))
    return (*unmounts, *mounts)
