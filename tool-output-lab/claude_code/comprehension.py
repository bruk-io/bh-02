"""Comprehension A/B: does telling Claude about `fold` help it answer structural questions about large files?

    ./lab comprehension [--model claude-sonnet-5-5] [--reps 2] [--workers 4] [--name comp-1]

Each question is about the structure of one large standard-library file (which methods of a class
are async, which methods are defined in both branches of a platform check, ...), with the answer
computed from the file by Python's `ast`, so nothing is hand-written. Both conditions have `fold`
on the PATH; in `fold` a project CLAUDE.md says what it does, in `native` nothing mentions it, so
Claude works as it would anyway (it greps an outline, the probes found). A run is correct when the
answer names at least 90% of the expected items as whole words. Writes `results/<name>.jsonl` and
`results/<name>.md`. Costs money: each run is a real Claude Code session.
"""

import argparse
import ast
import json
import os
import statistics
import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from claude_code.ab import parse_stream
from harness.needle import contains

_LAB = Path(__file__).resolve().parent.parent
_STDLIB = Path("/usr/local/lib/python3.13")
CONDITIONS = ("native", "fold")
_CLAUDE_MD = """# Tools

`fold FILE` prints a file's outline with its real line numbers: every class, function and method
header, and the blocks inside them, opened as far as a token budget allows (`--budget N`, default
2000; 6000 or more suits a large file). A folded part shows as `[... lines A-B folded]`; read it with
Read offset=A limit=B-A+1. Use it to see the structure of a large file before reading parts of it.
"""


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == name)


def _defs(body: list[ast.stmt]) -> set[str]:
    return {n.name for n in body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}


def _async_methods(src: str) -> frozenset[str]:
    return frozenset(
        n.name for n in _class(ast.parse(src), "BaseEventLoop").body if isinstance(n, ast.AsyncFunctionDef)
    )


def _both_platforms(src: str) -> frozenset[str]:
    names: set[str] = set()
    for n in _class(ast.parse(src), "Popen").body:
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "_mswindows":
            names |= _defs(n.body) & _defs(n.orelse)
    return frozenset(names)


def _action_subclasses(src: str) -> frozenset[str]:
    return frozenset(
        c.name
        for c in ast.walk(ast.parse(src))
        if isinstance(c, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == "Action" for b in c.bases)
    )


def _close_methods(src: str) -> frozenset[str]:
    out: set[str] = set()
    for c in ast.walk(ast.parse(src)):
        if isinstance(c, ast.ClassDef):
            for n in c.body:
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == "close":
                    out |= {c.name, str(n.lineno)}
    return frozenset(out)


def _tp_cached(src: str) -> frozenset[str]:
    def cached(d: ast.expr) -> bool:
        target = d.func if isinstance(d, ast.Call) else d
        return isinstance(target, ast.Name) and target.id == "_tp_cache"

    return frozenset(
        f.name
        for f in ast.parse(src).body
        if isinstance(f, ast.FunctionDef) and any(map(cached, f.decorator_list))
    )


@dataclass(frozen=True)
class Question:
    qid: str
    file: str  # relative to the standard library
    prompt: str
    truth: Callable[[str], frozenset[str]]

    def path(self) -> Path:
        return _STDLIB / self.file

    def expected(self) -> frozenset[str]:
        return self.truth(self.path().read_text(encoding="utf-8"))


QUESTIONS = (
    Question(
        "async-methods",
        "asyncio/base_events.py",
        "In {path}, which methods of the class BaseEventLoop itself are coroutines (defined with "
        "`async def`), private ones included? List every name.",
        _async_methods,
    ),
    Question(
        "both-platforms",
        "subprocess.py",
        "In {path}, class Popen defines some methods once for Windows and once for POSIX, in the two "
        "branches of its `if _mswindows:` check. Which method names are defined in both branches? "
        "List every name.",
        _both_platforms,
    ),
    Question(
        "action-subclasses",
        "argparse.py",
        "In {path}, which classes subclass Action directly (Action is in their bases)? List every name.",
        _action_subclasses,
    ),
    Question(
        "close-methods",
        "asyncio/base_events.py",
        "In {path}, which classes define a method named close? For each, give the class name and the "
        "line number where its close method is defined.",
        _close_methods,
    ),
    Question(
        "tp-cache",
        "typing.py",
        "In {path}, which top-level functions (not methods) are decorated with _tp_cache, as "
        "@_tp_cache or @_tp_cache(...)? List every name.",
        _tp_cached,
    ),
)


def score(answer: str, expected: frozenset[str]) -> float:
    """The share of expected items the answer names as whole words."""
    return sum(contains(answer, e) for e in expected) / len(expected)


def _fold_bin(work: Path) -> Path:
    bin_dir = work / "bin"
    bin_dir.mkdir()
    script = bin_dir / "fold"
    script.write_text(
        "#!/bin/sh\n"
        f'exec env PYTHONPATH="{_LAB}" uv run -q --no-project --python 3.15 --with ast-grep-py '
        'python -m compressors.cli "$@"\n'
    )
    script.chmod(0o755)
    return bin_dir


