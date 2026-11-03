"""Layer 1: fold every eval task with the `fold` interface itself and check it, with no model.

    ./lab evals l1 [--budget 2000] [--only FORMAT ...] [--name l1-1]

For each task, fold the payload (with no query, and again with the task's query when it has one)
through `compressors.cli.fold_text`, then check:

- invariants (any failure is a bug):
  - coverage: walking the output accounts for every source line exactly once, shown at its own
    number or inside exactly one marker;
  - JSON markers: every `_folded` path and slice, read back with `resolve`, holds the count it
    claims;
  - the output is no larger than the input, and folding twice gives the same text;
- sufficiency: the task's own scorer, run on the fold text (can the answer be read off it?);
- size: tokens in and out, and whether the output fits the budget.

Writes `results/<name>.md` and `results/<name>.jsonl`.
"""

import argparse
import json
import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from compressors import markers
from compressors.cli import fold_text
from compressors.code import language_for
from compressors.common import estimate_tokens, split_lines
from compressors.json_fold import parse_json_or_jsonl
from compressors.recovery import RecoveryError, resolve
from compressors.route import detect
from evals.tasks import BUDGET, FORMATS, Task, tasks
from evals.truth import score_fold

_LAB = Path(__file__).resolve().parent.parent
_MARKER, _INLINE, _CLIPPED, _NOTE = markers.LINE_RANGE, markers.INLINE, markers.CLIPPED, markers.NOTE
_JSON_FOLD, _JSON_KEYS = markers.JSON_SLICE, markers.JSON_KEYS


def _same(shown: str, source: str) -> bool:
    m = _CLIPPED.search(shown)
    if m is None:
        return shown == source
    head = shown[: m.start()]
    return source.startswith(head) and len(source) - len(head) == int(m[1])


def coverage(source: str, out: str, numbered: bool) -> list[str]:
    """Problems with how the output accounts for the source's lines; empty when every line is
    shown at its place or inside exactly one marker."""
    src = split_lines(source)
    problems: list[str] = []
    i = 0  # the next source line (0-based) the output must account for
    for k, line in enumerate(split_lines(out)):
        if _NOTE.match(line.strip()):
            continue
        if (m := _MARKER.match(line.strip())) is not None:
            a, b = int(m[1]), int(m[2])
            if a != i + 1 or b < a:
                problems.append(f"output line {k + 1}: marker hides {a}-{b}, expected it to start at {i + 1}")
            i = max(i, b)
            continue
        text = line
        if numbered:
            n = re.match(r"^(\d+)\t", line)
            if n is None or int(n[1]) != i + 1:
                problems.append(f"output line {k + 1}: expected source line {i + 1}, got {line[:60]!r}")
                return problems
            text = line[n.end() :]
        inline = _INLINE.search(text)
        if inline is not None:
            text = text[: inline.start()]
        if i >= len(src) or not _same(text, src[i]):
            problems.append(f"output line {k + 1}: not source line {i + 1}: {text[:60]!r}")
            return problems
        i += 1
        if inline is not None:
            a, b = int(inline[1]), int(inline[2])
            if a != i + 1 or b < a:
                problems.append(f"output line {k + 1}: inline marker hides {a}-{b}, expected {i + 1}-")
            i = max(i, b)
    if i != len(src):
        problems.append(f"output accounts for {i} of {len(src)} source lines")
    return problems


def json_markers(raw: str, out: str) -> list[str]:
    """Problems with the JSON fold's markers, each checked against the source with `resolve`."""
    parsed = parse_json_or_jsonl(raw)
    if parsed is None:
        return ["the JSON fold's source does not parse"]
    source = parsed[0]
    body = out.split("\n", 1)[1] if out.startswith("JSONL") else out
    try:
        folded = json.loads(body)
    except ValueError as e:
        return [f"the JSON fold does not parse: {e}"]
    problems: list[str] = []

    def walk(v: object) -> None:
        if isinstance(v, dict):
            note = v.get("_folded")
            if isinstance(note, str) and (m := _JSON_FOLD.match(note)):
                path, a, b, k, n = m[1], int(m[2]), int(m[3]), int(m[4]), int(m[5])
                try:
                    hidden, whole = resolve(source, f"{path}[{a}:{b}]"), resolve(source, path)
                except RecoveryError as e:
                    problems.append(f"{note!r}: {e}")
                    return
                if len(hidden) != k or b - a != k or len(whole) != n:
                    problems.append(f"{note!r}: the source has {len(hidden)} there, {len(whole)} in all")
            keys = v.get("_folded_keys")
            if isinstance(keys, str) and (m := _JSON_KEYS.match(keys)):
                try:
                    whole = resolve(source, m[3])
                except RecoveryError as e:
                    problems.append(f"{keys[:60]!r}: {e}")
                    return
                if not isinstance(whole, dict) or len(whole) != int(m[2]) or int(m[1]) > int(m[2]):
                    problems.append(f"{keys[:60]!r}: the source object has {len(whole)} keys")
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(folded)
    return problems


@dataclass(frozen=True)
class Row:
    task_id: str
    fmt: str
    kind: str
    band: str
    query_on: bool
    branch: str
    raw_tokens: int
    out_tokens: int
    sufficient: bool
    recall: float | None
    over_budget: bool
    violations: list[str]


