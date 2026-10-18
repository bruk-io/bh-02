"""A session laid out in time: the pure part of `bh-02 trajectory` (decision-0009, Reading).

The record is the transcript: its entries carry when they came, how long each step and call took,
who answered a call's question, what a step cost and which sub-agent a call started (CONTRACTS.md:
message, step record, call record). Nothing here is stored. `trajectory` computes the session's
trajectory from the bytes of its transcript files, and `rendered` lays it out as lines of text; the
files are found, read and printed by `bh_02.viewing` and `bh_02.cli`.

bh_02 imports no plugin (plugin-layering), so the entries are read as TypedDicts of this module's
own (`_Entry` and the records on it), which say what the agent plugin's `records.py` writes. The
file is the person's, but a hand-edited or half-written one must not stop the view: every field is
checked as it is read, and one that is missing or of the wrong type is left out. A field the loop
leaves out for its own reason is left out of the line the same way: the answer to a message the model
was never asked is no step and has no `step`, and a call refused before approval has no `answer`.

A conversation is one transcript file. The live `transcript.jsonl` is the last, and the backups
`/clear` and `/compact` keep (`transcript.jsonl.bak`, `.bak.2`, ...) come before it, in the order of
their first `at`, else of their modification time (a backup is copied when its conversation ends).
A conversation holds replies (a message of the person's, and the steps the loop took to answer it),
each step the calls it made, each call the calls its input made through `tools` and the sub-agent it
started. A sub-agent's own transcripts (under `<session>/agents/NAME/`) are placed under the call
that started it, and one no call names after the session's own conversations, by its own times.

A session's row reloads are its `rows.jsonl` (the shell appends a line for each row that reloaded or
failed, a sub-agent's rows too, after a line that marks the start of each run). Each is printed in time
order among the lines of whose rows it is, the session's own or a sub-agent's (`agents/NAME/...`):
before the first reply, step, call or conversation of theirs that came after it, at that line's
indentation, and after the last line when none did. A sub-agent's lines run alongside the session's, so
each is placed by its own.

cordis has no first-load event, so a row's first load is a `reload` like any other. It is told apart by
the row id: the first record of a row in a run is its first load, every later `reload` is a reload (a
restart, a dependency replaced, a layer edit), and a `failed` is always a failure. A run is what one
`bh-02` process wrote: a session resumed goes on in the same `rows.jsonl`, and the shell starts each
run's part of it with a line of kind `run` (`{at, kind: "run"}`, no row; `bootstrap._run_line`). The
file's start is the start of the first run, and each `run` line the start of the next, so what a
resumed run comes up with, which was all seen before, is that run's first loads, folded as the first
run's are. The line itself prints nothing. The first loads of a run that follow one another with
nothing else of their writer's between them (no reload, no failure, no line of the session's or the
sub-agent's) are one line: the session's boot, and under each sub-agent the rows it came up with, which
would otherwise bury the reloads that matter. A reload and a failure are a line each, as ever.

A line that is not a JSON object is skipped: the last one may be half written while the loop appends.
A call whose `tool` entry is not there shows `no result recorded`.

Times are UTC in the files and local in `rendered` (the date the model is told is the local day too).
Every text from a file is stripped of control characters (`bh_02.watching.clean`) before it is
printed. Everything here is pure; `rendered` reads the machine's time zone when it is given none.
"""

import datetime
import json
import math
import re
from collections import Counter, deque
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import groupby
from typing import Any, Literal, NotRequired, TypedDict, assert_never, cast

from bh_02.sessions import TRANSCRIPT
from bh_02.watching import clean

__all__ = ["Key", "Line", "Trajectory", "Transcript", "is_conversation_file", "rendered", "trajectory"]

type Key = tuple[str | int, ...]
type Answer = Literal["unasked", "yes", "no"]

# A conversation's file: the live one, or a backup `rewrite` kept (`.bak`, then `.bak.2`, ...).
_FILE = re.compile(re.escape(TRANSCRIPT) + r"(?:\.bak(?:\.([0-9]+))?)?")
_MESSAGES = ("user", "assistant", "tool")  # the roles that are the conversation; `system` and `tools` are not
_CLIP = 200  # characters of a message shown on one line
_DATED = "(Today's date: {}.)"  # what the loop puts before a message that tells the date (CONTRACTS.md)
_UNKNOWN = "?"
_OWN = ""  # the first element of a key from the session's own conversations; a sub-agent's is its name
_ROWS = "rows"  # the first element of a row reload's key
_RELOAD = "reload"  # the kind of a record in `rows.jsonl` that is a row's setup beginning
_RUN = "run"  # the kind of a record in `rows.jsonl` that marks a run's start; it names no row
_AGENTS = "agents"  # the first part of the id of a sub-agent's row


