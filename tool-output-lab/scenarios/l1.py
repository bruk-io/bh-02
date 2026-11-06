"""Layer 1 on the scenarios: every task's probe commands run in its built world, and their real
outputs folded and checked as layer 1 checks any output. No model is involved.

    ./lab scenarios [--size M] [--seeds 5] [--name scenarios-l1-code-M]

A probe's query is its command, as the hook takes it from a Bash call, so `grep -rn fee_for_points`
folds with `fee_for_points` as the query. Only open seeds are built here: a sealed set is built
only for its one sealed run (scenarios/seal.py).
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from functools import partial
from pathlib import Path

from claude_code.hook import viewed_file
from compressors.config import FoldConfig
from evals import l1
from evals.tasks import BUDGET
from evals.tasks import Task as EvalTask
from scenarios import code
from scenarios.seal import open_seeds

_LAB = Path(__file__).resolve().parent.parent
_CONFIG = FoldConfig(banner="exact")  # the final version: the banner does not change a fold's text


def probe_tasks(w: code.World, built: code.Built) -> list[EvalTask]:
    """Each task's probes as layer-1 tasks: the command's real output, the task's truth."""
    out = []
    for t in code.tasks(w, built):
        for cmd in t.probes:
            text = subprocess.run(
                cmd, shell=True, cwd=built.root, capture_output=True, text=True, check=False
            ).stdout
            out.append(
                EvalTask(
                    f"{t.task_id} | {cmd}",
                    "code-tests",
                    t.kind,
                    w.size,
                    viewed_file(cmd) or "",  # a whole file's view folds as code, as the hook folds it
                    t.prompt,
                    t.truth,
                    cmd,
                    partial(str, text),  # the output, every time it is asked for
                )
            )
    return out


def run(size: str, seeds: tuple[int, ...]) -> list[l1.Row]:
    rows = []
    root = Path(tempfile.mkdtemp(prefix="scenarios-"))
    try:
        for seed in seeds:
            w = code.world(seed, size)
            built = code.build(w, root / f"code-{size}-{seed}")
            rows += [
                l1.check(t, BUDGET, query_on=True, view="schema", config=_CONFIG)
                for t in probe_tasks(w, built)
            ]
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return rows


def report(rows: list[l1.Row], size: str, seeds: int) -> str:
    """The folds' violations first, then each task kind's probes: output and envelope sizes, and
    how often the envelope alone answers."""
    bad = [r for r in rows if r.violations]
    out = [
        f"# Layer 1 on the code-and-tests scenarios, size {size}, open seeds 0 to {seeds - 1}",
        "",
        "Each task's probe commands run in its built world; their real outputs are folded as the hook",
        "folds a Bash result (the command is the query), under the final recipe, and checked.",
        "",
        f"## Invariants: {len(bad)} folds of {len(rows)} with violations",
        "",
        *([f"- {r.task_id}: {'; '.join(r.violations)}" for r in bad] or ["None."]),
        "",
        "## By task kind and command",
        "",
        "| task | command | median output | folded | median envelope | answered by the envelope |",
        "|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str], list[l1.Row]] = {}
    for r in rows:
        task_id, cmd = r.task_id.split(" | ", 1)
        general = re.sub(r"shop/\w+\.py", "shop/<module>.py", cmd)
        general = re.sub(r"\b\w+_for_\w+\b", "<function>", general)
        groups.setdefault((task_id.rsplit("-", 1)[1], general), []).append(r)
    for (kind, cmd), rs in groups.items():
        ins = sorted(r.raw_tokens for r in rs)
        folded = [r for r in rs if r.branch != "passthrough"]
        outs = sorted(r.out_tokens for r in folded)
        envelope = f"{outs[len(outs) // 2]:,}" if outs else ""
        answered = f"{sum(r.sufficient for r in folded)} of {len(folded)}" if folded else ""
        out.append(
            f"| {kind} | `{cmd}` | {ins[len(ins) // 2]:,} | {len(folded)} of {len(rs)} |"
            f" {envelope} | {answered} |"
        )
    out += [
        "",
        "Answered by the envelope counts only the outputs it replaced: an output under the threshold",
        "reaches the model whole. An edit is answered when the envelope shows the definition with its",
        "line number, where the edit starts.",
    ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="./lab scenarios", description=__doc__.split("\n\n")[0] if __doc__ else None
    )
    parser.add_argument("--size", choices=("M", "L"), default="M")
    parser.add_argument("--seeds", type=int, default=5, help="how many open seeds, from 0")
    parser.add_argument("--name", default="", help="the results file's name (default scenarios-l1-code-SIZE)")
    ns = parser.parse_args(argv)
    rows = run(ns.size, open_seeds(ns.seeds))
    name = ns.name or f"scenarios-l1-code-{ns.size}"
    results = _LAB / "results"
    with (results / f"{name}.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(asdict(r)) + "\n")
    text = report(rows, ns.size, ns.seeds)
    (results / f"{name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if any(r.violations for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
