"""Layer 1: fold every eval task with the `fold` interface itself and check it, with no model.

    ./lab evals l1 [--budget 2000] [--only FORMAT ...] [--bands S M L XL XXL] [--name l1-1]

For each task, fold the payload (with no query, and again with the task's query when it has one)
through `compressors.cli.fold_text`, then check:

- invariants (any failure is a bug):
  - every claim an envelope's parts make holds against the data and is said in its text
    (`evals.envelope_check`; its commands run with jq or grep), and the envelope made again is the
    same; a JSON Lines note counts the records and says rightly whether index i is line i+1;
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
from compressors.common import estimate_tokens, query_words, split_lines
from compressors.config import DEFAULT, FoldConfig, load, with_sets
from compressors.envelope_json import VIEWS, envelope
from compressors.json_items import parse_json_or_jsonl
from compressors.route import lines_envelope
from evals import envelope_check
from evals.tasks import BANDS, BUDGET, FORMATS, Task, skipped, tasks
from evals.truth import score_fold

_LAB = Path(__file__).resolve().parent.parent
_MARKER, _INLINE, _CLIPPED, _NOTE = markers.LINE_RANGE, markers.INLINE, markers.CLIPPED, markers.NOTE


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


def _line_holds(lines: list[str], i: int, item: object) -> bool:
    try:
        return bool(json.loads(lines[i]) == item)
    except IndexError, ValueError:
        return False


def jsonl_note(raw: str, out: str) -> list[str]:
    """Problems with a JSON Lines envelope's note: the records it counts, and the line it says each is on."""
    parsed = parse_json_or_jsonl(raw)
    if parsed is None:
        return ["the envelope's source does not parse as JSON"]
    source, kind = parsed
    note = markers.JSONL_NOTE.match(out)
    if (note is not None) != (kind == "jsonl"):
        return ["the JSONL note is missing" if note is None else "a JSONL note on a JSON document"]
    if note is None:
        return []
    problems = []
    if int(note["records"]) != len(source):
        problems.append(f"the JSONL note says {note['records']} records, the source has {len(source)}")
    if note["where"] == "index i is line i+1":  # read each record back from its claimed line
        lines = split_lines(raw)
        if not all(_line_holds(lines, i, item) for i, item in enumerate(source)):
            problems.append("the JSONL note maps index i to line i+1, and a record is not there")
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
    view: str = "sample"
    config: str = "defaults"  # what the knobs changed (`compressors.config.label`)


def check(task: Task, budget: int, query_on: bool, view: str = "sample", config: FoldConfig = DEFAULT) -> Row:
    raw = task.payload()
    query = task.query if query_on else ""
    result = fold_text(raw, budget=budget, path=task.path, query=query, quiet=True, view=view, config=config)
    again = fold_text(raw, budget=budget, path=task.path, query=query, quiet=True, view=view, config=config)
    out = result.text
    passthrough = result.branch is None
    branch = f"code-{result.language}" if result.language else (result.branch or "passthrough")
    violations: list[str] = []
    if again.text != out:
        violations.append("folding twice gave different text")
    if estimate_tokens(out) > estimate_tokens(raw):
        violations.append("the fold is larger than the input")
    if estimate_tokens(out) > budget * 1.1:  # over the budget is a bug unless nothing smaller exists
        floor = fold_text(
            raw, budget=1, path=task.path, query=query, quiet=True, view=view, config=config
        ).text
        if out != floor:
            violations.append(f"{estimate_tokens(out)} tokens for a budget of {budget}, and not the floor")
    if not passthrough:
        if branch in ("json", "jsonl"):
            violations += jsonl_note(raw, out)
            parsed = parse_json_or_jsonl(raw)
            assert parsed is not None
            body = out[note.end() :] if (note := markers.JSONL_NOTE.match(out)) else out
            env = envelope(parsed[0], query_words(query), budget, branch == "jsonl", config, view)
            if env.text() != body:
                violations.append("the envelope made again from the same input differs from the fold")
            violations += envelope_check.problems(raw, parsed[0], env, config.schema)
        elif not (branch == "html" and out == result.source):  # a page's text that fits is shown whole
            kind = "code" if branch.startswith("code-") else branch
            env, source = lines_envelope(
                raw, kind, query_words(query), budget, config, view, language=result.language or ""
            )
            if env.text() != out:
                violations.append("the envelope made again from the same input differs from the fold")
            violations += envelope_check.text_problems(source, env)
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


