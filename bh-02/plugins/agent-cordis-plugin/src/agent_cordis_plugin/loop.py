"""The loop: a reply is a model step, the calls it asked for, and the next step, until a step asks for none.

A plain function of the values it declares its own contracts for (CONTRACTS.md: model,
tools, transcript, system, approval, asides, executor). The model is offered the tools rows
register (`tools`, a broker), through the provider's standard tool calling, and each call runs
through the tool its name has; CodeAct's `python` is one of them, the python row's. The list is
read at a conversation's first request, after the tools the loop's config `requires` have
registered, and kept in its transcript; a later change (a tool added, removed or redefined) is
kept there too and told to the model as an aside on the next message it reads (`toolset`),
while each request offers the list as the provider chooses (`tool_changes`: by default the one
the conversation began with, so a model server's cache of the conversation's start stays good).
Each call is put to `approval` first and runs only on its yes (at once when it runs in a jail
that confines it, or is bh-02's own harness tool and the runner confines; otherwise the
person's answer): one place for every model provider, and the loop knows whether a stopped call
ever reached its tool.

Every request begins with the system prompt the conversation began with, kept in its transcript,
so a model server's cache of the conversation stays good. When the prompt reads differently (an
extension loaded, the branch switched, CLAUDE.md edited), the new reading is kept after it, as
the edits from the one before (`prompt.edits`), not another whole copy, and the model is told
what changed (`prompt.changes`) as an aside on the next message it reads. The date is not in
the prompt: the loop tells it with the person's message, the first of a conversation and the
first of each new day (`(Today's date: ...)`), so the prompt reads the same from one day to the
next.

After each call it runs, the loop asks `asides`, the functions rows have added there, what to
tell the model beside that call's result (`asides_for`): each is given the tool's name, the
call's input, its result and the files it opened (what the tool answered with), and may add an
aside, never change the result. A path-scoped rule arrives that way when the model first works
on a file it covers.
The model reads the asides after the result; the `tool` entry also keeps them as a list
(`asides`), so a row reading a resumed transcript for what it told finds each aside whole, not
somewhere in a text the result and the other asides share.

Reading the prompt (every section function, which may read many files and search the project)
and asking `asides` (which may read rule files) both run on `executor` (`executor.OneAtATime`),
never on the event loop, which the TUI shares: a slow section freezes nothing. One runs at a
time, a reading a stopped reply left running included: the next waits for it rather than
starting beside it. `executor` is a row of its own that depends on nothing, so a loop reloaded
by `/clear` or `/model` waits for the call the last loop left running too: stopping reply after
reply leaves at most one in flight, however often the loop reloads between them.
"""

import asyncio
import contextlib
import datetime
import json
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, assert_never, runtime_checkable

from agent_cordis_plugin.executor import OneAtATime
from agent_cordis_plugin.prompt import changes, edits, latest
from agent_cordis_plugin.records import (
    Answer,
    CallRecord,
    Clock,
    NestedRecord,
    Settings,
    StepRecord,
    call_record,
    day_of,
    nested_record,
    settings_to_record,
    stamp,
    step_record,
)
from agent_cordis_plugin.stops import ACT, ANSWERED, FEEDBACK, REFUSED, classify
from agent_cordis_plugin.toolset import LISTED, begun, changed, listed, mode_of, removed, told

__all__ = [
    "DECLINED",
    "FAILED",
    "STOPPED",
    "Approval",
    "Asked",
    "Confirm",
    "Executor",
    "Model",
    "LoopModel",
    "Asides",
    "Ran",
    "Rule",
    "Step",
    "System",
    "Tool",
    "Tools",
    "Transcript",
    "Unstarted",
    "called",
    "malformed",
    "asides_for",
    "lost_answers",
    "refusal",
    "request_for",
    "shown",
]

type Json = Mapping[str, Any]


@runtime_checkable
class Model(Protocol):
    """One step of a model over a transcript, with tools it may ask for but never runs."""

    def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]: ...


@runtime_checkable
class Tool(Protocol):
    """What the loop needs of one registered tool (CONTRACTS.md: tools): its spec, the function
    that runs a call, where a call runs, and how one is put to the person (None: the loop's way)."""

    @property
    def spec(self) -> Json: ...
    @property
    def run(self) -> Callable[[Json], Awaitable[Json]]: ...
    @property
    def runs(self) -> str: ...
    @property
    def show(self) -> Callable[[Json], Json] | None: ...


@runtime_checkable
class Tools(Protocol):
    """What the loop needs of the `tools` value: the specs to offer (in name order), the tool a
    call names, a wait for the ones it requires, and the seam through which it runs the calls a
    tool's own call makes (`serve`, CONTRACTS.md: tools)."""

    def specs(self) -> Sequence[Json]: ...
    def get(self, name: str) -> Tool | None: ...
    async def ready(self, names: Iterable[str], timeout: float) -> tuple[str, ...]: ...
    def serve(self, call: Callable[[str, Json], Awaitable[Json]]) -> Callable[[], None]: ...


type Aside = Callable[[Json], str]


@runtime_checkable
class Asides(Protocol):
    """What the loop needs of the `asides` value: the functions that may add an aside to a
    call's result, each called as `fn({"name", "input", "result", "touched"}) -> str`, on `executor`:
    one call's at a time, and never beside a reading of the prompt."""

    def __iter__(self) -> Iterator[Aside]: ...


