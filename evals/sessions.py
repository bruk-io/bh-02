"""Layer 2 over sessions: one tool result, then follow-up questions about it in the same session.

    ./lab evals sessions sessions/haiku.toml [--dry-run]

    name = "haiku"
    model = "claude-haiku-5-5"
    bands = ["M", "L"]
    formats = ["json", "log", "a11y", "figma"]
    reps = 2
    max_cost = 8                  # USD; no new session starts once this is spent
    ids = ["json-M-count-k7"]     # exact conversations, for a smoke run (optional)

    [[setting]]                   # as in a dials spec (evals/dials.py)
    name = "fold"
    mode = "all"

Each conversation (`evals.tasks.conversations`) is built on a count task's payload: the count (whose
prompt names the tool), every planted item, then four items looked up across the payload, asked in
turn to one Claude Code process (stream-json in and out), as a person would ask them. Under the
spill threshold a native session holds the raw result and can answer each follow-up from it; a
folded one holds the fold, and fetches from the saved raw when the fold does not show the answer.
Every turn is scored, and its tokens, cache, cost and time recorded. Writes results/sessions-NAME.md:
each setting against native per band (session totals, then turn by turn, then by format). Costs
money: --dry-run first.
"""

import argparse
import contextlib
import json
import os
import queue
import statistics
import subprocess
import tempfile
import threading
import time
import tomllib
from collections import defaultdict
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path
from typing import IO, Any

from compressors.config import label
from evals.dials import Setting, settings
from evals.l2 import Dials, Run, mcp_channel, parse_stream, run_all
from evals.stats import bootstrap, paired, paired_accuracy
from evals.tasks import BANDS, Conversation, conversations
from evals.truth import answer_line, score_answer

_LAB = Path(__file__).resolve().parent.parent
_TURN_TIMEOUT = 600  # seconds a turn may take before the session is stopped
_COST_PER_TURN = {"haiku": 0.006, "sonnet": 0.08, "opus": 0.2}  # rough


def split_turns(lines: list[str]) -> list[list[str]]:
    """A stream-json session's lines, one list per turn: each ends at its result event. Lines after
    the last result (a turn that never finished) are left out."""
    out: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        try:
            is_result = json.loads(line).get("type") == "result"
        except ValueError, AttributeError:
            is_result = False
        if is_result:
            out.append(current)
            current = []
    return out


def turn_rows(
    conv: Conversation, head: dict[str, Any], turns: list[list[str]], error: str | None
) -> list[dict[str, Any]]:
    """Each turn of a conversation scored, with its own cost and one-hour cache writes (the session's
    result events add them up; `usage` and the duration are the turn's own). A turn the session never
    reached carries the session's error."""
    rows = []
    spent, hour = 0.0, 0
    for i, t in enumerate(conv.turns):
        if i < len(turns):
            s = parse_stream(turns[i])
            so_far, hour_so_far = max(spent, s.cost_usd), max(hour, s.cache_write_1h)
            s = replace(s, cost_usd=so_far - spent, cache_write_1h=hour_so_far - hour)
            spent, hour = so_far, hour_so_far
        else:
            s = parse_stream([])
            s = replace(s, error=error or "the session ended before this turn")
        score = score_answer(t.truth, s.answer)
        rows.append(
            {
                **head,
                "conv_id": conv.conv_id,
                "turn": i + 1,
                "task_id": t.task_id,
                "kind": t.kind,
                "correct": score.correct,
                "parsed": score.parsed,
                "recall": score.recall,
                "precision": score.precision,
                "answer_line": answer_line(s.answer),
                **{k: v for k, v in asdict(s).items() if k != "answer"},
                "answer": s.answer[-1000:],
            }
        )
    return rows


def _read(stream: IO[str], lines: queue.Queue[str | None]) -> None:
    for line in stream:
        lines.put(line)
    lines.put(None)


