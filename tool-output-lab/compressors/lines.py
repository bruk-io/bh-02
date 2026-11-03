"""Line-oriented text (logs, build output, grep hits): dedupe runs, keep head, tail and windows.

Runs of lines that differ only in numbers or hex (timestamps, counters, ids) collapse to one line
and a count. Of the runs, the first `head` and last `tail` are kept, plus a window around every run
that carries an anomaly word or a query term. Every gap says which original lines it hides, so the
model can ask for them by number.
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from compressors import markers
from compressors.common import ANOMALY_RE, discriminating, estimate_tokens, matches, split_lines

_VARIABLE = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8,}|\d+")


@dataclass(frozen=True)
class _Run:
    first: int  # 0-based index of the first line in the run
    last: int  # 0-based index of the last line in the run
    line: str  # the first line, as written
    rare: bool = False  # a value its run's lines almost never hold, in a slot with few values


def _normalise(line: str) -> str:
    return _VARIABLE.sub("#", line.strip())


def _rare_lines(lines: list[str], first: int, last: int) -> set[int]:
    """Lines of one run (same shape, numbers aside) holding a rare value in a categorical slot:
    a slot (the k-th number) with few distinct values, one of them dominant, such as a status
    code, an exit code or a failure count. Slots with many values (times, sizes, ids) say nothing."""
    n = last - first + 1
    if n < 10:
        return set()
    slots = [_VARIABLE.findall(lines[i].strip()) for i in range(first, last + 1)]
    rare: set[int] = set()
    for k in range(min(len(s) for s in slots)):
        counts = Counter(s[k] for s in slots)
        if len(counts) > 10 or counts.most_common(1)[0][1] / n < 0.8:
            continue
        cut = max(1, int(0.02 * n))
        rare |= {first + j for j, s in enumerate(slots) if counts[s[k]] <= cut}
    return rare


def _runs_of(lines: list[str]) -> list[_Run]:
    """Consecutive lines of the same shape (numbers aside) as one run each, except that a line with
    a rare value in a categorical slot (one 500 among 200s) is a run of its own, and stands out."""
    groups: list[tuple[int, int]] = []
    prev_norm: str | None = None
    for i, line in enumerate(lines):
        norm = _normalise(line)
        if groups and norm == prev_norm:
            groups[-1] = (groups[-1][0], i)
        else:
            groups.append((i, i))
        prev_norm = norm
    runs: list[_Run] = []
    for first, last in groups:
        rare = _rare_lines(lines, first, last)
        start = first
        for i in sorted(rare):
            if i > start:
                runs.append(_Run(start, i - 1, lines[start]))
            runs.append(_Run(i, i, lines[i], rare=True))
            start = i + 1
        if start <= last:
            runs.append(_Run(start, last, lines[start]))
    return runs


def _is_signal(line: str, terms: Iterable[str]) -> bool:
    if ANOMALY_RE.search(line):
        return True
    return any(matches(line, t) for t in terms)


def _choose_runs(
    runs: list[_Run], terms: frozenset[str], *, head: int, tail: int, window: int, max_window_runs: int
) -> tuple[list[int], int]:
    """Indices of the runs to keep, and how many signal lines are hidden.

    A signal's window is kept when it fits; otherwise the signal's own line, when that fits."""
    n = len(runs)
    terms = discriminating(terms, [r.line for r in runs])
    keep = set(range(min(head, n))) | set(range(max(0, n - tail), n))
    added = 0
    hidden_signals = 0
    for i, run in enumerate(runs):
        if not (run.rare or _is_signal(run.line, terms)):
            continue
        span = set(range(max(0, i - window), min(n, i + window + 1))) - keep
        if added + len(span) > max_window_runs:
            span = {i} - keep
        if added + len(span) > max_window_runs:
            if i not in keep:
                hidden_signals += run.last - run.first + 1
            continue
        keep |= span
        added += len(span)
    return sorted(keep), hidden_signals


def _render_run(run: _Run, max_chars: int) -> list[str]:
    out = [markers.clipped(run.line, max_chars)]
    if run.last > run.first:
        count = run.last - run.first
        out.append(markers.repeated(count, run.first + 2, run.last + 1))
    return out


@dataclass(frozen=True)
class _Limits:
    head: int
    tail: int
    window: int
    max_window_runs: int
    max_line_chars: int


# tried in order until the fold fits the budget; the last is the floor
_LEVELS = (
    _Limits(15, 25, 3, 60, 400),
    _Limits(10, 15, 2, 40, 240),
    _Limits(6, 8, 1, 24, 160),
    _Limits(3, 4, 0, 12, 120),
    _Limits(2, 2, 0, 6, 80),
)


def _fold_once(runs: list[_Run], terms: frozenset[str], lim: _Limits) -> str:
    kept, hidden_signals = _choose_runs(
        runs, terms, head=lim.head, tail=lim.tail, window=lim.window, max_window_runs=lim.max_window_runs
    )
    out: list[str] = []
    prev: int | None = None
    for idx in kept:
        if prev is not None and idx > prev + 1:
            gap_first = runs[prev + 1].first
            gap_last = runs[idx - 1].last
            out.append(markers.lines_omitted(gap_first + 1, gap_last + 1))
        out.extend(_render_run(runs[idx], lim.max_line_chars))
        prev = idx
    if hidden_signals:
        out.append(markers.signals_hidden(hidden_signals))
    return "\n".join(out)


def fold_lines(raw: str, terms: frozenset[str] = frozenset(), budget_tokens: int | None = None) -> str:
    """The folded lines, at the loosest level of limits that fits the budget (no budget: the first)."""
    runs = _runs_of(split_lines(raw))
    text = ""
    for lim in _LEVELS:
        text = _fold_once(runs, terms, lim)
        if budget_tokens is None or estimate_tokens(text) <= budget_tokens:
            break
    return text
