"""The loop: a turn is one model step plus the calls it asked for, until it asks for none.

A plain function of the values it declares its own contracts for (CONTRACTS.md: model,
tools, transcript, system, approval, notes, executor). The model is offered the tools rows
register (`tools`, a broker), through the provider's standard tool calling, and each call runs
through the tool its name has; CodeAct's `python` is one of them, the python row's. The list is
read at a conversation's first request, after the tools the loop's config `requires` have
registered, and kept in its transcript; a later change (a tool added, removed or redefined) is
kept there too and told to the model on the next message it reads (`toolset`), while each
request offers the list as the provider chooses (`tool_changes`: by default the one the
conversation began with, so a model server's cache of the conversation's start stays good).
Each call is put to `approval` first and runs only on its yes (at once when it runs in a jail
that confines it; otherwise the person's answer): one place for every model provider, and the
loop knows whether a stopped call ever reached its tool.

Every request begins with the system prompt the conversation began with, kept in its transcript,
so a model server's cache of the conversation stays good. When the prompt reads differently (an
extension loaded, the branch switched, CLAUDE.md edited), the new reading is kept after it, as
the edits from the one before (`prompt.edits`), not another whole copy, and the model is told
what changed (`prompt.changes`) on the next message it reads. The date is not in the prompt:
the loop tells it with the person's message, the first of a conversation and the first of each
new day (`(Today's date: ...)`), so the prompt reads the same from one day to the next.

After each call it runs, the loop asks `notes`, the functions rows have added there, what to
tell the model with that call's result (`noted`): each is given the tool's name, the call's
input, its result and the files it opened (what the tool answered with), and may add a note,
never change the result. A path-scoped rule arrives that way when the model first works on a
file it covers.
The model reads the notes after the result; the `tool` entry also keeps them as a list
(`notes`), so a row reading a resumed transcript for what it told finds each note whole, not
somewhere in a text the result and the other notes share.

Reading the prompt (every section function, which may read many files and search the project)
and asking `notes` (which may read rule files) both run on `executor` (`executor.OneAtATime`),
never on the event loop, which the TUI shares: a slow section freezes nothing. One runs at a
time, a reading a stopped reply left running included: the next waits for it rather than
starting beside it. `executor` is a row of its own that depends on nothing, so a loop reloaded
by `/clear` or `/model` waits for the call the last loop left running too: stopping reply after
reply leaves at most one in flight, however often the loop reloads between them.
"""

import asyncio
import datetime
import json
import time
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
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.executor import OneAtATime
from agent_cordis_plugin.prompt import changes, edits, latest
from agent_cordis_plugin.stops import ACT, ANSWERED, FEEDBACK, REFUSED, classify
from agent_cordis_plugin.toolset import FIXED, LISTED, begun, changed, listed, removed, told

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
    "Notes",
    "Rule",
    "System",
    "Tool",
    "Tools",
    "Transcript",
    "Unstarted",
    "called",
    "malformed",
    "noted",
    "refusal",
    "request_for",
    "shown",
]

type Json = Mapping[str, Any]


@runtime_checkable
class Model(Protocol):
    """One turn of a model over a transcript, with tools it may ask for but never runs."""

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


type Note = Callable[[Json], str]


@runtime_checkable
class Notes(Protocol):
    """What the loop needs of the `notes` value: the functions that may add a note to a call's
    result, each called as `fn({"name", "input", "result", "touched"}) -> str`, on `executor`:
    one call's at a time, and never beside a reading of the prompt."""

    def __iter__(self) -> Iterator[Note]: ...


@runtime_checkable
class Approval(Protocol):
    """What the loop asks of each call: whether it may run (`Asked`: unasked by the `approval`
    rule, else the person's answer)."""

    async def approve(self, request: Json) -> bool: ...


@runtime_checkable
class Rule(Protocol):
    """What the loop needs of the `approval` value (CONTRACTS.md: approval): whether a call runs
    without asking the person (it runs in a runner that confines it)."""

    def unasked(self, request: Json) -> bool: ...


@runtime_checkable
class Confirm(Protocol):
    """What the loop needs of the `output` value: the person's yes or no about a call."""

    async def confirm(self, request: Json) -> bool: ...


