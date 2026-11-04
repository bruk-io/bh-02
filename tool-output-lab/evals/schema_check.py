"""Layer 1's readers for JSON envelopes: a jq-path walker, a reader of field lines, and a note check.

Written apart from the producers, so a bug in one cannot hide in the other: `walk` reads jq paths
into the input, `shape_claims` reads an envelope's shape back line by line (a collection's row
count; a field's presence, its single value, its value counts, its types, its range and median,
"unique") and checks each against the data, and `note_claims` checks what an anomaly row says of
itself. `evals.envelope_check` uses all three. A claim the text clipped (`...[+N chars]`) is not
checked.
"""

import json
import re
import statistics
from collections import Counter
from typing import Any

from compressors import markers

MISSING = object()
_SEGMENT = re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)|\[("(?:[^"\\]|\\.)*")\]|\[(\d+)\]|(\[\])')
_HEADER = re.compile(
    r"^(?P<ind> *)(?P<path>\S+): (?:array\[(?P<n>\d+)\] of \S+|object of (?P<keys>\d+) keys)"
)
_FIELD = re.compile(r"^(?P<ind> *)(?P<field>[.\[]\S*|\(each\)) {2,}(?P<desc>.+)$")
_TYPES = {"str", "int", "float", "bool", "null", "array", "object"}
_DECODER = json.JSONDecoder()


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


def walk(value: Any, path: str) -> list[Any]:
    """Every value a jq path reaches (`[]` iterates an array's elements or an object's values);
    a step that does not exist reaches nothing.

    Raises:
        ValueError: the path has a step this walker does not read.
    """
    found = [value]
    pos = 0
    while pos < len(path):
        m = _SEGMENT.match(path, pos)
        if m is None:
            raise ValueError(f"not a jq path this check reads: {path!r} at {pos}")
        pos = m.end()
        name, quoted, index, every = m.groups()
        step = []
        for v in found:
            if every:
                step += list(v.values()) if isinstance(v, dict) else list(v) if isinstance(v, list) else []
            elif index is not None:
                if isinstance(v, list) and int(index) < len(v):
                    step.append(v[int(index)])
            else:
                key = name if name is not None else json.loads(quoted)
                if isinstance(v, dict) and key in v:
                    step.append(v[key])
        found = step
    return found


def get(row: Any, rel: str) -> Any:
    got = walk(row, rel)
    return got[0] if got else MISSING


def _values_then_counts(text: str) -> list[tuple[Any, int]] | None:
    """`"a" 3, "b" 2` as [(a, 3), (b, 2)], or None when it is not a list of JSON values and counts."""
    out, pos = [], 0
    while pos < len(text):
        try:
            value, pos = _DECODER.raw_decode(text, pos)
        except ValueError:
            return None
        m = re.match(r" (\d+)(, |$)", text[pos:])
        if m is None:
            return None
        out.append((value, int(m[1])))
        pos += m.end()
    return out


