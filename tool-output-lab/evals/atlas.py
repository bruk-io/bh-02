"""MCP-Atlas (ScaleAI/MCP-Atlas, `./lab fetch mcp-atlas`): real multi-step MCP tasks, replayed.

Each task is a prompt someone wrote for real MCP servers (GitHub, fetch, Airtable, Wikipedia...),
the claims a right answer makes, written with it, and the trajectory recorded when it ran. A
replay server (`claude_code.replay_mcp`) offers the tools the trajectory called and answers each
call with the recorded output of the closest recorded call of that tool, so native and folded
sessions see the same data.

The answer is scored by a program, not a model: each claim becomes the facts it states (its
numbers, its quoted titles, and the names in it the prompt does not already give), and a claim
holds when the answer states them (`evals.truth.Claims`). A task is used only when that is fair:
exactly one tool output is large (over 8,000 characters, where a fold acts); no tool computes an
answer from what the model sends (a code runner or a calculator would replay the recorded result
for any code); every claim has a fact; and every fact is in the recorded outputs, so the replayed
data can answer it.
"""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from evals.truth import Fact, claim_holds, fact_holds, numbers_in, plain

ATLAS = Path(__file__).resolve().parent.parent / "corpus/real/mcp-atlas/tasks.jsonl"
LARGE = 8_000  # characters: a larger output is one the fold acts on (the budget is 2,000 tokens)
# Tools whose output is computed from what they are sent: replaying a recorded result would be wrong.
_COMPUTES = frozenset(
    {
        "calculator_calculate",
        "cli-mcp-server_run_command",
        "e2b-server_run_code",
        "mcp-code-executor_execute_code",
        "mcp-code-executor_read_code_file",
        "mcp-server-code-runner_run-code",
    }
)
_MAX_NAME = 56  # Claude Code prefixes a server's tools with mcp__r__; tool names stop at 64 characters
# Capitalised words that start sentences or are generic, not names a claim asserts.
_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "in",
        "on",
        "at",
        "of",
        "for",
        "from",
        "by",
        "with",
        "to",
        "and",
        "or",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "first",
        "second",
        "third",
        "according",
        "during",
        "after",
        "before",
        "since",
        "there",
        "their",
        "his",
        "her",
        "he",
        "she",
        "they",
        "we",
        "you",
        "your",
        "our",
        "also",
        "both",
        "each",
        "all",
        "any",
        "some",
        "no",
        "not",
        "yes",
        "however",
        "while",
        "when",
        "where",
        "which",
        "who",
        "what",
        "how",
        "than",
        "then",
        "so",
        "if",
        "but",
    ]
)
_NAME = re.compile(r"(?<![\w'])[A-Z][\w'&.-]*[\w]|(?<![\w'])[A-Z]\b")
_QUOTED = re.compile(r'"([^"]{3,})"|“([^”]{3,})”')


@dataclass(frozen=True)
class Call:
    tool: str
    args: Mapping[str, Any]
    output: str


@dataclass(frozen=True)
class Record:
    task: str
    prompt: str
    claims: tuple[str, ...]
    calls: tuple[Call, ...]


def records(text: str) -> tuple[Record, ...]:
    out = []
    for line in text.splitlines():
        if line.strip():
            r = json.loads(line)
            calls = tuple(Call(c["tool"], c["args"], c["output"]) for c in r["calls"])
            out.append(Record(r["task"], r["prompt"], tuple(r["claims"]), calls))
    return tuple(out)


def facts(claim: str, prompt: str) -> tuple[Fact, ...]:
    """What a claim states that the prompt does not: its numbers, its quoted titles, its names."""
    asked = plain(prompt)
    asked_numbers = set(numbers_in(asked))
    out: list[Fact] = []
    quoted = [a or b for a, b in _QUOTED.findall(claim)]
    out += [Fact("quote", q.strip()) for q in quoted if plain(q.strip()) not in asked]
    rest = _QUOTED.sub(" ", claim)
    for m in re.finditer(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?!\w)", rest):
        value = float(m[0].replace(",", ""))
        if value not in asked_numbers:
            out.append(Fact("number", m[0], value))
    seen: set[str] = set()
    for m in _NAME.finditer(rest):
        word = m[0].strip(".'")
        key = plain(word)
        if (
            len(word) < 2
            or key in _STOP
            or key in seen
            or re.search(rf"(?<!\w){re.escape(key)}(?!\w)", asked)
        ):
            continue
        seen.add(key)
        out.append(Fact("name", word))
    return tuple(out)