@runtime_checkable
class Approval(Protocol):
    """What the loop asks of each call: whether it may run, as an `Answer` (`Asked`: `unasked` by
    the `approval` rule, else the person's `yes` or `no`)."""

    async def approve(self, question: Json) -> Answer: ...


@runtime_checkable
class Rule(Protocol):
    """What the loop needs of the `approval` value (CONTRACTS.md: approval): whether a call runs
    without asking the person (it runs in a runner that confines it, or it is bh-02's own
    harness tool and the runner confines)."""

    def unasked(self, question: Json) -> bool: ...


@runtime_checkable
class Confirm(Protocol):
    """What the loop needs of the `output` value: the person's yes or no about a call."""

    async def confirm(self, question: Json) -> bool: ...


@dataclass(frozen=True, slots=True)
class Asked:
    """Whether a call may run, as an `Answer`: `unasked` at once when the `approval` rule says it
    runs unasked, else the person's `yes` or `no` through `output.confirm`. The rule is the runner
    plugin's, in one place; the asking is the asker's."""

    rule: Rule
    output: Confirm

    async def approve(self, question: Json) -> Answer:
        if self.rule.unasked(question):
            return Answer.UNASKED
        return Answer.YES if await self.output.confirm(question) else Answer.NO


@runtime_checkable
class System(Protocol):
    """What the loop needs of the `system` value: what to tell the model about where it is,
    read on `executor` (it may read many files), one reading at a time."""

    def text(self) -> str: ...


@runtime_checkable
class Executor(Protocol):
    """What the loop needs of the `executor` value: `fn()` run off the event loop, once the call
    before it has ended, and its result (or what it raised). A caller stopped meanwhile only
    stops waiting: the call runs to its end, and the next waits for it."""

    async def run[T](self, fn: Callable[[], T]) -> T: ...


@runtime_checkable
class Transcript(Protocol):
    """The conversation's entries: appended by the loop, read whole for each request."""

    @property
    def messages(self) -> Sequence[Json]: ...
    def append(self, message: Json) -> None: ...


@runtime_checkable
class _Flushable(Protocol):
    """What a transcript that writes behind the loop (`FileTranscript`) has besides `Transcript`:
    `flush()` returns once every message appended is where the transcript keeps it. A transcript
    that keeps the conversation in memory has no such method and is asked for none (CONTRACTS.md:
    transcript)."""

    async def flush(self) -> None: ...


@runtime_checkable
class _Checkable(Protocol):
    """What a transcript whose file can be replaced under it (`FileTranscript`) has besides
    `Transcript`: `check()` returns once its writer has looked at the file and found it the one it
    writes to, and raises what it is told of a file that is not. A reply asks it first, so a
    refusal comes before the model is asked. A transcript that keeps the conversation in memory
    has no such method and is asked for none (CONTRACTS.md: transcript)."""

    async def check(self) -> None: ...


_INTERRUPTED = "interrupted: the person stopped this call before it finished; it may have partly run"
# What a call is answered with when the process that ran it died, found so when the session
# resumes: bh-02 itself stopped, which no one asked, and what the call did is unknown.
_LOST = "interrupted: bh-02 stopped before this call finished; it may have partly run"
# A call the stop came before: at the person's approval, or queued behind the one stopped.
_NOT_RUN = "not run: the person stopped the reply before this call started, so none of it ran"
# What a call the person said no to answers the model with.
DECLINED = "denied: the person said no to this call, so it did not run; ask them what they want instead"
# What a step that never finished ends with in the transcript, after what it said so far: the
# person stopped it, or the model failed (a 429, a dropped connection).
STOPPED = "[the person stopped this reply here]"
FAILED = "[this reply failed here; the person saw the error]"
# What the person is shown when the model is told, as an aside, that its instructions, or its
# tools, changed.
_TOLD = "told the model its instructions changed since the conversation began"
_TOOLS_TOLD = "told the model its tools changed since the conversation began"
_ASIDE = "told the model with this result: "  # then the first line of an aside
_SHOWN = 120  # how much of that line the person is shown
# What the model is told of the date, before the person's message: the first of a conversation,
# and the first of each new day.
_DATED = "(Today's date: {}.)"
# What the person is shown while the loop waits for the tools it requires, at its first request.
_WAITING = "waiting for {} to start before the model is asked"


class Unstarted(Exception):
    """A tool the loop requires never registered: a recoverable `loop` failure (CONTRACTS.md:
    loop), its `kind` `tools_missing`."""

    def __init__(self, missing: Sequence[str], waited: float) -> None:
        self.kind = "tools_missing"
        self.message = (
            f"{_listed(missing)} did not start within {waited:g} seconds, so the model was not asked: "
            "/rows shows the row that offers it and why it is not up (`/restart ROW` tries it again), "
            "and the next message waits for it again"
        )
        super().__init__(self.message)


