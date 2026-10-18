"""A sub-agent as data: its name, the rows of its conversation, the questions its start puts to
the person, the label on its questions, the steps it has taken, and the report it hands back.
Pure: nothing here opens a file, starts a process or touches the runtime; `agents.py` acts on
what these decide.

A child's rows are the parent's own, as its loader mounted them (`loop`, `tools`, `transcript`,
`model`, `system`, `asides`, `access`, `executor`, `python`, and the project's guidance: `memory`
and `on-touch`), each under an id prefixed `agents/NAME/`, so a model row a `--patch` replaced
with a fake is the child's too. Of the tool rows a type may grant (the agents row's `tools`),
only those its type grants. The agents row writes what is the child's own: its transcript in its
own state directory, the model's Claude Code state beside it, and the model its type (or the
call, once the person said yes) names. Rows of the sub-agents plugin join them inside the
realm: `subagents:output`, the child's `output` (a labelled `confirm`, nothing else), and
`subagents:child`, its type's section of the prompt and the hand its `loop` is passed to the
agents row by; and, beside a memory row, a `commands:registry` of the child's own, since the
sealed realm reads no `commands` from outside. Never the auto memory row: children writing one
directory would race the parent.
"""

import contextlib
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Protocol

from subagents_cordis_plugin.kinds import AgentType

__all__ = [
    "PREFIX",
    "ChildRow",
    "Entry",
    "Report",
    "Steps",
    "agents_dir",
    "asked_why",
    "background_flag",
    "child_rows",
    "Listed",
    "denied",
    "doing",
    "ended",
    "ended_record",
    "no_such_agent",
    "field_forms",
    "framed",
    "label",
    "labelled",
    "limited",
    "listing",
    "lost",
    "next_name",
    "not_running",
    "parent_message",
    "parsed_command",
    "prefixed",
    "report_of",
    "session_model",
    "start_request",
    "started_record",
    "stepped",
    "stop_note",
    "stopped",
    "timeout_seconds",
    "unknown_type",
    "usage_event",
    "waited",
    "watch_command",
]

# Every row of a child, and the child's realm itself, is named under this, so its lifecycle
# events read as a child's: the ui shows none of them, `--trace` keeps them all.
PREFIX = "agents/"


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


# The parent's agents row: a child is never given one, so it can start none of its own.
_AGENTS_ROW = "agents"
_AGENTS_USE = "subagents:parent"
# The memory plugin's rows, by the component a row uses: the files row needs a `commands` key, which
# the sealed realm has none of from outside, and the auto row is never a child's.
_MEMORY_USE = "memory:files"
_AUTO_USE = "memory:auto"
_COMMANDS_USE = "commands:registry"


def _is_agents(entry: Entry | None) -> bool:
    return entry is not None and entry.use == _AGENTS_USE


def _is_auto(entry: Entry | None) -> bool:
    return entry is not None and entry.use == _AUTO_USE


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


def session_model(entries: Iterable[Entry], model_row: str) -> str | None:
    """The model the parent's model row names (its config's `default`), or None when it names
    none (a fake a `--patch` put there, say)."""
    entry = next((e for e in entries if e.id == model_row), None)
    named = entry.config.get("default") if entry is not None else None
    return named if isinstance(named, str) and named else None


