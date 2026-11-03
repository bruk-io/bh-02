"""Line-oriented text (logs, build output, grep hits): dedupe runs, keep head, tail and windows.

Runs of lines that differ only in numbers or hex (timestamps, counters, ids) collapse to one line
and a count. Of the runs, the first `head` and last `tail` are kept, plus a window around every run
that carries an anomaly word or a query term. Every gap says which original lines it hides, so the
model can ask for them by number.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from compressors.common import ANOMALY_RE, discriminating, matches, split_lines

_VARIABLE = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8,}|\d+")


@dataclass(frozen=True)
class _Run:
    first: int  # 0-based index of the first line in the run
    last: int  # 0-based index of the last line in the run
    line: str  # the first line, as written


def _normalise(line: str) -> str:
    return _VARIABLE.sub("#", line.strip())


def _runs_of(lines: list[str]) -> list[_Run]:
    runs: list[_Run] = []
    prev_norm: str | None = None
    for i, line in enumerate(lines):
        norm = _normalise(line)
        if runs and norm == prev_norm:
            runs[-1] = _Run(runs[-1].first, i, runs[-1].line)
        else:
            runs.append(_Run(i, i, line))
        prev_norm = norm
    return runs


def _is_signal(line: str, terms: Iterable[str]) -> bool:
    if ANOMALY_RE.search(line):
        return True
    return any(matches(line, t) for t in terms)


def _choose_runs(
    runs: list[_Run], terms: frozenset[str], *, head: int, tail: int, window: int, max_window_runs: int
) -> tuple[list[int], int]:
    """Indices of the runs to keep, and how many signal runs did not fit."""
    n = len(runs)
    terms = discriminating(terms, [r.line for r in runs])
    keep = set(range(min(head, n))) | set(range(max(0, n - tail), n))
    added = 0
    dropped_signals = 0
    for i, run in enumerate(runs):
        if not _is_signal(run.line, terms):
            continue
        span = set(range(max(0, i - window), min(n, i + window + 1))) - keep
        if added + len(span) > max_window_runs:
            dropped_signals += 1
            continue
        keep |= span
        added += len(span)
    return sorted(keep), dropped_signals


def _clip(line: str, max_chars: int) -> str:
    if len(line) <= max_chars:
        return line
    return line[:max_chars] + f"...[+{len(line) - max_chars} chars]"


def _render_run(run: _Run, max_chars: int) -> list[str]:
    out = [_clip(run.line, max_chars)]
    if run.last > run.first:
        count = run.last - run.first
        out.append(
            f"[... same line pattern repeated {count} more times, lines {run.first + 2}-{run.last + 1}]"
        )
    return out


def fold_lines(
    raw: str,
    terms: frozenset[str] = frozenset(),
    *,
    head: int = 15,
    tail: int = 25,
    window: int = 3,
    max_window_runs: int = 60,
    max_line_chars: int = 400,
) -> str:
    lines = split_lines(raw)
    runs = _runs_of(lines)
    kept, dropped_signals = _choose_runs(
        runs, terms, head=head, tail=tail, window=window, max_window_runs=max_window_runs
    )
    out: list[str] = []
    prev: int | None = None
    for idx in kept:
        if prev is not None and idx > prev + 1:
            gap_first = runs[prev + 1].first
            gap_last = runs[idx - 1].last
            out.append(
                f"[... lines {gap_first + 1}-{gap_last + 1} omitted ({gap_last - gap_first + 1} lines)]"
            )
        out.extend(_render_run(runs[idx], max_line_chars))
        prev = idx
    if dropped_signals:
        out.append(f"[{dropped_signals} more lines matching error words or the query were omitted; use grep]")
    return "\n".join(out)