# What the files hold, as the agent plugin's `records.py` writes it. Not imported: bh_02 reads the
# files, so these are the reader's own, and a test builds a transcript with the plugin's loop to hold
# the two to one shape.
class _UsageRecord(TypedDict, closed=True):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    cost_usd: NotRequired[float]
    partial: NotRequired[Literal[True]]


class _SettingsRecord(TypedDict, closed=True):
    model: str
    provider: str
    max_tokens: NotRequired[int]
    temperature: NotRequired[float]


class _StepRecord(TypedDict, closed=True):
    at: str
    first_chunk: NotRequired[float]
    took: NotRequired[float]
    model: NotRequired[str]
    usage: NotRequired[_UsageRecord]
    settings: NotRequired[_SettingsRecord]
    tool_changes: NotRequired[Literal["listed"]]


class _NestedRecord(TypedDict, closed=True):
    name: str
    at: str
    answer: NotRequired[Answer]
    waited: NotRequired[float]
    took: NotRequired[float]
    child: NotRequired[str]


class _CallRecord(TypedDict, closed=True):
    at: str
    answer: NotRequired[Answer]
    waited: NotRequired[float]
    took: NotRequired[float]
    child: NotRequired[str]
    nested: NotRequired[list[_NestedRecord]]


class _SeedRecord(TypedDict, closed=True):
    keep: str


class _ToolCall(TypedDict, closed=True):
    id: str
    name: str
    input: Mapping[str, Any]


class _Entry(TypedDict, total=False):
    """One line of a transcript, with the keys this module reads. Not closed: a provider's own
    message (`provider`), a result's `asides` and the `system` and `tools` entries' keys ride on it."""

    role: str
    content: str
    tool_calls: list[_ToolCall]
    call_id: str
    today: str
    feedback: str
    at: str
    seed: _SeedRecord
    step: _StepRecord
    call: _CallRecord


class _RowRecord(TypedDict, closed=True):
    """One line of a session's `rows.jsonl` (decision-0009, Row reloads): a row's `reload` or `failed`, or
    the `run` line that marks a run's start, which names no row."""

    at: str
    kind: str
    row: NotRequired[str]
    error: NotRequired[str]


@dataclass(frozen=True, slots=True)
class Transcript:
    """One conversation's file as the shell read it: whose it is (`agent`: None for the session's
    own, else the sub-agent's name), its `name` (`transcript.jsonl`, `transcript.jsonl.bak`, ...),
    when it was last written (`modified`: seconds since the epoch) and its bytes."""

    agent: str | None
    name: str
    modified: float
    data: bytes


type _File = tuple[Transcript, list[_Entry]]  # a transcript file and the entries read from it


@dataclass(frozen=True, slots=True)
class _Usage:
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_written: int
    cost_usd: float | None
    partial: bool


@dataclass(frozen=True, slots=True)
class _Settings:
    model: str | None
    provider: str | None
    max_tokens: int | None
    temperature: float | None


@dataclass(frozen=True, slots=True)
class _Call:
    """A call: its `tool`, whether its result is in the transcript (`recorded`) and its record
    (`at`, `answer`, `waited`, `took`, each None when the transcript has none). `child`: the
    sub-agent it started, by name, and `agent` that sub-agent's conversations when they were found.
    `nested`: the calls its input made through `tools`."""

    tool: str
    recorded: bool
    at: datetime.datetime | None
    answer: Answer | None
    waited: float | None
    took: float | None
    child: str | None
    agent: _Agent | None
    nested: tuple[_Call, ...]


@dataclass(frozen=True, slots=True)
class _Step:
    """One request to the model and its answer: its record's fields (None for each the transcript
    leaves out) and the calls it made."""

    at: datetime.datetime | None
    model: str | None
    first_chunk: float | None
    took: float | None
    usage: _Usage | None
    settings: _Settings | None
    calls: tuple[_Call, ...]

    @property
    def generation(self) -> float | None:
        """Seconds from the first chunk to the last."""
        if self.first_chunk is None or self.took is None or self.took < self.first_chunk:
            return None
        return self.took - self.first_chunk

    @property
    def tokens_per_second(self) -> float | None:
        """Output tokens over the generation time; none for a step that stopped before its output
        was counted (`partial`) or whose generation took no time."""
        generation = self.generation
        if generation is None or generation <= 0 or self.usage is None or self.usage.partial:
            return None
        return self.usage.output_tokens / generation if self.usage.output_tokens else None


@dataclass(frozen=True, slots=True)
class _Nudge:
    """The loop telling the model why its last step did not count (`why`: how the step ended)."""

    at: datetime.datetime | None
    why: str


@dataclass(frozen=True, slots=True)
class _Reply:
    """What the loop did to answer one message: its time, the person's words (None: the file does not
    begin with one) and the steps it took, with the loop's nudges among them."""

    at: datetime.datetime | None
    message: str | None
    items: tuple[_Step | _Nudge, ...]


@dataclass(frozen=True, slots=True)
class _Seed:
    """What `/compact` began a conversation with: the text the person asked the summary to `keep`
    and the summary `step` (None when the entry is not there)."""

    keep: str
    step: _Step | None


