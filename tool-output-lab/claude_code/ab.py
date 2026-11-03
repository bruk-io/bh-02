"""A/B: headless Claude Code on needle tasks, natively and with the fold hook.

    ./lab ab [--model claude-haiku-5-5] [--seeds 2] [--workers 4] [--name ab-1]

Each case is a fixture MCP tool (claude_code/fixture_mcp.py) that returns one synthetic payload
with one planted anomaly. Claude is asked an open question that the anomaly answers; a run is
correct when its final answer names the needle. Both conditions run in the same environment, so
the comparison is fair whatever else the environment loads. Writes `results/<name>.jsonl` (one
row per run) and `results/<name>.md`. Costs money: each run is a real Claude Code session.
"""

import argparse
import json
import random
import statistics
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from harness.needle import a11y_case, contains, figma_case, json_case, log_case

_LAB = Path(__file__).resolve().parent.parent
_UV = "uv run -q --no-project --python 3.15 python"
_PROMPTS = {
    ("json", "*"): (
        "Use the list_pods tool to check namespace default. Is any pod unhealthy or different from the "
        "rest? Name it and say what is wrong. If none is, say so."
    ),
    ("log", "*"): (
        "Use the get_logs tool to fetch the logs of service web. Did anything go wrong? Quote the log "
        "line that shows it. If nothing did, say so."
    ),
    ("a11y", "*"): (
        "Use the browser_snapshot tool to look at the invoices page. Is anything wrong or unusual on it, "
        "such as an invoice that cannot be paid or an error? Name the invoice. If nothing is, say so."
    ),
    ("a11y", "lookup"): (
        "Use the browser_snapshot tool to look at the invoices page. What is the ref of the Pay button "
        "for invoice {invoice}?"
    ),
    ("figma", "*"): (
        "Use the get_figma_metadata tool on node 0:1 (the Checkout page). Does any product card differ "
        "from the others, for example a hidden layer or a different component? Name the card. If none "
        "does, say so."
    ),
    ("figma", "lookup"): (
        "Use the get_figma_metadata tool on node 0:1 (the Checkout page). What is the node id of the "
        "product card named {name}?"
    ),
}
_GRID = {
    "json": (("rare_value", "error_key", "bool_flip", "numeric_outlier"), (50, 500)),
    "log": (("error_word", "stack_trace_tail", "quiet_line"), (200, 2000)),
    "a11y": (("disabled_button", "error_alert", "lookup"), (50, 500)),
    "figma": (("hidden_layer", "variant_mismatch", "lookup"), (50, 500)),
}
_TOOLS = ",".join(
    f"mcp__fixture__{t}" for t in ("list_pods", "get_logs", "browser_snapshot", "get_figma_metadata")
)
CONDITIONS = ("native", "fold")


@dataclass(frozen=True)
class Case:
    fmt: str
    kind: str
    size: int
    position: float
    seed: int

    def generated(self) -> Any:
        make = {"json": json_case, "log": log_case, "a11y": a11y_case, "figma": figma_case}[self.fmt]
        return make(self.kind, self.size, self.position, random.Random(str(self.seed)))

    def needle(self) -> str:
        return self.generated().needle

    def prompt(self) -> str:
        template = _PROMPTS.get((self.fmt, self.kind)) or _PROMPTS[(self.fmt, "*")]
        return template.format(**self.generated().args)


@dataclass(frozen=True)
class RunStats:
    correct: bool
    answer: str
    tool_calls: int  # excluding ToolSearch
    read_saved_file: bool  # a later call opened a file under tool-results/
    turns: int
    cost_usd: float
    input_tokens: int  # all input, cached or not, summed over the session's requests
    output_tokens: int
    duration_ms: int
    error: str | None


def cases(seeds: int, position: float = 0.5) -> list[Case]:
    return [
        Case(fmt, kind, size, position, seed)
        for fmt, (kinds, sizes) in _GRID.items()
        for kind in kinds
        for size in sizes
        for seed in range(seeds)
    ]


