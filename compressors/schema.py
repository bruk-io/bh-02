"""A schema view of JSON: the data's shape, the rows that break it, and a query, instead of samples.

    .items: array[500] of object
      .name      str, unique, like web-<hex>
      .phase     "Running" 488, "CrashLoopBackOff" 12
      .restarts  int 0..97, median 1
      exceptions in 13 rows:
        .items[312] web-a9da82d697: .restarts 97 (outlier)
        .items[7] web-0c41d2e6b0: .phase "CrashLoopBackOff", .ready false
    query: jq '.items[] | select(.phase != "Running") | .name' FILE

A collection is an array of objects (or of values), or an object with many keys whose values share
one shape (PyPI's releases by version); its rows are merged into one list of fields, each a jq path
relative to the row, and an array of objects inside the rows is a collection of its own (`.items[]
.containers[]`). Every count, range and exception is computed over all rows, never sampled. A row
is an exception when it holds a value few rows hold where one value dominates, a number far outside
the rest, a key few rows have (or lacks one nearly all have), or a value of another type. Paths are
jq paths into the input; FILE in the query stands for it. The view's size depends on the structure,
not on the number of rows; when it does not fit the budget, fewer values, fields and exception rows
are shown, and each cut says what it left out.
"""

import json
import re
import statistics
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from compressors import markers
from compressors.common import discriminating, estimate_tokens, matches

_MIN_ROWS = 5  # fewer rows than this and a list is shown as values, not as a schema
_MAP_MIN_KEYS = 20  # an object with this many keys of one shape is a collection keyed by its keys
_DOMINANT = 0.75  # a value held by this share of rows makes the rows without it exceptions,
_RARE = 0.1  # when the value they hold instead is at most this share
_KEY_RARE = 0.1  # a key in at most this share of rows marks the rows that have it,
_KEY_COMMON = 0.9  # and one in at least this share (but not all) the rows that lack it
_IQR_FACTOR = 3.0
_IDENT_NAMES = ("name", "id", "uid", "key", "ref", "title", "slug", "filename", "sha", "version")
_HEX = re.compile(r"[0-9a-fA-F]{6,}")
_DIGITS = re.compile(r"\d+")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_FLATTEN_DEPTH = 3
_NEST_DEPTH = 2  # collections inside collections, at most this deep
# Dates and times sort as text, so their first and last say something; versions and IPs do not.
_ORDERED_SHAPE = re.compile(r"<n>-<n>-<n>|<n>:<n>:<n>")


@dataclass(frozen=True)
class _Limits:
    values: int  # values shown for a field with few of them
    fields: int  # fields shown per collection, keys per plain object
    rows: int  # exception rows shown per collection
    clip: int  # characters of a value shown


_LEVELS = (
    _Limits(values=8, fields=40, rows=25, clip=60),
    _Limits(values=6, fields=25, rows=12, clip=48),
    _Limits(values=4, fields=15, rows=6, clip=36),
    _Limits(values=3, fields=10, rows=3, clip=24),
)


@dataclass(frozen=True)
class Field:
    """One field of a collection's rows, over every row."""

    path: str  # jq path relative to a row, e.g. ".status.phase"; "" for a row that is a value
    present: int  # rows that have it
    types: tuple[tuple[str, int], ...]  # JSON type -> rows, most common first
    counts: tuple[tuple[str, int], ...]  # JSON-encoded value -> rows, most common first (scalars only)
    unique: bool  # in every row, a scalar, and never repeated
    low: float | None  # for numbers
    high: float | None
    median: float | None
    shape: tuple[str, float] | None  # the strings' dominant shape and its share
    lengths: tuple[int, int] | None  # for arrays: the shortest and the longest
    span: tuple[str, str] | None  # for strings of one ordered shape (dates, versions): the first and last


@dataclass(frozen=True)
class RowException:
    row: str  # the row's jq path, e.g. ".items[312]"
    ident: str | None  # its name: a unique field's value, or the key of a keyed row
    notes: tuple[str, ...]  # what breaks the pattern, e.g. '.phase "CrashLoopBackOff"'