def check(task: Task, budget: int, query_on: bool) -> Row:
    raw = task.payload()
    query = task.query if query_on else ""
    result = fold_text(raw, budget=budget, path=task.path, query=query, quiet=True)
    again = fold_text(raw, budget=budget, path=task.path, query=query, quiet=True)
    out = result.text
    passthrough = out == raw
    language = language_for(task.path) if task.path else None
    branch = "passthrough" if passthrough else (f"code-{language}" if language else detect(raw))
    violations: list[str] = []
    if again.text != out:
        violations.append("folding twice gave different text")
    if estimate_tokens(out) > estimate_tokens(raw):
        violations.append("the fold is larger than the input")
    if estimate_tokens(out) > budget * 1.1:  # over the budget is a bug unless nothing smaller exists
        floor = fold_text(raw, budget=1, path=task.path, query=query, quiet=True).text
        if out != floor:
            violations.append(f"{estimate_tokens(out)} tokens for a budget of {budget}, and not the floor")
    if not passthrough:
        if branch == "json":
            violations += json_markers(raw, out)
        elif branch in ("xml", "outline", "lines") or branch.startswith("code-"):
            source = result.source if result.source is not None else raw
            violations += coverage(source, out, numbered=branch.startswith("code-"))
    score = score_fold(task.truth, out)
    return Row(
        task.task_id,
        task.fmt,
        task.kind,
        task.band,
        query_on,
        branch,
        estimate_tokens(raw),
        estimate_tokens(out),
        score.correct,
        score.recall,
        estimate_tokens(out) > budget * 1.1,
        violations,
    )


def run(budget: int, only: tuple[str, ...] = ()) -> list[Row]:
    rows = []
    for t in tasks():
        if only and t.fmt not in only:
            continue
        rows.append(check(t, budget, query_on=False))
        if t.query:
            rows.append(check(t, budget, query_on=True))
    return rows


def report(rows: list[Row], budget: int) -> str:
    bad = [r for r in rows if r.violations]
    folded = [r for r in rows if r.branch != "passthrough"]
    out = [
        f"# Layer 1: the fold alone, budget {budget} tokens",
        "",
        f"{len(rows)} folds of {len({r.task_id for r in rows})} tasks. Sufficient = the task's scorer finds",
        "the answer in the fold text (an upper bound on what a model can answer without fetching more).",
        "",
        f"Sufficient overall: {sum(r.sufficient for r in rows)}/{len(rows)}; over the folds that folded "
        f"(not passed through): {sum(r.sufficient for r in folded)}/{len(folded)}.",
        "",
        f"## Invariants: {len(bad)} folds with violations",
        "",
    ]
    out += [
        f"- {r.task_id} (query {'on' if r.query_on else 'off'}, {r.branch}): {'; '.join(r.violations)}"
        for r in bad
    ]
    if not bad:
        out.append("None.")
    out += ["", "## Sufficiency, query off", "", "| format | kind | S | M | L |", "|---|---|---|---|---|"]
    cells: dict[tuple[str, str, str, bool], list[Row]] = defaultdict(list)
    for r in rows:
        cells[(r.fmt, r.kind, r.band, r.query_on)].append(r)
    kinds = sorted({(r.fmt, r.kind) for r in rows}, key=lambda fk: (FORMATS.index(fk[0]), fk[1]))

    def cell(fmt: str, kind: str, band: str, q: bool) -> str:
        rs = cells.get((fmt, kind, band, q), [])
        return f"{sum(r.sufficient for r in rs)}/{len(rs)}" if rs else ""

    for fmt, kind in kinds:
        out.append(f"| {fmt} | {kind} | " + " | ".join(cell(fmt, kind, b, False) for b in "SML") + " |")
    queried = [(fmt, kind) for fmt, kind in kinds if any(cells.get((fmt, kind, b, True)) for b in "SML")]
    if queried:
        out += ["", "## Sufficiency, query on (tasks whose tool call would name what is asked)", ""]
        out += ["| format | kind | S | M | L |", "|---|---|---|---|---|"]
        for fmt, kind in queried:
            out.append(f"| {fmt} | {kind} | " + " | ".join(cell(fmt, kind, b, True) for b in "SML") + " |")
    out += [
        "",
        "## Size, query off",
        "",
        "| format | band | tasks | median tokens in | median out | median kept | over budget |",
    ]
    out.append("|---|---|---|---|---|---|---|")
    for fmt in FORMATS:
        for band in "SML":
            rs = [r for r in rows if r.fmt == fmt and r.band == band and not r.query_on]
            if rs:
                kept = statistics.median(r.out_tokens / r.raw_tokens for r in rs)
                out.append(
                    f"| {fmt} | {band} | {len(rs)} | {int(statistics.median(r.raw_tokens for r in rs))} "
                    f"| {int(statistics.median(r.out_tokens for r in rs))} | {kept:.0%} "
                    f"| {sum(r.over_budget for r in rs)} |"
                )
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--budget", type=int, default=BUDGET)
    parser.add_argument("--only", nargs="+", choices=FORMATS, default=())
    parser.add_argument("--name", default="l1-1")
    ns = parser.parse_args(argv)
    rows = run(ns.budget, tuple(ns.only))
    results = _LAB / "results"
    with (results / f"{ns.name}.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(asdict(r)) + "\n")
    text = report(rows, ns.budget)
    (results / f"{ns.name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if any(r.violations for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
