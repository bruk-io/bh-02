"""Needle survival: plant one anomaly in synthetic output and check it survives compression.

    ./lab needle [--seeds 5] [-o results/needle.md]

No model is involved. A needle that is not in the compressed text cannot be found without a
recovery call, so survival is an upper bound on what a model will notice unprompted. Some kinds are
built to be missed (a numeric outlier, a quiet log line, the last line of a stack trace), so the
report shows where the heuristics stop, not only where they work.
"""

import argparse
import json
import random
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compressors.route import compress

JSON_KINDS = ("rare_value", "nested_rare_value", "error_key", "bool_flip", "query_match", "numeric_outlier")
LOG_KINDS = ("error_word", "query_match", "stack_trace_tail", "quiet_line")
POSITIONS = (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)
JSON_SIZES = (50, 500, 5000)
LOG_SIZES = (200, 2000, 20000)
BUDGET = 2000


@dataclass(frozen=True)
class Case:
    fmt: str  # json | log
    kind: str
    size: int  # items or lines
    position: float
    raw: str
    args: dict[str, Any]  # the tool call's arguments; carries the needle only for query_match
    needle: str  # a unique string that is in the output only if the anomalous part is


@dataclass(frozen=True)
class Outcome:
    fmt: str
    kind: str
    size: int
    position: float
    use_query: bool
    survived: bool
    raw_tokens: int
    out_tokens: int


def _index(size: int, position: float) -> int:
    return min(size - 1, round(position * (size - 1)))


def json_case(kind: str, size: int, position: float, rng: random.Random) -> Case:
    nodes = [f"node-{c}" for c in "abcdefgh"]
    items: list[dict[str, Any]] = [
        {
            "name": f"web-{rng.getrandbits(40):010x}",
            "namespace": "default",
            "node": rng.choice(nodes),
            "image": "registry.local/web:1.4.2",
            "restarts": rng.randint(0, 3),
            "ready": True,
            "phase": "Running",
            "status": {"phase": "Running", "qos": "Burstable"},
            "labels": {"app": "web", "tier": rng.choice(["a", "b", "c"])},
        }
        for _ in range(size)
    ]
    i = _index(size, position)
    needle = f"needle-{rng.getrandbits(32):08x}"
    target = items[i]
    target["name"] = needle
    args: dict[str, Any] = {"namespace": "default"}
    match kind:
        case "rare_value":
            target["phase"] = "CrashLoopBackOff"
        case "nested_rare_value":
            target["status"]["phase"] = "Pending"
        case "error_key":
            target["error"] = "OOMKilled after 3 restarts"
        case "bool_flip":
            target["ready"] = False
        case "query_match":
            args["name"] = needle
        case "numeric_outlier":
            target["restarts"] = 9999
        case _:
            raise ValueError(f"unknown JSON kind {kind!r}: use one of {', '.join(JSON_KINDS)}")
    return Case("json", kind, size, position, json.dumps({"items": items}), args, needle)


_LOG_TEMPLATES = (
    "INFO  http GET {path} {status} {ms}ms",
    "INFO  http POST {path} {status} {ms}ms",
    "DEBUG cache {verb} key={key}",
    "INFO  worker {worker} picked job {job}",
    "INFO  worker {worker} finished job {job} in {ms}ms",
    "DEBUG db query users.find_by_id {ms}ms",
)


def _log_line(rng: random.Random, t: int) -> str:
    template = rng.choice(_LOG_TEMPLATES)
    line = template.format(
        path=rng.choice(["/api/items", "/api/users", "/api/orders", "/health", "/static/app.js"]),
        status=rng.choice([200, 200, 200, 204, 304]),
        ms=rng.randint(1, 900),
        verb=rng.choice(["hit", "miss", "set"]),
        key=f"user:{rng.randint(1, 99999)}",
        worker=rng.choice(["alpha", "beta", "gamma"]),
        job=rng.getrandbits(32),
    )
    return f"2026-11-03T{t // 3600 % 24:02d}:{t // 60 % 60:02d}:{t % 60:02d}Z {line}"


