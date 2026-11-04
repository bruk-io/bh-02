"""A log's envelope, or that of any output read line by line: its parts made from line templates.

    shape: 300 lines, 9 line templates (<*> is a word holding a digit)
         262  <*>-<*>-<*>:<*>:<*> INFO  GET /api/items req=req-<*> user=u-<*> <*> <*>  [<*>8: 200 260, 500 2]
    anomalies: 5 lines in 2 groups, all listed
      3 lines like: <*>-<*>-<*>:<*>:<*> ERROR payment failed for order ORD-<*> req=req-<*> user=u-<*>
        187: 2026-11-03T00:03:07Z ERROR payment failed for order ORD-4e4b61 req=req-525f51ac user=u-a7cedc
      <*>8 is 500 in 2 lines like: ...
    samples: ...
    get more:
      grep -nF 'payment failed for order ORD-' FILE  (the 3 lines like it)
      sed -n 'A,Bp' FILE  (any lines above, by number)

The shape is the log's templates and how often each is said, with the values a few-valued hole
holds (a status code, a level, a count). Anomalies read the shape: a template few lines say, while
most lines say common ones; one that names an error, when few lines do; and a rare value in a hole
whose usual value dominates. Producers and recipes as in `compressors.envelope_json`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from compressors.common import ANOMALY_RE, split_lines
from compressors.config import DEFAULT, FoldConfig, LogEnvelopeKnobs
from compressors.envelope import (
    NOTHING,
    Alike,
    Claim,
    Envelope,
    Level,
    Navigator,
    Part,
    Producers,
    Recipe,
    Role,
    Sampler,
    Shaper,
    Shows,
    Spotter,
    Total,
    compose,
    nothing,
    recipe_of,
)
from compressors.envelope_text import (
    SED,
    Group,
    Slot,
    few_valued,
    grep_for,
    groups,
    numbered,
    query_rows,
    slots,
)


@dataclass(frozen=True)
class LogData:
    lines: tuple[str, ...]
    terms: frozenset[str]
    knobs: LogEnvelopeKnobs
    groups: tuple[Group, ...]  # every non-blank line's template, most lines first
    filled: int  # non-blank lines


def log_data(raw: str, terms: frozenset[str], knobs: LogEnvelopeKnobs) -> LogData:
    lines = tuple(split_lines(raw))
    gs = groups(lines, range(len(lines)))
    return LogData(lines, terms, knobs, gs, sum(len(g.rows) for g in gs))


def _lines(n: int) -> str:
    return f"{n} line" if n == 1 else f"{n} lines"


_TEMPLATE_CLIP = 300  # a longer template is shown cut short, and claims nothing


def _slots(data: LogData, g: Group, rare: float) -> tuple[Slot, ...]:
    k = data.knobs
    return few_valued(data.lines, g, False, few=k.few, dominant=k.dominant, rare=rare, min_rows=10, clip=40)


# --- shape ---------------------------------------------------------------------------------------------

_SHAPE_LEVELS = ((40, True), (20, True), (10, False), (5, False))  # templates shown, few-valued holes


def _total(data: LogData) -> tuple[str, Total]:
    n, k = len(data.lines), len(data.groups)
    kinds = f"{k} line template{'' if k == 1 else 's'}"
    return f"{_lines(n)}, {kinds} (<*> is a token holding a digit, or a hex id)", Total(n, k)


def templates(data: LogData, /) -> Part:
    """Each template said more than once and its count, most said first, and the values of its
    few-valued holes; the rest counted."""
    head, total = _total(data)
    last = len(data.lines)
    levels = []
    for cap, with_slots in _SHAPE_LEVELS:
        body: list[str] = []
        claims: list[Claim] = [total]
        repeated = [g for g in data.groups if len(g.rows) > 1]  # a template said once describes nothing
        for g in repeated[:cap]:
            n = len(g.rows)
            if len(g.template) > _TEMPLATE_CLIP:
                body.append(f"{n:>6}  {g.template[:_TEMPLATE_CLIP]}...")
                continue
            line = f"{n:>6}  {g.template}"
            claims.append(Alike(g.template, n, 1, last))
            if with_slots:
                for s in _slots(data, g, data.knobs.value_rare):
                    if len(s.counts) < 2 or s.counts[0][1] < len(g.rows) / 2:  # a constant, or a counter
                        continue
                    line += f"  [<*>{s.k}: {', '.join(f'{v} {c}' for v, c in s.counts)}]"
                    claims += [Alike(g.template, c, 1, last, slot=s.k, value=v) for v, c in s.counts]
            body.append(line)
        if rest := data.groups[len(repeated[:cap]) :]:
            body.append(f"[+ {len(rest)} more templates, {sum(len(g.rows) for g in rest)} lines]")
        levels.append(Level(head, tuple(body), tuple(claims)))
    levels.append(Level(head, (), (total,)))
    return Part(Role.SHAPE, tuple(levels))


def count(data: LogData, /) -> Part:
    """The totals alone."""
    head, total = _total(data)
    return Part(Role.SHAPE, (Level(head, (), (total,)),))


# --- anomalies -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Odd:
    """Lines that break the shape: a whole template (slot 0), or the lines holding a rare value."""

    group: Group
    rows: tuple[int, ...]
    slot: int = 0
    value: str = ""


def _odd(data: LogData, rare: bool) -> list[_Odd]:
    """Rare templates, while common ones cover most lines (with `rare`), templates naming an error
    that few lines say, and rare values in a hole (with `rare`), in the order the log says them."""
    k, n = data.knobs, data.filled
    cut = max(1, int(k.rare * n))
    common = sum(len(g.rows) for g in data.groups if len(g.rows) > cut)
    out = []
    for g in data.groups:
        few = len(g.rows) <= cut and common >= k.common * n
        if (rare and few) or (len(g.rows) <= k.errors * n and ANOMALY_RE.search(g.template)):
            out.append(_Odd(g, g.rows))
        elif rare:
            for s in _slots(data, g, k.value_rare):
                for v in s.rare:
                    rows = tuple(i for i in g.rows if slots(data.lines[i])[s.k - 1] == v)
                    out.append(_Odd(g, rows, s.k, v))
    return sorted(out, key=lambda o: o.rows[0])


_ODD_LEVELS = ((25, 300), (12, 200), (5, 160), (1, 120))  # lines shown in all, characters of each


def _title(o: _Odd, last: int) -> tuple[str, Alike]:
    n = len(o.rows)
    if o.slot:
        return f"<*>{o.slot} is {o.value} in {_lines(n)} like: {o.group.template}", Alike(
            o.group.template, n, 1, last, slot=o.slot, value=o.value
        )
    return f"{_lines(n)} like: {o.group.template}", Alike(o.group.template, n, 1, last)


def _dealt(sizes: tuple[int, ...], cap: int) -> tuple[int, ...]:
    """How many lines of each group to show, `cap` in all: one of each in turn, then another."""
    share = [0] * len(sizes)
    while cap > 0 and any(s < n for s, n in zip(share, sizes, strict=True)):
        for i, n in enumerate(sizes):
            if cap > 0 and share[i] < n:
                share[i] += 1
                cap -= 1
    return tuple(share)


def _anomalies(data: LogData, odd: list[_Odd]) -> Part:
    if not odd:
        return Part(Role.ANOMALIES, (Level("none", ()),))
    last = len(data.lines)
    total = sum(len(o.rows) for o in odd)
    what = f"{_lines(total)} in {len(odd)} group{'s' if len(odd) > 1 else ''}"
    levels = []
    for cap, clip in _ODD_LEVELS:
        body: list[str] = []
        claims: list[Claim] = []
        share = _dealt(tuple(len(o.rows) for o in odd), cap)
        shown = sum(share)
        for o, k in zip(odd, share, strict=True):
            title, claim = _title(o, last)
            body.append(title)
            claims.append(claim)
            lines, said = numbered(data.lines, o.rows[:k], clip)
            body += [f"  {line}" for line in lines]
            claims += said
        listed = "all listed" if shown == total else f"{shown} listed"
        levels.append(Level(f"{what}, {listed}", tuple(body), tuple(claims)))
    titles = [_title(o, last) for o in odd]
    levels.append(Level(f"{what}, none listed", tuple(t for t, _ in titles), tuple(c for _, c in titles)))
    levels.append(Level(what, ()))
    return Part(Role.ANOMALIES, tuple(levels))


def rare(data: LogData, _shape: Part, /) -> Part:
    """Rare templates, error words few lines say, and rare values in a few-valued hole."""
    return _anomalies(data, _odd(data, rare=True))


def errors(data: LogData, _shape: Part, /) -> Part:
    """Templates naming an error that few lines say."""
    return _anomalies(data, _odd(data, rare=False))


def no_anomalies(_data: LogData, _shape: Part, /) -> Part:
    return nothing(Role.ANOMALIES)


# --- samples -------------------------------------------------------------------------------------------

_SAMPLE_LEVELS = ((15, 300), (8, 240), (4, 200), (2, 200))  # a sample is read for its values


def _listed(anomalies: Part) -> set[int]:
    """The lines (0-based) the fullest anomalies level shows."""
    return {
        c.first - 1 + k
        for c in anomalies.levels[0].claims
        if isinstance(c, Shows)
        for k in range(len(c.lines))
    }


def _samples(data: LogData, anomalies: Part, extra: tuple[int, ...]) -> Part:
    seen = _listed(anomalies)
    matched = tuple(i for i in query_rows(data.lines, data.terms) if i not in seen)
    picked = (*matched, *(i for i in extra if i not in seen and i not in matched))
    if not picked:
        return nothing(Role.SAMPLES)
    levels = []
    for cap, clip in _SAMPLE_LEVELS:
        rows = tuple(sorted(picked[:cap]))
        lines, claims = numbered(data.lines, rows, clip)
        head = f"{_lines(len(matched))} match{'es' if len(matched) == 1 else ''} the query" if matched else ""
        levels.append(Level(head, tuple(lines), tuple(claims)))
    levels.append(NOTHING)
    return Part(Role.SAMPLES, tuple(levels))


def matches(data: LogData, _shape: Part, anomalies: Part, /) -> Part:
    """Lines holding a query term few lines hold."""
    return _samples(data, anomalies, ())


def typical(data: LogData, _shape: Part, anomalies: Part, /) -> Part:
    """Those, and the first line of each of the three most common templates."""
    return _samples(data, anomalies, tuple(g.rows[0] for g in data.groups[:3]))


def head_tail(data: LogData, _shape: Part, anomalies: Part, /) -> Part:
    """Those, and the first three lines and the last two."""
    n = len(data.lines)
    return _samples(data, anomalies, (*range(min(3, n)), *range(max(3, n - 2), n)))


def no_samples(_data: LogData, _shape: Part, _anomalies: Part, /) -> Part:
    return nothing(Role.SAMPLES)


# --- nav -----------------------------------------------------------------------------------------------


def grep(data: LogData, _shape: Part, anomalies: Part, _samples: Part, /) -> Part:
    """For each whole template the anomalies list, a grep that prints exactly its lines; and sed."""
    found = []
    for c in anomalies.levels[0].claims:
        if isinstance(c, Alike) and not c.slot:
            rows = tuple(sorted(_rows_of(data, c.template)))
            if (cmd := grep_for(data.lines, rows, c.template)) is not None:
                found.append((f"{cmd.command}  (the {_lines(c.n)} like it)", cmd))
    levels = []
    for cap in (3, 1):
        picked = found[:cap]
        levels.append(Level("", (*(t for t, _ in picked), SED), tuple(c for _, c in picked)))
    levels.append(Level("", (SED,)))
    return Part(Role.NAV, tuple(levels))


def _rows_of(data: LogData, tmpl: str) -> frozenset[int]:
    return next((frozenset(g.rows) for g in data.groups if g.template == tmpl), frozenset())


_INDEX_GROUPS = (20, 8, 3)  # templates given a command, at each level


def index(data: LogData, _shape: Part, anomalies: Part, _samples: Part, /) -> Part:
    """A grep for every template said more than once and every anomaly's, each printing exactly its
    lines (most said first, the anomalies' first of all), and sed for any range."""
    odd = [c.template for c in anomalies.levels[0].claims if isinstance(c, Alike) and not c.slot]
    order = [*odd, *(g.template for g in data.groups if len(g.rows) > 1 and g.template not in odd)]
    found = []
    for tmpl in order[: _INDEX_GROUPS[0] * 2]:
        rows = tuple(sorted(_rows_of(data, tmpl)))
        if (cmd := grep_for(data.lines, rows, tmpl)) is not None:
            found.append((f"{cmd.command}  (the {_lines(len(rows))} like it)", cmd))
    levels = []
    for cap in _INDEX_GROUPS:
        picked = found[:cap]
        levels.append(Level("", (*(t for t, _ in picked), SED), tuple(c for _, c in picked)))
    levels.append(Level("", (SED,)))
    return Part(Role.NAV, tuple(levels))


def sed(_data: LogData, _shape: Part, _anomalies: Part, _samples: Part, /) -> Part:
    """How to read any lines."""
    return Part(Role.NAV, (Level("", (SED,)),))


def no_nav(_data: LogData, _shape: Part, _anomalies: Part, _samples: Part, /) -> Part:
    return nothing(Role.NAV)


SHAPES: Mapping[str, Shaper[LogData]] = {"templates": templates, "count": count}
ANOMALIES: Mapping[str, Spotter[LogData]] = {"rare": rare, "errors": errors, "none": no_anomalies}
SAMPLES: Mapping[str, Sampler[LogData]] = {
    "matches": matches,
    "typical": typical,
    "head-tail": head_tail,
    "none": no_samples,
}
NAVS: Mapping[str, Navigator[LogData]] = {"grep": grep, "sed": sed, "index": index, "none": no_nav}
_PRODUCERS = Producers(SHAPES, ANOMALIES, SAMPLES, NAVS)

# The views, as for JSON: sample shows samples from the ends and how to read any lines; schema the
# lines the query names and a command per anomaly.
PRESETS = {
    "sample": LogEnvelopeKnobs(shape="templates", anomalies="rare", samples="head-tail", nav="sed"),
    "schema": LogEnvelopeKnobs(shape="templates", anomalies="rare", samples="matches", nav="grep"),
    "full": LogEnvelopeKnobs(shape="templates", anomalies="rare", samples="typical", nav="grep"),
    "lean": LogEnvelopeKnobs(shape="count", anomalies="rare", samples="none", nav="grep"),
    "index": LogEnvelopeKnobs(shape="templates", anomalies="rare", samples="matches", nav="index"),
}


def recipe(k: LogEnvelopeKnobs, view: str = "sample") -> Recipe[LogData]:
    """The view's recipe, with each part a knob names in place of the view's (ValueError from
    `envelope.recipe_of` when a name is wrong)."""
    return recipe_of("log_envelope", _PRODUCERS, PRESETS, k, view)


def envelope(
    raw: str, terms: frozenset[str], budget_tokens: int, config: FoldConfig = DEFAULT, view: str = "sample"
) -> Envelope:
    """The envelope of a log within the budget, by the view's recipe and the parts `config` changes."""
    data = log_data(raw, terms, config.log_envelope)
    return compose(recipe(config.log_envelope, view), data, budget_tokens)