@dataclass(frozen=True, slots=True)
class Asked:
    """Whether a call may run: at once when the `approval` rule says it runs unasked, else the
    person's answer through `output.confirm`. The rule is the runner plugin's, in one place; the
    asking is the asker's."""

    rule: Rule
    output: Confirm

    async def approve(self, request: Json) -> bool:
        return self.rule.unasked(request) or await self.output.confirm(request)


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
    """The conversation's history: appended by the loop, read whole for each request."""

    @property
    def messages(self) -> Sequence[Json]: ...
    def append(self, message: Json) -> None: ...


_INTERRUPTED = "interrupted: the person stopped this call before it finished; it may have partly run"
# A call the stop came before: at the person's approval, or queued behind the one stopped.
_NOT_RUN = "not run: the person stopped the turn before this call started, so none of it ran"
# What a call the person said no to answers the model with.
DECLINED = "denied: the person said no to this call, so it did not run; ask them what they want instead"
# What a turn that never finished ends with in the transcript, after what it said so far: the
# person stopped it, or the model failed (a 429, a dropped connection).
STOPPED = "[the person stopped this reply here]"
FAILED = "[this reply failed here; the person saw the error]"
# What the person is shown when the model is told its instructions, or its tools, changed.
_TOLD = "told the model its instructions changed since the conversation began"
_TOOLS_TOLD = "told the model its tools changed since the conversation began"
_NOTED = "told the model with this result: "  # then the first line of a note
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


def _today() -> str:
    """Today's date as the loop tells it (`2026-10-07`): `LoopModel`'s clock unless a test gives one."""
    return datetime.date.today().isoformat()


def _undated(messages: Sequence[Json], today: str) -> bool:
    """Whether the model is yet to be told `today`: the transcript has told it no date (a new
    conversation, or one begun before the loop told dates), or the last one it told (a user
    entry's `today`) is another day's (a conversation run past midnight, or resumed later)."""
    told = next((str(m["today"]) for m in reversed(messages) if m.get("today")), None)
    return told != today


def _asked(message: str, today: str | None, note: str) -> dict[str, Any]:
    """The person's message as the transcript keeps it: the date first when it is told
    (`today`), then what changed in the model's instructions (`note`), then the message. The date
    rides on the entry as `today` too, which is how a later message finds the last one told."""
    told = [*([_DATED.format(today)] if today else []), *([note] if note else []), message]
    return {"role": "user", "content": "\n\n".join(told)} | ({"today": today} if today else {})


def _answer(call: Json, content: str, notes: Sequence[str]) -> dict[str, Any]:
    """The transcript entry answering `call`: `content`, what the model reads (the input's result,
    then its notes and any change in the instructions, each after a blank line), and the `notes`
    alone (`notes`, `[]` for none), so what was told is read back without searching the text.
    The loop's own, as `today` is: a provider sends `content`."""
    return {"role": "tool", "content": content, "call_id": call["id"], "notes": list(notes)}


def noted(functions: Iterable[Note], input: Json) -> list[str]:
    """What the functions in `notes` say about one call (`name`, `input`, `result`, `touched`),
    sorted, so the order rows added them in means nothing. A function that fails or returns something
    other than text says so in one line, and the rest still say theirs."""
    notes: list[str] = []
    for fn in functions:
        try:
            said = fn(input)
            if not isinstance(said, str):
                raise TypeError(f"it returned a {type(said).__name__}, not text")
        except Exception as error:  # one row's function failing must not cost the input its result
            named = getattr(fn, "__qualname__", type(fn).__qualname__)
            said = (
                f"(bh-02 could not make a note with {getattr(fn, '__module__', '?')}:{named}: {error}. "
                "The call's result is whole; tell the person this function in `notes` failed.)"
            )
        if said.strip():
            notes.append(said.strip())
    return sorted(notes)


