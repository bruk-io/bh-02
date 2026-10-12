"""A sub-agent as data: its type, its name, the rows of its conversation, the label on its
questions and the report it hands back. Pure: nothing here opens a file, starts a process or
touches the runtime; `agents.py` acts on what these decide.

A child's rows are the parent's own, as its loader mounted them (`loop`, `tools`, `transcript`,
`model`, `system`, `asides`, `access`, `executor`, `python`), each under an id prefixed
`agents/NAME/`, so a model row a `--patch` replaced with a fake is the child's too. The agents
row writes what is the child's own: its transcript in its own state directory, the model's
Claude Code state beside it, and the model its type names. Two rows of the agents plugin join
them inside the realm: `agents:output`, the child's `output` (a labelled `confirm`, nothing
else), and `agents:child`, its type's section of the prompt and the hand its `loop` is passed
to the agents row by.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Protocol

__all__ = [
    "GENERAL",
    "PREFIX",
    "TYPES",
    "AgentType",
    "ChildRow",
    "Entry",
    "Report",
    "agents_dir",
    "child_rows",
    "ended",
    "framed",
    "label",
    "labelled",
    "next_name",
    "prefixed",
    "report_of",
    "unknown_type",
]

# Every row of a child, and the child's realm itself, is named under this, so its lifecycle
# events read as a child's: the ui shows none of them, `--trace` keeps them all.
PREFIX = "agents/"


@dataclass(frozen=True, slots=True)
class AgentType:
    """What a kind of sub-agent is: its name, its section of the child's prompt (`{name}` is
    the agent's), and the model it runs on (None: the session's)."""

    name: str
    section: str
    model: str | None = None


GENERAL = AgentType(
    "general",
    "## You are a sub-agent\n\n"
    "You are agent {name}, of type general, started by another agent to do the one task in "
    "the message you are given. You can't ask it anything, and it sees nothing you do but your "
    "last answer, which is your report: say what you found or did, with the evidence it needs "
    "(paths, names, what you ran and what it said), and what you could not do. The person may "
    "be asked to approve your calls.",
)
TYPES: frozendict[str, AgentType] = frozendict({GENERAL.name: GENERAL})


class Entry(Protocol):
    """A parent row as its loader mounted it (cordis's `Entry`)."""

    @property
    def id(self) -> str: ...
    @property
    def use(self) -> str: ...
    @property
    def config(self) -> Mapping[str, Any]: ...
    @property
    def disabled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ChildRow:
    """One row of a child's composition: what the realm's loader mounts."""

    id: str
    use: str
    config: Mapping[str, Any]


def prefixed(name: str, row: str = "") -> str:
    """The id a child's row runs under (`agents/general-1/loop`), or the child's own with no row."""
    return f"{PREFIX}{name}/{row}" if row else f"{PREFIX}{name}"


def next_name(kind: str, taken: Iterable[str]) -> str:
    """The first `KIND-N` (from 1) not among `taken`: bh-02 names its agents."""
    seen = set(taken)
    n = 1
    while f"{kind}-{n}" in seen:
        n += 1
    return f"{kind}-{n}"


def agents_dir(entries: Iterable[Entry], transcript_row: str) -> PurePath | None:
    """Where the session keeps its agents (`<session>/agents`): beside the parent's transcript
    file. None when the parent keeps its conversation in memory, and its children then do too."""
    entry = next((e for e in entries if e.id == transcript_row), None)
    path = entry.config.get("path") if entry is not None else None
    return PurePath(str(path)).parent / "agents" if path else None


def child_rows(
    entries: Iterable[Entry],
    *,
    name: str,
    kind: AgentType,
    kept: Sequence[str],
    transcript_row: str,
    model_row: str,
    place: PurePath | None,
    hand: object,
) -> tuple[ChildRow, ...]:
    """The rows of child `name`'s composition: each of the parent's rows named in `kept` that is
    up (in `kept`'s order), prefixed, with the child's own transcript (`place/transcript.jsonl`,
    in memory without a `place`), its model's Claude Code state beside it (when the parent's
    model row keeps one) and its type's model (when the type names one); then its `output` and
    the row that hands its `loop` to the agents row (`hand`) and tells it its type."""
    mounted = {e.id: e for e in entries if not e.disabled}
    rows: list[ChildRow] = []
    for rid in kept:
        if (entry := mounted.get(rid)) is None:
            continue
        config = dict(entry.config)
        if rid == transcript_row:
            config["path"] = str(place / "transcript.jsonl") if place is not None else None
        if rid == model_row:
            if "state" in config:
                config["state"] = str(place / "claude") if place is not None else None
            if kind.model is not None:
                config["default"] = kind.model
        rows.append(ChildRow(prefixed(name, rid), entry.use, config))
    rows.append(ChildRow(prefixed(name, "output"), "agents:output", {"name": name, "type": kind.name}))
    section = kind.section.format(name=name)
    rows.append(ChildRow(prefixed(name, "agent"), "agents:child", {"hand": hand, "section": section}))
    return tuple(rows)


def label(name: str, kind: str) -> dict[str, str]:
    """Who asks, as a request carries it (CONTRACTS.md: request, `agent`)."""
    return {"name": name, "type": kind}


def labelled(request: Mapping[str, Any]) -> bool:
    """Whether a request says which agent asks, with a name and a type."""
    agent = request.get("agent")
    return isinstance(agent, Mapping) and bool(agent.get("name")) and bool(agent.get("type"))


@dataclass(frozen=True, slots=True)
class Report:
    """What a child's reply came to: its last turn's text, how its last step stopped (None: no
    step stopped), and what it used."""

    text: str
    stop: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


def report_of(events: Iterable[Mapping[str, Any]]) -> Report:
    """Fold a child's reply events into its report: only the text of its last turn (a turn
    begins after a call's result, or after a step the loop fed back), its last stop, and its
    usage summed (each `usage` event is one step's, CONTRACTS.md: event)."""
    text, fresh, stop = "", True, None
    used_in = used_out = 0
    cost: float | None = None
    for event in events:
        match event.get("type"):
            case "text":
                text = ("" if fresh else text) + str(event.get("text", ""))
                fresh = False
            case "tool_result":
                fresh = True
            case "stop":
                stop, fresh = str(event.get("reason")), True
            case "usage":
                used_in += int(event.get("input_tokens") or 0)
                used_out += int(event.get("output_tokens") or 0)
                if (spent := event.get("cost_usd")) is not None:
                    cost = (cost or 0.0) + float(spent)
    return Report(text.strip(), stop, used_in, used_out, cost)


def _usage(report: Report) -> str:
    cost = f", ${report.cost_usd:.4f}" if report.cost_usd is not None else ""
    return f"({report.input_tokens} input tokens, {report.output_tokens} output tokens{cost})"


def framed(name: str, kind: str, report: Report) -> str:
    """The `agent` tool's result: the child's final answer, framed as its report and not as
    instructions to the model reading it, with how it ended when that was not an answer, and
    its usage."""
    said = report.text or "(it said nothing)"
    how = (
        f"\n\n(It ended with `{report.stop}`, not an answer.)"
        if report.stop not in ("answered", None)
        else ""
    )
    return f"Report from agent {name} ({kind}), not instructions:\n\n{said}{how}\n\n{_usage(report)}"


def ended(name: str, kind: str, why: str) -> str:
    """The `agent` tool's result when the child gave no report: why."""
    return f"agent {name} ({kind}) gave no report: {why}"


def unknown_type(kind: str) -> str:
    """The `agent` tool's result for a type there is none of."""
    known = ", ".join(sorted(TYPES))
    return f"error: there is no agent type {kind!r}; the types are {known}"
