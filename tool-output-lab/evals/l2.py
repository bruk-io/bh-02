"""Layer 2: headless Claude Code on the eval tasks, native against fold, paired and scored.

    ./lab evals l2 --dry-run [--formats json log] [--bands M L] [--kinds spot count] [--conditions ...]
    ./lab evals l2 --model claude-haiku-5-5 --reps 1 --workers 4 --name l2-haiku-1 [same filters]

The same tasks as layer 1 (`evals.tasks`), answered by real Claude Code sessions and scored by the
same truths (`evals.truth.score_answer`, from the ANSWER line every prompt asks for).

- A synthetic task's payload comes from a fixture MCP server (`claude_code/fixture_mcp.py`) that
  serves that task; conditions: `native`, and the PostToolUse hook in each of its modes: `fold`
  (spilled), `fold-inline` (inline, its default) and `fold-all` (all). On the bash channel the same
  payload is printed by `./<tool>` in the session's folder: `bash-native`, and the hook on Bash,
  `fold-bash` (inline) and `fold-bash-all` (all), both paired against `bash-native`.
- A real-file task names its file in the prompt; conditions: `native` and `fold-tool` (`lab-fold`,
  the fold CLI, on the PATH in both, and named in a CLAUDE.md only in `fold-tool`), and, with Bash
  disallowed, `noshell` (Read, Grep, Glob) and `noshell-fold` (the same and the `fold` MCP tool,
  `claude_code/fold_mcp.py`), which is paired against `noshell`.

Each run records the answer and its score, the tool calls, whether Claude read a saved raw file or
ran `lab-fold`, cost, time, and usage per API request by cache class, with the size of the final
context. The report gives accuracy with Wilson intervals and, per condition against native, paired
differences (Newcombe's interval for accuracy, a bootstrap for the rest), and applies the README's
kill criteria to the intervals; the input criterion is the final context.
`--dry-run` lists the runs and an estimate of their cost without running anything. Costs money.
"""

import argparse
import difflib
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from compressors.common import read_text
from compressors.config import DEFAULT, FoldConfig, label, load, sets, with_sets
from compressors.route import VIEWS
from evals.stats import bootstrap, paired, paired_accuracy, wilson
from evals.tasks import FORMATS, KINDS, TOOLS, Task, bash_prompt, skipped, tasks
from evals.truth import Edited, Truth, answer_line, score_answer, score_edit

_LAB = Path(__file__).resolve().parent.parent
_UV = "uv run -q --no-project --python 3.15 --with ast-grep-py python"
MCP_CONDITIONS = ("native", "fold", "fold-inline", "fold-all")
# The bash channel: the same synthetic payloads, printed by `./<tool>` in the session's folder.
BASH_CONDITIONS = ("bash-native", "fold-bash", "fold-bash-all")
HOOK_MODE = {
    "fold": "spilled",
    "fold-inline": "inline",
    "fold-all": "all",
    "fold-bash": "inline",
    "fold-bash-all": "all",
}  # condition -> TOOL_OUTPUT_LAB_MODE
FILE_CONDITIONS = ("native", "fold-tool", "noshell", "noshell-fold")
# What each condition is paired against: a fold condition against the same session without it.
BASELINE = {"noshell-fold": "noshell", "fold-bash": "bash-native", "fold-bash-all": "bash-native"}
_FOLD_TOOL = "mcp__fold__fold"
_STOP_AFTER_FAILURES = 5
_COST_PER_RUN = {"haiku": 0.007, "sonnet": 0.10, "opus": 0.25}  # rough, from the A/Bs so far
_CLAUDE_MD = """# Tools

`lab-fold FILE` prints a file's outline with its real line numbers: every class, function and method
header, and the blocks inside them, opened as far as a token budget allows (`--budget N`, default
2000; 6000 or more suits a large file). A folded part shows as `[... lines A-B folded]`; read it with
Read offset=A limit=B-A+1. Use it to see the structure of a large file before reading parts of it.
"""