def run_conversation(
    conv: Conversation, condition: str, model: str, rep: int, dials: Dials, log: Path
) -> list[dict[str, Any]]:
    """One Claude Code process, asked each turn's question once the last has its result."""
    first = conv.turns[0]
    head = {"fmt": first.fmt, "band": first.band, "condition": condition, "rep": rep, "model": model}
    head |= {"view": dials.view, "config": label(dials.config), "budget": dials.budget}
    head["mode"] = dials.mode_for(condition)
    turns: list[list[str]] = []
    error: str | None = None
    with tempfile.TemporaryDirectory(prefix="sessions-") as work:
        w = Path(work)
        command = ["claude", "-p", "--model", model, "--max-turns", "25", "--verbose"]
        command += ["--input-format", "stream-json", "--output-format", "stream-json"]
        command += mcp_channel(first, condition, w, log, dials)
        stderr = (w / "stderr.txt").open("w", encoding="utf-8")  # a file: a full pipe would stall the CLI
        proc = subprocess.Popen(
            command,
            cwd=w,
            env=dict(os.environ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
        )
        assert proc.stdin is not None and proc.stdout is not None
        lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=_read, args=(proc.stdout, lines), daemon=True).start()
        for t in conv.turns:
            message = {"type": "user", "message": {"role": "user", "content": t.prompt}}
            try:
                proc.stdin.write(json.dumps(message) + "\n")
                proc.stdin.flush()
            except OSError as e:
                error = f"the session ended: {e}"
                break
            got: list[str] = []
            deadline = time.monotonic() + _TURN_TIMEOUT
            while error is None:
                try:
                    line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
                except queue.Empty:
                    error = f"turn {len(turns) + 1} timed out after {_TURN_TIMEOUT}s"
                    break
                if line is None:
                    error = f"the session ended in turn {len(turns) + 1}"
                    break
                got.append(line)
                if split_turns([line]):
                    turns += split_turns(got)
                    break
            if error:
                break
        with contextlib.suppress(OSError):  # the process may have gone already
            proc.stdin.close()
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stderr.close()
        if error:
            error += f"; {(w / 'stderr.txt').read_text(encoding='utf-8')[-300:]}"
    return turn_rows(conv, head, turns, error)


def jobs(spec: dict[str, Any], chosen: list[Setting]) -> list[tuple[Conversation, str, int, Dials]]:
    """Native and every setting that covers each conversation, conversation by conversation."""
    formats = set().union(*(s.formats for s in chosen))
    ids = set(spec.get("ids", ()))
    convs = [c for c in conversations(spec.get("bands", ["M"]), formats) if not ids or c.conv_id in ids]
    out = []
    for rep in range(int(spec.get("reps", 1))):
        for c in convs:
            out.append((c, "native", rep, Dials()))
            out += [(c, s.name, rep, s.dials) for s in chosen if c.turns[0].fmt in s.formats]
    return out


# --- the report --------------------------------------------------------------------------------------


