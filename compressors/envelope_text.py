"""What every envelope of lines shares: templates and their slots, numbered lines, and commands.

Logs, trees, code and documents are read as the lines of a source text: the raw output, or a copy
of it pretty-printed or converted to text, which the hook saves beside it. Their envelopes address
everything by line number, as `sed -n` and `grep -n` count lines, and their claims
(`compressors.envelope`: Shows, Total, Alike, Prints) are checked against that text.

A line's template is the line with every token (a run of letters, digits, `_` and `-`) that holds a
digit or a part of six or more hex digits (a number, an id, a time, a negative number), and every
quoted string when `quoted`, replaced by <*>. Lines that differ only there say the same thing,
so a template's count is how often the source says it, and the values in one hole, its slot, are
the data's fields: few of them and one dominant, and the lines holding a rare one stand out.
"""

import re
import shlex
from collections import Counter
from dataclasses import dataclass

from compressors import markers
from compressors.common import discriminating, matches
from compressors.envelope import Prints, Shows

HOLE = "<*>"
_TOKEN = re.compile(r"[A-Za-z0-9_-]+")
_QUOTED_TOKEN = re.compile(r'"[^"\n]*"|[A-Za-z0-9_-]+')
_HOLE = re.compile(r"[0-9]|(?:^|[-_])[0-9a-fA-F]{6,}(?:$|[-_])")  # a digit, or a hex id: u-ebbadf
SED = "sed -n 'A,Bp' FILE  (any lines above, by number)"
FAR = "a number far from the rest"  # why an outlier is listed


_NOT_PROOF = "which is not proof there are none"


def none_found(rules: str) -> str:
    """The head of an anomalies part that found nothing: what its rules looked for, and that their
    finding nothing does not mean the data holds nothing (a model read a bare "none" as a fact)."""
    return f"none found by its rules ({rules}), {_NOT_PROOF}"


_MEASURE = re.compile(r"-?[0-9]{6,}")


def _holes(line: str, quoted: bool) -> list[re.Match[str]]:
    tokens = (_QUOTED_TOKEN if quoted else _TOKEN).finditer(line.rstrip())
    return [m for m in tokens if m[0].startswith('"') or _HOLE.search(m[0])]


def template(line: str, quoted: bool = False) -> str:
    """The line with its holes as <*> (trailing white space dropped)."""
    text, out, at = line.rstrip(), [], 0
    for m in _holes(text, quoted):
        out += [text[at : m.start()], HOLE]
        at = m.end()
    return "".join([*out, text[at:]])


def slots(line: str, quoted: bool = False) -> list[str]:
    """What the line's holes hold, in order."""
    return [m[0] for m in _holes(line, quoted)]


@dataclass(frozen=True)
class Group:
    """Lines (0-based) with one template."""

    template: str
    rows: tuple[int, ...]


def groups(lines: tuple[str, ...], rows: range | tuple[int, ...], quoted: bool = False) -> tuple[Group, ...]:
    """The non-blank lines among `rows`, by template: most lines first, then first seen."""
    by: dict[str, list[int]] = {}
    for i in rows:
        if lines[i].strip():
            by.setdefault(template(lines[i], quoted), []).append(i)
    ordered = sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[1][0]))
    return tuple(Group(t, tuple(r)) for t, r in ordered)


@dataclass(frozen=True)
class Slot:
    """One hole of a group's template that holds few values: their counts, most first."""

    k: int  # counted from 1
    counts: tuple[tuple[str, int], ...]
    rare: tuple[str, ...]  # values few lines hold while one dominates


def few_valued(
    lines: tuple[str, ...],
    g: Group,
    quoted: bool,
    *,
    few: int,
    dominant: float,
    rare: float,
    min_rows: int,
    clip: int,
) -> tuple[Slot, ...]:
    """The holes of a group holding at most `few` values (none longer than `clip`, and none a number of
    six or more digits, which measures something: a size, a time), in a group of at least `min_rows`
    lines. A value is rare when at most `rare` of the lines hold it and the most
    common value holds at least `dominant` of them."""
    n = len(g.rows)
    if n < min_rows:
        return ()
    held = [slots(lines[i], quoted) for i in g.rows]
    out = []
    for k in range(min(len(h) for h in held)):
        counts = Counter(h[k] for h in held)
        if len(counts) > few or any(len(v) > clip or _MEASURE.fullmatch(v) for v in counts):
            continue
        top = counts.most_common()
        cut = max(1, int(rare * n))
        odd = tuple(v for v, c in top if c <= cut) if top[0][1] / n >= dominant else ()
        out.append(Slot(k + 1, tuple(top), odd))
    return tuple(out)


