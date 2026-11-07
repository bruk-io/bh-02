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
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from claude_code.hook import digest
from compressors.common import read_text
from compressors.config import DEFAULT, FoldConfig, label, load, sets, with_sets
from compressors.envelope_json import VIEWS
from evals import atlas
from evals.stats import bootstrap, paired, paired_accuracy, wilson
from evals.tasks import BANDS, FORMATS, KINDS, TOOLS, Task, bash_prompt, size_order, skipped, task, tasks
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


@dataclass(frozen=True)
class Dials:
    """How a fold condition folds: the hook's mode (None: the condition's own, `HOOK_MODE`), the
    budget, the view and the knobs. Native conditions ignore them."""

    mode: str | None = None
    budget: int = 2000
    view: str = "sample"
    config: FoldConfig = DEFAULT

    def mode_for(self, condition: str) -> str | None:
        """The hook's mode for a condition: a native one has none; a fold condition its own, or
        this record's when it names one (a dial setting is a fold condition of its own)."""
        if condition in _NATIVE:
            return None
        return self.mode or HOOK_MODE.get(condition)


_DIALS = Dials()
_NATIVE = frozenset({"native", "bash-native", "noshell"})  # conditions with no hook


_STOP_AFTER_FAILURES = 5
_COST_PER_RUN = {"haiku": 0.007, "sonnet": 0.10, "opus": 0.25}  # rough, from the A/Bs so far
_CLAUDE_MD = """# Tools

`lab-fold FILE` prints a file's envelope within a token budget (`--budget N`, default 2000; 6000 or
more suits a large file): its outline at its real line numbers (every class, function and method
header), what breaks it, samples, and how to read the rest. Read any lines it names with Read
offset=A limit=B-A+1. Use it to see the structure of a large file before reading parts of it.
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
    first_cache_read: int  # the first request's cache reads: a prefix another session had warmed
    first_cache_write: int  # the first request's cache writes
    cache_write_1h: (
        int  # cache writes with the one-hour lifetime (2x the input price; five-minute ones 1.25x)
    )
    error: str | None  # the run failed to produce an answer (no result, an API or usage error): not scored
    session_id: str = ""  # Claude Code's id for the session, which the hook logs with each fold


def parse_stream(lines: Iterable[str]) -> Session:
    """Read a `--output-format stream-json --verbose` session."""
    calls, read_saved, ran_fold, session_id = 0, False, False, ""
    usage: dict[str, dict[str, int]] = {}  # per API request (assistant message id), last seen
    result: dict[str, Any] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        session_id = session_id or str(event.get("session_id") or "")
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

    found = result.get("usage")
    totals: dict[str, Any] = found if isinstance(found, dict) else {}

    def total(key: str) -> int:
        """The session's total: the result event's (a message's own usage is a streaming snapshot,
        whose output count is what had streamed when it was sent), else the messages' sum."""
        if key in totals:
            return int(totals[key] or 0)
        return sum(int(u.get(key, 0) or 0) for u in usage.values())

    models = (result.get("modelUsage") or {}).values()
    hour = sum(int(m.get("cacheCreationEphemeral1hInputTokens", 0) or 0) for m in models)

    last = list(usage.values())[-1] if usage else {}
    first = next(iter(usage.values()), {})
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
        first_cache_read=int(first.get("cache_read_input_tokens", 0) or 0),
        first_cache_write=int(first.get("cache_creation_input_tokens", 0) or 0),
        cache_write_1h=hour,
        error=_run_error(result),
        session_id=session_id,
    )


def acted(entries: Iterable[dict[str, Any]], payload: str) -> dict[str, Any]:
    """What the hook did in one session (its log entries for that session): how many results it
    folded, and whether it saw the task's large output and folded it, matched by digest (a shell's
    output may lose the trailing newline)."""
    want = {digest(payload), digest(payload.rstrip("\n"))}
    mine = list(entries)
    large = [e for e in mine if e.get("digest") in want]
    return {
        "folds": sum(e.get("branch", "passthrough") != "passthrough" for e in mine),
        "large_seen": bool(large),
        "large_folded": any(e.get("branch", "passthrough") != "passthrough" for e in large),
    }