def _sessions(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Each session's turns in order, by (conversation#rep, condition); a session with a failed turn
    is left out whole, so every total covers the same turns."""
    found: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        found[(f"{r['conv_id']}#{r['rep']}", r["condition"])].append(r)
    return {k: sorted(v, key=lambda r: r["turn"]) for k, v in found.items() if not any(r["error"] for r in v)}


def _total(turns: list[dict[str, Any]], field: str) -> float:
    if field == "all_input":
        return float(sum(r["input_tokens"] + r["cache_read"] + r["cache_write"] for r in turns))
    if field == "last_context":
        return float(turns[-1]["final_context"])
    return float(sum(r[field] for r in turns))


def _mean(values: list[float], fmt: str) -> str:
    mid, lo, hi = bootstrap(values, statistics.mean)
    return f"{mid:{fmt}} [{lo:{fmt}}, {hi:{fmt}}]"


def _against(
    sessions: dict[tuple[str, str], list[dict[str, Any]]], name: str, keep: set[str] | None = None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Native's sessions and a setting's, by conversation#rep, where both finished."""
    runs = {k: v for (k, c), v in sessions.items() if c == name and (keep is None or k in keep)}
    base = {k: v for (k, c), v in sessions.items() if c == "native" and k in runs}
    return base, {k: runs[k] for k in base}


def _change(
    base: dict[str, list[dict[str, Any]]], runs: dict[str, list[dict[str, Any]]], field: str
) -> list[float]:
    return paired(
        {k: _total(v, field) for k, v in base.items()}, {k: _total(v, field) for k, v in runs.items()}
    )


def _accuracy(base: dict[str, list[dict[str, Any]]], runs: dict[str, list[dict[str, Any]]]) -> str:
    pairs = [(b["correct"], r["correct"]) for k in base for b, r in zip(base[k], runs[k], strict=True)]
    both = sum(1 for b, r in pairs if b and r)
    gains = sum(1 for b, r in pairs if r and not b)
    losses = sum(1 for b, r in pairs if b and not r)
    change, lo, hi, p = paired_accuracy(both, gains, losses, len(pairs) - both - gains - losses)
    return f"{change:+.0%} [{lo:+.0%}, {hi:+.0%}], {gains}/{losses}, p {p:.2f}"


def _right(sessions: dict[str, list[dict[str, Any]]], turn: int | None = None) -> str:
    turns = [r for v in sessions.values() for r in v if turn is None or r["turn"] == turn]
    return f"{sum(r['correct'] for r in turns)}/{len(turns)}"


def _totals_table(sessions: dict[tuple[str, str], list[dict[str, Any]]], chosen: list[Setting]) -> list[str]:
    native = {k: v for (k, c), v in sessions.items() if c == "native"}
    out = [
        "| setting | sessions | turns right | accuracy (turn pairs) | cost | time | requests | summed input "
        "| cache writes | cache reads | context after the last turn |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    if native:
        cells = [
            "native (absolute)",
            str(len(native)),
            _right(native),
            "-",
            f"${statistics.mean(_total(v, 'cost_usd') for v in native.values()):.4f}",
            f"{statistics.mean(_total(v, 'duration_ms') for v in native.values()) / 1000:.1f}s",
            f"{statistics.mean(_total(v, 'requests') for v in native.values()):.1f}",
            f"{statistics.mean(_total(v, 'all_input') for v in native.values()):,.0f}",
            f"{statistics.mean(_total(v, 'cache_write') for v in native.values()):,.0f}",
            f"{statistics.mean(_total(v, 'cache_read') for v in native.values()):,.0f}",
            f"{statistics.median(_total(v, 'last_context') for v in native.values()):,.0f}",
        ]
        out.append("| " + " | ".join(cells) + " |")
    for s in chosen:
        base, runs = _against(sessions, s.name)
        if not runs:
            continue
        cost = statistics.mean(_change(base, runs, "cost_usd"))
        cost_base = statistics.mean(_total(v, "cost_usd") for v in base.values())
        cells = [
            s.name,
            str(len(runs)),
            f"{_right(runs)} (native {_right(base)})",
            _accuracy(base, runs),
            f"{cost / cost_base:+.0%} (${cost:+.4f})",
            _mean([x / 1000 for x in _change(base, runs, "duration_ms")], "+.1f") + "s",
            _mean(_change(base, runs, "requests"), "+.1f"),
            _mean(_change(base, runs, "all_input"), "+,.0f"),
            _mean(_change(base, runs, "cache_write"), "+,.0f"),
            _mean(_change(base, runs, "cache_read"), "+,.0f"),
            f"{statistics.median(_change(base, runs, 'last_context')):+,.0f}",
        ]
        out.append("| " + " | ".join(cells) + " |")
    return out


def _turns_table(sessions: dict[tuple[str, str], list[dict[str, Any]]], chosen: list[Setting]) -> list[str]:
    native = {k: v for (k, c), v in sessions.items() if c == "native"}
    if not native:
        return []
    kinds = [r["kind"] for r in next(iter(native.values()))]
    out = [
        "| setting | " + " | ".join(f"turn {i} ({k})" for i, k in enumerate(kinds, 1)) + " |",
        "|---|" + "---|" * len(kinds),
    ]
    contexts = [
        f"{statistics.median(v[i]['final_context'] for v in native.values()):,.0f}, {_right(native, i + 1)}"
        for i in range(len(kinds))
    ]
    out.append("| native: context, right | " + " | ".join(contexts) + " |")
    for s in chosen:
        base, runs = _against(sessions, s.name)
        if not runs:
            continue
        cells = []
        for i in range(len(kinds)):
            context = statistics.median(
                runs[k][i]["final_context"] - base[k][i]["final_context"] for k in runs
            )
            cost = sum(v[i]["cost_usd"] for v in runs.values()) / sum(v[i]["cost_usd"] for v in base.values())
            cells.append(f"{context:+,.0f}, {cost - 1:+.0%}, {_right(runs, i + 1)}")
        out.append(f"| {s.name}: context, cost, right | " + " | ".join(cells) + " |")
    return out


def _formats_table(sessions: dict[tuple[str, str], list[dict[str, Any]]], chosen: list[Setting]) -> list[str]:
    out = [
        "| format | setting | sessions | turns right (native) | cost | time | requests "
        "| context after the last "
        "turn (native, change) | read the raw (native) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    fmts = sorted({v[0]["fmt"] for v in sessions.values()})
    for fmt in fmts:
        keep = {k for (k, _), v in sessions.items() if v[0]["fmt"] == fmt}
        for s in chosen:
            base, runs = _against(sessions, s.name, keep)
            if not runs:
                continue
            cost = statistics.mean(_change(base, runs, "cost_usd"))
            cost_base = statistics.mean(_total(v, "cost_usd") for v in base.values())
            native_ctx = statistics.median(_total(v, "last_context") for v in base.values())
            read = sum(any(r["read_saved_file"] for r in v) for v in runs.values())
            read_base = sum(any(r["read_saved_file"] for r in v) for v in base.values())
            cells = [
                fmt,
                s.name,
                str(len(runs)),
                f"{_right(runs)} ({_right(base)})",
                f"{cost / cost_base:+.0%}",
                f"{statistics.mean(_change(base, runs, 'duration_ms')) / 1000:+.1f}s",
                f"{statistics.mean(_change(base, runs, 'requests')):+.1f}",
                f"{native_ctx:,.0f}, {statistics.median(_change(base, runs, 'last_context')):+,.0f}",
                f"{read}/{len(runs)} ({read_base}/{len(base)})",
            ]
            out.append("| " + " | ".join(cells) + " |")
    return out


def report(rows: list[dict[str, Any]], chosen: list[Setting], name: str, model: str) -> str:
    sessions = _sessions(rows)
    failed = {(f"{r['conv_id']}#{r['rep']}", r["condition"]) for r in rows if r["error"]}
    lines = [
        f"# Sessions {name}: {model}, follow-up questions on one tool result",
        "",
        f"{len(sessions) + len(failed)} sessions, ${sum(r['cost_usd'] for r in rows):.2f}; "
        f"{len(failed)} with a failed turn, left out whole. Each session asks its turns in one Claude Code "
        "process; each setting is "
        "paired against native by conversation and repetition.",
        "",
    ]
    for band in [b for b in BANDS if any(r["band"] == b for r in rows)]:
        banded = {k: v for k, v in sessions.items() if v[0]["band"] == band}
        lines += [f"## Band {band}", "", "### Session totals", "", *_totals_table(banded, chosen), ""]
        lines += ["### Turn by turn", "", *_turns_table(banded, chosen), ""]
        lines += ["### By format", "", *_formats_table(banded, chosen), ""]
    lines += [
        "Session totals: turns right, and the accuracy change over turn pairs with its 95% interval "
        "(Newcombe) "
        "and the pairs won and lost (turns of one session are not independent: read it as indicative); cost "
        "as the mean change per session against native's mean; time, requests, summed input (every input "
        "token "
        "every request carried, cached or not), cache writes and reads as mean changes per session with "
        "bootstrap intervals; the context after the last turn as the median change, which every later "
        "request "
        "in the session would carry. Turn by turn: native's median context after each turn and its turns "
        "right; each setting's median change in that context, its change in that turn's cost (summed over "
        "sessions), and its turns right.",
    ]
    if failed:
        lines += ["", "Failed:", ""]
        lines += [f"- {r['task_id']} {r['condition']}: {r['error']}" for r in rows if r["error"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="a sessions spec's TOML file (see sessions/)")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the sessions and an estimated cost; run nothing"
    )
    parser.add_argument("--workers", type=int, default=6)
    ns = parser.parse_args(argv)
    spec = tomllib.loads(ns.spec.read_text(encoding="utf-8"))
    name, model = str(spec.get("name", ns.spec.stem)), str(spec.get("model", "claude-haiku-5-5"))
    chosen = settings(spec)
    planned = jobs(spec, chosen)
    turns = sum(len(c.turns) for c, _, _, _ in planned)
    per_turn = next((v for k, v in _COST_PER_TURN.items() if k in model), _COST_PER_TURN["sonnet"])
    print(
        f"{len(planned)} sessions, {turns} turns on {model}, "
        f"about ${turns * per_turn:.2f} (a rough estimate):"
    )
    for cond in ["native", *(s.name for s in chosen)]:
        print(f"  {cond:16} {sum(1 for _, c, _, _ in planned if c == cond):4} sessions")
    if ns.dry_run:
        return 0
    runs: list[Run] = [partial(run_conversation, c, cond, model, rep, d) for c, cond, rep, d in planned]
    rows = run_all(runs, turns, f"sessions-{name}", ns.workers, spec.get("max_cost"))
    text = report(rows, chosen, name, model)
    (_LAB / "results" / f"sessions-{name}.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
