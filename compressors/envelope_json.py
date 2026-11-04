"""JSON as an envelope (`compressors.envelope`): the producers of each part, by name, and the recipe
the knobs name (`compressors.config.JsonEnvelopeKnobs`).

    shape      fields      each collection's header and fields: types, values and counts, ranges
               summary     each collection's header, each field's type, the counts of a field with few values
    anomalies  exceptions  every row that breaks its collection's shape, and what breaks it
               standouts   the items the sample fold's rules pick: rare values, error keys, failing statuses
               none
    samples    matches     rows holding a query term few rows hold
               typical     those, and the first row of each collection that breaks nothing
               head-tail   those, and each collection's first two rows and its last
               none
    nav        jq          a ready query for the rows that break a dominant value, and how to read a path
               rows        how to read any row, or a range, of each collection
               none

The schema view is fields, exceptions, matches and jq (the defaults); the sample fold is summary,
standouts, head-tail and rows. Every producer reads one analysis (`JsonData.found`, from
`compressors.schema.collections`), so the parts agree on what the collections and their rows are.
Paths are jq paths into the input; FILE in a command stands for it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from compressors import markers
from compressors.config import DEFAULT, FoldConfig, JsonEnvelopeKnobs, SchemaKnobs
from compressors.envelope import (
    NOTHING,
    Breaks,
    Claim,
    Count,
    Envelope,
    Fetches,
    Level,
    Lists,
    Navigator,
    Part,
    Recipe,
    Role,
    Sampler,
    Shaper,
    Spotter,
    Values,
    Verbatim,
    compose,
    nothing,
    priority,
)
from compressors.json_fold import promote
from compressors.schema import Collection, Found, collections, describe, lists_values, query, shape_levels


@dataclass(frozen=True)
class JsonData:
    value: Any
    terms: frozenset[str]
    slurp: bool  # JSON Lines read as one array: commands take jq -s
    knobs: SchemaKnobs
    found: tuple[Found, ...]  # the collections, outermost first


def json_data(
    value: Any, terms: frozenset[str] = frozenset(), slurp: bool = False, knobs: SchemaKnobs = DEFAULT.schema
) -> JsonData:
    return JsonData(value, terms, slurp, knobs, collections(value, terms, knobs))


def _every(cs: tuple[Collection, ...] | list[Collection]) -> list[Collection]:
    """Collections and those inside their rows, outermost first."""
    return [x for c in cs for x in (c, *_every(c.inner))]


def _all(data: JsonData) -> list[Collection]:
    return _every([f.collection for f in data.found])


def _verbatim(at: str, text: str, clip: int) -> tuple[str, Verbatim]:
    """An item's compact text, clipped, and the claim that the item is (or starts with) what is shown."""
    shown = markers.clipped(text, clip)
    whole = shown == text
    return shown, Verbatim(at, text if whole else shown[: shown.rindex("...[+")], whole)


def _compact(item: Any) -> str:
    return json.dumps(item, ensure_ascii=False, separators=(",", ":"))


def _counted(c: Collection, fields: int, values: int, clip: int) -> list[Claim]:
    claims: list[Claim] = [Count(c.path, c.rows)]
    for f in c.fields[:fields]:
        if lists_values(f, values) and all(len(v) <= clip for v, _ in f.counts):
            claims.append(Values(c.path, f.path, f.counts))
    return claims


# --- shape ------------------------------------------------------------------------------------------------


def fields(data: JsonData, /) -> Part:
    """The schema view's outline without its exceptions: the unique structure, and each collection's
    fields with their types, values and counts, ranges and shapes."""
    levels = []
    for lv in shape_levels(data.value, data.terms, data.found, data.knobs):
        claims = [x for c, n in lv.shown for x in _counted(c, n, lv.values, lv.clip)]
        levels.append(Level("", lv.lines, tuple(claims)))
    return Part(Role.SHAPE, tuple(levels))


_FEW = 6  # a summary lists the values of a field with at most this many, held by every row