@dataclass(frozen=True)
class Session:
    """What one stream-json session says about itself."""

    answer: str
    tool_calls: int  # excluding ToolSearch
    read_saved_file: bool  # a call opened a file under tool-results/
    ran_fold: bool  # a Bash call ran lab-fold, or the fold MCP tool was called
    turns: int
    hit_max_turns: bool  # it ran out of turns: the model's failure, scored as a wrong answer
    cost_usd: float
    duration_ms: int
    requests: int  # API requests
    input_tokens: int  # uncached input, summed over requests
    cache_read: int
    cache_write: int
    output_tokens: int
    final_context: int  # the last request's whole input: how big the context grew
    error: str | None  # the run failed to produce an answer (no result, an API or usage error): not scored


def parse_stream(lines: Iterable[str]) -> Session:
    """Read a `--output-format stream-json --verbose` session."""
    calls, read_saved, ran_fold = 0, False, False
    usage: dict[str, dict[str, int]] = {}  # per API request (assistant message id), last seen
    result: dict[str, Any] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            message = event.get("message", {})
            if message.get("id") and isinstance(message.get("usage"), dict):
                usage[message["id"]] = message["usage"]
            for block in message.get("content", []):
                if block.get("type") == "tool_use" and block.get("name") != "ToolSearch":
                    calls += 1
                    text = json.dumps(block.get("input", {}))
                    read_saved |= "tool-results/" in text
                    ran_fold |= (block.get("name") == "Bash" and "lab-fold" in text) or block.get(
                        "name"
                    ) == _FOLD_TOOL
        elif event.get("type") == "result":
            result = event

    def total(key: str) -> int:
        return sum(int(u.get(key, 0) or 0) for u in usage.values())

    last = list(usage.values())[-1] if usage else {}
    final = sum(
        int(last.get(k, 0) or 0)
        for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    return Session(
        answer=str(result.get("result") or ""),
        tool_calls=calls,
        read_saved_file=read_saved,
        ran_fold=ran_fold,
        turns=int(result.get("num_turns", 0) or 0),
        hit_max_turns=result.get("subtype") == "error_max_turns",
        cost_usd=float(result.get("total_cost_usd", 0.0) or 0.0),
        duration_ms=int(result.get("duration_ms", 0) or 0),
        requests=len(usage),
        input_tokens=total("input_tokens"),
        cache_read=total("cache_read_input_tokens"),
        cache_write=total("cache_creation_input_tokens"),
        output_tokens=total("output_tokens"),
        final_context=final,
        error=_run_error(result),
    )


def _run_error(result: dict[str, Any]) -> str | None:
    """Why a session produced no answer to score, or None. Running out of turns is not one: it is
    an outcome of the condition (recovering spent the turns), so it is scored as a wrong answer."""
    if not result:
        return "no result event"
    if result.get("is_error") and result.get("subtype") != "error_max_turns":
        return f"{result.get('subtype', 'error')}: {str(result.get('result', ''))[:200]}"
    return None


def conditions_for(t: Task) -> tuple[str, ...]:
    return FILE_CONDITIONS if t.path else MCP_CONDITIONS + BASH_CONDITIONS


def _hook_settings(
    mode: str, log: Path, matcher: str = "mcp__.*", view: str = "sample", config: FoldConfig = DEFAULT
) -> dict[str, Any]:
    knobs = shlex.quote(";".join(sets(config)))
    env = f"TOOL_OUTPUT_LAB_LOG={log} TOOL_OUTPUT_LAB_MODE={mode} TOOL_OUTPUT_LAB_VIEW={view}"
    env += f" TOOL_OUTPUT_LAB_SET={knobs}"
    command = f"cd {_LAB} && {env} {_UV} -m claude_code.hook"
    hook = {"type": "command", "timeout": 30, "command": command}
    return {"hooks": {"PostToolUse": [{"matcher": matcher, "hooks": [hook]}]}}


def bash_channel(
    t: Task, condition: str, w: Path, log: Path, view: str = "sample", config: FoldConfig = DEFAULT
) -> list[str]:
    """The flags (and files in the run's folder) for a synthetic task on the bash channel: `./<tool>`
    prints the payload (the task id reaches it through the environment, not the script), and the
    hook, when the condition has one, folds Bash."""
    script = w / TOOLS[t.fmt]
    script.write_text(f'#!/bin/sh\ncd "{_LAB}" && exec {_UV} -m claude_code.fixture_cmd\n')
    script.chmod(0o755)
    mode = HOOK_MODE.get(condition)
    (w / "settings.json").write_text(
        json.dumps(_hook_settings(mode, log, "Bash", view, config) if mode else {})
    )
    return ["--strict-mcp-config", "--settings", "settings.json", "--allowedTools", "Bash,Read,Grep"]


def _fold_shim(bin_dir: Path, view: str = "sample", config: FoldConfig = DEFAULT) -> None:
    bin_dir.mkdir()
    shim = bin_dir / "lab-fold"  # not `fold`, which would shadow coreutils fold
    knobs = " ".join(f"--set {shlex.quote(s)}" for s in sets(config))
    shim.write_text(
        f'#!/bin/sh\nexec env PYTHONPATH="{_LAB}" {_UV} -m compressors.cli --view {view} {knobs} "$@"\n'
    )
    shim.chmod(0o755)


def file_tools(
    condition: str, w: Path, edit: bool = False, view: str = "sample", config: FoldConfig = DEFAULT
) -> list[str]:
    """The flags (and files in the run's folder) that set up a file task's condition. Edit is allowed
    only for an edit task, whose file is a copy in the run's folder: read tasks name real files."""
    edits = ",Edit" if edit else ""
    if condition in ("noshell", "noshell-fold"):
        tools = f"Read,Grep,Glob{edits}"
        flags = ["--strict-mcp-config", "--disallowedTools", "Bash"]
        if condition == "noshell-fold":
            env = {"TOOL_OUTPUT_LAB_VIEW": view, "TOOL_OUTPUT_LAB_SET": ";".join(sets(config))}
            server = {
                "command": "sh",
                "args": ["-c", f"cd {_LAB} && exec {_UV} -m claude_code.fold_mcp"],
                "env": env,
            }
            (w / "mcp.json").write_text(json.dumps({"mcpServers": {"fold": server}}))
            flags += ["--mcp-config", "mcp.json"]
            tools += f",{_FOLD_TOOL}"
        return [*flags, "--allowedTools", tools]
    _fold_shim(w / "bin", view, config)
    if condition == "fold-tool":
        (w / "CLAUDE.md").write_text(_CLAUDE_MD)
    return ["--strict-mcp-config", "--allowedTools", f"Read,Grep,Glob,Bash{edits}"]


def run_one(
    t: Task,
    condition: str,
    model: str,
    rep: int,
    log: Path,
    view: str = "sample",
    config: FoldConfig = DEFAULT,
) -> dict[str, Any]:
    """One Claude Code session for one task under one condition, scored."""
    with tempfile.TemporaryDirectory(prefix="l2-") as work:
        w = Path(work)
        env = dict(os.environ)
        env["PATH"] = f"{w / 'bin'}:{env.get('PATH', '')}"  # lab-fold, where the condition puts it there
        bash = condition in BASH_CONDITIONS
        prompt = bash_prompt(t) if bash else t.prompt
        command = ["claude", "-p", prompt, "--model", model, "--max-turns", "25"]
        command += ["--output-format", "stream-json", "--verbose"]
        edit = isinstance(t.truth, Edited)
        if bash:
            command += bash_channel(t, condition, w, log, view, config)
            env["TOOL_OUTPUT_LAB_TASK"] = t.task_id
        elif t.path:
            command += file_tools(condition, w, edit, view, config)
            copy, original = w / Path(t.path).name, Path(t.path)
            if edit:
                copy.write_text(t.payload(), encoding="utf-8")
                guarded = original.read_bytes()
        else:
            server = {
                "command": "sh",
                "args": ["-c", f"cd {_LAB} && exec {_UV} -m claude_code.fixture_mcp"],
                "env": {"TOOL_OUTPUT_LAB_TASK": t.task_id},
            }
            (w / "mcp.json").write_text(json.dumps({"mcpServers": {"fixture": server}}))
            mode = HOOK_MODE.get(condition)
            (w / "settings.json").write_text(
                json.dumps(_hook_settings(mode, log, view=view, config=config) if mode else {})
            )
            command += ["--mcp-config", "mcp.json", "--strict-mcp-config", "--settings", "settings.json"]
            command += ["--allowedTools", f"mcp__fixture__{TOOLS[t.fmt]},Bash,Read,Grep"]
        try:
            proc = subprocess.run(
                command, cwd=w, env=env, capture_output=True, text=True, timeout=900, check=False
            )
            session = parse_stream(proc.stdout.splitlines())
            if session.error:
                session = Session(**{**asdict(session), "error": f"{session.error}; {proc.stderr[-300:]}"})
        except subprocess.TimeoutExpired:
            session = Session(
                answer="",
                tool_calls=0,
                read_saved_file=False,
                ran_fold=False,
                turns=0,
                hit_max_turns=False,
                cost_usd=0.0,
                duration_ms=900_000,
                requests=0,
                input_tokens=0,
                cache_read=0,
                cache_write=0,
                output_tokens=0,
                final_context=0,
                error="timed out after 900s",
            )
        if edit:
            edited = read_text(str(copy))
            if original.read_bytes() != guarded:  # the copy was the one to edit: put the original back
                original.write_bytes(guarded)
                session = replace(session, error=f"edited the original {original}, not the copy (restored)")
    extra: dict[str, Any] = {}
    if isinstance(t.truth, Edited):
        score, problem = score_edit(t.truth, t.payload(), edited)
        diff = "".join(difflib.unified_diff(t.payload().splitlines(True), edited.splitlines(True), n=1))
        extra = {
            "edit_problem": problem,
            "edit_diff": diff[:_MAX_DIFF],
            "edit_diff_cut": len(diff) > _MAX_DIFF,
        }
    else:
        score = score_answer(t.truth, session.answer)
    head = {"task_id": t.task_id, "fmt": t.fmt, "kind": t.kind, "band": t.band, "condition": condition}
    return {
        **head,
        "rep": rep,
        "model": model,
        "view": view,
        "config": label(config),
        "correct": score.correct,
        "parsed": score.parsed,
        "recall": score.recall,
        "precision": score.precision,
        "answer_line": answer_line(session.answer),
        **{k: v for k, v in asdict(session).items() if k != "answer"},
        "answer": session.answer[-2000:],  # the end: the ANSWER line and what led to it
        **extra,
    }


def _ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} [{lo:.0%}, {hi:.0%}]"