def run_one(q: Question, condition: str, model: str, rep: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="comp-") as work:
        w = Path(work)
        env = {**os.environ, "PATH": f"{_fold_bin(w)}:{os.environ.get('PATH', '')}"}
        if condition == "fold":
            (w / "CLAUDE.md").write_text(_CLAUDE_MD)
        command = [
            "claude", "-p", q.prompt.format(path=q.path()),
            "--model", model,
            "--allowedTools", "Read,Grep,Glob,Bash",
            "--max-turns", "25",
            "--output-format", "stream-json", "--verbose",
        ]  # fmt: skip
        try:
            proc = subprocess.run(
                command, cwd=w, env=env, capture_output=True, text=True, timeout=900, check=False
            )
            lines = proc.stdout.splitlines()
            stats = asdict(parse_stream(lines, needle="\x00"))
            used_fold = any(
                '"name": "Bash"' in line and "fold " in line and '"type": "tool_use"' in line
                for line in lines
            )
            error = stats["error"] and f"{stats['error']}; stderr: {proc.stderr[-300:]}"
        except subprocess.TimeoutExpired:
            stats = {"answer": "", "tool_calls": 0, "turns": 0, "cost_usd": 0.0, "input_tokens": 0}
            stats |= {"output_tokens": 0, "duration_ms": 900_000}
            used_fold, error = False, "timed out after 900s"
    expected = q.expected()
    recall = score(stats["answer"], expected)
    stats.pop("correct", None)
    stats.pop("read_saved_file", None)
    stats["error"] = error
    head = {"qid": q.qid, "condition": condition, "rep": rep, "model": model, "recall": recall}
    return {**head, "correct": recall >= 0.9, "used_fold": used_fold, "expected": sorted(expected), **stats}


def summarise(rows: list[dict[str, Any]], model: str) -> str:
    out = [
        f"# Comprehension A/B: Claude's own approach against `fold` named in CLAUDE.md ({model})",
        "",
        f"{len(rows)} runs, ${sum(r['cost_usd'] for r in rows):.2f}. Correct = the answer names at least 90%",
        "of the expected items (computed with `ast`).",
        "",
        "| question | condition | correct | mean recall | median input tokens | median cost | median calls "
        "| median time | ran fold |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for q in QUESTIONS:
        for cond in CONDITIONS:
            rs = [r for r in rows if r["qid"] == q.qid and r["condition"] == cond]
            if not rs:
                continue
            out.append(
                f"| {q.qid} | {cond} | {sum(r['correct'] for r in rs)}/{len(rs)} "
                f"| {statistics.mean(r['recall'] for r in rs):.2f} "
                f"| {int(statistics.median(r['input_tokens'] for r in rs))} "
                f"| ${statistics.median(r['cost_usd'] for r in rs):.4f} "
                f"| {statistics.median(r['tool_calls'] for r in rs)} "
                f"| {statistics.median(r['duration_ms'] for r in rs) / 1000:.1f}s "
                f"| {sum(r['used_fold'] for r in rs)}/{len(rs)} |"
            )
    out += ["", "| condition | correct | mean recall | total cost | median input tokens | median time |"]
    out.append("|---|---|---|---|---|---|")
    for cond in CONDITIONS:
        rs = [r for r in rows if r["condition"] == cond]
        if rs:
            out.append(
                f"| {cond} | {sum(r['correct'] for r in rs)}/{len(rs)} "
                f"| {statistics.mean(r['recall'] for r in rs):.2f} "
                f"| ${sum(r['cost_usd'] for r in rs):.2f} "
                f"| {int(statistics.median(r['input_tokens'] for r in rs))} "
                f"| {statistics.median(r['duration_ms'] for r in rs) / 1000:.1f}s |"
            )
    errors = [r for r in rows if r["error"]]
    if errors:
        out += ["", f"{len(errors)} runs had errors:"] + [
            f"- {r['qid']} {r['condition']}: {r['error']}" for r in errors
        ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--name", default="comp-1")
    ns = parser.parse_args(argv)
    jobs = [(q, cond, rep) for rep in range(ns.reps) for q in QUESTIONS for cond in CONDITIONS]
    rows: list[dict[str, Any]] = []
    results = _LAB / "results"
    with (
        ThreadPoolExecutor(ns.workers) as pool,
        (results / f"{ns.name}.jsonl").open("w", encoding="utf-8") as f,
    ):
        for row in pool.map(lambda job: run_one(job[0], job[1], ns.model, job[2]), jobs):
            f.write(json.dumps(row) + "\n")
            f.flush()
            rows.append(row)
            fold_note = "yes" if row["used_fold"] else "no"
            print(f"{len(rows)}/{len(jobs)} {row['qid']} {row['condition']}: recall {row['recall']:.2f} "
                  f"fold={fold_note} ${row['cost_usd']:.4f}", flush=True)  # fmt: skip
    report = summarise(rows, ns.model)
    (results / f"{ns.name}.md").write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