def _brief(c: Collection, cap: int, indent: str) -> tuple[list[str], list[Claim]]:
    head = f"{indent}{c.path or '.'}: " + (
        f"object of {c.rows} keys" if c.keyed else f"array[{c.rows}] of {c.of}"
    )
    lines: list[str] = [head]
    claims: list[Claim] = [Count(c.path, c.rows)]
    shown = c.fields[:cap]
    width = max((len(f.path) for f in shown), default=0)
    for f in shown:
        few = not f.unique and 1 < len(f.counts) <= _FEW and sum(n for _, n in f.counts) == c.rows
        if few:
            desc = describe(f, c.rows, _FEW, 60)
            claims.append(Values(c.path, f.path, f.counts))
        else:
            desc = ", ".join(f"{t} {n}" for t, n in f.types) if len(f.types) > 1 else f.types[0][0]
        lines.append(f"{indent}  {(f.path or '(each)').ljust(width)}  {desc}")
    if len(c.fields) > cap:
        lines.append(f"{indent}  [... {len(c.fields) - cap} more fields]")
    for sub in c.inner:
        more, said = _brief(sub, cap, indent + "  ")
        lines += more
        claims += said
    return lines, claims


def summary(data: JsonData, /) -> Part:
    """What the sample fold's summary says: each collection's header, its fields' types, and the
    counts of a field with few values; with the top level's own scalars."""
    levels = []
    for cap in (30, 15, 8):
        lines: list[str] = []
        claims: list[Claim] = []
        if isinstance(data.value, Mapping):
            scalars = [(k, v) for k, v in data.value.items() if not isinstance(v, list | Mapping)][:cap]
            lines += [f".{k}  {markers.clipped(json.dumps(v, ensure_ascii=False), 60)}" for k, v in scalars]
        for f in data.found:
            more, said = _brief(f.collection, cap, "")
            lines += more
            claims += said
        levels.append(Level("", tuple(lines), tuple(claims)))
    return Part(Role.SHAPE, tuple(levels))


# --- anomalies ----------------------------------------------------------------------------------------------


def _lists(c: Collection, k: SchemaKnobs) -> list[Claim]:
    """Completeness: for a field one value dominates and every other value is rare, every row holding
    another is listed (rows inside rows are not named by one index, so not claimed)."""
    if "[]" in c.path or not c.rows:
        return []
    listed = tuple(e.row for e in c.exceptions)
    return [
        Lists(c.path, f.path, f.counts[0][0], listed)
        for f in c.fields
        if f.objects == 0
        and len(f.counts) > 1
        and f.counts[0][1] / c.rows >= k.dominant
        and all(n / c.rows <= k.rare for _, n in f.counts[1:])
    ]


_ROWS = ((25, 60), (12, 48), (6, 36), (3, 24))  # rows listed per collection, and characters of a name


def exceptions(data: JsonData, _shape: Part, /) -> Part:
    """Every row that breaks its collection's shape, with what breaks it: a value few rows hold where
    one dominates, a number far outside the rest, a key few rows have or one nearly all have missing,
    a value of another type."""
    every = _all(data)
    if not every:
        return nothing(Role.ANOMALIES)
    total = sum(len(c.exceptions) for c in every)
    complete = [x for c in every for x in _lists(c, data.knobs)]
    if total == 0:
        return Part(Role.ANOMALIES, (Level("none", (), tuple(complete)),))
    levels = []
    for cap, clip in _ROWS:
        body: list[str] = []
        claims: list[Claim] = []
        for c in every:
            for e in c.exceptions[:cap]:
                who = f" {markers.clipped(e.ident, clip)}" if e.ident else ""
                body.append(f"{e.row}{who}: {', '.join(e.notes)}")
                claims += [Breaks(e.row, note) for note in e.notes]
            if len(c.exceptions) > cap:
                body.append(f"[... {len(c.exceptions) - cap} more rows of {c.path or '.'}]")
            else:
                claims += _lists(c, data.knobs)
        listed = sum(min(len(c.exceptions), cap) for c in every)
        head = f"{total} rows, all listed" if listed == total else f"{total} rows, {listed} listed"
        levels.append(Level(head, tuple(body), tuple(claims)))
    levels.append(Level(f"{total} rows", ()))
    return Part(Role.ANOMALIES, tuple(levels))