def run(
    budget: int,
    only: tuple[str, ...] = (),
    view: str = "sample",
    config: FoldConfig = DEFAULT,
    bands: tuple[str, ...] = BANDS[:3],
) -> list[Row]:
    rows = []
    for t in tasks(bands):
        if only and t.fmt not in only:
            continue
        rows.append(check(t, budget, query_on=False, view=view, config=config))
        if t.query:
            rows.append(check(t, budget, query_on=True, view=view, config=config))
    return rows


def report(rows: list[Row], budget: int) -> str:
    bad = [r for r in rows if r.violations]
    folded = [r for r in rows if r.branch != "passthrough"]
    out = [
        f"# Layer 1: the fold alone, budget {budget} tokens",
        "",
        f"View: {rows[0].view if rows else 'sample'}. Knobs: {rows[0].config if rows else 'defaults'}.",
        "",
        f"{len(rows)} folds of {len({r.task_id for r in rows})} tasks. Sufficient = the task's scorer finds",
        "the answer in the fold text (an upper bound on what a model can answer without fetching more).",
        "",
        f"Sufficient overall: {sum(r.sufficient for r in rows)}/{len(rows)}; over the folds that folded "
        f"(not passed through): {sum(r.sufficient for r in folded)}/{len(folded)}.",
        "",
        *[f"Left out on this host: {source} ({why})." for source, why in skipped().items()],
        *([""] if skipped() else []),
        f"## Invariants: {len(bad)} folds with violations",
        "",
    ]
    out += [
        f"- {r.task_id} (query {'on' if r.query_on else 'off'}, {r.branch}): {'; '.join(r.violations)}"
        for r in bad
    ]
    if not bad:
        out.append("None.")
    sizes = [b for b in BANDS if any(r.band == b for r in rows)]
    head = ["| format | kind | " + " | ".join(sizes) + " |", "|---|---|" + "---|" * len(sizes)]
    out += ["", "## Sufficiency, query off", "", *head]
    cells: dict[tuple[str, str, str, bool], list[Row]] = defaultdict(list)
    for r in rows:
        cells[(r.fmt, r.kind, r.band, r.query_on)].append(r)
    kinds = sorted({(r.fmt, r.kind) for r in rows}, key=lambda fk: (FORMATS.index(fk[0]), fk[1]))

    def cell(fmt: str, kind: str, band: str, q: bool) -> str:
        rs = cells.get((fmt, kind, band, q), [])
        return f"{sum(r.sufficient for r in rs)}/{len(rs)}" if rs else ""

    for fmt, kind in kinds:
        out.append(f"| {fmt} | {kind} | " + " | ".join(cell(fmt, kind, b, False) for b in sizes) + " |")
    queried = [(fmt, kind) for fmt, kind in kinds if any(cells.get((fmt, kind, b, True)) for b in sizes)]
    if queried:
        out += ["", "## Sufficiency, query on (tasks whose tool call would name what is asked)", ""]
        out += head
        for fmt, kind in queried:
            out.append(f"| {fmt} | {kind} | " + " | ".join(cell(fmt, kind, b, True) for b in sizes) + " |")
    out += [
        "",
        "## Size, query off",
        "",
        "| format | band | tasks | median tokens in | median out | median kept | over budget |",
    ]
    out.append("|---|---|---|---|---|---|---|")
    for fmt in FORMATS:
        for band in sizes:
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
    parser.add_argument(
        "--bands",
        nargs="+",
        choices=BANDS,
        default=list(BANDS[:3]),
        help="size bands (XL and XXL: synthetic)",
    )
    parser.add_argument("--name", default="l1-1")
    parser.add_argument("--view", choices=VIEWS, default="sample", help="how data (JSON) is shown")
    parser.add_argument("--config", type=Path, help="a TOML file of knobs (compressors/config.py)")
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="NAME=VALUE")
    ns = parser.parse_args(argv)
    config = with_sets(load(ns.config) if ns.config else DEFAULT, ns.sets)
    rows = run(ns.budget, tuple(ns.only), ns.view, config, tuple(ns.bands))
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