@dataclass(frozen=True, slots=True)
class _Conversation:
    """One transcript file. `ident` tells it from the session's others and stays the same when
    `/clear` or `/compact` renames the file (its first `at`, else its file's name); `seed` is set when
    `/compact` began it."""

    name: str
    ident: str
    at: datetime.datetime | None
    seed: _Seed | None
    replies: tuple[_Reply, ...]


@dataclass(frozen=True, slots=True)
class _Agent:
    """A sub-agent: its name and its own conversations."""

    name: str
    conversations: tuple[_Conversation, ...]

    @property
    def at(self) -> datetime.datetime | None:
        """When it began."""
        return next((c.at for c in self.conversations if c.at is not None), None)


@dataclass(frozen=True, slots=True)
class _Reload:
    """A row's lifecycle event kept in a session's `rows.jsonl`: a `reload` (a row's setup began: it
    came up, was restarted, or a dependency was replaced) or a `failed` (with its `error`). `first`: a
    `reload` of a row not recorded before in its run, which is its first load there (cordis emits no
    event of its own for one). `run`: how many `run` lines came before it in the file, so the first loads
    of two runs are never one line."""

    at: datetime.datetime
    kind: str
    row: str
    error: str | None
    first: bool = False
    run: int = 0


@dataclass(frozen=True, slots=True)
class Trajectory:
    """A session laid out in time. `conversations`: its own, in order, with the sub-agents they
    started inside their calls. `unlinked`: the sub-agents no call names, by their first time.
    `reloads`: its row reloads (first loads included) and failures, by time."""

    conversations: tuple[_Conversation, ...]
    unlinked: tuple[_Agent, ...]
    reloads: tuple[_Reload, ...]


@dataclass(frozen=True, slots=True)
class Line:
    """One line of `rendered`, without its newline. `key` says where in the trajectory it is, in a way
    that stays the same as the files grow and a file is replaced, so a viewer that follows them prints
    a line once; its first element is whose it is (`""`: the session's own conversations, a
    sub-agent's name, or `"rows"`: a row reload). `at` is when what it shows happened, and `depth`
    how far it is indented (what it is inside), for a line that has a time."""

    key: Key
    text: str
    at: datetime.datetime | None = None
    depth: int = 0


def is_conversation_file(name: str) -> bool:
    """Whether `name` is a conversation's file: the live transcript or one of its backups."""
    return _FILE.fullmatch(name) is not None


# --- reading ---------------------------------------------------------------------------------------


def _entries(data: bytes) -> list[_Entry]:
    """The JSON objects among the lines of `data`: a line that is not one (the half-written last line
    of a file the loop is appending to) is skipped."""
    found: list[_Entry] = []
    for line in data.splitlines():
        try:
            value = json.loads(line)
        except ValueError, RecursionError:
            continue
        if isinstance(value, dict):
            found.append(cast(_Entry, value))
    return found


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:  # an integer too large for a float: not a duration
        return None
    return number if math.isfinite(number) else None


def _moment(value: object) -> datetime.datetime | None:
    """A time as the transcript keeps it (UTC ISO-8601), as an aware time; None if it is not one."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=datetime.UTC)


def _answer(value: object) -> Answer | None:
    match value:
        case "unasked":
            return "unasked"
        case "yes":
            return "yes"
        case "no":
            return "no"
        case _:
            return None


def _step_record(entry: _Entry) -> _StepRecord | None:
    value: object = entry.get("step")
    return cast(_StepRecord, value) if isinstance(value, dict) else None


def _call_record(entry: _Entry) -> _CallRecord | None:
    value: object = entry.get("call")
    return cast(_CallRecord, value) if isinstance(value, dict) else None


def _tool_calls(entry: _Entry) -> list[_ToolCall]:
    value: object = entry.get("tool_calls")
    return (
        [cast(_ToolCall, call) for call in value if isinstance(call, dict)] if isinstance(value, list) else []
    )


def _nested_records(record: _CallRecord) -> list[_NestedRecord]:
    value: object = record.get("nested")
    return (
        [cast(_NestedRecord, one) for one in value if isinstance(one, dict)]
        if isinstance(value, list)
        else []
    )


def _usage(value: object) -> _Usage | None:
    if not isinstance(value, dict):
        return None
    record = cast(_UsageRecord, value)
    return _Usage(
        input_tokens=_count(record.get("input_tokens")) or 0,
        output_tokens=_count(record.get("output_tokens")) or 0,
        cache_read=_count(record.get("cache_read_input_tokens")) or 0,
        cache_written=_count(record.get("cache_creation_input_tokens")) or 0,
        cost_usd=_number(record.get("cost_usd")),
        partial=record.get("partial") is True,
    )


def _settings(value: object) -> _Settings | None:
    if not isinstance(value, dict):
        return None
    record = cast(_SettingsRecord, value)
    return _Settings(
        model=_text(record.get("model")),
        provider=_text(record.get("provider")),
        max_tokens=_count(record.get("max_tokens")),
        temperature=_number(record.get("temperature")),
    )


def _stamped(entry: _Entry) -> datetime.datetime | None:
    """When an entry says it happened: its own `at`, else its step's or its call's."""
    step, call = _step_record(entry), _call_record(entry)
    return (
        _moment(entry.get("at"))
        or _moment(step.get("at") if step else None)
        or _moment(call.get("at") if call else None)
    )


def _began(entries: Sequence[_Entry]) -> datetime.datetime | None:
    """The first time a conversation's entries say."""
    return next((moment for entry in entries if (moment := _stamped(entry)) is not None), None)