_STANDOUTS = ((10, 600), (5, 300), (2, 160), (1, 100))  # items listed per collection, characters of each


def standouts(data: JsonData, _shape: Part, /) -> Part:
    """The items the sample fold shows out of order, by its rules: a rare value where one dominates,
    a key few items have, an error key that is set, a failing status, a value matching the query."""
    # the rules read items that are all objects or all strings; of others they can say nothing
    read = [
        f
        for f in data.found
        if all(isinstance(x, Mapping) for x in f.items) or all(isinstance(x, str) for x in f.items)
    ]
    if not read:
        return nothing(Role.ANOMALIES)
    picks = [(f, promote(list(f.items), data.terms, len(f.items), set())) for f in read]
    total = sum(len(p) for _, p in picks)
    if total == 0:
        return Part(Role.ANOMALIES, (Level("none", ()),))
    levels = []
    for cap, clip in _STANDOUTS:
        body: list[str] = []
        claims: list[Claim] = []
        for f, picked in picks:
            for i, why in picked[:cap]:
                shown, said = _verbatim(f.paths[i], _compact(f.items[i]), clip)
                body.append(f"{f.paths[i]} ({why}): {shown}")
                claims.append(said)
            if len(picked) > cap:
                body.append(f"[... {len(picked) - cap} more items of {f.collection.path or '.'} stand out]")
        listed = sum(min(len(p), cap) for _, p in picks)
        head = f"{total} items stand out" + (", all listed" if listed == total else f", {listed} listed")
        levels.append(Level(head, tuple(body), tuple(claims)))
    levels.append(Level(f"{total} items stand out", ()))
    return Part(Role.ANOMALIES, tuple(levels))


def no_anomalies(_data: JsonData, _shape: Part, /) -> Part:
    return nothing(Role.ANOMALIES)


# --- samples ------------------------------------------------------------------------------------------------


def _anomalous(anomalies: Part) -> set[str]:
    """The rows the anomalies part names, at its fullest."""
    claims = anomalies.levels[0].claims
    return {c.row for c in claims if isinstance(c, Breaks)} | {
        c.at for c in claims if isinstance(c, Verbatim)
    }


def _samples(data: JsonData, picked: list[tuple[str, Any]], clips: tuple[tuple[int, int], ...]) -> Part:
    """The query's matching rows and the picked rows, verbatim, at each (matches, picked) clip."""
    matched = [(row, text) for c in _all(data) for row, text in c.matched]
    if not matched and not picked:
        return nothing(Role.SAMPLES)
    levels = []
    for clip_matched, clip_picked in clips:
        body: list[str] = []
        claims: list[Claim] = []
        for row, text in matched:
            shown, said = _verbatim(row, text, clip_matched)
            body.append(f"{row}: {shown}  (matches the query)")
            claims.append(said)
        if clip_picked:
            for at, item in picked:
                shown, said = _verbatim(at, _compact(item), clip_picked)
                body.append(f"{at}: {shown}")
                claims.append(said)
        levels.append(Level("", tuple(body), tuple(claims)) if body else NOTHING)
    return Part(Role.SAMPLES, tuple(levels))


def matches(data: JsonData, _shape: Part, _anomalies: Part, /) -> Part:
    """Rows holding a query term few rows hold: likely the answer, shown near whole."""
    return _samples(data, [], ((1500, 0), (600, 0), (200, 0)))


def typical(data: JsonData, _shape: Part, anomalies: Part, /) -> Part:
    """The query's rows, and the first row of each collection that breaks nothing."""
    odd = _anomalous(anomalies)
    picked = []
    for f in data.found:
        i = next((i for i, p in enumerate(f.paths) if p not in odd), None)
        if i is not None:
            picked.append((f.paths[i], f.items[i]))
    return _samples(data, picked, ((1500, 600), (600, 300), (200, 0)))