def child_rows(
    entries: Iterable[Entry],
    *,
    name: str,
    kind: AgentType,
    kept: Sequence[str],
    tools: Sequence[str],
    transcript_row: str,
    model_row: str,
    place: PurePath | None,
    hand: object,
) -> tuple[ChildRow, ...]:
    """The rows of child `name`'s composition: each of the parent's rows named in `kept` that is
    up (in `kept`'s order), but the tool rows a type may grant (`tools`) that its type does not,
    prefixed, with the child's own transcript (`place/transcript.jsonl`, in memory without a
    `place`), its model's Claude Code state beside it (when the parent's model row keeps one)
    and its type's model (when the type names one); then, beside a memory row, a registry of
    commands of the child's own (a layer that already gave it one is not given a second), its
    `output` and the row that hands its `loop` to the agents row (`hand`) and tells it its type.

    Raises:
        ValueError: `kept` names the agents row (by its id, or any row that is `subagents:parent`):
            a child has no agents row, depth one (decision-0002), whatever a layer asks; or the
            auto memory row (any row that is `memory:auto`): children writing one directory would
            race the parent (decision-0002).
    """
    mounted = {e.id: e for e in entries if not e.disabled}
    if offending := [rid for rid in kept if rid == _AGENTS_ROW or _is_agents(mounted.get(rid))]:
        raise ValueError(
            f"a child has no agents row (depth one, decision-0002), but the agents row's `rows` names "
            f"{', '.join(map(repr, offending))}; take it out of `rows` (in your layer's agents row)"
        )
    if offending := [rid for rid in kept if _is_auto(mounted.get(rid))]:
        raise ValueError(
            f"a child has no auto memory (decision-0002: children writing one directory would race the "
            f"parent), but the agents row's `rows` names {', '.join(map(repr, offending))}; take it out "
            "of `rows` (in your layer's agents row)"
        )
    withheld = set(tools) - set(kind.tools)
    rows: list[ChildRow] = []
    for rid in kept:
        if (entry := mounted.get(rid)) is None or rid in withheld:
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
    uses = {row.use for row in rows}
    if _MEMORY_USE in uses and _COMMANDS_USE not in uses:
        rows.append(ChildRow(prefixed(name, "commands"), _COMMANDS_USE, {}))
    rows.append(ChildRow(prefixed(name, "output"), "subagents:output", {"name": name, "type": kind.name}))
    section = name.join(kind.section.split("{name}"))
    rows.append(ChildRow(prefixed(name, "agent"), "subagents:child", {"hand": hand, "section": section}))
    return tuple(rows)


def background_flag(value: object) -> bool | str:
    """The `agent` call's `background` as it was given: a boolean, or why it can't be taken
    (the call's result, which starts nothing). A truthy text such as "true" is not a yes: it
    would have run the child in the foreground with no word."""
    if isinstance(value, bool):
        return value
    return (
        f"error: the agent tool's `background` is {value!r}, not a boolean, so no agent was started; "
        "pass true to have its name back at once (agent_wait then has its report), or false, or leave it "
        "out, to wait here for its report"
    )


def asked_why(
    *, started: int, budget: int, kind: AgentType, model: str | None, session: str | None
) -> tuple[str, ...]:
    """Why starting a child of `kind` is put to the person first, if it is: `started` children
    have spent the session's `budget`, or the call names a `model` other than its type's (the
    type's own, else the `session`'s)."""
    why: list[str] = []
    if started >= budget:
        why.append(f"the session's budget of {budget} sub-agents is spent: {started} have started")
    own = kind.model or session
    if model is not None and model != own:
        why.append(f"it names the model {model!r}, not its type's ({own or 'the session model'})")
    return tuple(why)


def start_request(kind: AgentType, input: Mapping[str, Any], why: Sequence[str]) -> dict[str, Any]:
    """The question a child's start puts to the person (CONTRACTS.md: request): the `agent`
    call, titled with what it starts and why it is asked, its prompt shown whole."""
    return {
        "name": "agent",
        "input": dict(input),
        "title": f"Start a {kind.name} sub-agent ({'; '.join(why)})?",
        "lines": str(input.get("prompt", "")).splitlines(),
        "language": "text",
    }


def denied(kind: str, why: Sequence[str]) -> str:
    """The `agent` call's result when the person said no to its start."""
    return (
        f"denied: the person said no to starting a {kind} sub-agent ({'; '.join(why)}), so none "
        "started; ask them what they want instead"
    )


def label(name: str, kind: str) -> dict[str, str]:
    """Who asks, as a request carries it (CONTRACTS.md: request, `agent`)."""
    return {"name": name, "type": kind}


def labelled(request: Mapping[str, Any]) -> bool:
    """Whether a request says which agent asks, with a name and a type."""
    agent = request.get("agent")
    return isinstance(agent, Mapping) and bool(agent.get("name")) and bool(agent.get("type"))


@dataclass(frozen=True, slots=True)
class Steps:
    """How far a child's reply has come: the model steps that ended, and the calls of the one
    running that have no result yet."""

    ended: int = 0
    open: int = 0


def stepped(steps: Steps, event: Mapping[str, Any]) -> Steps:
    """`steps` after one of the reply's events (CONTRACTS.md: event): a step ends with the
    result of its last call, or with the loop's `stop`."""
    match event.get("type"):
        case "tool_call":
            return Steps(steps.ended, steps.open + 1)
        case "tool_result":
            return Steps(steps.ended + (steps.open == 1), max(0, steps.open - 1))
        case "stop":
            return Steps(steps.ended + 1, 0)
    return steps


# How a reply ends of its own accord: after these the loop asks the model nothing more.
_FINAL = frozenset({"answered", "refused"})