def _backup_number(name: str) -> int:
    """Which backup a file is, by its name: `.bak` is the first, `.bak.2` the second."""
    found = _FILE.fullmatch(name)
    if found is None or ".bak" not in name:
        return 0
    return int(found.group(1) or 1)


def _ordered(files: Sequence[_File]) -> list[_File]:
    """A session's conversations in order: the live transcript last, the backups before it by their
    first `at`, else by the time they were last written (the time they were copied, which is when
    their conversation ended). The backup's name breaks a tie."""

    def started(file: _File) -> tuple[datetime.datetime, int]:
        transcript, entries = file
        began = _began(entries) or datetime.datetime.fromtimestamp(transcript.modified, datetime.UTC)
        return began, _backup_number(transcript.name)

    backups = sorted((f for f in files if f[0].name != TRANSCRIPT), key=started)
    return [*backups, *(f for f in files if f[0].name == TRANSCRIPT)]


def _message(entry: _Entry) -> str:
    """The person's words on a `user` entry: its content less the date the loop put before it."""
    content = _text(entry.get("content")) or ""
    today = _text(entry.get("today"))
    return content.removeprefix(_DATED.format(today)).lstrip() if today else content


def _feedback(entry: _Entry) -> str | None:
    return _text(entry.get("feedback")) or None


def _seed_record(entry: _Entry) -> _SeedRecord | None:
    value: object = entry.get("seed")
    return cast(_SeedRecord, value) if isinstance(value, dict) else None


def _begins_reply(entry: _Entry) -> bool:
    """Whether an entry is a message of the person's (a seed and the loop's nudge are not)."""
    return entry.get("role") == "user" and _feedback(entry) is None and _seed_record(entry) is None


def _call(
    tool: str,
    recorded: bool,
    record: Mapping[str, object] | None,
    nested: tuple[_Call, ...],
    agents: Mapping[str, _Agent],
) -> _Call:
    """A call from its record (a call's or a nested call's: None when the transcript has none)."""
    fields: Mapping[str, object] = record if record is not None else {}
    child = _text(fields.get("child"))
    return _Call(
        tool=tool,
        recorded=recorded,
        at=_moment(fields.get("at")),
        answer=_answer(fields.get("answer")),
        waited=_number(fields.get("waited")),
        took=_number(fields.get("took")),
        child=child,
        agent=agents.get(child) if child is not None else None,
        nested=nested,
    )


def _step(entry: _Entry, results: Sequence[_Entry], agents: Mapping[str, _Agent]) -> _Step:
    """A step from its `assistant` entry and the `tool` entries after it. A call is matched to its
    result by its id; a call with none is `recorded=False`, a result no call asked for is a call of
    an unknown tool."""
    record = _step_record(entry)
    by_id = {str(result.get("call_id")): result for result in results}
    calls: list[_Call] = []
    for made in _tool_calls(entry):
        calls.append(
            _answered(_text(made.get("name")) or _UNKNOWN, by_id.pop(str(made.get("id")), None), agents)
        )
    calls.extend(_answered(_UNKNOWN, result, agents) for result in by_id.values())
    return _Step(
        at=_moment(record.get("at")) if record else None,
        model=_text(record.get("model")) if record else None,
        first_chunk=_number(record.get("first_chunk")) if record else None,
        took=_number(record.get("took")) if record else None,
        usage=_usage(record.get("usage")) if record else None,
        settings=_settings(record.get("settings")) if record else None,
        calls=tuple(calls),
    )


def _answered(tool: str, result: _Entry | None, agents: Mapping[str, _Agent]) -> _Call:
    """A call of `tool` and the `tool` entry that answers it (None: it is not there)."""
    if result is None:
        return _call(tool, False, None, (), agents)
    record = _call_record(result)
    nested = (
        tuple(
            _call(_text(one.get("name")) or _UNKNOWN, True, one, (), agents)
            for one in _nested_records(record)
        )
        if record
        else ()
    )
    return _call(tool, True, record, nested, agents)


