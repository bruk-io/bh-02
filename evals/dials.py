"""Layer 2 over dial settings: the same tasks on one model, native against each setting of the fold.

    ./lab evals dials dials/haiku-atlas.toml [--dry-run]

    name = "haiku-json"
    model = "claude-haiku-5-5"
    bands = ["M"]
    formats = ["json", "atlas"]
    reps = 2
    max_cost = 6                  # USD; no new session starts once this is spent
    ids = ["json-M-spot-at50"]    # exact tasks, for a smoke run (optional)

    [[setting]]                   # the sample recipe, the default view
    name = "sample"

    [[setting]]
    name = "schema"
    view = "schema"

    [[setting]]                   # a composition: the schema recipe without its samples
    name = "schema-no-samples"
    view = "schema"
    set = ["json_envelope.samples=none"]
    formats = ["json"]            # a setting that names formats runs on those alone

    [[setting]]
    name = "budget-500"
    budget = 500

A setting takes `mode` (inline by default), `budget` (2000), `view` (sample), `set` (knobs, as for
`--set`) and `formats`. Every task runs natively and under each setting that covers it, interleaved
so the cache warms evenly; each setting is a condition of its own, paired against native by task
and repetition. Writes results/dials-NAME.md: one table with a row per setting (accuracy, final
context, summed input, cache writes and reads, what each later request saves, cost and time, each
against native), then the full layer-2 report. Costs money: --dry-run first.
"""

import argparse
import statistics
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compressors.common import estimate_tokens
from compressors.config import DEFAULT, with_sets
from compressors.envelope_json import VIEWS
from evals.l2 import _COST_PER_RUN, Dials, implied_input_price, report, run_jobs
from evals.stats import bootstrap, paired, paired_accuracy
from evals.tasks import BANDS, FORMATS, Task, tasks

_LAB = Path(__file__).resolve().parent.parent
_MODES = ("inline", "spilled", "all")


@dataclass(frozen=True)
class Setting:
    name: str
    dials: Dials
    formats: frozenset[str]


def settings(spec: dict[str, Any]) -> list[Setting]:
    """The spec's settings, each with its dials and the formats it runs on.

    Raises:
        ValueError: no setting, a setting without a name or with one already taken, a mode or view
            that is none, a format that is none, or a knob that is not one (from `with_sets`).
    """
    every = frozenset(spec.get("formats", ("json", "log", "a11y", "figma")))
    out: list[Setting] = []
    for raw in spec.get("setting", []):
        name = str(raw.get("name", ""))
        if not name or name == "native" or name in {s.name for s in out}:
            raise ValueError(f"each [[setting]] needs a name of its own (not native); {name!r} is not one")
        mode, view = str(raw.get("mode", "inline")), str(raw.get("view", "sample"))
        if mode not in _MODES or view not in VIEWS:
            raise ValueError(
                f"setting {name}: mode is one of {', '.join(_MODES)}, view one of {', '.join(VIEWS)}"
            )
        formats = frozenset(raw.get("formats", every))
        if unknown := formats - set(FORMATS):
            raise ValueError(f"setting {name}: no format {', '.join(sorted(unknown))}")
        config = with_sets(DEFAULT, list(raw.get("set", [])))
        out.append(
            Setting(
                name, Dials(mode=mode, budget=int(raw.get("budget", 2000)), view=view, config=config), formats
            )
        )
    if not out:
        raise ValueError('a dials spec needs at least one [[setting]], such as [[setting]] name = "default"')
    return out


def jobs(
    spec: dict[str, Any], chosen: list[Setting], registry: list[Task]
) -> list[tuple[Task, str, int, Dials]]:
    """Native and every setting that covers each task, task by task, so the conditions interleave."""
    bands = set(spec.get("bands", ["M"]))
    formats = set().union(*(s.formats for s in chosen))
    ids = set(spec.get("ids", ()))  # exact tasks, for a smoke run (the bands and formats still apply)
    out = []
    for rep in range(int(spec.get("reps", 1))):
        for t in registry:
            if t.path or t.band not in bands or t.fmt not in formats or (ids and t.task_id not in ids):
                continue
            out.append((t, "native", rep, Dials()))
            out += [(t, s.name, rep, s.dials) for s in chosen if t.fmt in s.formats]
    return out