def claim_facts(r: Record) -> tuple[tuple[Fact, ...], ...]:
    return tuple(facts(c, r.prompt) for c in r.claims)


def large(r: Record) -> list[Call]:
    return [c for c in r.calls if len(c.output) > LARGE]


def usable(r: Record) -> bool:
    """Whether the task can be replayed and scored fairly (see the module's docstring)."""
    if len(large(r)) != 1 or any(c.tool in _COMPUTES for c in r.calls):
        return False
    per_claim = claim_facts(r)
    if not per_claim or not all(per_claim):
        return False
    data = plain("\n".join(c.output for c in r.calls))
    numbers = numbers_in(data)
    return all(claim_holds(fs, data, numbers) for fs in per_claim)


def in_payload(r: Record) -> tuple[Fact, ...]:
    """The answer's facts that the large output holds: what a fold of it must keep."""
    text = plain(large(r)[0].output)
    numbers = numbers_in(text)
    return tuple(f for fs in claim_facts(r) for f in fs if fact_holds(f, text, numbers))


# --- replay -----------------------------------------------------------------------------------------------


def exposed(tool: str) -> str:
    """The name a tool is offered under: itself, or when too long, its start and a digest of it."""
    if len(tool) <= _MAX_NAME:
        return tool
    return f"{tool[: _MAX_NAME - 8]}_{hashlib.sha1(tool.encode()).hexdigest()[:7]}"


def _kind(v: Any) -> str:
    match v:
        case bool():
            return "boolean"
        case int() | float():
            return "number"
        case list():
            return "array"
        case dict():
            return "object"
        case _:
            return "string"


def tools(r: Record) -> list[dict[str, Any]]:
    """The tools the trajectory called, as MCP tool definitions; each argument's type is the one its
    recorded values have (the dataset keeps the tools' names, not their schemas)."""
    out: dict[str, dict[str, Any]] = {}
    for c in r.calls:
        server, _, rest = c.tool.partition("_")
        tool = out.setdefault(
            c.tool,
            {
                "name": exposed(c.tool),
                "description": f"{rest or c.tool} (from the {server} MCP server)",
                "inputSchema": {"type": "object", "properties": {}},
            },
        )
        for k, v in c.args.items():
            tool["inputSchema"]["properties"].setdefault(k, {"type": _kind(v)})
    return list(out.values())


def _similarity(recorded: Mapping[str, Any], sent: Mapping[str, Any]) -> float:
    score = 0.0
    for k in recorded.keys() | sent.keys():
        a, b = recorded.get(k), sent.get(k)
        if a is None or b is None:
            score -= 0.5
        elif plain(json.dumps(a)) == plain(json.dumps(b)):
            score += 1.0
        else:
            wa, wb = set(re.findall(r"\w+", plain(str(a)))), set(re.findall(r"\w+", plain(str(b))))
            score += len(wa & wb) / len(wa | wb) if wa | wb else 0.0
    return score


def reply(r: Record, name: str, args: Mapping[str, Any]) -> Call | None:
    """The recorded call to answer a call of tool `name` (as offered) with: the closest by its
    arguments, the first of the closest; None for a tool the trajectory never called."""
    calls = [c for c in r.calls if exposed(c.tool) == name]
    if not calls:
        return None
    return max(calls, key=lambda c: _similarity(c.args, args))  # max keeps the first of equals


def by_task(rs: Iterable[Record]) -> dict[str, Record]:
    return {r.task: r for r in rs}


def task_id(r: Record, band: str) -> str:
    return f"atlas-{band}-{r.task}"


@cache
def _index() -> dict[str, Record]:
    return by_task(records(ATLAS.read_text(encoding="utf-8")))


def record_for(eval_task_id: str) -> Record:
    """The record behind an `atlas-<band>-<task>` eval task id. An id no MCP-Atlas task has raises
    KeyError, from the index (so does a missing corpus/real/mcp-atlas: ./lab fetch mcp-atlas)."""
    return _index()[eval_task_id.split("-", 2)[2]]
