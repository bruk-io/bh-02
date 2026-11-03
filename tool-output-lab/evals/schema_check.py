"""Layer 1's check of a schema view: every claim it makes, recomputed from the data.

The view is parsed as the model reads it (collection headers, field lines, exception rows, the
query), and each claim is checked against the input with this module's own jq-path walker, not the
schema module's code, so a bug in one cannot hide in the other:

- a collection's row count; a field's presence ("in P of N"), its single value ("(all N)"), its
  value counts, its types, its range and median, and "unique";
- each exception row: the row exists, and each note holds (the value is there and is not the
  field's dominant one; the key is missing; the type differs);
- completeness: when the exception list is not cut, every row holding a rare value of a field whose
  value counts show one dominant value is listed;
- the query: `jq` runs it on the input, and it returns exactly the rows its select names.

A claim the view clipped (`...[+N chars]`) is not checked.
"""

import json
import re
import shutil
import statistics
import subprocess
from collections import Counter
from typing import Any

from compressors import markers
from compressors.config import DEFAULT, SchemaKnobs

_MISSING = object()
_SEGMENT = re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)|\[("(?:[^"\\]|\\.)*")\]|\[(\d+)\]|(\[\])')
_HEADER = re.compile(
    r"^(?P<ind> *)(?P<path>\S+): (?:array\[(?P<n>\d+)\] of \S+|object of (?P<keys>\d+) keys)"
)
_FIELD = re.compile(r"^(?P<ind> *)(?P<field>[.\[]\S*|\(each\)) {2,}(?P<desc>.+)$")
_EXCEPTION = re.compile(r"^ *(?P<row>\.\S+?)(?: (?P<name>[^:]+?))?: (?P<notes>.+)$")
_QUERY = re.compile(r"^query: jq(?P<slurp> -s)? '(?P<prog>.+)' FILE$")
_SELECT = re.compile(
    r"^(?P<base>.*)\[\] \| select\((?P<field>\S+) != (?P<value>.+?)\)(?: \| (?P<pick>\S+))?$"
)
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


def _get(row: Any, rel: str) -> Any:
    got = walk(row, rel)
    return got[0] if got else _MISSING


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
    present = [v for v in (_get(r, rel) for r in rows) if v is not _MISSING]
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


def _note_claims(row_path: str, row: Any, note: str) -> tuple[list[str], str | None]:
    """A note's problems, and the field it is about (for completeness)."""
    if m := re.fullmatch(r"lacks (\S+)", note):
        return ([] if _get(row, m[1]) is _MISSING else [f"{row_path}: says it lacks {m[1]}, it has it"]), None
    if m := re.fullmatch(r"has (\S+) (.+)", note):
        return (
            [] if _get(row, m[1]) is not _MISSING else [f"{row_path}: says it has {m[1]}, it does not"]
        ), None
    if m := re.fullmatch(r"(\S+) is (\w+) (.+)", note):
        got = _get(row, m[1])
        return (
            [] if got is not _MISSING and _type(got) == m[2] else [f"{row_path}: {m[1]} is not {m[2]}"]
        ), None
    if m := re.fullmatch(r"(\S+) (.+?)( \(outlier\))?", note):
        if markers.CLIPPED.search(m[2]) or "...[+" in m[2]:
            return [], m[1]
        try:
            value = json.loads(m[2])
        except ValueError:
            return [f"{row_path}: cannot read the note {note!r}"], None
        got = _get(row, m[1])
        return ([] if got == value else [f"{row_path}: says {m[1]} {m[2]}, it is {json.dumps(got)}"]), m[1]
    return [f"{row_path}: cannot read the note {note!r}"], None


def _notes(text: str) -> list[str]:
    """A row's notes, split on the commas between them (not those inside a JSON value)."""
    out, pos, start = [], 0, 0
    while pos < len(text):
        if text[pos] in '"[{':
            try:
                _, pos = _DECODER.raw_decode(text, pos)
                continue
            except ValueError:
                pass
        if text.startswith(", ", pos):
            out.append(text[start:pos])
            pos += 2
            start = pos
            continue
        pos += 1
    out.append(text[start:])
    return out


