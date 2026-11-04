"""A tree's envelope: an accessibility snapshot or another indented outline, or XML, read as lines.

    shape: 610 lines, 12 line templates (<*> is a token holding a digit, a hex id or a quoted string)
      3: - generic [ref=e75532]:
      6:   - main [ref=e69811]:
      8:     - list [ref=e46713]:
            200 items, lines 9-808
            200 items like: - listitem [ref=<*>]:
    anomalies: 7 of 200 items in 1 run, all listed
      7 lines like: - button <*> [ref=<*>] [disabled]  (in 7 of 200 items)
        21:       - listitem [ref=e24214]:
        24:         - button "Pay INV-64e32d4" [ref=e37425] [disabled]
    samples: ...
    get more:
      grep -nF '] [disabled]' FILE  (the 7 lines like it)
      sed -n 'A,Bp' FILE  (any lines above, by number)

A run is a node with many children most of whose first lines share a template: list items, rows,
cards. It is read as a log is (`compressors.envelope_log`), over its items' lines, but counted by
item: a line template few items hold, or a rare value in a hole most items fill with one value,
marks the items that hold it. The shape is the tree's headers, each run counted instead of shown;
the source is the raw text, or XML pretty-printed, whose line numbers the claims use.
"""

import bisect
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from compressors.common import ANOMALY_RE
from compressors.config import DEFAULT, FoldConfig, TreeEnvelopeKnobs
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
    few_valued,
    grep_for,
    groups,
    numbered,
    query_rows,
    slots,
    template,
)
from compressors.tree import Node

_QUOTED = True  # a tree's names and attribute values are quoted strings: holes, so like items match


@dataclass(frozen=True)
class Run:
    """A node's children, most of them alike: the items a list, a table or a grid holds."""

    parent: int  # the node's line (0-based), or -1 for the top level
    items: tuple[Node, ...]

    @property
    def first(self) -> int:
        return self.items[0].first

    @property
    def last(self) -> int:
        return self.items[-1].last


@dataclass(frozen=True)
class TreeData:
    lines: tuple[str, ...]
    roots: tuple[Node, ...]
    terms: frozenset[str]
    knobs: TreeEnvelopeKnobs
    runs: tuple[Run, ...]  # the outermost runs, in order
    templates: int  # distinct templates among the non-blank lines


def _is_run(lines: tuple[str, ...], nodes: tuple[Node, ...], k: TreeEnvelopeKnobs) -> bool:
    if len(nodes) < k.min_items:
        return False
    top = Counter(template(lines[n.first], _QUOTED) for n in nodes).most_common(1)[0][1]
    return top >= k.alike * len(nodes)


def tree_data(
    lines: tuple[str, ...], roots: tuple[Node, ...], terms: frozenset[str], knobs: TreeEnvelopeKnobs
) -> TreeData:
    runs: list[Run] = []
    pending = [(-1, roots)]
    while pending:
        parent, nodes = pending.pop()
        if _is_run(lines, nodes, knobs):
            runs.append(Run(parent, nodes))
        else:
            pending += [(n.first, n.children) for n in reversed(nodes)]
    k = len({template(line, _QUOTED) for line in lines if line.strip()})
    return TreeData(lines, roots, terms, knobs, tuple(sorted(runs, key=lambda r: r.first)), k)


def _item_at(data: TreeData, i: int) -> tuple[Run, int] | None:
    """The run and item index holding line i (0-based), if a run does."""
    starts = [r.first for r in data.runs]
    k = bisect.bisect_right(starts, i) - 1
    if k < 0 or i > data.runs[k].last:
        return None
    run = data.runs[k]
    j = bisect.bisect_right([n.first for n in run.items], i) - 1
    return (run, j) if j >= 0 and i <= run.items[j].last else None


def _lines(n: int, what: str = "line") -> str:
    return f"{n} {what}" if n == 1 else f"{n} {what}s"


# --- shape ---------------------------------------------------------------------------------------------

_OUTLINE_LEVELS = ((80, 12, 300), (40, 6, 200), (20, 4, 160), (10, 2, 120))  # headers, depth, clip


def _total(data: TreeData) -> tuple[str, Total]:
    n, k = len(data.lines), data.templates
    kinds = f"{k} line template{'' if k == 1 else 's'}"
    rule = "<*> is a token holding a digit, a hex id or a quoted string"
    return f"{_lines(n)}, {kinds} ({rule})", Total(n, k, quoted=_QUOTED)