def hook_entries(log: Path, session_id: str) -> list[dict[str, Any]]:
    """The hook's log entries for one session (none when it has no id or the log is missing)."""
    if not session_id or not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("session_id") == session_id:
            out.append(entry)
    return out


def _run_error(result: dict[str, Any]) -> str | None:
    """Why a session produced no answer to score, or None. Running out of turns is not one: it is
    an outcome of the condition (recovering spent the turns), so it is scored as a wrong answer."""
    if not result:
        return "no result event"
    if result.get("is_error") and result.get("subtype") != "error_max_turns":
        return f"{result.get('subtype', 'error')}: {str(result.get('result', ''))[:200]}"
    return None


def conditions_for(t: Task) -> tuple[str, ...]:
    if t.fmt == "atlas":  # replayed MCP tools: there is no command that prints them
        return MCP_CONDITIONS
    return FILE_CONDITIONS if t.path else MCP_CONDITIONS + BASH_CONDITIONS


def hook_settings(
    mode: str,
    log: Path,
    matcher: str = "mcp__.*",
    view: str = "sample",
    config: FoldConfig = DEFAULT,
    budget: int = 2000,
) -> dict[str, Any]:
    knobs = shlex.quote(";".join(sets(config)))
    env = f"TOOL_OUTPUT_LAB_LOG={log} TOOL_OUTPUT_LAB_MODE={mode} TOOL_OUTPUT_LAB_VIEW={view}"
    env += f" TOOL_OUTPUT_LAB_SET={knobs} TOOL_OUTPUT_LAB_BUDGET={budget}"
    command = f"cd {_LAB} && {env} {_UV} -m claude_code.hook"
    hook = {"type": "command", "timeout": 30, "command": command}
    return {"hooks": {"PostToolUse": [{"matcher": matcher, "hooks": [hook]}]}}


def bash_channel(t: Task, condition: str, w: Path, log: Path, dials: Dials = _DIALS) -> list[str]:
    """The flags (and files in the run's folder) for a synthetic task on the bash channel: `./<tool>`
    prints the payload (the task id reaches it through the environment, not the script), and the
    hook, when the condition has one, folds Bash."""
    script = w / TOOLS[t.fmt]
    script.write_text(f'#!/bin/sh\ncd "{_LAB}" && exec {_UV} -m claude_code.fixture_cmd\n')
    script.chmod(0o755)
    mode = dials.mode_for(condition)
    (w / "settings.json").write_text(
        json.dumps(hook_settings(mode, log, "Bash", dials.view, dials.config, dials.budget) if mode else {})
    )
    return ["--strict-mcp-config", "--settings", "settings.json", "--allowedTools", "Bash,Read,Grep"]