def claims(raw_value: Any, view: str, knobs: SchemaKnobs = DEFAULT.schema) -> list[str]:
    """Every claim of the view that the data does not bear out (judged by the knobs it was made with)."""
    problems: list[str] = []
    rows: list[Any] = []
    path = ""
    fields: dict[str, str] = {}
    listed: set[str] = set()
    cut = False

    def close() -> None:  # completeness, once a collection's lines are all read
        if not path or cut or path.endswith("[]"):  # rows inside rows are not named by one index
            return
        for rel, desc in fields.items():
            counts = _values_then_counts(desc.split("; ")[-1])
            if not counts or counts[0][1] / max(1, len(rows)) < knobs.dominant:
                continue
            rare = {json.dumps(v) for v, n in counts[1:] if n / len(rows) <= knobs.rare}
            for i, r in enumerate(rows):
                v = _get(r, rel)
                if (
                    v is not _MISSING
                    and json.dumps(v) in rare
                    and not any(row.endswith(f"[{i}]") or row in walk_keys.get(i, ()) for row in listed)
                ):
                    problems.append(f"{path}: row {i} holds {rel} {json.dumps(v)} and is not listed")

    walk_keys: dict[int, tuple[str, ...]] = {}
    for line in view.splitlines():
        if m := _HEADER.match(line):
            close()
            path, fields, listed, cut = m["path"], {}, set(), False
            base = "" if path == "." else path
            rows = walk(raw_value, base + "[]")
            n = int(m["n"] or m["keys"])
            if len(rows) != n:
                problems.append(f"{path}: says {n} rows, it has {len(rows)}")
            if m["keys"]:  # a keyed collection's rows are named by key
                keys = list(walk(raw_value, base)[0]) if walk(raw_value, base) else []
                walk_keys = {i: (f"{base}[{json.dumps(k)}]", f"{base}.{k}") for i, k in enumerate(keys)}
            else:
                walk_keys = {}
            continue
        if not path:
            continue
        if (m := _FIELD.match(line)) and not line.strip().startswith(("exceptions", "keys:", "matches")):
            rel = "" if m["field"] == "(each)" else m["field"]
            fields[rel] = m["desc"]
            problems += _field_claims(path, rows, rel, m["desc"])
            continue
        if line.strip().startswith("[... ") and "more exception rows" in line:
            cut = True
            continue
        if (m := _EXCEPTION.match(line)) and line.startswith("    "):
            got = walk(raw_value, m["row"])
            if not got:
                problems.append(f"{m['row']}: listed as an exception, and there is no such row")
                continue
            listed.add(m["row"])
            for note in _notes(m["notes"]):
                problems += _note_claims(m["row"], got[0], note)[0]
    close()
    return problems


def query_runs(raw: str, raw_value: Any, view: str, knobs: SchemaKnobs = DEFAULT.schema) -> list[str]:
    """The view's query, run with jq on the input, against what its select names."""
    line = next((x for x in view.splitlines() if x.startswith("query: ")), None)
    if line is None or shutil.which("jq") is None:
        return []
    m = _QUERY.match(line)
    if m is None:
        return [f"cannot read the query line {line!r}"]
    flags = ["-r", "-s"] if m["slurp"] else ["-r"]
    proc = subprocess.run(
        ["jq", *flags, m["prog"]], input=raw, capture_output=True, text=True, timeout=60, check=False
    )
    if proc.returncode != 0:
        return [f"jq rejects the query: {proc.stderr.strip()[:200]}"]
    sel = _SELECT.match(m["prog"])
    if sel is None:
        return []
    value = json.loads(sel["value"])
    rows = walk(raw_value, sel["base"] + "[]") if sel["base"] not in ("", ".") else walk(raw_value, "[]")
    held = sum(1 for r in rows if _get(r, sel["field"]) == value)
    if not rows or held / len(rows) < knobs.dominant:  # it must select the rows that break the dominant value
        said = f"the query selects against {sel['value']}, which {held} of {len(rows)} rows hold"
        return [f"{said}: not the dominant value"]
    want = [_get(r, sel["pick"]) if sel["pick"] else r for r in rows if _get(r, sel["field"]) != value]
    got = proc.stdout.splitlines()
    expected = [w if isinstance(w, str) else json.dumps(w) for w in want]
    return [] if got == expected else [f"the query returns {len(got)} rows, its select names {len(expected)}"]