def _groups(entries: Sequence[_Entry], begins: Callable[[_Entry], bool]) -> list[list[_Entry]]:
    """`entries` cut into runs, a new one at each entry `begins` says begins one; what comes before
    the first is a run of its own."""
    runs: list[list[_Entry]] = []
    for entry in entries:
        if not runs or begins(entry):
            runs.append([])
        runs[-1].append(entry)
    return runs


def _begins_item(entry: _Entry) -> bool:
    return entry.get("role") == "assistant" or (entry.get("role") == "user" and _feedback(entry) is not None)


def _reply(run: Sequence[_Entry], agents: Mapping[str, _Agent]) -> _Reply:
    """A reply from its run of entries: the person's message, then the steps and nudges after it.
    A run that does not begin with a message (a file cut at its start) has none."""
    head = run[0] if _begins_reply(run[0]) else None
    items: list[_Step | _Nudge] = []
    # a `tool` entry before any assistant entry answers nothing in this file, and is left out
    for group in _groups(run[1:] if head is not None else run, _begins_item):
        first, *rest = group
        if first.get("role") == "assistant":
            items.append(_step(first, [r for r in rest if r.get("role") == "tool"], agents))
        elif (why := _feedback(first)) is not None:
            items.append(_Nudge(_stamped(first), why))
    return _Reply(_moment(head.get("at")) if head else None, _message(head) if head else None, tuple(items))


def _conversation(name: str, entries: Sequence[_Entry], agents: Mapping[str, _Agent]) -> _Conversation:
    said = [entry for entry in entries if entry.get("role") in _MESSAGES]
    began = _began(said)
    seed: _Seed | None = None
    given = _seed_record(said[0]) if said else None
    if given is not None:
        # `/compact` began it: the first entry says what the person asked to keep, the second is the
        # summary step (it answers the old conversation, so it is the boundary, not a step of this one)
        summary = said[1] if len(said) > 1 and said[1].get("role") == "assistant" else None
        seed = _Seed(_text(given.get("keep")) or "", _step(summary, [], agents) if summary else None)
        said = said[2:] if summary is not None else said[1:]
    replies = tuple(_reply(run, agents) for run in _groups(said, _begins_reply))
    return _Conversation(name, began.isoformat() if began else f"file {name}", began, seed, replies)


def _kept(files: Sequence[_File], agents: Mapping[str, _Agent]) -> tuple[_Conversation, ...]:
    """The conversations of one writer (the session, or a sub-agent), in order, those that hold
    a message only: a file the loop has only written its prompt to, or that `/clear` emptied, is none."""
    ordered = _ordered([f for f in files if any(e.get("role") in _MESSAGES for e in f[1])])
    return tuple(_conversation(transcript.name, entries, agents) for transcript, entries in ordered)


def _calls(conversations: Sequence[_Conversation]) -> Iterator[_Call]:
    """Every call in `conversations`, nested ones included."""
    for conversation in conversations:
        for reply in conversation.replies:
            for item in reply.items:
                if isinstance(item, _Step):
                    for call in item.calls:
                        yield call
                        yield from call.nested


def _reloads(rows: bytes) -> tuple[_Reload, ...]:
    """The records of `rows` in time order. A `run` record (a run's start) is not one of the reloads: it
    starts the next run, so the rows after it are told first loads afresh. Each `reload` of a row the
    records have not named before in its run is marked `first`; a row that has failed has been named,
    so its next `reload` is not."""
    found: list[_Reload] = []
    for line in rows.splitlines():
        try:
            value = json.loads(line)
        except ValueError, RecursionError:
            continue
        if not isinstance(value, dict):
            continue
        record = cast(_RowRecord, value)
        at, kind, row = _moment(record.get("at")), _text(record.get("kind")), _text(record.get("row"))
        if at is None or kind is None:
            continue
        if kind == _RUN:
            found.append(_Reload(at, kind, "", None))
        elif row is not None:
            found.append(_Reload(at, kind, row, _text(record.get("error"))))
    ordered = sorted(found, key=lambda reload: reload.at)
    seen: set[str] = set()
    run = 0
    marked: list[_Reload] = []
    for reload in ordered:
        if reload.kind == _RUN:
            seen.clear()
            run += 1
            continue
        marked.append(replace(reload, first=reload.kind == _RELOAD and reload.row not in seen, run=run))
        seen.add(reload.row)
    return tuple(marked)


def trajectory(conversations: Sequence[Transcript], rows: bytes = b"") -> Trajectory:
    """A session's trajectory from the transcript files read (`conversations`: the session's own, and
    each sub-agent's, told apart by `Transcript.agent`) and its `rows.jsonl` (`rows`: the bytes). No
    file is opened and nothing is stored: the same files give the same trajectory."""
    read = [(transcript, _entries(transcript.data)) for transcript in conversations]
    names = sorted({transcript.agent for transcript in conversations if transcript.agent is not None})
    # depth one (decision-0002): a sub-agent has no sub-agents, so what its calls name is not followed
    agents = {name: _Agent(name, _kept([f for f in read if f[0].agent == name], {})) for name in names}
    own = _kept([f for f in read if f[0].agent is None], agents)
    linked = {call.agent.name for call in _calls(own) if call.agent is not None}
    unlinked = sorted(
        (agent for name, agent in agents.items() if name not in linked and agent.conversations),
        key=lambda agent: (
            agent.at is None,
            agent.at or datetime.datetime.max.replace(tzinfo=datetime.UTC),
            agent.name,
        ),
    )
    return Trajectory(own, tuple(unlinked), _reloads(rows))