def _listed(names: Sequence[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def _undated(messages: Sequence[Json], today: str) -> bool:
    """Whether the model is yet to be told `today`: the transcript has told it no date (a new
    conversation, or one `/compact` began), or the last one it told (a user entry's `today`) is
    another day's (a conversation run past midnight, or resumed later)."""
    told = next((str(m["today"]) for m in reversed(messages) if m.get("today")), None)
    return told != today


def _asked(message: str, today: str | None, aside: str, at: str) -> dict[str, Any]:
    """The person's message as the transcript keeps it: the date first when it is told
    (`today`), then what changed in the model's instructions (`aside`), then the message. The date
    rides on the entry as `today` too, which is how a later message finds the last one told. `at`:
    when the message came (`records.stamp`), which a provider does not send either."""
    told = [*([_DATED.format(today)] if today else []), *([aside] if aside else []), message]
    return {"role": "user", "content": "\n\n".join(told)} | ({"today": today} if today else {}) | {"at": at}


def _answer(call: Json, content: str, asides: Sequence[str], record: CallRecord) -> dict[str, Any]:
    """The transcript entry answering `call`: `content`, what the model reads (the input's result,
    then its asides and any change in the instructions, each after a blank line), the asides
    alone (`asides`, `[]` for none), so what was told is read back without searching the text, and
    the call's `record` (`call`). The loop's own, as `today` is: a provider sends `content`."""
    return {"role": "tool", "content": content, "call_id": call["id"], "asides": list(asides), "call": record}


def asides_for(functions: Iterable[Aside], input: Json) -> list[str]:
    """What the functions in `asides` say about one call (`name`, `input`, `result`, `touched`),
    sorted, so the order rows added them in means nothing. A function that fails or returns something
    other than text says so in one line, and the rest still say theirs."""
    asides: list[str] = []
    for fn in functions:
        try:
            said = fn(input)
            if not isinstance(said, str):
                raise TypeError(f"it returned a {type(said).__name__}, not text")
        except Exception as error:  # one row's function failing must not cost the input its result
            named = getattr(fn, "__qualname__", type(fn).__qualname__)
            said = (
                f"(bh-02 could not make an aside with {getattr(fn, '__module__', '?')}:{named}: {error}. "
                "The call's result is whole; tell the person this function in `asides` failed.)"
            )
        if said.strip():
            asides.append(said.strip())
    return sorted(asides)


def _unanswered_calls(messages: Sequence[Json]) -> list[Json]:
    """The calls a transcript's `messages` leave without an answer, in the calls' order: those of
    its last `assistant` entry that no `tool` entry after it answers. A step's entry is appended
    before its calls run, and a reply that ends answers every one, so only a process that died
    mid-call leaves any."""
    answered: set[str] = set()
    for message in reversed(messages):
        role = message.get("role")
        if role == "tool":
            answered.add(str(message.get("call_id")))
        elif role == "assistant":
            return [call for call in message.get("tool_calls") or () if call["id"] not in answered]
    return []


def lost_answers(messages: Sequence[Json], at: datetime.datetime) -> list[dict[str, Any]]:
    """The `tool` entries that answer each call a transcript's `messages` leave unanswered
    (`_unanswered_calls`) with `_LOST`, in the calls' order, each with a call record of the time
    alone (`at`): no answer, wait or run time was recorded, and none is known. The loop keeps them
    in the transcript at its next reply (`_answer_the_unanswered`); `/compact` sends them with its
    summary request and keeps nothing (`conversation.asked`), so both word and record them alike."""
    return [
        _answer(call, _LOST, [], call_record(at, None, None, None, None, ()))
        for call in _unanswered_calls(messages)
    ]


def request_for(messages: Sequence[Json]) -> list[Json]:
    """The messages for one request over a transcript's `messages`: the prompt the conversation
    began with (its first `system` entry), then the conversation. The prompts kept after the
    first were told as asides, so they stay out: a model is sent one `system` message, whole, and
    never sees the loop's edits. The `tools` entries, the lists the conversation was offered,
    stay out too: they are the request's tools, not its messages."""
    first = next((m for m in messages if m.get("role") == "system"), None)
    head: list[Json] = [{"role": "system", "content": first["content"]}] if first else []
    return [*head, *(m for m in messages if m.get("role") not in ("system", "tools"))]


def refusal(call: Json, offered: Sequence[str], later: Iterable[str] = ()) -> str | None:
    """Why a call can't run (its name is none of the tools `offered`), as text the model reads
    instead of a result; None when it can. `later`: the tools registered after the conversation
    began, which a provider that keeps the list it began with does not offer. A tool checks its
    own input."""
    name = call["name"]
    if name in offered:
        return None
    if name in set(later):
        return (
            f"error: {name!r} was added after this conversation began, so it is not among the "
            "tools offered in it; it is offered from the next conversation (/clear or /compact)"
        )
    yours = f"your tools are {', '.join(offered)}" if offered else "you have no tools"
    return f"error: there is no tool named {name!r}; {yours}"


# JSON Schema's simple types, as Python checks them (a bool is not a number here, as in JSON)
_TYPES: Mapping[str, Callable[[object], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, Mapping),
}
_NAMED = {"string": "a string", "integer": "an integer", "number": "a number", "boolean": "a boolean"}
_NAMED |= {"array": "an array", "object": "an object"}


def _json_type(value: object) -> str:
    """What JSON calls the type of `value`, with its article (`an integer`, `null`)."""
    if value is None:
        return "null"
    return next((said for kind, said in _NAMED.items() if _TYPES[kind](value)), f"a {type(value).__name__}")


def malformed(spec: Json, input: object) -> str | None:
    """Why a call's input does not fit the tool's spec, as text the model reads instead of a
    result (so a malformed call is never put to the person): not an object, a `required`
    property missing, or a property not of the simple type its schema names. None when it fits;
    the tool checks the rest."""
    name = spec.get("name")
    if not isinstance(input, Mapping):
        return f"error: {name} takes an object of named arguments, not {_json_type(input)}"
    schema = spec.get("parameters") or {}
    properties = schema.get("properties") or {}
    for key in schema.get("required") or ():
        if key not in input:
            return f"error: {name} needs `{key}`"
    for key, value in input.items():
        expected = (properties.get(key) or {}).get("type")
        if isinstance(expected, str) and expected in _TYPES and not _TYPES[expected](value):
            return f"error: {name} takes `{key}` as {_NAMED[expected]}, not {_json_type(value)}"
    return None


_SHOW_KEYS = ("title", "lines", "language")  # the only keys a tool's `show` may give


def shown(tool: Tool, name: str, input: Json) -> dict[str, Any]:
    """How a call is put to the person (`approval`): the tool's own `show(input)`, else the loop's
    way, the tool's name and its input as JSON. A show may give only `title`, `lines` and
    `language` (CONTRACTS.md: question); any other key it returns is dropped, so a show never sets
    the question's `name`, `input`, `runs` or `agent`, which are the loop's and the asker's. A
    `show` that fails, or answers with something other than a mapping, leaves the loop's way."""
    title = {"title": f"Call {name} with this input?"}
    try:
        own = tool.show(input) if tool.show is not None else None
    except Exception:  # a tool's own way of showing a call failing must not cost the person the question
        own = None
    if isinstance(own, Mapping):
        return title | {key: own[key] for key in _SHOW_KEYS if key in own}
    lines = json.dumps(input, indent=2, ensure_ascii=False, default=str).splitlines()
    return title | {"lines": lines, "language": "json"}


@dataclass(frozen=True, slots=True)
class Ran:
    """One call run through its tool (`called`): `content`, what the model reads; `touched`, the
    files the tool says it opened; `child`, the sub-agent it started, as the `agent` tool's result
    names it (CONTRACTS.md: tool result); `failed`, whether the tool failed rather than answered."""

    content: str
    touched: tuple[str, ...] = ()
    child: str | None = None
    failed: bool = False


async def called(tool: Tool, name: str, input: Json) -> Ran:
    """One call run through `tool`: what the model reads, the files it opened, the sub-agent it
    started, and whether the tool failed. A tool that fails, or answers with something other than
    `{"content": str, ...}`, answers with an error the model reads, so one tool's fault is never
    the reply's."""
    try:
        ran = await tool.run(input)
    except Exception as error:
        return Ran(
            f"error: the {name} tool failed ({type(error).__name__}: {error}); tell the person", failed=True
        )
    content = ran.get("content") if isinstance(ran, Mapping) else None
    if not isinstance(content, str):
        return Ran(
            f"error: the {name} tool answered with something other than its result as text; tell the person",
            failed=True,
        )
    touched, child = ran.get("touched") or (), ran.get("child")
    return Ran(
        content,
        tuple(str(path) for path in touched) if isinstance(touched, list | tuple) else (),
        child if isinstance(child, str) and child else None,
    )


class LoopModel:
    """The `loop` value: the transcript holds the conversation, and the model answers it one step at a time.

    Each step is classified (`stops.classify`): only `act` runs calls, and only `answered` (or
    `refused`: the provider declined, which asking again won't change) ends the reply. A
    truncated, silent or undecodable step is fed back to the model up to `max_nudges` times
    in one reply, then shown as the reason the reply stopped. The
    provider's assistant message rides on its transcript entry as `provider`, for the
    model to replay as it was received. An `act` step's calls run one at a time, each only on
    `approval.approve({"name", "input", "runs", "title", "lines", ...})`'s `unasked` or `yes`
    (`shown`); a `no` is that call's answer, `DECLINED`.

    The tools are read at a conversation's first request (`tools.specs()`, in name order), once
    the ones `requires` names have registered (waiting up to `wait` seconds, and saying so; one
    that never does fails the message, `Unstarted`), and kept in the transcript as a `tools`
    entry. Before each message the model reads they are read again, and a change kept as another
    `tools` entry and told on that message (`toolset.told`); a tool the conversation has that is
    missing for less than `wait` seconds is restarting (the python row's, on `/restart python`), not
    removed. Each request offers the list the model's `tool_changes` asks for: the one the
    conversation began with (`fixed`, the default) or the one as it reads now (`listed`). A call
    runs through the tool its name has now, waiting `wait` seconds for one that is restarting; a
    name it was not offered, or one removed since, answers with an error (`refusal`).

    A reply the person stops (the reply closed, or its task cancelled) while a step streams
    still leaves the transcript whole: what the step said so far, then `STOPPED`, as the
    assistant's answer; a model step that fails (it raises: rate limited, cut off) the same,
    with `FAILED`. Otherwise the next request would carry that message unanswered, and the
    model would answer it too, doing the stopped work again before the next one. A process that
    dies mid-call answers nothing, since a step's entry is appended before its calls run, so the
    next reply, before anything else, answers each call of the last step that no `tool` entry
    answers with `_LOST` (it may have partly run), in the calls' order, each with a call record of
    the time alone: a resumed conversation is whole before its first request (`_unanswered_calls`).

    The system prompt (`system.text()`, the sections rows add, the python tool's among them) is
    read before each message the model reads, on `executor`, but sent as the conversation began
    with it: a `system` entry in the transcript, the first one, kept whole. A later reading that
    differs from the last told is kept as another `system` entry, the edits from that one
    (`prompt.edits`), and told on that message (`prompt.changes`), so the conversation's start
    never changes under a model server's cache and the transcript holds the prompt once, not
    once per change. The date is told on the person's message instead, when the transcript has
    told none yet or another day's (the day where bh-02 runs, from `clock`; a test gives its own):
    first on that message, then any change to the instructions, then the message.

    The loop also records, on the entries it appends, when and how long (`records`; CONTRACTS.md:
    message, step record, call record): `at` on the person's message, and on each assistant entry a
    model step made, its `step`: when its request was handed over, the seconds to its first and
    its last chunk, the model that answered, its usage, and the model's settings when they are
    new to the conversation. On each `tool` entry it records the call, its `call`: when it
    reached approval, what approval made of it (`Answer`: `unasked`, `yes` or `no`) and the
    seconds the person took when they were asked, the seconds its tool ran, the sub-agent it
    started (the tool's result names it as `child`) and the calls its input made through
    `tools`, in order, each a record of its own; a call refused before approval, or never
    reached, has the time alone. A provider sends none of it.

    The prompt is read, and `asides` asked, on `executor` (the `executor` row's, which a reloaded
    loop shares with the last one); a loop built without one (a test, direct use) makes its own.

    A transcript that writes behind the loop (it has `flush()`: `FileTranscript` queues each
    entry to a thread, so the event loop never waits on a disk) is flushed at the end of every
    reply, however it ends (answered, failed, stopped, closed), once the last entry is appended.
    A command runs only after the reply before it has ended (the chat row reads its next line
    then), so `/clear` and `/compact` find every entry in the file, and a failed write is
    raised there at the latest.

    A transcript whose file can be replaced under it (it has `check()`) is asked first thing in a
    reply, before anything is appended, whether its file is still the one it writes to: the
    writer looks at the file only before a write, so a file `/clear` or `/compact` replaced and
    whose restart failed would otherwise be found at the step's entry, after the model had
    answered once. The check is the writing thread's stat, awaited with the event loop free; it
    waits for no write and the transcript is not flushed for it, so the flush stays one per reply.
    A refused reply keeps nothing and the model is never asked.
    """

    def __init__(
        self,
        model: Model,
        tools: Tools,
        transcript: Transcript,
        approval: Approval,
        max_nudges: int = 2,
        system: System | None = None,
        asides: Asides | None = None,
        executor: Executor | None = None,
        *,
        requires: Sequence[str] = (),
        wait: float = 30.0,
        clock: Clock | None = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._transcript = transcript
        self._approval = approval
        self._max_nudges = max_nudges
        self._system = system
        self._asides = asides
        self._requires = tuple(requires)
        self._wait = wait
        # what the model was last told (`prompt.latest`), and of how many `system` entries: the
        # transcript keeps a change as edits, so this saves applying them all for every message
        self._last: tuple[int, str | None] = (0, None)
        self._executor: Executor = executor if executor is not None else OneAtATime()
        self._clock = clock if clock is not None else Clock()
        self._ready = False  # whether the tools `requires` names have registered, once
        self._missing: dict[str, float] = {}  # a tool the conversation has, missing since when
        self._nested: list[_Made] = []  # the calls the running call made through `tools` (`nested`)

    def _prompt(self) -> str:
        """The system prompt as it reads now. Run on `executor` (`_told`)."""
        return self._system.text() if self._system else ""

    async def _told(self) -> tuple[str, list[str]]:
        """The aside the model is told with the next message it reads, and what the person is
        shown of it: what changed in its instructions (`_prompt_told`), then in its tools
        (`_tools_told`); ('', []) when nothing did."""
        prompt = await self._prompt_told()
        tools = self._tools_told()
        shown = [*([_TOLD] if prompt else []), *([_TOOLS_TOLD] if tools else [])]
        return "\n\n".join(part for part in (prompt, tools) if part), shown

    def _mode(self) -> str:
        """How the model wants its tools offered (CONTRACTS.md: model, `tool_changes`)."""
        return mode_of(self._model)

    def _tools_told(self) -> str:
        """Keep a change in the tools since the transcript last recorded them as a `tools` entry,
        and return what the model is told of it ('' when nothing changed, or the transcript
        records no list yet: `_offer` keeps the one the conversation begins with)."""
        before = listed(self._transcript.messages)
        if before is None:
            return ""
        change = changed(before, self._present(before))
        if change is None:
            return ""
        self._transcript.append(change)
        return told(change, self._mode())

    def _present(self, before: Sequence[Json]) -> list[Json]:
        """The tools registered now, in name order, with each of `before` that is missing for
        less than `wait` seconds kept as it was: its row is restarting, not gone."""
        now = {str(spec["name"]): spec for spec in self._tools.specs()}
        at = self._clock.monotonic()
        self._missing = {name: since for name, since in self._missing.items() if name not in now}
        for spec in before:
            name = str(spec["name"])
            if name not in now and at - self._missing.setdefault(name, at) < self._wait:
                now[name] = spec
        return [now[name] for name in sorted(now)]

    def _offered(self) -> list[Json]:
        """The tools a request offers: the list the conversation began with (`fixed`), or the
        list as the transcript last recorded it (`listed`)."""
        messages = self._transcript.messages
        return (listed(messages) if self._mode() == LISTED else begun(messages)) or []

    async def _prompt_told(self) -> str:
        """Bring what the transcript says the model was told up to date, before a message it is
        about to read: the first prompt is kept whole as the conversation's start, a later one
        that reads differently from the last told as the edits from it (`prompt.edits`), and
        what changed is returned to go with that message ('' when nothing did).

        The prompt is read on `executor`, off the event loop the TUI shares, and the transcript
        is touched only once it has been, so a reply stopped meanwhile changes nothing. One
        reading runs at a time: one a stopped reply left running (this loop's, or the one it
        reloaded from) finishes, unused, before the next begins."""
        now = await self._executor.run(self._prompt)
        kept = [m for m in self._transcript.messages if m.get("role") == "system"]
        if len(kept) != self._last[0]:
            # a transcript this loop has not read yet (a resume, a reloaded loop) or one another
            # loop kept a reading in since: what its entries come to, once
            self._last = (len(kept), latest(kept))
        last = self._last[1]
        if now == (last or ""):
            return ""
        kept_now = {"content": now} if last is None else {"edits": edits(last, now)}
        self._transcript.append({"role": "system", **kept_now})
        self._last = (len(kept) + 1, now)
        return changes(last, now) if last is not None else ""

    async def _offer(self) -> None:
        """Keep the tools a conversation begins with, at its first request: once every one
        `requires` names has registered (once a loop), or raise `Unstarted` naming those that did
        not within `wait` seconds. A conversation that already has its list keeps it."""
        if not self._ready:
            if missing := await self._tools.ready(self._requires, self._wait):
                raise Unstarted(missing, self._wait)
            self._ready = True
        if begun(self._transcript.messages) is None:
            self._transcript.append({"role": "tools", "tools": [dict(spec) for spec in self._tools.specs()]})

    async def _callable(self, call: Json, offered: Sequence[str]) -> Tool | str:
        """The tool `call` names, as registered now, or why the call can't run (text the model
        reads instead of a result): a name it was not offered (`refusal`), a tool that is not
        registered now (its row restarting) and did not come back within `wait` seconds, or an
        input that does not fit its spec (`malformed`)."""
        messages = self._transcript.messages
        later = {str(spec["name"]) for spec in listed(messages) or ()} - set(offered)
        if (refused := refusal(call, offered, later)) is not None:
            return refused
        name = str(call["name"])
        if name in removed(messages):
            return (
                f"error: the {name} tool was removed since this conversation began, so this call did not run"
            )
        if self._tools.get(name) is None:
            await self._tools.ready((name,), self._wait)
        tool = self._tools.get(name)
        if tool is None:
            return (
                f"error: the {name} tool is not running now (its row did not come back within "
                f"{self._wait:g} seconds), so this call did not run; tell the person"
            )
        return malformed(tool.spec, call["input"]) or tool

    async def nested(self, name: str, input: Json) -> Json:
        """A call a tool's own call makes (an input's `tools.NAME(...)`, CONTRACTS.md: tools,
        `serve`), run as the model's are: through the tool its name has now, if its input fits,
        once `approval` says yes, then asked of `asides`, whose asides are told with the call it
        was made from. Answers `{"content", "failed"}`: what the caller reads, and whether that
        is why it did not run or failed rather than its result."""
        call = _Call(self._clock)
        tool = self._tools.get(name)
        if tool is None:
            self._made(name, call, ())
            return {"content": f"error: there is no {name} tool now", "failed": True}
        if (why := malformed(tool.spec, input)) is not None:
            self._made(name, call, ())
            return {"content": why, "failed": True}
        if not await call.ask(
            self._approval, {"name": name, "input": input, "runs": tool.runs, **shown(tool, name, input)}
        ):
            self._made(name, call, ())
            return {"content": DECLINED, "failed": True}
        with call.running():
            ran = await called(tool, name, input)
        call.child = ran.child
        done = {"name": name, "input": input, "result": ran.content, "touched": ran.touched}
        asides = await self._executor.run(partial(asides_for, tuple(self._asides or ()), done))
        self._made(name, call, asides)
        return {"content": ran.content, "failed": ran.failed}

    def _made(self, name: str, call: _Call, asides: Sequence[str]) -> None:
        """Keep a call an input made, once it has ended: its record, and the asides told of it."""
        self._nested.append(_Made(nested_record(name, call.record()), tuple(asides)))

    def _answer_the_unanswered(self) -> None:
        """Keep the answer to each call a process that died left unanswered (`lost_answers`), in the
        calls' order, so the conversation is whole before any request. The record of each has the
        time alone, as a call the stop never reached has: no answer, wait or run time was recorded,
        and none is known."""
        for entry in lost_answers(self._transcript.messages, self._clock.now()):
            self._transcript.append(entry)

    def _unanswered(self, message: str, dated: str | None, why: str, at: str) -> None:
        """Keep the person's message (that came `at`), answered with `why`: the reply ended before
        the model was asked, so the answer is no step and has no `step` record."""
        self._transcript.append(_asked(message, dated, "", at))
        self._transcript.append({"role": "assistant", "content": why})

    async def reply(self, message: str) -> AsyncIterator[Json]:
        """Run model steps until one answers the message, yielding what happens (CONTRACTS.md: event),
        then flush the transcript, however the reply ended.

        Raises:
            OSError: an entry could not be written to the transcript's file, or the file was
                replaced under the transcript (checked before anything is appended or the model
                asked).
        """
        try:
            # closed here, not left to the event loop to finalize: a reply the person stops must
            # end its model step now, and be flushed after the entries that ending appends
            async with contextlib.aclosing(self._reply(message)) as events:
                async for event in events:
                    yield event
        finally:
            await self._flushed()

    async def _checked(self) -> None:
        """Ask the transcript whether its file is still the one it writes to, when it can be asked."""
        if isinstance(self._transcript, _Checkable):
            await self._transcript.check()

    async def _flushed(self) -> None:
        """Wait for the transcript's writes, when it writes behind the loop."""
        if isinstance(self._transcript, _Flushable):
            await self._transcript.flush()

    async def _reply(self, message: str) -> AsyncGenerator[Json]:
        """`reply`, without the flush: run model steps until one answers the message."""
        await self._checked()  # before anything is kept: a refused reply leaves no entry, asks no model
        self._answer_the_unanswered()  # first: however the reply ends, the conversation is whole
        came = self._clock.now()
        at, today = stamp(came), day_of(came)
        dated = today if _undated(self._transcript.messages, today) else None
        if not self._ready and (waiting := [n for n in self._requires if self._tools.get(n) is None]):
            yield {"type": "note", "text": _WAITING.format(_listed(waiting))}
        try:
            await self._offer()
            aside, shown_told = await self._told()
        except asyncio.CancelledError:
            # stopped while the tools or the prompt were read: the message is kept all the same,
            # answered as one stopped in its first model step is
            self._unanswered(message, dated, STOPPED, at)
            raise
        except Unstarted:  # a tool it requires never came: as a model step that failed
            self._unanswered(message, dated, FAILED, at)
            raise
        self._transcript.append(_asked(message, dated, aside, at))
        for text in shown_told:
            yield {"type": "note", "text": text}
        nudges = 0
        while True:
            tools = self._offered()
            offered = [str(spec["name"]) for spec in tools]
            settings = settings_to_record(getattr(self._model, "settings", None), self._transcript.messages)
            step = Step(self._clock, settings, self._mode())  # begins now: its request is handed over next
            chunks = self._model.complete(request_for(self._transcript.messages), tools)
            try:
                async for chunk in chunks:
                    if (seen := step.take(chunk)) is not None:
                        yield seen
            except BaseException as error:
                # stopped or failed: the step gets an answer, so the message it was answering is
                # not asked again with the next one
                stopped = isinstance(error, GeneratorExit | asyncio.CancelledError)
                self._transcript.append(step.unfinished(STOPPED if stopped else FAILED))
                raise
            finally:
                # a reply the person stops closes the model step now (its HTTP stream with it),
                # not whenever the event loop gets round to finalizing an abandoned generator
                if isinstance(chunks, AsyncGenerator):
                    await chunks.aclose()
            stop = classify(step.finish, step.text, step.calls)
            self._transcript.append(step.entry(stop))
            if stop == ACT:
                answered, running = 0, False  # running: the unanswered call reached its tool
                result: str | None = None  # the unanswered call's answer, once it has one
                asides: list[str] = []  # and what `asides` said with it
                collected: _Call | None = None  # and its record so far, from its reaching approval
                made: list[_Made] = []  # and the calls its input made, once it has ended
                try:
                    for call in step.calls:
                        name, input = str(call["name"]), call["input"]
                        asides, collected, made = [], None, []
                        tool = await self._callable(call, offered)
                        collected = _Call(self._clock)
                        if isinstance(tool, str):  # why it can't run
                            result = tool
                        elif not await collected.ask(
                            self._approval,
                            {"name": name, "input": input, "runs": tool.runs, **shown(tool, name, input)},
                        ):
                            result = DECLINED
                        else:
                            running, self._nested = True, []
                            with collected.running():
                                ran = await called(tool, name, input)
                            running = False
                            result, collected.child = ran.content, ran.child
                            done = {"name": name, "input": input, "result": result, "touched": ran.touched}
                            # off the event loop too (an on-touch section reads rule files), over
                            # the functions `asides` holds now. A stop meanwhile waits for them: each
                            # has marked what it told as told, so the answer must carry it
                            asked = asyncio.ensure_future(
                                self._executor.run(partial(asides_for, tuple(self._asides or ()), done))
                            )
                            try:
                                asides = await asyncio.shield(asked)
                            except asyncio.CancelledError:
                                asides = await asked
                                raise
                            # what the calls it made said too: each marked its aside as told
                            made, self._nested = self._nested, []
                            asides = sorted([*asides, *(each for one in made for each in one.asides)])
                        aside, shown_told = await self._told()
                        said = "\n\n".join([result, *asides, *([aside] if aside else [])])
                        self._transcript.append(
                            _answer(call, said, asides, collected.record([m.record for m in made]))
                        )
                        answered, answer, result = answered + 1, result, None
                        yield {
                            "type": "tool_result",
                            "call_id": call["id"],
                            "content": answer,
                            "is_error": False,
                        }
                        for each in asides:
                            first = each.splitlines()[0]
                            yield {"type": "note", "text": _ASIDE + first[:_SHOWN]}
                        for text in shown_told:
                            yield {"type": "note", "text": text}
                finally:
                    # Interrupted part-way: every call the transcript holds still gets an answer,
                    # or the next request would carry a call no result follows. Only the one with
                    # its tool when the stop came may have partly run; one stopped after it had
                    # its answer (while its asides were made or the prompt read) gets that answer,
                    # with its asides.
                    for n, call in enumerate(step.calls[answered:]):
                        said, kept = _NOT_RUN, []
                        # the call the stop came to keeps its record so far; any other has the time alone
                        so_far = collected if n == 0 and collected is not None else _Call(self._clock)
                        if n == 0 and result is not None:
                            said, kept = "\n\n".join([result, *asides]), asides
                        elif n == 0 and running:
                            said = _INTERRUPTED
                        nested = [one.record for one in [*made, *self._nested]] if n == 0 else []
                        self._transcript.append(_answer(call, said, kept, so_far.record(nested)))
                continue
            yield {"type": "stop", "reason": stop}
            if stop in (ANSWERED, REFUSED) or nudges >= self._max_nudges:
                return
            nudges += 1
            aside, shown_told = await self._told()
            said = f"{FEEDBACK[stop]}\n\n{aside}" if aside else FEEDBACK[stop]
            fed = {"role": "user", "content": said, "feedback": stop, "at": stamp(self._clock.now())}
            self._transcript.append(fed)
            for text in shown_told:
                yield {"type": "note", "text": text}


@dataclass(frozen=True, slots=True)
class _Made:
    """A call an input made through `tools` (`LoopModel.nested`), once it has ended: its record, and
    the asides `asides` said of it, which are told with the call the input was made from."""

    record: NestedRecord
    asides: tuple[str, ...]


class _Call:
    """One call's `call` record, collected as the call goes (`record`). It begins when the call
    reaches approval, or is refused before it. `ask` puts it to approval and keeps the answer, and the
    seconds the person took when they were asked; `running` times its tool; `child` is the
    sub-agent it started."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._at = clock.now()
        self._answer: Answer | None = None
        self._waited: float | None = None
        self._took: float | None = None
        self.child: str | None = None

    async def ask(self, approval: Approval, question: Json) -> bool:
        """Put the call to `approval`; whether it may run. Only a person asked is timed: `waited`
        runs from the question put to its answer, the time it queued behind another question
        included, since the ui shows one at a time. A call whose question the reply's stop
        withdrew (it is cancelled here) keeps no answer."""
        began = self._clock.monotonic()
        answer = await approval.approve(question)
        waited = self._clock.monotonic() - began
        self._answer = answer
        match answer:
            case Answer.UNASKED:
                may = True
            case Answer.YES:
                may, self._waited = True, waited
            case Answer.NO:
                may, self._waited = False, waited
            case _ as unreachable:
                assert_never(unreachable)
        return may

    @contextlib.contextmanager
    def running(self) -> Iterator[None]:
        """Time the tool's run, however it ends: one the stop interrupts is timed to the stop."""
        began = self._clock.monotonic()
        try:
            yield
        finally:
            self._took = self._clock.monotonic() - began

    def record(self, nested: Sequence[NestedRecord] = ()) -> CallRecord:
        """This call's `call` (`records.call_record`), with the calls its input made, `nested`."""
        return call_record(self._at, self._answer, self._waited, self._took, self.child, nested)


class Step:
    """One model step's chunks, collected: its text, its calls, why it stopped, what it was, and
    when (`record`). It begins when it is made, as the request is handed to the model: `settings`
    are the model's, to record when this step is the first of the conversation or they changed
    (`records.settings_to_record`), and `mode` how it wants its tools offered. The loop's steps
    are collected by it, and so is `/compact`'s summary step (`conversation.summarise`), so the
    one function builds both records."""

    def __init__(self, clock: Clock, settings: Settings | None, mode: str) -> None:
        self._clock = clock
        self._settings = settings
        self._mode = mode
        self._at = clock.now()
        self._began = clock.monotonic()
        self._first: float | None = None  # when the first chunk of any kind came
        self._last: float | None = None  # and the last
        self._usage: list[Json] = []
        self._text: list[str] = []
        self.calls: list[Json] = []
        self.finish: str | None = None
        self.provider: Json | None = None

    @property
    def text(self) -> str:
        return "".join(self._text)

    @property
    def usage(self) -> Sequence[Json]:
        """The `usage` chunks the step sent so far, in the order they came."""
        return self._usage

    def take(self, chunk: Json) -> Json | None:
        """Record one chunk, and when it came; return it if the person should see it."""
        self._last = self._clock.monotonic()
        if self._first is None:
            self._first = self._last
        match chunk["type"]:
            case "text":
                self._text.append(chunk["text"])
            case "tool_call":
                self.calls.append(
                    {"id": chunk["id"], "name": chunk["name"], "input": chunk["input"]}
                    | ({"error": chunk["error"]} if chunk.get("error") else {})
                )
            case "stop":
                self.finish = chunk.get("reason")
                return None  # the loop says why the reply stopped, once it has classified it
            case "message":
                self.provider = chunk.get("message")
                return None
            case "usage":
                self._usage.append(chunk)
        return chunk

    def record(self) -> StepRecord:
        """This step's `step` (`records.step_record`): when it began, how long its first chunk and
        its last took, the model that answered, its usage, and its settings if they are new."""
        return step_record(
            self._at, self._began, self._first, self._last, self._usage, self._settings, self._mode
        )

    def unfinished(self, why: str) -> Json:
        """The transcript entry for a step that never finished: what it said, then `why`, and the
        step's record (what came before it ended). No calls: none of them ran."""
        said = self.text.rstrip()
        return {"role": "assistant", "content": f"{said}\n\n{why}" if said else why, "step": self.record()}

    def entry(self, stop: str) -> Json:
        """The transcript entry for this step. Only an `act` step keeps its calls: a call that
        was cut off or would not decode never ran, so nothing may answer it. The provider's own
        message (thinking blocks and their signatures included) is replayed verbatim for an `act`
        step, and for an `answered` or `refused` one that made no call; a truncated or
        undecodable step's message is dropped, since its calls would go back with no result. Each
        carries the step's record (`record`)."""
        if stop == ACT:
            entry: dict[str, Any] = {"role": "assistant", "content": self.text, "tool_calls": self.calls}
        elif stop in (ANSWERED, REFUSED) and not self.calls:
            entry = {"role": "assistant", "content": self.text}
        else:
            return {"role": "assistant", "content": self.text, "step": self.record()}
        if self.provider is not None:
            entry["provider"] = self.provider
        return entry | {"step": self.record()}