def _diffs(
    base: dict[str, dict[str, Any]], runs: dict[str, dict[str, Any]], field: str, scale: float = 1.0
) -> list[float]:
    return paired(
        {k: float(v[field]) * scale for k, v in base.items()},
        {k: float(v[field]) * scale for k, v in runs.items()},
    )


def _against(condition: str) -> str:
    """The condition, and what it is paired against when that is not native."""
    base = BASELINE.get(condition)
    return f"{condition} (against {base})" if base else condition


def _paired(base: dict[str, dict[str, Any]], runs: dict[str, dict[str, Any]]) -> str:
    """The table cells for one condition against native: each change with its 95% interval, and the
    verdict the kill criteria give."""
    diffs = partial(_diffs, base, runs)  # (field, scale=1.0): this condition minus native, per pair
    shared = base.keys() & runs.keys()
    outcome = Counter((runs[k]["correct"], base[k]["correct"]) for k in shared)  # (here, native)
    gains, losses = outcome[True, False], outcome[False, True]
    change, lo, hi, p = paired_accuracy(outcome[True, True], gains, losses, outcome[False, False])
    acc = (change, lo, hi)
    cost, ctx, inp, secs = (
        bootstrap(diffs("cost_usd")),
        bootstrap(diffs("final_context")),
        bootstrap(diffs("all_input")),
        bootstrap(diffs("duration_ms", 1e-3)),
    )
    n = len(diffs("correct"))
    keeps_answers, saves = acc[1] > -0.03, ctx[2] < 0
    verdict = (
        "passes" if keeps_answers and saves else "fails" if acc[2] < -0.03 or ctx[1] > 0 else "undecided"
    )
    verdict += " (indicative: under 30 pairs)" if n < 30 else ""
    return (
        f"| {n} | {acc[0]:+.0%} [{acc[1]:+.0%}, {acc[2]:+.0%}] | {gains}/{losses}, p {p:.2f} "
        f"| ${cost[0]:+.4f} [{cost[1]:+.4f}, {cost[2]:+.4f}] "
        f"| {ctx[0]:+.0f} [{ctx[1]:+.0f}, {ctx[2]:+.0f}] "
        f"| {inp[0]:+.0f} [{inp[1]:+.0f}, {inp[2]:+.0f}] "
        f"| {secs[0]:+.1f}s [{secs[1]:+.1f}, {secs[2]:+.1f}] | {verdict} |"
    )