# --- laying out ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _View:
    """How to lay out: in the zone `tz` (None: the machine's), and whether the files are still being
    written (`live`), when a call whose result is not there yet may be running and is not shown."""

    tz: datetime.tzinfo | None
    live: bool


def _say(text: str, limit: int = _CLIP) -> str:
    """Text from a file as one line of at most `limit` characters, with no control character."""
    one = " ".join(clean(text).split())
    return one if len(one) <= limit else f"{one[:limit]}…"


def _when(moment: datetime.datetime | None, view: _View, day: datetime.date | None) -> str:
    """A time in the view's zone, `HH:MM:SS.mmm`, with its date unless that is `day`; empty for none."""
    if moment is None:
        return ""
    local = moment.astimezone(view.tz)
    clock = f"{local:%H:%M:%S}.{local.microsecond // 1000:03d}"
    return clock if local.date() == day else f"{local:%Y-%m-%d} {clock}"


def _day(moment: datetime.datetime | None, view: _View) -> datetime.date | None:
    return moment.astimezone(view.tz).date() if moment is not None else None


def _seconds(value: float) -> str:
    return f"{value:.2f}s"


def _line(depth: int, *parts: str) -> str:
    return "  " * depth + "  ".join(part for part in parts if part)


def _usage_text(usage: _Usage) -> list[str]:
    parts = [f"in {usage.input_tokens:,} tokens", f"out {usage.output_tokens:,} tokens"]
    if usage.cache_read:
        parts.append(f"cache read {usage.cache_read:,}")
    if usage.cache_written:
        parts.append(f"cache written {usage.cache_written:,}")
    if usage.cost_usd is not None:
        parts.append(f"cost ${usage.cost_usd:.4f}")
    if usage.partial:
        parts.append("(partial: stopped before its output was counted)")
    return parts


def _step_parts(step: _Step, view: _View, day: datetime.date | None) -> list[str]:
    """What a step line says after its label, in the order the task asks: its time, model, time to
    first chunk, generation time and speed, then usage and cost."""
    parts = [_when(step.at, view, day), _say(step.model) if step.model else ""]
    if step.at is not None and step.took is None:
        parts.append("no chunk came")
    if step.first_chunk is not None:
        parts.append(f"first chunk {_seconds(step.first_chunk)}")
    if (generation := step.generation) is not None:
        parts.append(f"generated in {_seconds(generation)}")
    if (speed := step.tokens_per_second) is not None:
        parts.append(f"{speed:.1f} tokens/s")
    if step.usage is not None:
        parts.extend(_usage_text(step.usage))
    return parts


def _settings_text(settings: _Settings) -> str:
    named = _say(settings.model or _UNKNOWN)
    via = f" via {_say(settings.provider)}" if settings.provider else ""
    sent = [
        *([f"max_tokens {settings.max_tokens}"] if settings.max_tokens is not None else []),
        *([f"temperature {settings.temperature:g}"] if settings.temperature is not None else []),
    ]
    return "settings: " + ", ".join([f"{named}{via}", *sent])


def _answer_text(call: _Call) -> list[str]:
    match call.answer:
        case "unasked":
            return ["answer unasked"]
        case "yes" | "no":
            waited = f" (waited {_seconds(call.waited)})" if call.waited is not None else ""
            return [f"answer {call.answer}{waited}"]
        case None:
            return ["not put to approval"] if call.at is not None else []
        case _ as unreachable:
            assert_never(unreachable)


def _call_lines(
    key: Key, label: str, call: _Call, depth: int, day: datetime.date | None, view: _View
) -> Iterator[Line]:
    """A call's line, then the sub-agent it started and the calls its input made, under it."""
    parts = [f"{label} {_say(call.tool)}", _when(call.at, view, day)]
    if not call.recorded:
        parts.append("no result recorded")
    parts.extend(_answer_text(call))
    if call.took is not None:
        parts.append(f"ran {_seconds(call.took)}")
    if call.child is not None:
        found = "" if call.agent is not None else " (its transcript was not found)"
        parts.append(f"started sub-agent {_say(call.child)}{found}")
    yield Line(key, _line(depth, *parts), call.at, depth)
    if call.agent is not None:
        yield from _agent_lines(call.agent, depth + 1, "", view)
    for n, nested in enumerate(call.nested, 1):
        yield from _call_lines((*key, "nested", n), "nested call", nested, depth + 1, day, view)