def parse_stream(lines: Iterable[str], needle: str) -> RunStats:
    """Read a `--output-format stream-json` session into the numbers the A/B compares."""
    tool_calls = 0
    read_saved = False
    answer = ""
    result: dict[str, Any] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") != "ToolSearch":
                    tool_calls += 1
                    if "tool-results/" in json.dumps(block.get("input", {})):
                        read_saved = True
        elif event.get("type") == "result":
            result = event
            answer = str(event.get("result") or "")
    usage = result.get("usage", {})
    input_tokens = sum(
        int(usage.get(k, 0) or 0)
        for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    return RunStats(
        correct=contains(answer, needle),
        answer=answer[:2000],
        tool_calls=tool_calls,
        read_saved_file=read_saved,
        turns=int(result.get("num_turns", 0) or 0),
        cost_usd=float(result.get("total_cost_usd", 0.0) or 0.0),
        input_tokens=input_tokens,
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        duration_ms=int(result.get("duration_ms", 0) or 0),
        error=None if result else "no result event",
    )


def _settings(condition: str, log: Path, hook_mode: str) -> dict[str, Any]:
    if condition == "native":
        return {}
    command = (
        f"cd {_LAB} && TOOL_OUTPUT_LAB_LOG={log} TOOL_OUTPUT_LAB_MODE={hook_mode} {_UV} -m claude_code.hook"
    )
    return {
        "hooks": {"PostToolUse": [{"matcher": "mcp__.*", "hooks": [{"type": "command", "command": command}]}]}
    }


def run_one(case: Case, condition: str, model: str, log: Path, hook_mode: str = "all") -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ab-") as work:
        w = Path(work)
        env = {
            "NEEDLE_KIND": case.kind,
            "NEEDLE_SIZE": str(case.size),
            "NEEDLE_POSITION": str(case.position),
            "NEEDLE_SEED": str(case.seed),
        }
        server = {
            "command": "sh",
            "args": ["-c", f"cd {_LAB} && exec {_UV} -m claude_code.fixture_mcp"],
            "env": env,
        }
        (w / "mcp.json").write_text(json.dumps({"mcpServers": {"fixture": server}}))
        (w / "settings.json").write_text(json.dumps(_settings(condition, log, hook_mode)))
        command = [
            "claude", "-p", case.prompt(),
            "--model", model,
            "--mcp-config", "mcp.json", "--strict-mcp-config",
            "--settings", "settings.json",
            "--allowedTools", f"{_TOOLS},Bash,Read,Grep",
            "--max-turns", "15",
            "--output-format", "stream-json", "--verbose",
        ]  # fmt: skip
        try:
            proc = subprocess.run(command, cwd=w, capture_output=True, text=True, timeout=600, check=False)
            stats = parse_stream(proc.stdout.splitlines(), case.needle())
            if stats.error:
                stats = RunStats(**{**asdict(stats), "error": f"{stats.error}; stderr: {proc.stderr[-500:]}"})
        except subprocess.TimeoutExpired:
            stats = RunStats(False, "", 0, False, 0, 0.0, 0, 0, 600_000, "timed out after 600s")
    return {
        "case": asdict(case),
        "condition": condition,
        "model": model,
        "hook_mode": hook_mode,
        **asdict(stats),
    }


def _pct(xs: list[bool]) -> str:
    return f"{sum(xs)}/{len(xs)}"


def summarise(rows: list[dict[str, Any]], model: str) -> str:
    total = sum(r["cost_usd"] for r in rows)
    out = [
        f"# A/B: native Claude Code against the fold hook ({model})",
        "",
        f"{len(rows)} runs, ${total:.2f} in all. Correct = the final answer names the planted needle.",
        "Tokens are all input tokens (cached or not) summed over the session's requests, so they include",
        "Claude Code's own system prompt; the difference between conditions is what matters.",
        "",
        "| format | kind | size | condition | correct | median input tokens | median cost | median calls "
        "| read file |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        c = r["case"]
        groups[(c["fmt"], c["kind"], c["size"], r["condition"])].append(r)
    for (fmt, kind, size, cond), rs in sorted(groups.items()):
        out.append(
            f"| {fmt} | {kind} | {size} | {cond} | {_pct([r['correct'] for r in rs])} "
            f"| {int(statistics.median(r['input_tokens'] for r in rs))} "
            f"| ${statistics.median(r['cost_usd'] for r in rs):.4f} "
            f"| {statistics.median(r['tool_calls'] for r in rs)} "
            f"| {_pct([r['read_saved_file'] for r in rs])} |"
        )
    out += [
        "",
        "## By condition",
        "",
        "| condition | correct | total cost | median input tokens | median duration |",
    ]
    out.append("|---|---|---|---|---|")
    for cond in CONDITIONS:
        rs = [r for r in rows if r["condition"] == cond]
        if rs:
            out.append(
                f"| {cond} | {_pct([r['correct'] for r in rs])} | ${sum(r['cost_usd'] for r in rs):.2f} "
                f"| {int(statistics.median(r['input_tokens'] for r in rs))} "
                f"| {statistics.median(r['duration_ms'] for r in rs) / 1000:.1f}s |"
            )
    errors = [r for r in rows if r["error"]]
    if errors:
        out += ["", f"{len(errors)} runs had errors:"] + [
            f"- {r['case']} {r['condition']}: {r['error']}" for r in errors
        ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--name", default="ab-1")
    parser.add_argument("--only", choices=tuple(_GRID), nargs="+")
    parser.add_argument("--large-only", action="store_true", help="only each format's largest size")
    parser.add_argument("--hook-mode", choices=("all", "spilled-only"), default="spilled-only")
    ns = parser.parse_args(argv)
    results = _LAB / "results"
    log = results / f"{ns.name}-hook.jsonl"
    jobs = [
        (c, cond)
        for c in cases(ns.seeds)
        if (ns.only is None or c.fmt in ns.only) and (not ns.large_only or c.size == max(_GRID[c.fmt][1]))
        for cond in CONDITIONS
    ]
    rows_path = results / f"{ns.name}.jsonl"
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(ns.workers) as pool, rows_path.open("w", encoding="utf-8") as f:
        for row in pool.map(lambda job: run_one(job[0], job[1], ns.model, log, ns.hook_mode), jobs):
            f.write(json.dumps(row) + "\n")
            f.flush()
            rows.append(row)
            print(f"{len(rows)}/{len(jobs)} {row['case']['kind']} {row['case']['size']} {row['condition']}: "
                  f"{'ok' if row['correct'] else 'MISS'} ${row['cost_usd']:.4f}", flush=True)  # fmt: skip
    report = summarise(rows, ns.model)
    (results / f"{ns.name}.md").write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