def log_case(kind: str, size: int, position: float, rng: random.Random) -> Case:
    lines = [_log_line(rng, t) for t in range(size)]
    i = _index(size, position)
    needle = f"needle-{rng.getrandbits(32):08x}"
    stamp = lines[i][:20]
    args: dict[str, Any] = {"command": "kubectl logs deploy/web"}
    match kind:
        case "error_word":
            lines[i] = f"{stamp} ERROR payment failed for order {needle}"
        case "query_match":
            lines[i] = f"{stamp} INFO  processed order {needle}"
            args["pattern"] = needle
        case "stack_trace_tail":
            frames = [
                f'  File "/app/{m}.py", line {rng.randint(10, 400)}, in {f}\n    {f}(payload)'
                for m, f in [
                    ("server", "handle"),
                    ("routes", "dispatch"),
                    ("orders", "create"),
                    ("models", "save"),
                ]
            ]
            trace = ["Traceback (most recent call last):", *"\n".join(frames).splitlines()]
            lines[i : i + 1] = [*trace, f"ValueError: order total is negative ({needle})"]
        case "quiet_line":
            lines[i] = f"{stamp} INFO  pool connections available=0 of 50 ({needle})"
        case _:
            raise ValueError(f"unknown log kind {kind!r}: use one of {', '.join(LOG_KINDS)}")
    return Case("log", kind, size, position, "\n".join(lines), args, needle)


def cases(seeds: int) -> Iterator[Case]:
    grids: list[tuple[Callable[..., Case], tuple[str, ...], tuple[int, ...]]] = [
        (json_case, JSON_KINDS, JSON_SIZES),
        (log_case, LOG_KINDS, LOG_SIZES),
    ]
    for make, kinds, sizes in grids:
        for kind in kinds:
            for size in sizes:
                for position in POSITIONS:
                    for seed in range(seeds):
                        rng = random.Random(f"{kind}/{size}/{position}/{seed}")
                        yield make(kind, size, position, rng)


def evaluate(case: Case, use_query: bool) -> Outcome:
    c = compress("tool", case.args, case.raw, budget_tokens=BUDGET, use_query=use_query)
    survived = case.needle in c.text
    return Outcome(
        case.fmt, case.kind, case.size, case.position, use_query, survived, c.raw_tokens, c.out_tokens
    )


def _rate(outcomes: list[Outcome]) -> str:
    return f"{sum(o.survived for o in outcomes) / len(outcomes):.0%}"


def report(outcomes: Iterable[Outcome], seeds: int) -> str:
    outcomes = list(outcomes)
    out = [
        "# Needle survival",
        "",
        f"Budget {BUDGET} tokens, {seeds} seeds per cell, "
        f"positions {', '.join(f'{p:.0%}' for p in POSITIONS)}. "
        "Survival means the needle's unique string is in the compressed text.",
        "",
        "## By kind (query from tool arguments on / off)",
        "",
        "| format | kind | survived, query on | survived, query off | tokens kept (median) |",
        "|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str], dict[bool, list[Outcome]]] = defaultdict(lambda: defaultdict(list))
    for o in outcomes:
        groups[(o.fmt, o.kind)][o.use_query].append(o)
    for (fmt, kind), by_q in groups.items():
        kept = statistics.median(o.out_tokens / o.raw_tokens for o in by_q[True])
        out.append(f"| {fmt} | {kind} | {_rate(by_q[True])} | {_rate(by_q[False])} | {kept:.1%} |")

    out += [
        "",
        "## By position, query off",
        "",
        "| format | kind | " + " | ".join(f"{p:.0%}" for p in POSITIONS) + " |",
    ]
    out.append("|---|---|" + "---|" * len(POSITIONS))
    for (fmt, kind), by_q in groups.items():
        cells = []
        for p in POSITIONS:
            at = [o for o in by_q[False] if o.position == p]
            cells.append(_rate(at))
        out.append(f"| {fmt} | {kind} | " + " | ".join(cells) + " |")

    out += [
        "",
        "## By size, query off",
        "",
        "| format | kind | size | survived | tokens in (median) | out (median) |",
    ]
    out.append("|---|---|---|---|---|---|")
    for (fmt, kind), by_q in groups.items():
        for size in sorted({o.size for o in by_q[False]}):
            at = [o for o in by_q[False] if o.size == size]
            raw_median = int(statistics.median(o.raw_tokens for o in at))
            out_median = int(statistics.median(o.out_tokens for o in at))
            out.append(f"| {fmt} | {kind} | {size} | {_rate(at)} | {raw_median} | {out_median} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("-o", "--out", type=Path)
    ns = parser.parse_args(argv)
    outcomes = [evaluate(c, q) for c in cases(ns.seeds) for q in (True, False)]
    text = report(outcomes, ns.seeds)
    if ns.out:
        ns.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