_INT = re.compile(r"-?[0-9]+")
_OUTLIER_IQR = 3.0  # a number beyond this many interquartile ranges of the middle half stands out,
_OUTLIER_FLOOR = 10  # as does a zero or a negative where every other value is at least this


@dataclass(frozen=True)
class Outlier:
    """A hole of a group's template whose numbers include some far from the rest."""

    k: int  # counted from 1
    values: tuple[str, ...]  # the outlying values, as written


def _quartiles(xs: list[int]) -> tuple[float, float]:
    s = sorted(xs)
    n = len(s)

    def at(q: float) -> float:
        i = q * (n - 1)
        lo = int(i)
        return s[lo] + (s[min(lo + 1, n - 1)] - s[lo]) * (i - lo)

    return at(0.25), at(0.75)


def outlying(
    lines: tuple[str, ...], g: Group, quoted: bool, *, rare: float, min_rows: int
) -> tuple[Outlier, ...]:
    """The holes of a group whose every value is a whole number of fewer than six digits (longer
    ones are times, sizes and ids), in a group of at least `min_rows` lines, where few lines (at most
    `rare` of them) hold a number far from the rest: beyond three interquartile ranges of the middle
    half, or a zero or a negative where every other value is at least 10 (a $0.00 amount, a pool at
    0; a timestamp's :00 has neighbours from 1 to 59)."""
    n = len(g.rows)
    if n < min_rows:
        return ()
    held = [slots(lines[i], quoted) for i in g.rows]
    cut = max(1, int(rare * n))
    out = []
    for k in range(min(len(h) for h in held)):
        texts = [h[k] for h in held]
        if not all(_INT.fullmatch(x) and not _MEASURE.fullmatch(x) for x in texts):
            continue  # not numbers, or numbers of six digits or more: times, sizes and ids
        xs = [int(x) for x in texts]
        q1, q3 = _quartiles(xs)
        spread = q3 - q1
        odd: set[str] = set()
        if spread > 0:
            lo, hi = q1 - _OUTLIER_IQR * spread, q3 + _OUTLIER_IQR * spread
            odd |= {x for x, v in zip(texts, xs, strict=True) if v < lo or v > hi}
        positive = [v for v in xs if v > 0]
        if 0 < len(positive) < len(xs) and min(positive) >= _OUTLIER_FLOOR:
            odd |= {x for x, v in zip(texts, xs, strict=True) if v <= 0}
        counts = Counter(texts)
        flagged = tuple(sorted((x for x in odd if counts[x] <= cut), key=texts.index))
        if flagged and sum(counts[x] for x in flagged) <= cut:
            out.append(Outlier(k + 1, flagged))
    return tuple(out)


def numbered(lines: tuple[str, ...], rows: tuple[int, ...], clip: int) -> tuple[list[str], list[Shows]]:
    """The rows (0-based) as numbered lines, `412: text`, and what they claim: one Shows per run of
    consecutive rows."""
    body: list[str] = []
    claims: list[Shows] = []
    run: list[str] = []
    start = -1
    for k, i in enumerate(rows):
        text = markers.clipped(lines[i], clip)
        body.append(f"{i + 1}: {text}")
        if run and i == rows[k - 1] + 1:
            run.append(text)
        else:
            if run:
                claims.append(Shows(start + 1, tuple(run)))
            run, start = [text], i
    if run:
        claims.append(Shows(start + 1, tuple(run)))
    return body, claims


def query_rows(lines: tuple[str, ...], terms: frozenset[str], share: float = 0.05) -> tuple[int, ...]:
    """Lines holding a query term that at most `share` of the non-blank lines hold."""
    filled = [i for i, line in enumerate(lines) if line.strip()]
    useful = discriminating(terms, [lines[i] for i in filled], share=share)
    if not useful:
        return ()
    return tuple(i for i in filled if any(matches(lines[i], t) for t in useful))


def grep_for(lines: tuple[str, ...], rows: tuple[int, ...], tmpl: str, min_len: int = 4) -> Prints | None:
    """A `grep -nF` command that prints exactly these rows: the longest literal piece of their
    template that no other line holds, or None when no piece does."""
    want = set(rows)
    pieces = sorted({p.strip() for p in tmpl.split(HOLE) if len(p.strip()) >= min_len}, key=len, reverse=True)
    for piece in pieces[:8]:
        if "\n" in piece or "'" in piece:
            continue
        if {i for i, line in enumerate(lines) if piece in line} == want:
            dash = " -e" if piece.startswith("-") else ""  # else grep reads the pattern as an option
            return Prints(f"grep -nF{dash} {shlex.quote(piece)} FILE", tuple(i + 1 for i in sorted(rows)))
    return None