def _step_lines(
    key: Key, number: int, step: _Step, depth: int, day: datetime.date | None, tail: bool, view: _View
) -> Iterator[Line]:
    yield Line((*key, "step"), _line(depth, f"step {number}", *_step_parts(step, view, day)), step.at, depth)
    if step.settings is not None:
        yield Line((*key, "settings"), _line(depth + 1, _settings_text(step.settings)))
    for n, call in enumerate(step.calls, 1):
        if view.live and tail and not call.recorded:
            continue  # the last step's call may be running: shown once its result is
        yield from _call_lines((*key, "call", n), "call", call, depth + 1, day, view)


def _reply_lines(key: Key, number: int, reply: _Reply, depth: int, tail: bool, view: _View) -> Iterator[Line]:
    day = _day(reply.at, view)
    said = _say(reply.message) if reply.message is not None else "(the file begins with no message)"
    yield Line(
        (*key, "reply"), _line(depth, f"reply {number}", _when(reply.at, view, None), said), reply.at, depth
    )
    steps = 0
    for n, item in enumerate(reply.items, 1):
        match item:
            case _Step():
                steps += 1
                last = tail and n == len(reply.items)
                yield from _step_lines((*key, n), steps, item, depth + 1, day, last, view)
            case _Nudge(at=at, why=why):
                yield Line(
                    (*key, n, "nudge"),
                    _line(depth + 1, "nudge", _when(at, view, day), _say(why)),
                    at,
                    depth + 1,
                )
            case _ as unreachable:
                assert_never(unreachable)


def _boundary(conversation: _Conversation, number: int) -> str:
    """How a conversation began: `/compact` (said by its seed), `/clear` (any after the first without
    one), else it is the session's first."""
    if conversation.seed is not None:
        keep = f", asked to keep: {_say(conversation.seed.keep)}" if conversation.seed.keep else ""
        return f"begun by /compact{keep}"
    return "begun by /clear" if number > 1 else ""


def _conversation_lines(
    owner: str, conversation: _Conversation, number: int, depth: int, tail: bool, view: _View
) -> Iterator[Line]:
    key: Key = (owner, conversation.ident)
    yield Line(
        (*key, "conversation"),
        _line(
            depth,
            f"conversation {number}",
            _say(conversation.name),
            _when(conversation.at, view, None),
            _boundary(conversation, number),
        ),
        conversation.at,
        depth,
    )
    if conversation.seed is not None:
        step = conversation.seed.step
        # the boundary's own step: its request was the conversation before this one
        said = _step_parts(step, view, None) if step is not None else ["no step recorded"]
        yield Line(
            (*key, "summary"),
            _line(depth + 1, "summary step", *said),
            step.at if step is not None else None,
            depth + 1,
        )
        if step is not None and step.settings is not None:
            yield Line((*key, "summary", "settings"), _line(depth + 2, _settings_text(step.settings)))
    for n, reply in enumerate(conversation.replies, 1):
        last = tail and n == len(conversation.replies)
        yield from _reply_lines((*key, n), n, reply, depth + 1, last, view)


def _conversations_lines(
    owner: str, conversations: Sequence[_Conversation], depth: int, view: _View
) -> Iterator[Line]:
    for n, conversation in enumerate(conversations, 1):
        yield from _conversation_lines(owner, conversation, n, depth, n == len(conversations), view)


def _agent_lines(agent: _Agent, depth: int, note: str, view: _View) -> Iterator[Line]:
    yield Line((agent.name, "agent"), _line(depth, f"sub-agent {_say(agent.name)}", note))
    yield from _conversations_lines(agent.name, agent.conversations, depth + 1, view)


def _reload_keys(reloads: Sequence[_Reload]) -> list[Key]:
    """A key for each reload that stays the same as the file grows: its time, kind and row, and which of
    the reloads that are alike in all three it is."""
    counts: Counter[tuple[str, str, str]] = Counter()
    keys: list[Key] = []
    for reload in reloads:
        same = (reload.at.isoformat(), reload.kind, reload.row)
        counts[same] += 1
        keys.append((_ROWS, *same, counts[same]))
    return keys


def _reload_line(key: Key, reload: _Reload, depth: int, near: datetime.datetime | None, view: _View) -> Line:
    """A row reload as a line, with its date unless it is `near`'s day."""
    label = f"row {_say(reload.kind)} {_say(reload.row)}"
    text = _line(depth, label, _when(reload.at, view, _day(near, view)), _say(reload.error or ""))
    return Line(key, text, reload.at, depth)


type _Group = tuple[
    Key, tuple[_Reload, ...]
]  # what one line of the rows' log shows: its key, and its records