def request_for(messages: Sequence[Json]) -> list[Json]:
    """The messages for one request over a transcript's `messages`: the prompt the conversation
    began with (its first `system` entry), then the conversation. The prompts kept after the
    first were told as notes, so they stay out: a model is sent one `system` message, whole, and
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


def shown(tool: Tool, name: str, input: Json) -> dict[str, Any]:
    """How a call is put to the person (`approval`): the tool's own `show(input)` (`title`,
    `lines`, `language`), else the loop's way, the tool's name and its input as JSON. A `show`
    that fails, or answers with something other than a mapping, leaves the loop's way."""
    title = {"title": f"Call {name} with this input?"}
    try:
        own = tool.show(input) if tool.show is not None else None
    except Exception:  # a tool's own way of showing a call failing must not cost the person the question
        own = None
    if isinstance(own, Mapping):
        return title | dict(own)
    lines = json.dumps(input, indent=2, ensure_ascii=False, default=str).splitlines()
    return title | {"lines": lines, "language": "json"}


async def called(tool: Tool, name: str, input: Json) -> tuple[str, tuple[str, ...], bool]:
    """One call run through `tool`: what the model reads, the files it opened, and whether the
    tool failed. A tool that fails, or answers with something other than `{"content": str,
    ...}`, answers with an error the model reads, so one tool's fault is never the reply's."""
    try:
        ran = await tool.run(input)
    except Exception as error:
        return f"error: the {name} tool failed ({type(error).__name__}: {error}); tell the person", (), True
    content = ran.get("content") if isinstance(ran, Mapping) else None
    if not isinstance(content, str):
        return (
            f"error: the {name} tool answered with something other than its result as text; tell the person",
            (),
            True,
        )
    touched = ran.get("touched") or ()
    return content, tuple(str(path) for path in touched) if isinstance(touched, list | tuple) else (), False


