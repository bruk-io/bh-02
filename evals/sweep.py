"""Layer 1 over a grid of knobs: the same tasks folded under each point, side by side. Free.

    ./lab evals sweep sweeps/schema-rare.toml

    name = "schema-rare"
    only = ["json", "pypi"]       # formats (all of them when left out)
    by = "band"                   # a row per point and size band (optional): how a dial scales
    bands = ["L", "XL", "XXL"]    # the size bands to fold (S, M and L when left out)
    [base]                        # what every point sets: knobs, and budget or view
    view = "schema"
    [grid]                        # each axis's values; the points are every combination
    "schema.rare" = [0.05, 0.1, 0.15]
    budget = [1000, 2000]

Writes results/sweep-NAME.md, one row per point: sufficiency overall and over the folds that folded,
by task kind and for the quiet anomalies, the median tokens out, and how many folds broke an
invariant; and results/sweep-NAME.jsonl, every fold with its point. The knobs are those of
`compressors.config`; `budget` and `view` are axes too.
"""

import argparse
import itertools
import json
import statistics
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from compressors.config import DEFAULT, FoldConfig, with_values
from compressors.route import VIEWS
from evals.l1 import Row, run
from evals.tasks import BANDS, BUDGET, FORMATS, KINDS

_LAB = Path(__file__).resolve().parent.parent
_CALL = ("budget", "view")  # axes that are the call's, not knobs


@dataclass(frozen=True)
class Point:
    budget: int
    view: str
    config: FoldConfig
    axes: tuple[tuple[str, Any], ...]  # what this point sets along the grid, for its row


def points(spec: dict[str, Any]) -> list[Point]:
    """Every combination of the grid's axes, each over the base.

    Raises:
        ValueError: the spec sets no grid, an axis without values, a view that is none, or a knob
            that is not one (from `with_values`).
    """
    base = dict(spec.get("base", {}))
    grid = spec.get("grid", {})
    if not grid:
        raise ValueError('a sweep needs a [grid] with at least one axis, such as "schema.rare" = [0.05, 0.1]')
    for axis, values in grid.items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"grid axis {axis!r} needs a list of values, such as [0.05, 0.1]")
    out = []
    for combo in itertools.product(*grid.values()):
        setting = base | dict(zip(grid, combo, strict=True))
        view = str(setting.get("view", "sample"))
        if view not in VIEWS:
            raise ValueError(f"view {view!r} is none of {', '.join(VIEWS)}")
        knobs = {k: v for k, v in setting.items() if k not in _CALL}
        point = Point(
            int(setting.get("budget", BUDGET)),
            view,
            with_values(DEFAULT, knobs),
            tuple(zip(grid, combo, strict=True)),
        )
        out.append(point)
    return out


def _share(rows: Sequence[Row]) -> str:
    return f"{sum(r.sufficient for r in rows)}/{len(rows)}" if rows else "-"


def report(name: str, results: list[tuple[Point, list[Row]]], by_band: bool = False) -> str:
    axes = [a for a, _ in results[0][0].axes] if results else []
    kinds = [k for k in KINDS if any(r.kind == k for _, rows in results for r in rows)]
    band = ["band", "median in"] if by_band else []
    head = [*axes, *band, "sufficient", "of folded", *kinds, "quiet", "median out", "violations"]
    out = [
        f"# Sweep {name}: layer 1 over {len(results)} points",
        "",
        "Each row folds the same tasks under one point of the grid. Sufficient = the task's scorer "
        "finds the answer in the fold text; the kind columns count every fold of that kind; quiet = "
        "the quiet anomalies (no rule names them); median out = tokens shown; violations = folds that "
        "broke an invariant or made a false claim.",
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    groups = [
        (point, b, [r for r in rows if r.band == b])
        for point, rows in results
        for b in (BANDS if by_band else ("",))
        if not by_band or any(r.band == b for r in rows)
    ]
    for point, b, group in groups:
        rows = group if by_band else next(rs for p, rs in results if p is point)
        folded = [r for r in rows if r.branch != "passthrough"]
        cells = [str(v) for _, v in point.axes]
        if by_band:
            cells += [b, f"{int(statistics.median(r.raw_tokens for r in rows)):,}"]
        cells += [_share(rows), _share(folded)]
        cells += [_share([r for r in rows if r.kind == k]) for k in kinds]
        cells += [_share([r for r in rows if "quiet" in r.task_id])]
        cells += [str(int(statistics.median(r.out_tokens for r in folded))) if folded else "-"]
        cells += [str(sum(1 for r in rows if r.violations))]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="a sweep's TOML file (see sweeps/)")
    ns = parser.parse_args(argv)
    spec = tomllib.loads(ns.spec.read_text(encoding="utf-8"))
    name = str(spec.get("name", ns.spec.stem))
    only = tuple(spec.get("only", ()))
    bands = tuple(spec.get("bands", BANDS[:3]))
    if unknown := set(bands) - set(BANDS):
        parser.error(f"bands names no band {', '.join(sorted(unknown))}: the bands are {', '.join(BANDS)}")
    if unknown := set(only) - set(FORMATS):
        parser.error(
            f"only names no format {', '.join(sorted(unknown))}: the formats are {', '.join(FORMATS)}"
        )
    results = []
    for point in points(spec):
        rows = run(point.budget, only, point.view, point.config, bands)
        results.append((point, rows))
        broken = sum(1 for r in rows if r.violations)
        print(
            f"{dict(point.axes)}: {_share(rows)} sufficient, {broken} violations",
            flush=True,
        )
    results_dir = _LAB / "results"
    with (results_dir / f"sweep-{name}.jsonl").open("w", encoding="utf-8") as f:
        for point, rows in results:
            for r in rows:
                f.write(json.dumps({"point": dict(point.axes), "budget": point.budget} | asdict(r)) + "\n")
    text = report(name, results, by_band=spec.get("by") == "band")
    (results_dir / f"sweep-{name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