def _summary(data: TreeData, run: Run, indent: str) -> tuple[list[str], list[Claim]]:
    counts = Counter(template(data.lines[n.first], _QUOTED) for n in run.items)
    body = [f"{indent}{len(run.items)} items, lines {run.first + 1}-{run.last + 1}"]
    claims: list[Claim] = []
    for tmpl, k in counts.most_common(3):
        body.append(f"{indent}{_lines(k, 'item')} like: {tmpl.strip()}")
        claims.append(Alike(tmpl, k, run.first + 1, run.last + 1, quoted=_QUOTED))
    if len(counts) > 3:
        body.append(f"{indent}[+ {len(counts) - 3} more kinds of item]")
    return body, claims


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def outline(data: TreeData, /) -> Part:
    """The tree's headers to a depth, each at its number, and each run counted by its kinds of item."""
    head, total = _total(data)
    under = {r.parent: r for r in data.runs}
    levels = []
    for cap, depth, clip in _OUTLINE_LEVELS:
        body: list[str] = []
        claims: list[Claim] = [total]
        left = 0
        if (top := under.get(-1)) is not None:
            s, c = _summary(data, top, "")
            body += s
            claims += c
        pending = [(n, 0) for n in reversed(data.roots)] if top is None else []
        while pending:
            n, d = pending.pop()
            if len(body) >= cap or d > depth:
                left += 1
                continue
            text, said = numbered(data.lines, (n.first,), clip)
            body += text
            claims += said
            if (run := under.get(n.first)) is not None:
                s, c = _summary(data, run, _indent(data.lines[n.first]) + "      ")
                body += s
                claims += c
            else:
                pending += [(c, d + 1) for c in reversed(n.children)]
        if left:
            body.append(f"[+ {left} more nodes, deeper or further on]")
        levels.append(Level(head, tuple(body), tuple(claims)))
    levels.append(Level(head, (), (total,)))
    return Part(Role.SHAPE, tuple(levels))


# --- anomalies -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Odd:
    """Lines of a run's items that break its shape: a template few items hold (slot 0), or the
    lines holding a rare value in a hole."""

    run: Run
    template: str
    rows: tuple[int, ...]
    items: tuple[int, ...]  # the items holding them, by index in the run
    slot: int = 0
    value: str = ""


def _owners(run: Run, rows: tuple[int, ...]) -> tuple[int, ...]:
    starts = [n.first for n in run.items]
    return tuple(sorted({bisect.bisect_right(starts, i) - 1 for i in rows}))


def _odd_in(data: TreeData, run: Run, rare: bool) -> list[_Odd]:
    k, n = data.knobs, len(run.items)
    rows = range(run.first, run.last + 1)
    gs = groups(data.lines, rows, _QUOTED)
    cut = max(1, int(k.rare * n))
    held = {g.template: _owners(run, g.rows) for g in gs}
    common = sum(len(g.rows) for g in gs if len(held[g.template]) > cut)
    out = []
    for g in gs:
        items = held[g.template]
        few = len(items) <= cut and common >= k.common * len(rows)
        if (rare and few) or (len(items) <= k.errors * n and ANOMALY_RE.search(g.template)):
            out.append(_Odd(run, g.template, g.rows, items))
        elif rare:
            out += _odd_values(data, run, g)
    return out


def _odd_values(data: TreeData, run: Run, g: Group) -> list[_Odd]:
    k = data.knobs
    out = []
    found = few_valued(
        data.lines, g, _QUOTED, few=k.few, dominant=k.dominant, rare=k.rare, min_rows=k.min_items, clip=40
    )
    for s in found:
        for v in s.rare:
            rows = tuple(i for i in g.rows if slots(data.lines[i], _QUOTED)[s.k - 1] == v)
            out.append(_Odd(run, g.template, rows, _owners(run, rows), s.k, v))
    return out


def _odd(data: TreeData, rare: bool) -> list[_Odd]:
    return sorted((o for run in data.runs for o in _odd_in(data, run, rare)), key=lambda o: o.rows[0])


_ODD_LEVELS = ((20, 300), (10, 200), (5, 160), (2, 120))  # items shown in all, characters of a line


def _title(o: _Odd) -> tuple[str, Alike]:
    a, b = o.run.first + 1, o.run.last + 1
    where = f"  (in {len(o.items)} of {len(o.run.items)} items)"
    if o.slot:
        title = f"<*>{o.slot} is {o.value} in {_lines(len(o.rows))} like: {o.template.strip()}{where}"
        return title, Alike(o.template, len(o.rows), a, b, quoted=_QUOTED, slot=o.slot, value=o.value)
    title = f"{_lines(len(o.rows))} like: {o.template.strip()}{where}"
    return title, Alike(o.template, len(o.rows), a, b, quoted=_QUOTED)