def _first_loads_line(
    key: Key, run: Sequence[_Reload], depth: int, near: datetime.datetime | None, view: _View
) -> Line:
    """The first loads of a run (`_grouped`) as a line, with its date unless it is `near`'s day: the row,
    when it is one, else how many rows and the time from the first to the last."""
    first, last = run[0], run[-1]
    when = _when(first.at, view, _day(near, view))
    if len(run) == 1:
        text = _line(depth, f"row first load {_say(first.row)}", when)
    else:
        text = _line(
            depth,
            "row first load",
            when,
            f"{len(run)} rows in {_seconds((last.at - first.at).total_seconds())}",
        )
    return Line(key, text, first.at, depth)


def _grouped(batch: Iterable[tuple[Key, _Reload]]) -> Iterator[_Group]:
    """`batch`, the records of one writer's rows that fall in one place among its lines, in time order,
    as what is printed for each: first loads that follow one another in one run are one item (the key of
    the first record, and the loads), every other record an item of its own. Two runs' first loads are
    two items even with nothing between them, as a resumed run's boot follows an earlier one's."""
    for (first, _), group in groupby(batch, key=lambda item: (item[1].first, item[1].run)):
        items = list(group)
        if first:
            yield items[0][0], tuple(reload for _, reload in items)
        else:
            for key, reload in items:
                yield key, (reload,)


def _group_line(
    key: Key, group: Sequence[_Reload], depth: int, near: datetime.datetime | None, view: _View
) -> Line:
    if group[0].first:
        return _first_loads_line(key, group, depth, near, view)
    return _reload_line(key, group[0], depth, near, view)


def _owner(row: str) -> str:
    """Whose row it is, by the key its lines start with: a sub-agent's (`agents/NAME` or
    `agents/NAME/...`) is NAME's, any other the session's own."""
    head, _, rest = row.partition("/")
    return rest.partition("/")[0] if head == _AGENTS and rest else _OWN


def _unclosed(groups: list[_Group], view: _View) -> list[_Group]:
    """`groups`, the last of a writer's, without a last run of first loads when the files are still being
    written (`live`): nothing has come after it, so rows may still be loading, and printing it now would
    print it once with a count that goes on growing."""
    return groups[:-1] if view.live and groups and groups[-1][1][0].first else groups


def _with_reloads(lines: Iterable[Line], reloads: Sequence[_Reload], view: _View) -> Iterator[Line]:
    """`lines` with each reload put before the first line of its owner's (`_owner`) that has a later
    time, at that line's depth, and the rest after the last line, by time. A line with no time places
    nothing. A sub-agent's lines run alongside the session's own, so a reload is placed by the lines of
    the writer whose row it is, and its own order among them stays the order of the time. The first
    loads that fall in one place, one after another, are one line (`_grouped`): the boot is the rows the
    session came up with, before its first line. While the files are still being written (`live`), the
    first loads at the very end are held back, as more may be coming."""
    waiting: dict[str | int, deque[tuple[Key, _Reload]]] = {}
    for key, reload in zip(_reload_keys(reloads), reloads, strict=True):
        waiting.setdefault(_owner(reload.row), deque()).append((key, reload))
    last: Line | None = None  # the last line that had a time, whose day a reload is shown by
    for line in lines:
        if line.at is not None:
            queue = waiting.get(line.key[0])
            placed: list[tuple[Key, _Reload]] = []
            while queue and queue[0][1].at < line.at:
                placed.append(queue.popleft())
            for key, group in _grouped(placed):
                yield _group_line(key, group, line.depth, (last or line).at, view)
            last = line
        yield line
    trailing = [_unclosed(list(_grouped(queue)), view) for queue in waiting.values()]
    rest = sorted((item for groups in trailing for item in groups), key=lambda item: item[1][0].at)
    for key, group in rest:
        yield _group_line(key, group, 0, last.at if last is not None else None, view)


def rendered(laid: Trajectory, tz: datetime.tzinfo | None = None, *, live: bool = False) -> tuple[Line, ...]:
    """The trajectory as lines of text, indented by what is inside what: each conversation (with how
    it began, and for `/compact` the summary step's time and cost), its replies, their steps with the
    model, time to first chunk, generation time, speed, usage, cost and any settings, each step's calls
    with their answer, wait, run time and nested calls, and under a call the sub-agent it started.
    Each row reload (`Trajectory.reloads`) is a line of its own, in time order among the lines of its
    row's owner, the session's or its sub-agent's (`_with_reloads`), except that the first loads which
    follow one another are one line: the session's boot, and a sub-agent's rows coming up under it.
    Sub-agents no call names come last, by their own times.

    Times are in the zone `tz` (None: the machine's), with the date where it differs from the
    reply's. With `live`, the files are still being written: a call of the last step whose result is
    not there yet is held back, as it may be running; without it that call shows `no result recorded`."""
    view = _View(tz, live)
    lines = list(_conversations_lines(_OWN, laid.conversations, 0, view))
    for agent in laid.unlinked:
        lines.extend(_agent_lines(agent, 0, "(no call that started it is recorded)", view))
    return tuple(_with_reloads(lines, laid.reloads, view))