class LoopModel:
    """The `loop` value: the transcript is the history, the model is one step at a time.

    Each turn is classified (`stops.classify`): only `act` runs calls, and only `answered` (or
    `refused`: the provider declined, which asking again won't change) ends the reply. A
    truncated, silent or undecodable turn is fed back to the model up to `max_nudges` times
    in one reply, then shown as the reason the reply stopped. The
    provider's assistant message rides on its transcript entry as `provider`, for the
    model to replay as it was received. An `act` turn's calls run one at a time, each only on
    `approval.approve({"name", "input", "runs", "title", "lines", ...})`'s yes (`shown`); a no
    is that call's answer, `DECLINED`.

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

    A reply the person stops (the reply closed, or its task cancelled) while a turn streams
    still leaves the transcript whole: what the turn said so far, then `STOPPED`, as the
    assistant's answer; a model step that fails (it raises: rate limited, cut off) the same,
    with `FAILED`. Otherwise the next request would carry that message unanswered, and the
    model would answer it too, doing the stopped work again before the next one.

    The system prompt (`system.text()`, the sections rows add, the python tool's among them) is
    read before each message the model reads, on `executor`, but sent as the conversation began
    with it: a `system` entry in the transcript, the first one, kept whole. A later reading that
    differs from the last told is kept as another `system` entry, the edits from that one
    (`prompt.edits`), and told on that message (`prompt.changes`), so the conversation's start
    never changes under a model server's cache and the transcript holds the prompt once, not
    once per change. The date is told on the person's message instead, when the transcript has
    told none yet or another day's (`today`, the clock; a test gives its own): first on that
    message, then any change to the instructions, then the message.

    The prompt is read, and `notes` asked, on `executor` (the `executor` row's, which a reloaded
    loop shares with the last one); a loop built without one (a test, direct use) makes its own.
    """

    def __init__(
        self,
        model: Model,
        tools: Tools,
        transcript: Transcript,
        approval: Approval,
        max_nudges: int = 2,
        system: System | None = None,
        notes: Notes | None = None,
        today: Callable[[], str] = _today,
        executor: Executor | None = None,
        *,
        requires: Sequence[str] = (),
        wait: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._model = model
        self._tools = tools
        self._transcript = transcript
        self._approval = approval
        self._max_nudges = max_nudges
        self._system = system
        self._notes = notes
        self._today = today
        self._requires = tuple(requires)
        self._wait = wait
        # what the model was last told (`prompt.latest`), and of how many `system` entries: the
        # transcript keeps a change as edits, so this saves applying them all for every message
        self._last: tuple[int, str | None] = (0, None)
        self._executor: Executor = executor if executor is not None else OneAtATime()
        self._clock = clock
        self._ready = False  # whether the tools `requires` names have registered, once
        self._missing: dict[str, float] = {}  # a tool the conversation has, missing since when
        self._nested: list[str] = []  # what `notes` said of the calls the running call made (`nested`)

    def _prompt(self) -> str:
        """The system prompt as it reads now. Run on `executor` (`_told`)."""
        return self._system.text() if self._system else ""

    async def _told(self) -> tuple[str, list[str]]:
        """What the model is told with the next message it reads, and what the person is shown
        of it: what changed in its instructions (`_prompt_told`), then in its tools
        (`_tools_told`); ('', []) when nothing did."""
        prompt = await self._prompt_told()
        tools = self._tools_told()
        shown = [*([_TOLD] if prompt else []), *([_TOOLS_TOLD] if tools else [])]
        return "\n\n".join(part for part in (prompt, tools) if part), shown

    def _mode(self) -> str:
        """How the model wants its tools offered (CONTRACTS.md: model, `tool_changes`)."""
        mode = getattr(self._model, "tool_changes", FIXED)
        return mode if mode in (FIXED, LISTED) else FIXED

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
        at = self._clock()
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
        once `approval` says yes, then asked of `notes`, whose notes are told with the call it
        was made from. Answers `{"content", "failed"}`: what the caller reads, and whether that
        is why it did not run or failed rather than its result."""
        tool = self._tools.get(name)
        if tool is None:
            return {"content": f"error: there is no {name} tool now", "failed": True}
        if (why := malformed(tool.spec, input)) is not None:
            return {"content": why, "failed": True}
        if not await self._approval.approve(
            {"name": name, "input": input, "runs": tool.runs, **shown(tool, name, input)}
        ):
            return {"content": DECLINED, "failed": True}
        result, touched, failed = await called(tool, name, input)
        ran = {"name": name, "input": input, "result": result, "touched": touched}
        self._nested += await self._executor.run(partial(noted, tuple(self._notes or ()), ran))
        return {"content": result, "failed": failed}

    def _unanswered(self, message: str, dated: str | None, why: str) -> None:
        """Keep the person's message, answered with `why`: the reply ended before the model was asked."""
        self._transcript.append(_asked(message, dated, ""))
        self._transcript.append({"role": "assistant", "content": why})

    async def reply(self, message: str) -> AsyncIterator[Json]:
        """Run turns until one is answered, yielding what happens (CONTRACTS.md: event)."""
        today = self._today()
        dated = today if _undated(self._transcript.messages, today) else None
        if not self._ready and (waiting := [n for n in self._requires if self._tools.get(n) is None]):
            yield {"type": "note", "text": _WAITING.format(_listed(waiting))}
        try:
            await self._offer()
            note, shown_told = await self._told()
        except asyncio.CancelledError:
            # stopped while the tools or the prompt were read: the message is kept all the same,
            # answered as one stopped in its first model step is
            self._unanswered(message, dated, STOPPED)
            raise
        except Unstarted:  # a tool it requires never came: as a model step that failed
            self._unanswered(message, dated, FAILED)
            raise
        self._transcript.append(_asked(message, dated, note))
        for text in shown_told:
            yield {"type": "note", "text": text}
        nudges = 0
        while True:
            turn = _Turn()
            tools = self._offered()
            offered = [str(spec["name"]) for spec in tools]
            chunks = self._model.complete(request_for(self._transcript.messages), tools)
            try:
                async for chunk in chunks:
                    if (seen := turn.take(chunk)) is not None:
                        yield seen
            except BaseException as error:
                # stopped or failed: the turn gets an answer, so the message it was answering is
                # not asked again with the next one
                stopped = isinstance(error, GeneratorExit | asyncio.CancelledError)
                self._transcript.append(turn.unfinished(STOPPED if stopped else FAILED))
                raise
            finally:
                # a reply the person stops closes the model step now (its HTTP stream with it),
                # not whenever the event loop gets round to finalizing an abandoned generator
                if isinstance(chunks, AsyncGenerator):
                    await chunks.aclose()
            stop = classify(turn.finish, turn.text, turn.calls)
            self._transcript.append(turn.entry(stop))
            if stop == ACT:
                answered, running = 0, False  # running: the unanswered call reached its tool
                result: str | None = None  # the unanswered call's answer, once it has one
                notes: list[str] = []  # and what `notes` said with it
                try:
                    for call in turn.calls:
                        name, input = str(call["name"]), call["input"]
                        notes = []
                        tool = await self._callable(call, offered)
                        if isinstance(tool, str):  # why it can't run
                            result = tool
                        elif not await self._approval.approve(
                            {"name": name, "input": input, "runs": tool.runs, **shown(tool, name, input)}
                        ):
                            result = DECLINED
                        else:
                            running, self._nested = True, []
                            result, touched, _ = await called(tool, name, input)
                            running = False
                            ran = {"name": name, "input": input, "result": result, "touched": touched}
                            # off the event loop too (an on-touch section reads rule files), over
                            # the functions `notes` holds now. A stop meanwhile waits for them: each
                            # has marked what it told as told, so the answer must carry it
                            asked = asyncio.ensure_future(
                                self._executor.run(partial(noted, tuple(self._notes or ()), ran))
                            )
                            try:
                                notes = await asyncio.shield(asked)
                            except asyncio.CancelledError:
                                notes = await asked
                                raise
                            # what the calls it made said too: each marked its note as told
                            notes, self._nested = sorted([*notes, *self._nested]), []
                        note, shown_told = await self._told()
                        said = "\n\n".join([result, *notes, *([note] if note else [])])
                        self._transcript.append(_answer(call, said, notes))
                        answered, answer, result = answered + 1, result, None
                        yield {
                            "type": "tool_result",
                            "call_id": call["id"],
                            "content": answer,
                            "is_error": False,
                        }
                        for each in notes:
                            first = each.splitlines()[0]
                            yield {"type": "note", "text": _NOTED + first[:_SHOWN]}
                        for text in shown_told:
                            yield {"type": "note", "text": text}
                finally:
                    # Interrupted part-way: every call the transcript holds still gets an answer,
                    # or the next request would carry a call no result follows. Only the one with
                    # its tool when the stop came may have partly run; one stopped after it had
                    # its answer (while its notes were made or the prompt read) gets that answer,
                    # with its notes.
                    for n, call in enumerate(turn.calls[answered:]):
                        said, kept = _NOT_RUN, []
                        if n == 0 and result is not None:
                            said, kept = "\n\n".join([result, *notes]), notes
                        elif n == 0 and running:
                            said = _INTERRUPTED
                        self._transcript.append(_answer(call, said, kept))
                continue
            yield {"type": "stop", "reason": stop}
            if stop in (ANSWERED, REFUSED) or nudges >= self._max_nudges:
                return
            nudges += 1
            note, shown_told = await self._told()
            said = f"{FEEDBACK[stop]}\n\n{note}" if note else FEEDBACK[stop]
            self._transcript.append({"role": "user", "content": said, "feedback": stop})
            for text in shown_told:
                yield {"type": "note", "text": text}


class _Turn:
    """One model step's chunks, collected: its text, its calls, why it stopped, what it was."""

    def __init__(self) -> None:
        self._text: list[str] = []
        self.calls: list[Json] = []
        self.finish: str | None = None
        self.provider: Json | None = None

    @property
    def text(self) -> str:
        return "".join(self._text)

    def take(self, chunk: Json) -> Json | None:
        """Record one chunk; return it if the person should see it."""
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
        return chunk

    def unfinished(self, why: str) -> Json:
        """The transcript entry for a turn that never finished: what it said, then `why`. No
        calls: none of them ran."""
        said = self.text.rstrip()
        return {"role": "assistant", "content": f"{said}\n\n{why}" if said else why}

    def entry(self, stop: str) -> Json:
        """The transcript entry for this turn. Only an `act` turn keeps its calls: a call that
        was cut off or would not decode never ran, so nothing may answer it. The provider's own
        message (thinking blocks and their signatures included) is replayed verbatim for an `act`
        turn, and for an `answered` or `refused` one that made no call; a truncated or
        undecodable turn's message is dropped, since its calls would go back with no result."""
        if stop == ACT:
            entry: dict[str, Any] = {"role": "assistant", "content": self.text, "tool_calls": self.calls}
        elif stop in (ANSWERED, REFUSED) and not self.calls:
            entry = {"role": "assistant", "content": self.text}
        else:
            return {"role": "assistant", "content": self.text}
        if self.provider is not None:
            entry["provider"] = self.provider
        return entry