def _dealt(sizes: tuple[int, ...], cap: int) -> tuple[int, ...]:
    """How many items of each anomaly to show, `cap` in all: one of each in turn, then another."""
    share = [0] * len(sizes)
    while cap > 0 and any(s < n for s, n in zip(share, sizes, strict=True)):
        for i, n in enumerate(sizes):
            if cap > 0 and share[i] < n:
                share[i] += 1
                cap -= 1
    return tuple(share)


def _shown(data: TreeData, o: _Odd, k: int, clip: int) -> tuple[list[str], list[Claim]]:
    """The first k items of an anomaly: each item's first line, then its odd lines."""
    picked = set(o.items[:k])
    rows: set[int] = set()
    for i in o.rows:
        if (j := bisect.bisect_right([n.first for n in o.run.items], i) - 1) in picked:
            rows |= {o.run.items[j].first, i}
    body, claims = numbered(data.lines, tuple(sorted(rows)), clip)
    return [f"  {line}" for line in body], list(claims)


def _anomalies(data: TreeData, odd: list[_Odd]) -> Part:
    if not odd:
        return Part(Role.ANOMALIES, (Level("none", ()),))
    marked = {(id(o.run), j) for o in odd for j in o.items}
    items = sum(len(r.items) for r in data.runs if any(o.run is r for o in odd))
    runs = len({id(o.run) for o in odd})
    what = f"{len(marked)} of {items} items in {_lines(runs, 'run')}"
    levels = []
    for cap, clip in _ODD_LEVELS:
        share = _dealt(tuple(len(o.items) for o in odd), cap)
        body: list[str] = []
        claims: list[Claim] = []
        for o, k in zip(odd, share, strict=True):
            title, claim = _title(o)
            body.append(title)
            claims.append(claim)
            lines, said = _shown(data, o, k, clip)
            body += lines
            claims += said
        listed = (
            "all listed" if all(k == len(o.items) for o, k in zip(odd, share, strict=True)) else "some listed"
        )
        levels.append(Level(f"{what}, {listed}", tuple(body), tuple(claims)))
    titles = [_title(o) for o in odd]
    levels.append(Level(f"{what}, none listed", tuple(t for t, _ in titles), tuple(c for _, c in titles)))
    levels.append(Level(what, ()))
    return Part(Role.ANOMALIES, tuple(levels))


def rare(data: TreeData, _shape: Part, /) -> Part:
    """Items holding a line template few items hold, an error word, or a rare value in a hole."""
    return _anomalies(data, _odd(data, rare=True))


def errors(data: TreeData, _shape: Part, /) -> Part:
    """Items holding a line that names an error, when few items do."""
    return _anomalies(data, _odd(data, rare=False))


def no_anomalies(_data: TreeData, _shape: Part, /) -> Part:
    return nothing(Role.ANOMALIES)


# --- samples -------------------------------------------------------------------------------------------

_SAMPLE_LEVELS = ((8, 300), (4, 240), (2, 200), (1, 200))  # blocks shown, characters of a line
_BLOCK = 12  # an item longer than this many lines is shown by its first line and the lines asked for,
_BLOCK_LINES = 40  # and no more than this many lines of one item


def _listed(anomalies: Part) -> set[int]:
    return {
        c.first - 1 + k
        for c in anomalies.levels[0].claims
        if isinstance(c, Shows)
        for k in range(len(c.lines))
    }


def _blocks(data: TreeData, picked: tuple[int, ...]) -> list[tuple[int, ...]]:
    """The lines (0-based) to show for the picked lines, one block per item, in order: a short item
    whole, a long one by its first line and the lines picked in it; a line no run holds, alone."""
    by: dict[tuple[int, int], set[int]] = {}
    for i in picked:
        found = _item_at(data, i)
        if found is None:
            by.setdefault((i, -1), set()).add(i)
            continue
        item = found[0].items[found[1]]
        rows = range(item.first, item.last + 1) if item.last - item.first < _BLOCK else (item.first, i)
        by.setdefault((item.first, item.last), set()).update(rows)
    return [
        tuple(sorted(rows)[:_BLOCK_LINES])
        for _, rows in sorted(by.items(), key=lambda kv: picked.index(min(kv[1] & set(picked))))
    ]