def report(rows: list[dict[str, Any]], model: str) -> str:
    """The run as tables. Runs that failed to produce an answer (see `_run_error`) are listed, not
    scored: counted as wrong at no cost, they would make a condition look both worse and cheaper."""
    scored = [
        r | {"all_input": r["input_tokens"] + r["cache_read"] + r["cache_write"]}
        for r in rows
        if not r["error"]
    ]
    out = [
        f"# Layer 2: Claude Code on the eval tasks ({model})",
        "",
        f"{len(rows)} runs, ${sum(r['cost_usd'] for r in rows):.2f}; {len(scored)} scored, "
        f"{len(rows) - len(scored)} failed to answer (listed at the end). Correct = the ANSWER line "
        "matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired "
        f"differences)."
        f" {sum(not r['parsed'] for r in scored)} answers had no ANSWER line (scored on "
        f"their prose); {sum(r.get('hit_max_turns', False) for r in scored)} ran out of turns "
        "(scored as wrong).",
        "",
        "## By task group",
        "",
        "| format | kind | band | condition | correct | median cost | median final context | median calls "
        "| read the saved file | ran lab-fold |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in scored:
        groups[(r["fmt"], r["kind"], r["band"], r["condition"])].append(r)
    for (fmt, kind, band, cond), rs in sorted(groups.items()):
        out.append(
            f"| {fmt} | {kind} | {band} | {cond} | {_ci(sum(r['correct'] for r in rs), len(rs))} "
            f"| ${statistics.median(r['cost_usd'] for r in rs):.4f} "
            f"| {int(statistics.median(r['final_context'] for r in rs))} "
            f"| {statistics.median(r['tool_calls'] for r in rs)} "
            f"| {sum(r['read_saved_file'] for r in rs)}/{len(rs)} "
            f"| {sum(r['ran_fold'] for r in rs)}/{len(rs)} |"
        )
    columns = (
        "| pairs | accuracy change | right only here / only native | cost change | final context change "
        "| input change | time change | verdict |"
    )
    out += [
        "",
        "## Each condition against native (or its baseline), paired by task and repetition, per band",
        "",
    ]
    out += [f"| format | band | condition {columns}", "|---|---|---|---|---|---|---|---|---|---|---|"]
    by_cell: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in scored:  # a pair needs both runs scored
        by_cell[(r["fmt"], r["band"], r["condition"])][f"{r['task_id']}#{r['rep']}"] = r
    for (fmt, band, cond), runs in sorted(by_cell.items()):
        base = BASELINE.get(cond, "native")
        if cond != base and (fmt, band, base) in by_cell:
            out.append(f"| {fmt} | {band} | {_against(cond)} {_paired(by_cell[(fmt, band, base)], runs)}")
    out += ["", "## Every format together, per size band", ""]
    out += [f"| band | condition {columns}", "|---|---|---|---|---|---|---|---|---|---|"]
    by_band: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in scored:
        by_band[(r["band"], r["condition"])][f"{r['task_id']}#{r['rep']}"] = r
    for (band, cond), runs in sorted(by_band.items()):
        base = BASELINE.get(cond, "native")
        if cond != base and (band, base) in by_band:  # pairs: the tasks both conditions ran
            out.append(f"| {band} | {_against(cond)} {_paired(by_band[(band, base)], runs)}")
    out += [
        "",
        "Verdict: passes when the accuracy change's lower bound is above -3 points and the final context "
        "shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the "
        "context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired "
        "proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of "
        "the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed "
        "input, every input token the requests carried (cached or not), is reported beside it.",
    ]
    errors = [r for r in rows if r["error"]]
    if errors:
        out += ["", f"{len(errors)} runs had errors:"] + [
            f"- {r['task_id']} {r['condition']}: {r['error']}" for r in errors
        ]
    return "\n".join(out) + "\n"


def select(
    formats: Iterable[str],
    kinds: Iterable[str],
    bands: Iterable[str],
    conditions: Iterable[str] | None,
    ids: Iterable[str] = (),
) -> list[tuple[Task, str]]:
    want_f, want_k, want_b, want_ids = set(formats), set(kinds), set(bands), set(ids)
    jobs = []
    for t in tasks():
        if (
            (t.task_id in want_ids)
            if want_ids
            else (t.fmt in want_f and t.kind in want_k and t.band in want_b)
        ):
            jobs += [(t, c) for c in conditions_for(t) if conditions is None or c in conditions]
    return jobs


def merged(runs: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The rows of several runs as one, for one report.

    Raises:
        ValueError: two runs hold the same task, condition and repetition (pass --first-rep so
            repetitions added later are numbered after the earlier ones), or used different models.
    """
    seen: dict[tuple[str, str, int], str] = {}
    models = {r["model"] for rows in runs.values() for r in rows}
    if len(models) > 1:
        raise ValueError(f"the runs used different models ({', '.join(sorted(models))}); report them apart")
    settings = {
        (r.get("view", "sample"), r.get("config", "defaults")) for rows in runs.values() for r in rows
    }
    if len(settings) > 1:
        said = "; ".join(f"view {v}, knobs {c}" for v, c in sorted(settings))
        raise ValueError(f"the runs folded with different settings ({said}); report them apart")
    out = []
    for name, rows in runs.items():
        for r in rows:
            key = (r["task_id"], r["condition"], r["rep"])
            if key in seen:
                raise ValueError(
                    f"{name} and {seen[key]} both hold {key[0]} {key[1]} rep {key[2]}: "
                    "run later repetitions with --first-rep"
                )
            seen[key] = name
            out.append(r)
    return out


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
_MAX_DIFF = 50_000


def patched(original: str, diff: str) -> str | None:
    """`original` with a unified diff (difflib's, as an edit row stores it) applied, or None when the
    diff does not apply: what lets an edit be checked again after the session's folder is gone."""
    old, out, at = original.splitlines(True), [], 0
    lines = diff.splitlines(True)
    i = 0
    while i < len(lines):
        m = _HUNK.match(lines[i])
        i += 1
        if m is None:
            continue
        start = int(m[1]) - (0 if m[2] == "0" else 1)
        out += old[at:start]
        at = start
        while i < len(lines) and not lines[i].startswith("@@"):
            kind, text = lines[i][:1], lines[i][1:]
            if kind in " -":
                if at >= len(old) or old[at] != text:
                    return None
                at += 1
                if kind == " ":
                    out.append(text)
            elif kind == "+":
                out.append(text)
            i += 1
    return "".join(out + old[at:])


def rescored(row: dict[str, Any], truth: Truth, original: str | None = None) -> dict[str, Any]:
    """The row scored again with the current scorer, from its saved ANSWER line (or, when it had
    none, its saved prose), so a scorer fix reaches runs already made at no cost. An edit is checked
    again on its file rebuilt from the saved diff; when the diff was too long to keep, its score stays."""
    if row["error"]:
        return row
    if isinstance(truth, Edited):  # `original`: the file the edit was made to
        if original is None or row.get("edit_diff_cut"):
            return row
        edited = patched(original, row.get("edit_diff", ""))
        if edited is None:
            return row
        score, problem = score_edit(truth, original, edited)
        return row | {"correct": score.correct, "edit_problem": problem}
    text = f"ANSWER: {row['answer_line']}" if row["answer_line"] is not None else row["answer"]
    score = score_answer(truth, text)
    return row | {
        "correct": score.correct,
        "recall": score.recall,
        "precision": score.precision,
        "parsed": score.parsed,
    }


def _merge(names: list[str], name: str) -> int:
    results = _LAB / "results"
    runs = {
        n: [json.loads(line) for line in (results / f"{n}.jsonl").read_text(encoding="utf-8").splitlines()]
        for n in names
    }
    try:
        rows = merged(runs)
    except ValueError as e:
        print(f"l2 --merge: {e}", file=sys.stderr)
        return 1
    by_id = {t.task_id: t for t in tasks()}
    rows = [
        rescored(r, (t := by_id[r["task_id"]]).truth, t.payload() if isinstance(t.truth, Edited) else None)
        for r in rows
    ]
    text = report(rows, rows[0]["model"] if rows else "?")
    (results / f"{name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--formats", nargs="+", choices=FORMATS, default=list(FORMATS))
    parser.add_argument("--kinds", nargs="+", choices=KINDS, default=list(KINDS))
    parser.add_argument("--bands", nargs="+", choices=("S", "M", "L"), default=["M", "L"])
    parser.add_argument(
        "--conditions", nargs="+", choices=sorted({*MCP_CONDITIONS, *BASH_CONDITIONS, *FILE_CONDITIONS})
    )
    parser.add_argument("--ids", nargs="+", default=(), help="exact task ids (overrides the other filters)")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument(
        "--first-rep", type=int, default=0, help="number the repetitions from here, to add to an earlier run"
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--view", choices=VIEWS, default="sample", help="how the fold shows data (JSON)")
    parser.add_argument("--config", type=Path, help="a TOML file of knobs (compressors/config.py)")
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument(
        "--max-cost",
        type=float,
        help="USD: once the runs so far cost this much, start no more (those running finish)",
    )
    parser.add_argument("--name", default="l2-1")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the runs and an estimated cost; run nothing"
    )
    parser.add_argument(
        "--merge",
        nargs="+",
        metavar="NAME",
        help="report results/NAME.jsonl together as --name, rescored with the current scorer; run nothing",
    )
    ns = parser.parse_args(argv)
    if ns.merge:
        return _merge(ns.merge, ns.name)
    if unknown := set(ns.ids) - {t.task_id for t in tasks()}:
        parser.error(
            f"no eval task {', '.join(sorted(unknown))}: ids look like json-M-spot-at50 or "
            "python-L-locate-communicate, and every one is in the task_id field of results/l1-*.jsonl"
        )
    jobs = [
        (t, c, rep)
        for rep in range(ns.first_rep, ns.first_rep + ns.reps)
        for t, c in select(ns.formats, ns.kinds, ns.bands, ns.conditions, ns.ids)
    ]
    per_run = next((v for k, v in _COST_PER_RUN.items() if k in ns.model), _COST_PER_RUN["sonnet"])
    if ns.dry_run:
        counts: dict[str, int] = defaultdict(int)
        for t, c, _ in jobs:
            counts[f"{t.fmt}/{c}"] += 1
        for key, n in sorted(counts.items()):
            print(f"{key:24} {n:4} runs")
        print(f"{len(jobs)} runs, about ${len(jobs) * per_run:.2f} on {ns.model} (a rough estimate)")
        for source, why in skipped().items():
            print(f"left out on this host: {source} ({why})")
        return 0
    results = _LAB / "results"
    log = results / f"{ns.name}-hook.jsonl"
    rows: list[dict[str, Any]] = []
    with (
        ThreadPoolExecutor(ns.workers) as pool,
        (results / f"{ns.name}.jsonl").open("w", encoding="utf-8") as f,
    ):
        config = with_sets(load(ns.config) if ns.config else DEFAULT, ns.sets)
        pending = [pool.submit(run_one, t, c, ns.model, rep, log, ns.view, config) for t, c, rep in jobs]
        failed_in_a_row, spent, capped = 0, 0.0, False
        for future in as_completed(pending):
            row = future.result()
            f.write(json.dumps(row) + "\n")
            f.flush()
            rows.append(row)
            mark = "FAILED" if row["error"] else "ok" if row["correct"] else "MISS"
            print(
                f"{len(rows)}/{len(jobs)} {row['task_id']} {row['condition']}: {mark} ${row['cost_usd']:.4f}",
                flush=True,
            )
            failed_in_a_row = failed_in_a_row + 1 if row["error"] else 0
            spent += row["cost_usd"]
            if ns.max_cost is not None and spent >= ns.max_cost and not capped:
                capped = True
                print(f"stopping: ${spent:.2f} spent, the --max-cost of ${ns.max_cost:.2f}", flush=True)
                for p in pending:
                    p.cancel()
            if failed_in_a_row == _STOP_AFTER_FAILURES:  # a usage limit or an outage: stop spending
                print(f"stopping: {failed_in_a_row} runs in a row failed; last: {row['error']}", flush=True)
                for p in pending:
                    p.cancel()
    text = report(rows, ns.model)
    (results / f"{ns.name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
