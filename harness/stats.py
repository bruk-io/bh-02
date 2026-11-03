"""Corpus report: how big tool results are, from which tools, and what compression does to them.

    ./lab stats [corpus/results.jsonl] [--budget 2000] [-o results/stats.md]

No model is involved. Sizes are what the model saw after the agent harness's own limits (Claude
Code cuts long Bash output and pages long files), so they understate raw tool output.
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from compressors.common import estimate_tokens
from compressors.route import compress, detect

_BUCKETS = ((500, "<500"), (2000, "500-2k"), (8000, "2k-8k"), (32000, "8k-32k"), (None, ">=32k"))


def _bucket(tokens: int) -> str:
    for limit, name in _BUCKETS:
        if limit is None or tokens < limit:
            return name
    raise AssertionError("the last bucket has no limit")


def _table(header: list[str], rows: Iterable[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _kept(pairs: list[tuple[int, int]]) -> str:
    return f"{sum(o for _, o in pairs) / sum(i for i, _ in pairs):.0%}"


def summarise(rows: list[dict[str, Any]], budget: int) -> str:
    sizes = [estimate_tokens(r["text"]) for r in rows]
    total = sum(sizes) or 1
    out = [
        f"# Corpus stats (budget {budget} tokens)",
        "",
        f"{len(rows)} tool results from {len({r['source'] for r in rows})} transcripts, "
        f"~{total} tokens in all. {sum(r['images'] for r in rows)} image blocks were not counted.",
        "",
        "## Size distribution",
        "",
    ]
    by_bucket: Counter[str] = Counter()
    tokens_by_bucket: Counter[str] = Counter()
    for s in sizes:
        by_bucket[_bucket(s)] += 1
        tokens_by_bucket[_bucket(s)] += s
    out.append(
        _table(
            ["size (tokens)", "results", "share of tokens"],
            ([name, by_bucket[name], f"{tokens_by_bucket[name] / total:.0%}"] for _, name in _BUCKETS),
        )
    )

    per_tool: dict[str, list[int]] = defaultdict(list)
    for r, s in zip(rows, sizes, strict=True):
        per_tool[r["tool_name"]].append(s)
    out += ["", "## Per tool", ""]
    out.append(
        _table(
            ["tool", "results", "tokens", "share", "median", "max", f"over {budget}"],
            (
                [t, len(v), sum(v), f"{sum(v) / total:.0%}", int(statistics.median(v)), max(v)]
                + [sum(1 for x in v if x > budget)]
                for t, v in sorted(per_tool.items(), key=lambda kv: -sum(kv[1]))
            ),
        )
    )

    large = [r for r, s in zip(rows, sizes, strict=True) if s > budget]
    out += ["", f"## Results over the budget ({len(large)})", ""]
    if not large:
        out.append("None: at this budget the middleware would pass everything through.")
        return "\n".join(out) + "\n"
    per_branch: dict[str, list[tuple[int, int]]] = defaultdict(list)
    per_tool_compressed: dict[str, list[tuple[int, int]]] = defaultdict(list)
    detected: Counter[str] = Counter()
    for r in large:
        detected[detect(r["text"])] += 1
        c = compress(r["tool_name"], r["args"], r["text"], budget_tokens=budget)
        per_branch[c.branch].append((c.raw_tokens, c.out_tokens))
        per_tool_compressed[r["tool_name"]].append((c.raw_tokens, c.out_tokens))
    out.append(_table(["format", "results"], ([k, v] for k, v in detected.most_common())))
    out += ["", "Compression by branch (passthrough means folding saved under 10%):", ""]
    out.append(
        _table(
            ["branch", "results", "tokens in", "tokens out", "kept"],
            (
                [
                    b,
                    len(v),
                    sum(i for i, _ in v),
                    sum(o for _, o in v),
                    _kept(v),
                ]
                for b, v in sorted(per_branch.items())
            ),
        )
    )
    out += ["", "Compression by tool (to see a tool that should never be folded):", ""]
    out.append(
        _table(
            ["tool", "results", "tokens in", "tokens out", "kept"],
            (
                [t, len(v), sum(i for i, _ in v), sum(o for _, o in v), _kept(v)]
                for t, v in sorted(per_tool_compressed.items())
            ),
        )
    )
    saved = sum(i - o for v in per_branch.values() for i, o in v)
    out += ["", f"Tokens saved over the whole corpus: ~{saved} of ~{total} ({saved / total:.0%})."]
    for tool in sorted(per_tool_compressed):
        rest = sum(i - o for t, w in per_tool_compressed.items() if t != tool for i, o in w)
        out.append(f"Without folding {tool}: ~{rest} ({rest / total:.0%}).")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("corpus", nargs="?", type=Path, default=Path("corpus/results.jsonl"))
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("-o", "--out", type=Path)
    ns = parser.parse_args(argv)
    with ns.corpus.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    report = summarise(rows, ns.budget)
    if ns.out:
        ns.out.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