def _samples(data: TreeData, anomalies: Part, extra: tuple[int, ...]) -> Part:
    seen = _listed(anomalies)
    matched = tuple(i for i in query_rows(data.lines, data.terms) if i not in seen)
    picked = (*matched, *(i for i in extra if i not in matched))
    blocks = [b for b in (tuple(r for r in b if r not in seen) for b in _blocks(data, picked)) if b]
    if not blocks:
        return nothing(Role.SAMPLES)
    head = f"{_lines(len(matched))} match{'es' if len(matched) == 1 else ''} the query" if matched else ""
    levels = []
    for cap, clip in _SAMPLE_LEVELS:
        rows = tuple(sorted(r for b in blocks[:cap] for r in b))
        body, claims = numbered(data.lines, rows, clip)
        levels.append(Level(head, tuple(body), tuple(claims)))
    levels.append(NOTHING)
    return Part(Role.SAMPLES, tuple(levels))


def matches(data: TreeData, _shape: Part, anomalies: Part, /) -> Part:
    """The items holding a query term few lines hold."""
    return _samples(data, anomalies, ())


def typical(data: TreeData, _shape: Part, anomalies: Part, /) -> Part:
    """Those, and the first item of each run."""
    return _samples(data, anomalies, tuple(r.first for r in data.runs))


def head_tail(data: TreeData, _shape: Part, anomalies: Part, /) -> Part:
    """Those, and the first two items of each run and its last."""
    picked = tuple(n.first for r in data.runs for n in (*r.items[:2], r.items[-1]))
    return _samples(data, anomalies, picked)


def no_samples(_data: TreeData, _shape: Part, _anomalies: Part, /) -> Part:
    return nothing(Role.SAMPLES)


# --- nav -----------------------------------------------------------------------------------------------


def grep(data: TreeData, _shape: Part, anomalies: Part, _samples: Part, /) -> Part:
    """For each line template the anomalies name, a grep that prints exactly its lines; and sed."""
    found = []
    by = {g.template: g.rows for g in groups(data.lines, range(len(data.lines)), _QUOTED)}
    for c in anomalies.levels[0].claims:
        if not isinstance(c, Alike) or c.slot or c.template not in by:
            continue
        if (cmd := grep_for(data.lines, by[c.template], c.template)) is not None:
            found.append((f"{cmd.command}  (the {_lines(len(cmd.lines))} like it)", cmd))
    levels = []
    for cap in (3, 1):
        picked = found[:cap]
        levels.append(Level("", (*(t for t, _ in picked), SED), tuple(c for _, c in picked)))
    levels.append(Level("", (SED,)))
    return Part(Role.NAV, tuple(levels))


def sed(_data: TreeData, _shape: Part, _anomalies: Part, _samples: Part, /) -> Part:
    """How to read any lines."""
    return Part(Role.NAV, (Level("", (SED,)),))


def no_nav(_data: TreeData, _shape: Part, _anomalies: Part, _samples: Part, /) -> Part:
    return nothing(Role.NAV)


SHAPES: Mapping[str, Shaper[TreeData]] = {"outline": outline}
ANOMALIES: Mapping[str, Spotter[TreeData]] = {"rare": rare, "errors": errors, "none": no_anomalies}
SAMPLES: Mapping[str, Sampler[TreeData]] = {
    "matches": matches,
    "typical": typical,
    "head-tail": head_tail,
    "none": no_samples,
}
NAVS: Mapping[str, Navigator[TreeData]] = {"grep": grep, "sed": sed, "none": no_nav}
_PRODUCERS = Producers(SHAPES, ANOMALIES, SAMPLES, NAVS)

PRESETS = {
    "sample": TreeEnvelopeKnobs(shape="outline", anomalies="rare", samples="head-tail", nav="sed"),
    "schema": TreeEnvelopeKnobs(shape="outline", anomalies="rare", samples="matches", nav="grep"),
}


def recipe(k: TreeEnvelopeKnobs, view: str = "sample") -> Recipe[TreeData]:
    """The view's recipe, with each part a knob names in place of the view's (ValueError from
    `envelope.recipe_of` when a name is wrong)."""
    return recipe_of("tree_envelope", _PRODUCERS, PRESETS, k, view)


def envelope(
    lines: tuple[str, ...],
    roots: tuple[Node, ...],
    terms: frozenset[str],
    budget_tokens: int,
    config: FoldConfig = DEFAULT,
    view: str = "sample",
) -> Envelope:
    """The envelope of a tree (its source lines and nodes) within the budget, by the view's recipe and
    the parts `config` changes."""
    data = tree_data(lines, roots, terms, config.tree_envelope)
    return compose(recipe(config.tree_envelope, view), data, budget_tokens)