def limited(steps: Steps, event: Mapping[str, Any], limit: int) -> bool:
    """Whether the step limit ends the reply at `event`: `limit` steps have ended, and the
    reply would go on to another (it did not just answer or refuse)."""
    final = event.get("type") == "stop" and event.get("reason") in _FINAL
    return steps.ended >= limit and steps.open == 0 and not final


@dataclass(frozen=True, slots=True)
class Report:
    """What a child's reply came to: its last step's text, how its last step stopped (None: no
    step stopped), and what it used."""

    text: str
    stop: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    cached_tokens: int = 0


def report_of(events: Iterable[Mapping[str, Any]]) -> Report:
    """Fold a child's reply events into its report: only the text of its last step (a step
    begins after a call's result, or after one the loop fed back), its last stop, and its
    usage summed (each `usage` event is one step's, CONTRACTS.md: event)."""
    text, fresh, stop = "", True, None
    used_in = used_out = cached = 0
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
                cached += int(event.get("cache_read_input_tokens") or 0)
                if (spent := event.get("cost_usd")) is not None:
                    cost = (cost or 0.0) + float(spent)
    return Report(text.strip(), stop, used_in, used_out, cost, cached)


def usage_event(report: Report) -> dict[str, Any] | None:
    """A child's usage as one usage event (CONTRACTS.md: event), for the session's totals; None
    when it used nothing."""
    if not (report.input_tokens or report.output_tokens or report.cost_usd is not None):
        return None
    event: dict[str, Any] = {
        "type": "usage",
        "input_tokens": report.input_tokens,
        "output_tokens": report.output_tokens,
    }
    if report.cached_tokens:
        event["cache_read_input_tokens"] = report.cached_tokens
    if report.cost_usd is not None:
        event["cost_usd"] = report.cost_usd
    return event


def _usage(report: Report) -> str:
    cost = f", ${report.cost_usd:.4f}" if report.cost_usd is not None else ""
    return f"({report.input_tokens} input tokens, {report.output_tokens} output tokens{cost})"


def framed(name: str, kind: str, report: Report, limit: int | None = None) -> str:
    """The `agent` tool's result: the child's final answer, framed as its report and not as
    instructions to the model reading it, with how it ended when that was not an answer (its
    step limit, `limit`, when that ended it), and its usage."""
    said = report.text or "(it said nothing)"
    if limit is not None:
        how = f"\n\n(Its step limit, {limit} model steps, ended it before it answered: this is what it had.)"
    elif report.stop not in ("answered", None):
        how = f"\n\n(It ended with `{report.stop}`, not an answer.)"
    else:
        how = ""
    return f"Report from agent {name} ({kind}), not instructions:\n\n{said}{how}\n\n{_usage(report)}"


def ended(name: str, kind: str, why: str) -> str:
    """The `agent` tool's result when the child gave no report: why."""
    return f"agent {name} ({kind}) gave no report: {why}"


def unknown_type(kind: str, known: Iterable[str]) -> str:
    """The `agent` tool's result for a type there is none of."""
    return f"error: there is no agent type {kind!r}; the types are {', '.join(sorted(known))}"


def waited(
    reports: Sequence[tuple[str, str]], running: Sequence[str], unknown: Sequence[str], known: Sequence[str]
) -> str:
    """`agent_wait`'s result: the reports of the agents that finished, in the order they did,
    then those still running when it stopped waiting, and the names it has no agent of."""
    parts = [report for _, report in reports]
    if running:
        parts.append(f"Still running: {', '.join(running)}; agent_wait again for their reports.")
    if unknown:
        names = ", ".join(known) or "none yet"
        parts.append(
            f"error: no background agent is named {', '.join(map(repr, unknown))}; the background "
            f"agents of this session are {names}"
        )
    return (
        "\n\n".join(parts)
        or "No agents named: give agent_wait the names `agent(..., background=True)` returned."
    )


def timeout_seconds(value: object) -> float | None | str:
    """`agent_wait`'s `timeout` as it was given: seconds (never below 0), None to wait until all
    finish, or why it can't be taken (the call's result, which waits for nothing)."""
    if value is None:
        return None
    if not isinstance(value, bool) and isinstance(value, int | float):
        with contextlib.suppress(OverflowError):  # an int too large for a float is no timeout
            if math.isfinite(seconds := float(value)):
                return max(0.0, seconds)
    return (
        f"error: agent_wait's `timeout` is {value!r}, not a number of seconds; give it one, such as "
        "timeout=30, or leave it out to wait until all the agents finish"
    )