@dataclass(frozen=True)
class Collection:
    path: str  # jq path that iterates the rows' container: ".items", ".releases", ".items[].containers"
    keyed: bool  # an object whose keys name its rows
    rows: int
    of: str  # what a row is: "object", or a type such as "int" or "array"
    fields: tuple[Field, ...]
    ident: str | None  # the field that names a row, or "key"
    key_shape: tuple[str, float] | None  # a keyed collection's keys' shape
    keys: tuple[str, ...]  # a keyed collection's keys, in order
    exceptions: tuple[RowException, ...]
    matched: tuple[tuple[str, str], ...]  # rows holding a query term few rows hold: (path, compact JSON)
    inner: tuple[Collection, ...]  # collections inside the rows


def _type(v: Any) -> str:
    match v:
        case None:
            return "null"
        case bool():
            return "bool"
        case int():
            return "int"
        case float():
            return "float"
        case str():
            return "str"
        case list():
            return "array"
        case _:
            return "object"


def _key(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if _IDENTIFIER.match(key) else f"{path}[{json.dumps(key)}]"


def _flatten(item: Mapping[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """A row's fields: nested objects opened up to a depth, arrays and deeper objects kept whole."""
    out: dict[str, Any] = {}
    for k, v in item.items():
        p = _key(prefix, k)
        if isinstance(v, Mapping) and v and depth < _FLATTEN_DEPTH:
            out |= _flatten(v, p, depth + 1)
        else:
            out[p] = v
    return out


def _shape_of(s: str) -> str:
    """A string's shape: hex runs of six or more that hold a digit, then digit runs, blanked."""
    s = _HEX.sub(lambda m: "<hex>" if any(c.isdigit() for c in m[0]) else m[0], s)
    return _DIGITS.sub("<n>", s)


def _dominant_shape(strings: list[str]) -> tuple[str, float] | None:
    if not strings:
        return None
    shape, n = Counter(_shape_of(s) for s in strings).most_common(1)[0]
    return shape, n / len(strings)


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _field(path: str, values: list[Any], rows: int) -> Field:
    scalars = [v for v in values if not isinstance(v, list | Mapping)]
    counts = Counter(json.dumps(v, ensure_ascii=False) for v in scalars).most_common()
    numbers = [float(v) for v in values if _is_number(v)]
    arrays = [len(v) for v in values if isinstance(v, list)]
    return Field(
        path=path,
        present=len(values),
        types=tuple(Counter(_type(v) for v in values).most_common()),
        counts=tuple(counts),
        unique=rows > 1 and len(values) == rows == len(scalars) == len(counts),
        low=min(numbers) if numbers else None,
        high=max(numbers) if numbers else None,
        median=statistics.median(numbers) if numbers else None,
        shape=(shape := _dominant_shape(strings := [v for v in values if isinstance(v, str)])),
        lengths=(min(arrays), max(arrays)) if arrays else None,
        span=(min(strings), max(strings))
        if shape and shape[1] >= 0.9 and _ORDERED_SHAPE.search(shape[0])
        else None,
    )


def _outliers(values: list[tuple[int, float]]) -> list[int]:
    """Rows whose number is far outside the rest: beyond three interquartile ranges of the middle
    half, or an extreme further from the next value than the whole range of the others."""
    if len(values) < _MIN_ROWS:
        return []
    ordered = sorted(values, key=lambda x: x[1])
    nums = [v for _, v in ordered]
    q1, _, q3 = statistics.quantiles(nums, n=4)
    iqr = q3 - q1
    out = {i for i, v in values if iqr > 0 and not q1 - _IQR_FACTOR * iqr <= v <= q3 + _IQR_FACTOR * iqr}
    for (i, v), nxt, rest in (
        ((ordered[-1][0], nums[-1]), nums[-2], nums[:-1]),
        ((ordered[0][0], nums[0]), nums[1], nums[1:]),
    ):
        spread = rest[-1] - rest[0]
        if spread > 0 and abs(v - nxt) > spread:
            out.add(i)
    return sorted(out)


def _notes(rows: list[dict[str, Any]], fields: tuple[Field, ...]) -> dict[int, list[str]]:
    """What breaks the pattern, per row index."""
    n = len(rows)
    notes: dict[int, list[str]] = {}

    def note(i: int, text: str) -> None:
        notes.setdefault(i, []).append(text)

    for f in fields:
        present = [(i, r[f.path]) for i, r in enumerate(rows) if f.path in r]
        share = f.present / n
        if share <= _KEY_RARE:  # a key few rows have
            for i, v in present:
                note(i, f"has {f.path} {_show(v, 40)}")
            continue
        if _KEY_COMMON <= share < 1:  # a key nearly every row has
            for i in sorted(set(range(n)) - {i for i, _ in present}):
                note(i, f"lacks {f.path}")
        flagged = set()  # one note per field per row: a rare value, else another type, else an outlier
        if f.counts and f.counts[0][1] / n >= _DOMINANT:
            rare = {value for value, c in f.counts[1:] if c / n <= _RARE}
            for i, v in present:
                if not isinstance(v, list | Mapping) and json.dumps(v, ensure_ascii=False) in rare:
                    note(i, f"{f.path} {_show(v, 40)}")
                    flagged.add(i)
        main_type, main_n = f.types[0]
        if main_n / f.present >= _KEY_COMMON:
            for i, v in present:
                if (
                    i not in flagged
                    and _type(v) != main_type
                    and not (_is_number(v) and main_type in ("int", "float"))
                ):
                    note(i, f"{f.path} is {_type(v)} {_show(v, 40)}")
                    flagged.add(i)
        for i in _outliers([(i, float(v)) for i, v in present if _is_number(v)]):
            if i not in flagged:
                note(i, f"{f.path} {_show(rows[i][f.path], 40)} (outlier)")
    return notes


def _ident(fields: tuple[Field, ...]) -> str | None:
    """The field that names a row: a unique string, by a naming key when there is one."""
    candidates = [f.path for f in fields if f.unique and f.types[0][0] == "str" and f.path]
    for name in _IDENT_NAMES:
        for p in candidates:
            if p.rsplit(".", 1)[-1].lower() == name:
                return p
    return candidates[0] if candidates else None


def _matched(paths: list[str], items: list[Any], terms: frozenset[str]) -> tuple[tuple[str, str], ...]:
    texts = [json.dumps(x, separators=(",", ":"), ensure_ascii=False) for x in items]
    useful = discriminating(terms, texts, share=0.05, floor=3)
    hits = [i for i, t in enumerate(texts) if useful and any(matches(t, w) for w in useful)]
    return tuple((paths[i], texts[i]) for i in hits[:3])


def _rows_of(path: str, value: Any) -> tuple[list[str], list[Any], list[str] | None] | None:
    """A value's rows, if it is a collection: their concrete paths, the rows, and their keys when the
    value is an object keyed by them."""
    if isinstance(value, list) and len(value) >= _MIN_ROWS:
        return [_key(path, i) for i in range(len(value))], value, None
    if isinstance(value, Mapping) and len(value) >= _MAP_MIN_KEYS:
        kind, n = Counter(_type(v) for v in value.values()).most_common(1)[0]
        if n / len(value) >= 0.8 and kind in ("object", "array"):
            keys = list(value)
            return [_key(path, k) for k in keys], list(value.values()), keys
    return None


def collection(
    path: str,
    paths: list[str],
    items: list[Any],
    keys: list[str] | None,
    terms: frozenset[str],
    depth: int = 0,
) -> Collection:
    """`items` (whose own jq paths are `paths`) as one collection, iterated by `path`."""
    objects = all(isinstance(x, Mapping) for x in items)
    if objects:
        rows = [_flatten(x) for x in items]
        seen: dict[str, None] = {}
        for r in rows:
            seen.update(dict.fromkeys(r))
        fields = tuple(_field(p, [r[p] for r in rows if p in r], len(rows)) for p in seen)
        of = "object"
    else:
        rows = [{"": x} for x in items]
        fields = (_field("", items, len(items)),)
        of = Counter(_type(x) for x in items).most_common(1)[0][0]
    ident = "key" if keys is not None else _ident(fields)
    notes = _notes(rows, fields)
    exceptions = tuple(
        RowException(
            paths[i],
            keys[i] if keys is not None else (str(rows[i][ident]) if ident and ident in rows[i] else None),
            tuple(notes[i]),
        )
        for i in sorted(notes, key=lambda i: (-len(notes[i]), i))
    )
    inner = []
    if depth < _NEST_DEPTH:  # arrays of objects inside the rows: every one of their elements, as rows
        for f in fields:
            if f.lengths is None or f.types[0][0] != "array":
                continue
            sub_paths, sub_items = [], []
            for p, r in zip(paths, rows, strict=True):
                v = r.get(f.path)
                if isinstance(v, list):
                    sub_paths += [f"{p}{f.path}[{j}]" for j in range(len(v))]
                    sub_items += v
            if len(sub_items) >= _MIN_ROWS and all(isinstance(x, Mapping) for x in sub_items):
                iterate = f"{path}[]{f.path}"
                inner.append(collection(iterate, sub_paths, sub_items, None, terms, depth + 1))
    return Collection(
        path=path,
        keyed=keys is not None,
        rows=len(items),
        of=of,
        fields=fields,
        ident=ident,
        key_shape=_dominant_shape(keys) if keys is not None else None,
        keys=tuple(keys or ()),
        exceptions=exceptions,
        matched=_matched(paths, items, terms),
        inner=tuple(inner),
    )


def _number(x: float) -> str:
    return str(int(x)) if x == int(x) else f"{x:g}"


def _show(v: Any, clip: int) -> str:
    return markers.clipped(json.dumps(v, ensure_ascii=False), clip)


def describe(f: Field, rows: int, values: int = 8, clip: int = 60) -> str:
    """One field's line: where it is, what types, and what values it takes."""
    parts = []
    if f.present < rows:
        parts.append(f"in {f.present} of {rows}")
    if len(f.types) > 1:
        parts.append(", ".join(f"{t} {n}" for t, n in f.types))
    kind = f.types[0][0]
    if f.unique:
        like = f" like {markers.clipped(f.shape[0], clip)}" if f.shape and f.shape[1] >= 0.8 else ""
        span = f", {f.span[0]} to {f.span[1]}" if f.span else ""
        parts.append(f"{kind}, unique{like}{span}")
    elif len(f.counts) == 1 and f.counts[0][1] == f.present:
        parts.append(f"{markers.clipped(f.counts[0][0], clip)} (all {f.present})")
    elif f.counts and len(f.counts) <= values and sum(c for _, c in f.counts) == f.present:
        parts.append(", ".join(f"{markers.clipped(v, clip)} {c}" for v, c in f.counts))
    elif f.low is not None and f.high is not None and f.median is not None:
        parts.append(f"{kind} {_number(f.low)}..{_number(f.high)}, median {_number(f.median)}")
    elif f.lengths is not None:
        parts.append(f"array, length {f.lengths[0]}..{f.lengths[1]}")
    elif kind == "str":
        like = f", like {markers.clipped(f.shape[0], clip)}" if f.shape and f.shape[1] >= 0.5 else ""
        span = f", {f.span[0]} to {f.span[1]}" if f.span else ""
        repeated = [(v, c) for v, c in f.counts[: min(3, values)] if c > 1]
        top = (
            "; most common " + ", ".join(f"{markers.clipped(v, clip)} {c}" for v, c in repeated)
            if repeated
            else ""
        )
        parts.append(f"str, {len(f.counts)} values{like}{span}{top}")
    else:
        parts.append(kind)
    return "; ".join(parts)


def _render(c: Collection, indent: str, lim: _Limits) -> list[str]:
    if c.keyed:
        like = f" like {c.key_shape[0]}" if c.key_shape and c.key_shape[1] >= 0.5 else ""
        each = "an object" if c.of == "object" else c.of
        head = f"{indent}{c.path}: object of {c.rows} keys{like}, each {each}"
        keys = ", ".join(c.keys)
        if len(keys) > 8 * lim.clip:  # too many to list: the first and the last
            keys = ", ".join([*c.keys[:8], "...", *c.keys[-4:]])
        head += f"\n{indent}  keys: {keys}"
    else:
        head = f"{indent}{c.path or '.'}: array[{c.rows}] of {c.of}"
    out = [head]
    shown = c.fields[: lim.fields]
    width = max((len(f.path) for f in shown), default=0)
    for f in shown:
        out.append(
            f"{indent}  {(f.path or '(each)').ljust(width)}  {describe(f, c.rows, lim.values, lim.clip)}"
        )
    if len(c.fields) > lim.fields:
        rest = ", ".join(f.path for f in c.fields[lim.fields : lim.fields + 12])
        more = ", ..." if len(c.fields) > lim.fields + 12 else ""
        out.append(f"{indent}  [... {len(c.fields) - lim.fields} more fields: {rest}{more}]")
    if c.exceptions:
        out.append(f"{indent}  exceptions in {len(c.exceptions)} rows:")
        for e in c.exceptions[: lim.rows]:
            who = f" {markers.clipped(e.ident, lim.clip)}" if e.ident else ""
            out.append(f"{indent}    {e.row}{who}: {', '.join(e.notes)}")
        if len(c.exceptions) > lim.rows:
            out.append(f"{indent}    [... {len(c.exceptions) - lim.rows} more exception rows]")
    for row, text in c.matched:
        out.append(f"{indent}  matches the query: {row} {markers.clipped(text, 4 * lim.clip)}")
    for sub in c.inner:
        out += _render(sub, indent + "  ", lim)
    return out


def _outline(
    path: str, value: Any, terms: frozenset[str], lim: _Limits, found: list[Collection]
) -> list[str]:
    """The unique structure as an outline, and every collection in it as its schema."""
    if (rows := _rows_of(path, value)) is not None:
        c = collection(path, *rows, terms)
        found.append(c)
        return _render(c, "", lim)
    if isinstance(value, Mapping) and value:
        out = []
        for k, v in list(value.items())[: lim.fields]:
            p = _key(path, k)
            nested = (isinstance(v, Mapping) and v) or _rows_of(p, v) is not None
            out += _outline(p, v, terms, lim, found) if nested else [f"{p}  {_show(v, lim.clip)}"]
        if len(value) > lim.fields:
            rest = ", ".join(str(k) for k in list(value)[lim.fields : lim.fields + 12])
            out.append(f"[... {len(value) - lim.fields} more keys of {path or '.'}: {rest}, ...]")
        return out
    return [f"{path or '.'}  {_show(value, 4 * lim.clip)}"]


def _query(found: list[Collection], slurp: bool) -> str | None:
    """A ready jq query: the rows of the first collection whose dominant value some rows break."""
    jq = "jq -s" if slurp else "jq"
    for c in found:
        for sub in (c, *c.inner):
            if sub.keyed or sub.of != "object":
                continue
            broken = {note.split(" ", 1)[0] for e in sub.exceptions for note in e.notes}
            for f in sub.fields:
                dominant = len(f.counts) > 1 and f.counts[0][1] / sub.rows >= _DOMINANT
                if f.path in broken and f.present == sub.rows and dominant:
                    pick = f" | {sub.ident}" if sub.ident else ""
                    return f"{jq} '{sub.path or '.'}[] | select({f.path} != {f.counts[0][0]}){pick}' FILE"
    return None


def schema_view(value: Any, terms: frozenset[str], budget_tokens: int, slurp: bool = False) -> str:
    """The schema view of a parsed JSON value within the budget (JSON Lines: `slurp`, read as one
    array), or the tightest view when nothing fits."""
    text = ""
    for lim in _LEVELS:
        found: list[Collection] = []
        lines = _outline("", value, terms, lim, found)
        if (q := _query(found, slurp)) is not None:
            lines.append(f"query: {q}")
        text = "\n".join(lines)
        if estimate_tokens(text) <= budget_tokens:
            return text
    return text