def _field_claims(path: str, rows: list[Any], rel: str, desc: str) -> list[str]:
    where = f"{path} {rel}"
    present = [v for v in (get(r, rel) for r in rows) if v is not MISSING]
    problems = []
    for part in desc.split("; "):
        if markers.CLIPPED.search(part) or "...[+" in part:
            continue
        if m := re.fullmatch(r"in (\d+) of (\d+)", part):
            if (int(m[1]), int(m[2])) != (len(present), len(rows)):
                problems.append(f"{where}: says in {m[1]} of {m[2]}, it is in {len(present)} of {len(rows)}")
        elif m := re.fullmatch(r"(.+) \(all (\d+)\)", part):
            try:
                value = json.loads(m[1])
            except ValueError:
                continue
            if int(m[2]) != len(present) or any(v != value for v in present):
                problems.append(f"{where}: says {m[1]} in all {m[2]}, not so")
        elif m := re.match(r"(int|float|str|bool)\b.*\bunique\b", part):
            texts = [json.dumps(v) for v in present]
            if len(present) != len(rows) or len(set(texts)) != len(texts):
                problems.append(f"{where}: says unique, it is not")
        elif m := re.fullmatch(r"(int|float) (-?[\d.e+]+)\.\.(-?[\d.e+]+), median (-?[\d.e+]+)", part):
            nums = [float(v) for v in present if isinstance(v, int | float) and not isinstance(v, bool)]
            want = (float(m[2]), float(m[3]), float(m[4]))
            stats = (min(nums), max(nums), statistics.median(nums)) if nums else None
            if stats is None or any(
                abs(a - b) > 1e-6 * max(1.0, abs(b)) for a, b in zip(want, stats, strict=True)
            ):
                problems.append(f"{where}: says {m[2]}..{m[3]}, median {m[4]}; it is {stats}")
        elif all(p.split(" ")[0] in _TYPES and len(p.split(" ")) == 2 for p in part.split(", ")) and any(
            p.split(" ")[0] not in ("null", "true", "false") for p in part.split(", ")
        ):
            types = Counter(_type(v) for v in present)
            for p in part.split(", "):
                kind, said = p.split(" ")
                if types[kind] != int(said):
                    problems.append(f"{where}: says {kind} {said}, it is {types[kind]}")
        elif (counts := _values_then_counts(part)) is not None:
            held = Counter(
                json.dumps(v, ensure_ascii=False) for v in present if not isinstance(v, list | dict)
            )
            for value, n in counts:
                if held[json.dumps(value, ensure_ascii=False)] != n:
                    problems.append(f"{where}: says {json.dumps(value)} {n}, it is {held[json.dumps(value)]}")
    return problems


def note_claims(row_path: str, row: Any, note: str) -> tuple[list[str], str | None]:
    """A note's problems, and the field it is about (for completeness)."""
    if m := re.fullmatch(r"lacks (\S+)", note):
        return ([] if get(row, m[1]) is MISSING else [f"{row_path}: says it lacks {m[1]}, it has it"]), None
    if m := re.fullmatch(r"has (\S+) (.+)", note):
        return (
            [] if get(row, m[1]) is not MISSING else [f"{row_path}: says it has {m[1]}, it does not"]
        ), None
    if m := re.fullmatch(r"(\S+) is (\w+) (.+)", note):
        got = get(row, m[1])
        return (
            [] if got is not MISSING and _type(got) == m[2] else [f"{row_path}: {m[1]} is not {m[2]}"]
        ), None
    if m := re.fullmatch(r"(\S+) (.+?)( \(outlier\))?", note):
        if markers.CLIPPED.search(m[2]) or "...[+" in m[2]:
            return [], m[1]
        try:
            value = json.loads(m[2])
        except ValueError:
            return [f"{row_path}: cannot read the note {note!r}"], None
        got = get(row, m[1])
        return ([] if got == value else [f"{row_path}: says {m[1]} {m[2]}, it is {json.dumps(got)}"]), m[1]
    return [f"{row_path}: cannot read the note {note!r}"], None


def shape_claims(raw_value: Any, text: str) -> list[str]:
    """Every claim of a shape's lines that the data does not bear out: each collection header's row
    count, and each field line under it."""
    problems: list[str] = []
    rows: list[Any] = []
    path = ""
    for line in text.splitlines():
        if m := _HEADER.match(line):
            path = m["path"]
            rows = walk(raw_value, ("" if path == "." else path) + "[]")
            n = int(m["n"] or m["keys"])
            if len(rows) != n:
                problems.append(f"{path}: says {n} rows, it has {len(rows)}")
            continue
        if path and (m := _FIELD.match(line)) and not line.strip().startswith(("keys:", "[... ")):
            rel = "" if m["field"] == "(each)" else m["field"]
            problems += _field_claims(path, rows, rel, m["desc"])
    return problems