def head_tail(data: JsonData, _shape: Part, _anomalies: Part, /) -> Part:
    """The query's rows, and each collection's first two rows and its last."""
    picked = [(f.paths[i], f.items[i]) for f in data.found for i in sorted({0, 1, len(f.items) - 1})]
    return _samples(data, picked, ((1500, 600), (600, 200), (200, 0)))


def no_samples(_data: JsonData, _shape: Part, _anomalies: Part, /) -> Part:
    return nothing(Role.SAMPLES)


# --- nav ------------------------------------------------------------------------------------------------


def jq(data: JsonData, _shape: Part, anomalies: Part, _samples: Part, /) -> Part:
    """A ready query for the rows that break a dominant value, and how to read any path shown."""
    cmd = "jq -s" if data.slurp else "jq"
    named = [c.row for c in anomalies.levels[0].claims if isinstance(c, Breaks)]
    example = named[0] if named else (f"{data.found[0].paths[0]}" if data.found else ".")
    read = f"{cmd} '{example}' FILE  (reads any path above)"
    q = query(tuple(f.collection for f in data.found), data.slurp, data.knobs)
    if q is None:
        return Part(Role.NAV, (Level("", (read,)),))
    fetch = Fetches(q.command, q.at, q.field, q.usual, q.pick)
    return Part(Role.NAV, (Level("", (q.command, read), (fetch,)), Level("", (q.command,), (fetch,))))


def rows(data: JsonData, _shape: Part, _anomalies: Part, _samples: Part, /) -> Part:
    """How to read any row, or a range of rows, of each collection."""
    if not data.found:
        return nothing(Role.NAV)
    cmd = "jq -s" if data.slurp else "jq"
    body = []
    for f in data.found:
        p = f.collection.path or "."
        one = f'{p}["KEY"]' if f.collection.keyed else f"{p}[I]"
        many = f"{p} | keys" if f.collection.keyed else f"{p}[A:B]"
        body.append(f"{p}: {f.collection.rows} rows; one: {cmd} '{one}' FILE; more: {cmd} '{many}' FILE")
    return Part(Role.NAV, (Level("", tuple(body)),))


def no_nav(_data: JsonData, _shape: Part, _anomalies: Part, _samples: Part, /) -> Part:
    return nothing(Role.NAV)


# --- recipes -----------------------------------------------------------------------------------------------

SHAPES: Mapping[str, Shaper[JsonData]] = {"fields": fields, "summary": summary}
ANOMALIES: Mapping[str, Spotter[JsonData]] = {
    "exceptions": exceptions,
    "standouts": standouts,
    "none": no_anomalies,
}
SAMPLES: Mapping[str, Sampler[JsonData]] = {
    "matches": matches,
    "typical": typical,
    "head-tail": head_tail,
    "none": no_samples,
}
NAVS: Mapping[str, Navigator[JsonData]] = {"jq": jq, "rows": rows, "none": no_nav}


def recipe(k: JsonEnvelopeKnobs) -> Recipe[JsonData]:
    """The recipe the knobs name.

    Raises:
        ValueError: a knob names no producer, or the priority does not name each part once.
    """
    for name, table in (("shape", SHAPES), ("anomalies", ANOMALIES), ("samples", SAMPLES), ("nav", NAVS)):
        if getattr(k, name) not in table:
            raise ValueError(f"json_envelope.{name} is one of {', '.join(table)}; not {getattr(k, name)!r}")
    return Recipe(
        SHAPES[k.shape], ANOMALIES[k.anomalies], SAMPLES[k.samples], NAVS[k.nav], priority(k.priority)
    )


def envelope(
    value: Any, terms: frozenset[str], budget_tokens: int, slurp: bool = False, config: FoldConfig = DEFAULT
) -> Envelope:
    """The envelope of a parsed JSON value within the budget, by the recipe `config` names (JSON
    Lines: `slurp`, read as one array). A config that names no producer raises ValueError, from
    `recipe`."""
    return compose(recipe(config.json_envelope), json_data(value, terms, slurp, config.schema), budget_tokens)