def _pairs(
    rows: list[dict[str, Any]], name: str
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    def by_key(cond: str) -> dict[str, dict[str, Any]]:
        return {f"{r['task_id']}#{r['rep']}": r for r in rows if r["condition"] == cond and not r["error"]}

    runs = by_key(name)
    base = {k: v for k, v in by_key("native").items() if k in runs}
    return base, runs


def _change(
    base: dict[str, dict[str, Any]], runs: dict[str, dict[str, Any]], field: str, scale: float = 1.0
) -> list[float]:
    def value(r: dict[str, Any]) -> float:
        if field == "all_input":
            return float(r["input_tokens"] + r["cache_read"] + r["cache_write"])
        return float(r[field]) * scale

    return paired({k: value(v) for k, v in base.items()}, {k: value(v) for k, v in runs.items()})


def _mean(values: list[float], fmt: str) -> str:
    mid, lo, hi = bootstrap(values, statistics.mean)
    return f"{mid:{fmt}} [{lo:{fmt}}, {hi:{fmt}}]"


def dial_table(rows: list[dict[str, Any]], chosen: list[Setting]) -> list[str]:
    scored = [r for r in rows if not r["error"]]
    implied = sorted(p for r in scored if (p := implied_input_price(r)) is not None)
    read = 0.1 * statistics.median(implied) if implied else None
    native = [r for r in scored if r["condition"] == "native"]
    out = [
        "| setting | pairs | accuracy | final context | summed input | cache writes | cache reads "
        "| each later request | cost | time |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    if native:
        cells = [
            "native (absolute)",
            str(len(native)),
            f"{sum(r['correct'] for r in native) / len(native):.0%}",
            f"{statistics.median(r['final_context'] for r in native):,.0f}",
            f"{statistics.mean(r['input_tokens'] + r['cache_read'] + r['cache_write'] for r in native):,.0f}",
            f"{statistics.mean(r['cache_write'] for r in native):,.0f}",
            f"{statistics.mean(r['cache_read'] for r in native):,.0f}",
            "-",
            f"${statistics.mean(r['cost_usd'] for r in native):.4f}",
            f"{statistics.mean(r['duration_ms'] for r in native) / 1000:.1f}s",
        ]
        out.append("| " + " | ".join(cells) + " |")
    for s in chosen:
        base, runs = _pairs(scored, s.name)
        keys = base.keys() & runs.keys()
        if not keys:
            out.append(f"| {s.name} | 0 | - | - | - | - | - | - | - | - |")
            continue
        both = sum(1 for k in keys if runs[k]["correct"] and base[k]["correct"])
        gains = sum(1 for k in keys if runs[k]["correct"] and not base[k]["correct"])
        losses = sum(1 for k in keys if base[k]["correct"] and not runs[k]["correct"])
        change, lo, hi, _ = paired_accuracy(both, gains, losses, len(keys) - both - gains - losses)
        context = statistics.median(_change(base, runs, "final_context"))
        cost_base = statistics.mean(base[k]["cost_usd"] for k in keys)
        cost = statistics.mean(_change(base, runs, "cost_usd"))
        cells = [
            s.name,
            str(len(keys)),
            f"{change:+.0%} [{lo:+.0%}, {hi:+.0%}], {gains}/{losses}",
            _mean(_change(base, runs, "final_context"), "+,.0f"),
            _mean(_change(base, runs, "all_input"), "+,.0f"),
            _mean(_change(base, runs, "cache_write"), "+,.0f"),
            _mean(_change(base, runs, "cache_read"), "+,.0f"),
            f"{context:+,.0f}" + (f" (${context * read:+.5f})" if read else ""),
            f"{cost / cost_base:+.0%} (${cost:+.4f})",
            _mean(_change(base, runs, "duration_ms", 1e-3), "+.1f") + "s",
        ]
        out.append("| " + " | ".join(cells) + " |")
    note = (
        f"a cache read at ${read * 1e6:.3f} per million, as these runs' costs imply" if read else "unpriced"
    )
    return [
        *out,
        "",
        "Each setting against native on the same tasks and repetitions: accuracy as the change with its "
        "95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap "
        "intervals. Final context: the input of the session's last request. Summed input: every input token "
        "every request carried, cached or not. Each later request: what one more request in the same session "
        f"would save or pay, the median change in the final context ({note}).",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="a dials spec's TOML file (see dials/)")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the runs and an estimated cost; run nothing"
    )
    parser.add_argument("--workers", type=int, default=6)
    ns = parser.parse_args(argv)
    spec = tomllib.loads(ns.spec.read_text(encoding="utf-8"))
    name, model = str(spec.get("name", ns.spec.stem)), str(spec.get("model", "claude-haiku-5-5"))
    chosen = settings(spec)
    planned = jobs(spec, chosen, tasks(spec.get("bands", ["M"])))
    per_run = next((v for k, v in _COST_PER_RUN.items() if k in model), _COST_PER_RUN["sonnet"])
    print(f"{len(planned)} runs on {model}, about ${len(planned) * per_run:.2f} (a rough estimate):")
    for cond in ["native", *(s.name for s in chosen)]:
        print(f"  {cond:16} {sum(1 for _, c, _, _ in planned if c == cond):4} runs")
    if ns.dry_run:
        return 0
    rows = run_jobs(planned, model, f"dials-{name}", ns.workers, spec.get("max_cost"))
    lines = [f"# Dials {name}: {model}, the same tasks native and under each setting", ""]
    bands = [b for b in BANDS if any(r["band"] == b for r in rows)]
    if len(bands) > 1:  # how each setting scales: a table per size band, smallest first
        for b in bands:
            sized = [r for r in rows if r["band"] == b]
            inputs = [estimate_tokens(t.payload()) for t in {j[0] for j in planned if j[0].band == b}]
            lines += [f"## Band {b} (median input {statistics.median(inputs):,.0f} tokens)", ""]
            lines += [*dial_table(sized, chosen), ""]
        lines += ["## Every band together", ""]
    lines += dial_table(rows, chosen)
    text = "\n".join(lines) + "\n\n" + report(rows, model)
    (_LAB / "results" / f"dials-{name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
