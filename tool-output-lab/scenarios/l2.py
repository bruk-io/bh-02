"""Layer 2 on the scenarios: headless Claude Code in a freshly built world, without the hook (native)
or with it (fold), each run on a world of its own so an edit or a checkout never leaks between runs.

    ./lab scenarios-l2 --size M L --seeds 5 --conditions native --reps 2 --max-cost 5 [--dry-run]

A session gets the task's prompt and answer instruction, Bash, Read, Grep and Glob (and Edit for an
edit task), and no user-level settings or plugins (`--setting-sources project,local`), so what it
spends is the task's. Its row holds the score, the session's tokens and cost (`evals.l2.Session`),
and every call it made with the size of what came back. Only open seeds are run here; a sealed set
is run once, through `scenarios.seal.begin_run`.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path
from typing import Any

from compressors.common import estimate_tokens
from compressors.config import FoldConfig
from evals.l2 import Run, Session, hook_entries, hook_settings, parse_stream, run_all
from evals.truth import ANSWER_INSTRUCTION, Edited, answer_line, score_answer
from scenarios import code
from scenarios.seal import open_seeds

_LAB = Path(__file__).resolve().parent.parent
CONDITIONS = ("native", "fold")
KINDS = ("failing", "commit", "callers", "lookup", "edit")
_FINAL = FoldConfig(banner="exact")  # the final version: schema, the exact-counts banner
_COST_PER_RUN = {"haiku": 0.02, "sonnet": 0.25}  # rough: a scenario takes more turns than a v1 task
_TIMEOUT = 900


def prompt_for(t: code.Task) -> str:
    return f"{t.prompt}\n\n{ANSWER_INSTRUCTION['edit' if t.kind == 'edit' else t.kind]}"


def tools_for(t: code.Task) -> str:
    return "Bash,Read,Grep,Glob" + (",Edit" if t.kind == "edit" else "")


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def calls_in(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Every tool call of a stream-json session: the tool, what it was given (a command, a path or a
    pattern, cut to 200 characters), and how many tokens came back."""
    calls: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):  # a line that is JSON but not an event
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") != "ToolSearch":
                given = block.get("input") or {}
                what = (
                    given.get("command")
                    or given.get("file_path")
                    or given.get("pattern")
                    or json.dumps(given)
                )
                calls[str(block.get("id"))] = {
                    "tool": block.get("name"),
                    "input": str(what)[:200],
                    "tokens": 0,
                }
            elif block.get("type") == "tool_result" and (call := calls.get(str(block.get("tool_use_id")))):
                call["tokens"] = estimate_tokens(_result_text(block))
    return list(calls.values())


def unprefixed(answer: str, prefix: str) -> str:
    """The answer with `prefix` taken off every name that starts with it, so "shop.orders.total" is
    scored as the "orders.total" it names."""
    return re.sub(rf"(?<![\w.]){re.escape(prefix)}(?=\w)", "", answer) if prefix else answer


def rescored(row: dict[str, Any]) -> dict[str, Any]:
    """A row scored again from its answer with today's scorer. An edit (scored from the file) and a
    commit (whose truth needs the built hashes) keep their score."""
    if row["kind"] in ("edit", "commit") or row["error"]:
        return row
    w = code.world(row["seed"], row["size"])
    shas = tuple("0" * 40 for _ in w.history)  # these kinds' truths do not use the hashes
    t = next(x for x in code.tasks(w, code.Built(Path("."), shas)) if x.task_id.endswith(f"-{row['kind']}"))
    score = score_answer(t.truth, unprefixed(row["answer"], t.prefix))
    return {**row, "correct": score.correct, "recall": score.recall, "precision": score.precision}


def _failed(error: str) -> Session:
    return Session("", 0, False, False, 0, False, 0.0, _TIMEOUT * 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, error)


def run_one(
    size: str, seed: int, kind: str, condition: str, model: str, rep: int, log: Path
) -> dict[str, Any]:
    """One session on one task of a freshly built world, scored."""
    with tempfile.TemporaryDirectory(prefix="scenario-") as d:
        w = code.world(seed, size)
        built = code.build(w, Path(d) / "repo")
        t = next(x for x in code.tasks(w, built) if x.task_id.endswith(f"-{kind}"))
        original = (built.root / t.path).read_text(encoding="utf-8") if t.path else ""
        settings = Path(d) / "settings.json"
        hook = hook_settings("all", log, "Bash", "schema", _FINAL) if condition == "fold" else {}
        settings.write_text(json.dumps(hook), encoding="utf-8")
        command = ["claude", "-p", prompt_for(t), "--model", model, "--max-turns", "30"]
        command += ["--output-format", "stream-json", "--verbose", "--strict-mcp-config"]
        command += ["--setting-sources", "project,local", "--settings", str(settings)]
        command += ["--allowedTools", tools_for(t)]
        try:
            proc = subprocess.run(
                command,
                cwd=built.root,
                env=dict(os.environ),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                check=False,
            )
            lines = proc.stdout.splitlines()
            session, calls = parse_stream(lines), calls_in(lines)
            if session.error:
                session = replace(session, error=f"{session.error}; {proc.stderr[-300:]}")
        except subprocess.TimeoutExpired:
            session, calls = _failed(f"timed out after {_TIMEOUT}s"), []
        edited = (built.root / t.path).read_text(encoding="utf-8") if t.path else ""
    extra: dict[str, Any] = {}
    if isinstance(t.truth, Edited):
        problem = t.truth.check(original, edited)
        correct, recall, precision, parsed = problem is None, None, None, True
        extra["edit_problem"] = problem
    else:
        score = score_answer(t.truth, unprefixed(session.answer, t.prefix))
        correct, recall, precision, parsed = score.correct, score.recall, score.precision, score.parsed
    folds = [
        e for e in hook_entries(log, session.session_id) if e.get("branch", "passthrough") != "passthrough"
    ]
    return {
        "task_id": t.task_id,
        "family": "code",
        "kind": kind,
        "size": size,
        "seed": seed,
        "condition": condition,
        "rep": rep,
        "model": model,
        "correct": correct,
        "parsed": parsed,
        "recall": recall,
        "precision": precision,
        "answer_line": answer_line(session.answer),
        **{k: v for k, v in asdict(session).items() if k != "answer"},
        "folds": len(folds),
        "calls": calls,
        "large_calls": sum(c["tokens"] > 2000 for c in calls),
        "answer": session.answer[-2000:],
        **extra,
    }