def mcp_channel(t: Task, condition: str, w: Path, log: Path, dials: Dials = _DIALS) -> list[str]:
    """The flags (and files in the run's folder) for a synthetic task on the MCP channel: the fixture
    server's tool returns the task's payload, and the hook, when the condition has one, folds it."""
    replay = t.fmt == "atlas"  # an MCP-Atlas task: its recorded tools, replayed, under a short server name
    module = "claude_code.replay_mcp" if replay else "claude_code.fixture_mcp"
    server = {
        "command": "sh",
        "args": ["-c", f"cd {_LAB} && exec {_UV} -m {module}"],
        "env": {"TOOL_OUTPUT_LAB_TASK": t.task_id},
    }
    (w / "mcp.json").write_text(json.dumps({"mcpServers": {"r" if replay else "fixture": server}}))
    mode = dials.mode_for(condition)
    settings = (
        hook_settings(mode, log, view=dials.view, config=dials.config, budget=dials.budget) if mode else {}
    )
    (w / "settings.json").write_text(json.dumps(settings))
    flags = ["--mcp-config", "mcp.json", "--strict-mcp-config", "--settings", "settings.json"]
    if replay:
        offered = ",".join(f"mcp__r__{tool['name']}" for tool in atlas.tools(atlas.record_for(t.task_id)))
        return [*flags, "--allowedTools", f"{offered},Bash,Read,Grep"]
    return [*flags, "--allowedTools", f"mcp__fixture__{TOOLS[t.fmt]},Bash,Read,Grep"]


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
    t: Task, condition: str, model: str, rep: int, log: Path, dials: Dials = _DIALS
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
            command += bash_channel(t, condition, w, log, dials)
            env["TOOL_OUTPUT_LAB_TASK"] = t.task_id
        elif t.path:
            command += file_tools(condition, w, edit, dials.view, dials.config)
            copy, original = w / Path(t.path).name, Path(t.path)
            if edit:
                copy.write_text(t.payload(), encoding="utf-8")
                guarded = original.read_bytes()
        else:
            command += mcp_channel(t, condition, w, log, dials)
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
                first_cache_read=0,
                first_cache_write=0,
                cache_write_1h=0,
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
    hook = acted(hook_entries(log, session.session_id), t.payload())
    return {
        **head,
        "rep": rep,
        "model": model,
        "view": dials.view,
        "config": label(dials.config),
        "budget": dials.budget,
        "mode": dials.mode_for(condition),
        "correct": score.correct,
        "parsed": score.parsed,
        "recall": score.recall,
        "precision": score.precision,
        "answer_line": answer_line(session.answer),
        **{k: v for k, v in asdict(session).items() if k != "answer"},
        **hook,
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


_TOKEN_CLASSES = ("input_tokens", "cache_write", "cache_read", "output_tokens")
_WARM = 10_000  # a first request that reads this much from the cache started on a prefix already warm


def implied_input_price(row: dict[str, Any]) -> float | None:
    """The USD per input token a run's cost implies under Anthropic's price structure: uncached
    input at the base price, cache writes at 2x (one-hour lifetime) or 1.25x (five-minute), cache
    reads at 0.1x and output at 5x. The same value across runs says the structure holds, and prices
    a cache read without a price list that may be out of date. Rows recorded before the result
    event's totals were read undercount output, by under 2% of the cost."""
    hour = row.get("cache_write_1h", row["cache_write"])  # Claude Code writes with the one-hour lifetime
    weighted = (
        row["input_tokens"]
        + 2.0 * hour
        + 1.25 * (row["cache_write"] - hour)
        + 0.1 * row["cache_read"]
        + 5.0 * row["output_tokens"]
    )
    return row["cost_usd"] / weighted if weighted > 0 and row["cost_usd"] > 0 else None


def _mean_change(base: dict[str, dict[str, Any]], runs: dict[str, dict[str, Any]], field: str) -> str:
    diffs = _diffs(base, runs, field)
    mid, lo, hi = bootstrap(diffs, statistics.mean)
    return (
        f"{mid:+,.1f} [{lo:+,.1f}, {hi:+,.1f}]" if abs(mid) < 100 else f"{mid:+,.0f} [{lo:+,.0f}, {hi:+,.0f}]"
    )


def _warm(runs: dict[str, dict[str, Any]]) -> str:
    known = [r for r in runs.values() if "first_cache_read" in r]
    return f"{sum(r['first_cache_read'] >= _WARM for r in known)}/{len(known)}" if known else "-"


def _cache_section(
    by_band: dict[tuple[str, str], dict[str, dict[str, Any]]], rows: list[dict[str, Any]]
) -> list[str]:
    out = ["", "## Cache and requests, every format together, per size band", ""]
    implied = sorted(p for r in rows if "cache_read" in r and (p := implied_input_price(r)) is not None)
    read = None
    if implied:
        mid, lo, hi = (
            statistics.median(implied),
            implied[len(implied) // 10],
            implied[-1 - len(implied) // 10],
        )
        if (hi - lo) / mid <= 0.1:  # the structure holds when eight runs in ten imply the same price
            read = 0.1 * mid
        verdict = (
            f"so a cache read costs ${read * 1e6:.3f} per million" if read else "too spread to price a read"
        )
        out += [
            f"Input price these runs' costs imply: ${mid * 1e6:.3f} per million tokens (80% of runs between "
            f"${lo * 1e6:.3f} and ${hi * 1e6:.3f}); {verdict}.",
            "",
        ]
    out += [
        "| band | condition | pairs | requests | cache writes | cache reads | uncached input "
        "| warm starts (here, baseline) | each later request |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (band, cond), runs in sorted(by_band.items(), key=lambda kv: (size_order(kv[0][0]), kv[0][1])):
        base_cond = BASELINE.get(cond, "native")
        if cond == base_cond or (band, base_cond) not in by_band:
            continue
        base = by_band[(band, base_cond)]
        pairs = len(base.keys() & runs.keys())
        context = statistics.median(_diffs(base, runs, "final_context")) if pairs else 0.0
        later = f"{context:+,.0f} tokens" + (f", ${context * read:+.5f}" if read is not None else "")
        out.append(
            f"| {band} | {_against(cond)} | {pairs} | {_mean_change(base, runs, 'requests')} "
            f"| {_mean_change(base, runs, 'cache_write')} | {_mean_change(base, runs, 'cache_read')} "
            f"| {_mean_change(base, runs, 'input_tokens')} | {_warm(runs)}, {_warm(base)} | {later} |"
        )
    out += [
        "",
        "A folded result is written to the cache once and re-read by every later request, so a context N "
        "tokens smaller saves N cache-read tokens on each request after it: the last column, by the median "
        "change in the final context, priced at the implied cache-read price when the runs agree on it. "
        "Requests, writes, reads and uncached input are mean changes per run against the "
        "baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens "
        "or more from the cache: a prefix another session had written, which lowers that run's cost.",
    ]
    return out


def _acted_section(by_band: dict[tuple[str, str], dict[str, dict[str, Any]]], columns: str) -> list[str]:
    """How often each fold condition's hook folded the task's large output, and the pairs whose
    folded session it did: a session that never received it (a replay serving a smaller output) or
    never called its tool ran as native did, and dilutes the comparison."""
    out = [
        "",
        "## When the envelope acted: the pairs whose folded session folded the task's large output",
        "",
    ]
    out += [f"| band | condition | acted {columns}", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (band, cond), runs in sorted(by_band.items(), key=lambda kv: (size_order(kv[0][0]), kv[0][1])):
        base = BASELINE.get(cond, "native")
        if cond in _NATIVE or cond == base or (band, base) not in by_band:
            continue
        hit = {k: v for k, v in runs.items() if v.get("large_folded")}
        seen = sum(bool(v.get("large_seen")) for v in runs.values())
        share = f"{len(hit)}/{len(runs)} (saw it {seen})"
        if hit and hit.keys() & by_band[(band, base)].keys():
            out.append(f"| {band} | {_against(cond)} | {share} {_paired(by_band[(band, base)], hit)}")
        else:
            out.append(f"| {band} | {_against(cond)} | {share} |" + " |" * 8)
    return out


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
    for (fmt, kind, band, cond), rs in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][1], size_order(kv[0][2]), kv[0][3])
    ):
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
    for (fmt, band, cond), runs in sorted(
        by_cell.items(), key=lambda kv: (kv[0][0], size_order(kv[0][1]), kv[0][2])
    ):
        base = BASELINE.get(cond, "native")
        if cond != base and (fmt, band, base) in by_cell:
            out.append(f"| {fmt} | {band} | {_against(cond)} {_paired(by_cell[(fmt, band, base)], runs)}")
    out += ["", "## Every format together, per size band", ""]
    out += [f"| band | condition {columns}", "|---|---|---|---|---|---|---|---|---|---|"]
    by_band: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in scored:
        by_band[(r["band"], r["condition"])][f"{r['task_id']}#{r['rep']}"] = r
    for (band, cond), runs in sorted(by_band.items(), key=lambda kv: (size_order(kv[0][0]), kv[0][1])):
        base = BASELINE.get(cond, "native")
        if cond != base and (band, base) in by_band:  # pairs: the tasks both conditions ran
            out.append(f"| {band} | {_against(cond)} {_paired(by_band[(band, base)], runs)}")
    out += _acted_section(by_band, columns)
    out += [
        "",
        "Verdict: passes when the accuracy change's lower bound is above -3 points and the final context "
        "shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the "
        "context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired "
        "proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of "
        "the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed "
        "input, every input token the requests carried (cached or not), is reported beside it.",
    ]
    out += _cache_section(by_band, scored)
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
    for t in [task(i) for i in sorted(want_ids)] if want_ids else tasks(want_b):
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
    settings: dict[str, set[tuple[str, str, int]]] = {}
    for rows in runs.values():
        for r in rows:
            fold = (r.get("view", "sample"), r.get("config", "defaults"), r.get("budget", 2000))
            settings.setdefault(r["condition"], set()).add(fold)
    if mixed := {c: f for c, f in settings.items() if len(f) > 1}:
        cond, folds = next(iter(mixed.items()))
        said = "; ".join(f"view {v}, knobs {k}, budget {b}" for v, k, b in sorted(folds))
        raise ValueError(
            f"condition {cond} folded with different settings in these runs ({said}); report them apart"
        )
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
    by_id = {t.task_id: t for t in tasks({r["band"] for r in rows})}
    rows = [
        rescored(r, (t := by_id[r["task_id"]]).truth, t.payload() if isinstance(t.truth, Edited) else None)
        for r in rows
    ]
    text = report(rows, rows[0]["model"] if rows else "?")
    (results / f"{name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


type Run = Callable[[Path], list[dict[str, Any]]]  # one session, given the hook's log: its rows


def run_jobs(
    jobs: list[tuple[Task, str, int, Dials]], model: str, name: str, workers: int, max_cost: float | None
) -> list[dict[str, Any]]:
    """Run the sessions in parallel (see `run_all`), one row each."""
    runs: list[Run] = [partial(_one_row, t, c, model, rep, d) for t, c, rep, d in jobs]
    return run_all(runs, len(jobs), name, workers, max_cost)


def _one_row(t: Task, condition: str, model: str, rep: int, dials: Dials, log: Path) -> list[dict[str, Any]]:
    return [run_one(t, condition, model, rep, log, dials)]


def run_all(
    runs: list[Run], expected: int, name: str, workers: int, max_cost: float | None
) -> list[dict[str, Any]]:
    """Run the sessions in parallel, writing each row to results/NAME.jsonl as it comes (`expected`
    rows in all), and stop starting new ones after five failures in a row (a usage limit or an
    outage) or once `max_cost` is spent."""
    results = _LAB / "results"
    log = results / f"{name}-hook.jsonl"
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(workers) as pool, (results / f"{name}.jsonl").open("w", encoding="utf-8") as f:
        pending = [pool.submit(run, log) for run in runs]
        failed_in_a_row, spent, capped = 0, 0.0, False
        for future in as_completed(pending):
            for row in future.result():
                f.write(json.dumps(row) + "\n")
                f.flush()
                rows.append(row)
                mark = "FAILED" if row["error"] else "ok" if row["correct"] else "MISS"
                done = f"{len(rows)}/{expected} {row['task_id']} {row['condition']}"
                print(
                    f"{done}: {mark} ${row['cost_usd']:.4f}",
                    flush=True,
                )
                spent += row["cost_usd"]
            failed_in_a_row = failed_in_a_row + 1 if any(r["error"] for r in future.result()) else 0
            stop = None
            if max_cost is not None and spent >= max_cost and not capped:
                capped, stop = True, f"${spent:.2f} spent, the --max-cost of ${max_cost:.2f}"
            if failed_in_a_row == _STOP_AFTER_FAILURES:
                stop = f"{failed_in_a_row} sessions in a row failed; last: {rows[-1]['error']}"
            if stop:
                print(f"stopping: {stop}", flush=True)
                for p in pending:
                    p.cancel()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--formats", nargs="+", choices=FORMATS, default=list(FORMATS))
    parser.add_argument("--kinds", nargs="+", choices=KINDS, default=list(KINDS))
    parser.add_argument("--bands", nargs="+", choices=BANDS, default=["M", "L"])
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
    parser.add_argument("--budget", type=int, default=2000, help="tokens the hook folds into")
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
    if ns.ids and (unknown := set(ns.ids) - {t.task_id for t in tasks(BANDS)}):
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
    config = with_sets(load(ns.config) if ns.config else DEFAULT, ns.sets)
    dials = Dials(budget=ns.budget, view=ns.view, config=config)
    rows = run_jobs([(t, c, rep, dials) for t, c, rep in jobs], ns.model, ns.name, ns.workers, ns.max_cost)
    text = report(rows, ns.model)
    (_LAB / "results" / f"{ns.name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