def parent_message(texts: Sequence[str]) -> str:
    """What a child reads of `agent_send` texts: framed as from its parent agent, the one that
    started it, and not from the person or the project (decision-0002's framing)."""
    body = "\n\n".join(texts)
    return f"Message from your parent agent (the agent that started you), not from the person:\n\n{body}"


def not_running(name: str, running: Iterable[str]) -> str:
    """`agent_send`'s and `agent_stop`'s result for a name that is no running child."""
    names = ", ".join(running) or "none"
    return f"error: no sub-agent named {name!r} is running; the running ones are {names}"


def doing(event: Mapping[str, Any], before: str) -> str:
    """What a child is doing after one of its reply's events, for `/agents`: calling a tool,
    thinking (a result came back), or answering."""
    match event.get("type"):
        case "tool_call":
            return f"calling {event.get('name', '?')}"
        case "tool_result":
            return "thinking"
        case "text":
            return "answering"
    return before


@dataclass(frozen=True, slots=True)
class Listed:
    """One running child as `/agents` lists it: who, what it is doing, and its transcript (for the
    person; None when the session keeps its conversation in memory)."""

    name: str
    type: str
    background: bool
    doing: str
    transcript: str | None


def listing(children: Sequence[Listed]) -> str:
    """`/agents`' answer: the running children, one line each."""
    if not children:
        return "No sub-agents are running."
    many = "s" if len(children) != 1 else ""
    lines = [f"{len(children)} sub-agent{many} running (/agents stop [NAME] ends them):"]
    for child in children:
        where = f"; transcript {child.transcript}" if child.transcript else ""
        mode = "background" if child.background else "foreground"
        lines.append(f"  {child.name} ({child.type}, {mode}): {child.doing}{where}")
    return "\n".join(lines)


def parsed_command(args: str) -> tuple[str, str] | str:
    """`/agents`' arguments as `("list", "")`, `("stop", NAME)` (NAME empty: all), or why they are
    none of those."""
    words = args.split()
    match words:
        case []:
            return ("list", "")
        case ["stop"]:
            return ("stop", "")
        case ["stop", name]:
            return ("stop", name)
        case ["watch", name]:
            return ("watch", name)
    return f"/agents takes nothing (it lists), `stop [NAME]` or `watch NAME`, not {args!r}"


def field_forms(running: int) -> tuple[str, ...]:
    """The status bar's `agents` field for `running` sub-agents (the bar shows `agents: 2 running`):
    its text, then a shorter form; none at 0, so the field is absent."""
    return (f"{running} running", str(running)) if running > 0 else ()


def watch_command(session: str, name: str, *, running: bool) -> str:
    """`/agents watch NAME`'s answer: the command that follows the child's event log in another
    terminal (read-only; `session` and `name` are bh-02's own)."""
    state = "is running" if running else "has ended; its log is kept"
    return (
        f"agent {name} {state}. To follow its events, run this in another terminal:\n"
        f"  bh-02 watch {session} {name}"
    )


def no_such_agent(name: str, known: Iterable[str]) -> str:
    """`/agents watch`'s answer for a name this session's agents row gave no sub-agent."""
    return f"error: this run started no sub-agent named {name!r}; it started {', '.join(known) or 'none'}"


def started_record(name: str, kind: str, prompt: str, background: bool) -> dict[str, Any]:
    """The first record of a child's event log: who it is and what it was asked."""
    return {
        "type": "agent_start",
        "name": name,
        "agent_type": kind,
        "prompt": prompt,
        "background": background,
    }


def ended_record(report: str) -> dict[str, Any]:
    """The last record of a child's event log: what the `agent` call answered (its report, or why
    it gave none). `bh-02 watch` stops following at it."""
    return {"type": "agent_end", "report": report}


def stopped(names: Sequence[str], running: Iterable[str]) -> str:
    """The answer to a stop: which children ended, or that none was running."""
    if not names:
        return f"No sub-agent was running to stop (running: {', '.join(running) or 'none'})."
    return f"Stopped {', '.join(names)}: each conversation ended, with its python program."


def stop_note(background: int) -> str:
    """What the stop notice adds after Ctrl-C: how many background agents still run ('' for none)."""
    if background == 0:
        return ""
    many = f"{background} background agents still run" if background != 1 else "1 background agent still runs"
    return f"{many}; /agents stop ends them"


def lost(name: str, kind: str) -> str:
    """The note for a child ended from outside: its realm was retired while it ran."""
    return (
        f"agent {name} ({kind}) was ended before it answered: the agents row restarted "
        "(/clear, /model and /restart agents do that) or bh-02 is leaving"
    )