def _row(
    size: str, seed: int, kind: str, condition: str, model: str, rep: int, log: Path
) -> list[dict[str, Any]]:
    return [run_one(size, seed, kind, condition, model, rep, log)]


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def report(rows: list[dict[str, Any]], model: str) -> str:
    """Per task kind and size: how often each condition answered right, and what a run cost; then
    the commands whose output was large, which is where the hook can act."""
    scored = [r for r in rows if not r["error"]]
    out = [
        f"# Scenarios, layer 2: code and tests on {model}",
        "",
        f"{len(rows)} runs, {len(rows) - len(scored)} failed to produce an answer (not scored).",
        f"Spent ${sum(r['cost_usd'] for r in rows):.2f}.",
        "",
        "| task | size | condition | right | median turns | median final context | median cost"
        " | runs with a large output |",
        "|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in scored:
        groups[(r["kind"], r["size"], r["condition"])].append(r)
    for kind in KINDS:
        for (k, size, condition), rs in sorted(groups.items()):
            if k != kind:
                continue
            right = sum(bool(r["correct"]) for r in rs)
            out.append(
                f"| {kind} | {size} | {condition} | {right} of {len(rs)} ({right / len(rs):.0%}) |"
                f" {_median([r['turns'] for r in rs]):.0f} |"
                f" {_median([r['final_context'] for r in rs]):,.0f} |"
                f" ${_median([r['cost_usd'] for r in rs]):.4f} |"
                f" {sum(r['large_calls'] > 0 for r in rs)} of {len(rs)} |"
            )
    large: dict[str, list[int]] = defaultdict(list)
    for r in scored:
        for c in r["calls"]:
            if c["tokens"] > 2000:
                large[f"{c['tool']}: {' '.join(str(c['input']).split()[:3])}"].append(c["tokens"])
    out += [
        "",
        "## Calls whose output was over 2,000 tokens",
        "",
        "| call | times | median tokens |",
        "|---|---|---|",
    ]
    for name, sizes in sorted(large.items(), key=lambda kv: -len(kv[1]))[:25]:
        out.append(f"| `{name}` | {len(sizes)} | {_median([float(s) for s in sizes]):,.0f} |")
    misses = [r for r in scored if not r["correct"]][:12]
    out += ["", "## Some misses", ""]
    out += [
        f"- {r['task_id']} ({r['condition']}):"
        f" {r.get('edit_problem') or r['answer_line'] or 'no ANSWER line'}"
        for r in misses
    ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="./lab scenarios-l2", description=__doc__.split("\n\n")[0] if __doc__ else None
    )
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--size", nargs="+", choices=("M", "L"), default=["M"])
    parser.add_argument("--seeds", type=int, default=5, help="how many open seeds, from 0")
    parser.add_argument("--kinds", nargs="+", choices=KINDS, default=list(KINDS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=["native"])
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--max-cost", type=float, help="USD: once the runs so far cost this much, start no more"
    )
    parser.add_argument("--name", default="scenarios-l2")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the runs and an estimated cost; run nothing"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="keep results/NAME.jsonl's rows (scored again) and run only the jobs they do not cover",
    )
    ns = parser.parse_args(argv)
    jobs = [
        (size, seed, kind, condition, rep)
        for rep in range(ns.reps)
        for size in ns.size
        for seed in open_seeds(ns.seeds)
        for kind in ns.kinds
        for condition in ns.conditions
    ]
    per_run = next((v for k, v in _COST_PER_RUN.items() if k in ns.model), _COST_PER_RUN["sonnet"])
    if ns.dry_run:
        print(f"{len(jobs)} runs, about ${len(jobs) * per_run:.2f} on {ns.model} (a rough estimate)")
        return 0
    results = _LAB / "results"
    kept: list[dict[str, Any]] = []
    if ns.resume and (old := results / f"{ns.name}.jsonl").exists():
        kept = [rescored(json.loads(line)) for line in old.read_text(encoding="utf-8").splitlines() if line]
        done = {(r["size"], r["seed"], r["kind"], r["condition"], r["rep"]) for r in kept}
        jobs = [j for j in jobs if j not in done]
        print(f"resuming: {len(kept)} rows kept and scored again, {len(jobs)} runs to go")
    runs: list[Run] = [
        partial(_row, size, seed, kind, cond, ns.model, rep) for size, seed, kind, cond, rep in jobs
    ]
    rest = f"{ns.name}-rest" if kept else ns.name
    rows = kept + run_all(runs, len(jobs), rest, ns.workers, ns.max_cost)
    if kept:  # one file of rows, and one hook log, for the whole run
        (results / f"{ns.name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        (results / f"{rest}.jsonl").unlink()
        if (log := results / f"{rest}-hook.jsonl").exists():
            with (results / f"{ns.name}-hook.jsonl").open("a", encoding="utf-8") as f:
                f.write(log.read_text(encoding="utf-8"))
            log.unlink()
    text = report(rows, ns.model)
    (results / f"{ns.name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
