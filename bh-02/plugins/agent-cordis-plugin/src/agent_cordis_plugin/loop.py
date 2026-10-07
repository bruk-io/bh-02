"""The loop: a turn is one model step plus the inputs it asked for, until it asks for none.

A plain function of the values it declares its own contracts for (CONTRACTS.md: model,
kernel, transcript, system, approval, memory). The model has one tool, the kernel's `python(code)`,
offered through the provider's standard tool calling; every call runs as an input in the kernel.
Each input is put to `approval` first and runs only on its yes (at once when the jail confines
the kernel; otherwise the person's answer): one place for every model provider, and the loop
knows whether a stopped call ever reached the kernel.

Every request begins with the system prompt the conversation began with, kept in its transcript,
so a model server's cache of the conversation stays good. When the prompt reads differently (an
extension loaded, the branch switched, CLAUDE.md edited), the new reading is kept after it and
the model is told what changed (`prompt.changes`) on the next message it reads. The date is not
in the prompt: the loop tells it with the person's message, the first of a conversation and the
first of each new day (`(Today's date: ...)`), so the prompt reads the same from one day to the
next.

After each input it runs, the loop asks `memory`, the functions rows have added there, what to
tell the model with that input's result (`remembered`): each is given the input's code, its
result and the project files it opened (`kernel.touched()`), and may add a note, never change
the result. A path-scoped rule arrives that way when the model first works on a file it covers.

Reading the prompt (every section function, which may read many files and search the project)
and asking `memory` (which may read rule files) both run in a worker thread
(`asyncio.to_thread`), never on the event loop, which the TUI shares: a slow section freezes
nothing. The loop awaits each, so one runs at a time.
"""

import asyncio
import datetime
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.prompt import changes
from agent_cordis_plugin.stops import ACT, ANSWERED, FEEDBACK, REFUSED, classify

__all__ = [
    "DECLINED",
    "FAILED",
    "STOPPED",
    "Approval",
    "Model",
    "LoopModel",
    "Memory",
    "Python",
    "System",
    "Transcript",
    "refusal",
    "remembered",
    "request_for",
]

type Json = Mapping[str, Any]


@runtime_checkable
class Model(Protocol):
    """One turn of a model over a transcript, with tools it may ask for but never runs."""

    def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]: ...


@runtime_checkable
class Python(Protocol):
    """What the loop needs of the `kernel` value: the one tool's spec, what to tell the model
    about it (`instructions()`, called in a worker thread with the prompt), and an input run as
    the model reads it."""

    @property
    def spec(self) -> Json: ...
    def instructions(self) -> str: ...
    async def run(self, code: str) -> str: ...
    def touched(self) -> tuple[str, ...]: ...


type Remember = Callable[[Json], str]


@runtime_checkable
class Memory(Protocol):
    """What the loop needs of the `memory` value: the functions that may add a note to an
    input's result, each called as `fn({"code", "result", "touched"}) -> str`, in a worker
    thread, one input's at a time."""

    def __iter__(self) -> Iterator[Remember]: ...


@runtime_checkable
class Approval(Protocol):
    """What the loop needs of the `approval` value: whether an input may run (the person's
    answer when the jail does not confine it)."""

    async def approve(self, request: Json) -> bool: ...


@runtime_checkable
class System(Protocol):
    """What the loop needs of the `system` value: what to tell the model about where it is,
    read in a worker thread (it may read many files), one reading at a time."""

    def text(self) -> str: ...


@runtime_checkable
class Transcript(Protocol):
    """The conversation's history: appended by the loop, read whole for each request."""

    @property
    def messages(self) -> Sequence[Json]: ...
    def append(self, message: Json) -> None: ...


_INTERRUPTED = "interrupted: the person stopped this call before it finished; it may have partly run"
# A call the stop came before: at the person's approval, or queued behind the one stopped.
_NOT_RUN = "not run: the person stopped the turn before this call started, so none of it ran"
# What an input the person said no to answers the model with.
DECLINED = "denied: the person said no to this input, so it did not run; ask them what they want instead"
# What a turn that never finished ends with in the transcript, after what it said so far: the
# person stopped it, or the model failed (a 429, a dropped connection).
STOPPED = "[the person stopped this reply here]"
FAILED = "[this reply failed here; the person saw the error]"
# What the person is shown when the model is told its instructions changed.
_TOLD = "told the model its instructions changed since the conversation began"
_REMEMBERED = "told the model with this result: "  # then a memory note's first line
_SHOWN = 120  # how much of that line the person is shown
# What the model is told of the date, before the person's message: the first of a conversation,
# and the first of each new day.
_DATED = "(Today's date: {}.)"


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


def remembered(memory: Iterable[Remember], input: Json) -> list[str]:
    """What `memory`'s functions say about one input (`code`, `result`, `touched`), sorted, so
    the order rows added them in means nothing. A function that fails or returns something
    other than text says so in one line, and the rest still say theirs."""
    notes: list[str] = []
    for fn in memory:
        try:
            said = fn(input)
            if not isinstance(said, str):
                raise TypeError(f"it returned a {type(said).__name__}, not text")
        except Exception as error:  # one row's function failing must not cost the input its result
            named = getattr(fn, "__qualname__", type(fn).__qualname__)
            said = (
                f"(bh-02 could not make a note with {getattr(fn, '__module__', '?')}:{named}: {error}. "
                "The input's result is whole; tell the person this function in `memory` failed.)"
            )
        if said.strip():
            notes.append(said.strip())
    return sorted(notes)


def request_for(messages: Sequence[Json]) -> list[Json]:
    """The messages for one request over a transcript's `messages`: the prompt the conversation
    began with (its first `system` entry), then the conversation. The prompts kept after the
    first were told as notes, so they stay out."""
    first = next((m for m in messages if m.get("role") == "system"), None)
    head: list[Json] = [{"role": "system", "content": first["content"]}] if first else []
    return [*head, *(m for m in messages if m.get("role") != "system")]


def refusal(call: Json, spec: Json) -> str | None:
    """Why a call can't run as an input (a name other than the one tool's, or no `code` string),
    as text the model reads instead of a result; None when it can run."""
    name = str(spec["name"])
    if call["name"] != name:
        return f"error: there is no tool named {call['name']!r}; your one tool is {name}(code)"
    if not isinstance(call["input"].get("code"), str):
        return f"error: {name} takes `code`, the Python to run, as a string"
    return None


class LoopModel:
    """The `loop` value: the transcript is the history, the model is one step at a time.

    Each turn is classified (`stops.classify`): only `act` runs calls, and only `answered` (or
    `refused`: the provider declined, which asking again won't change) ends the reply. A
    truncated, silent or undecodable turn is fed back to the model up to `max_nudges` times
    in one reply, then shown as the reason the reply stopped. The
    provider's assistant message rides on its transcript entry as `provider`, for the
    model to replay as it was received. An `act` turn's calls run one at a time, each only on
    `approval.approve({"name", "input"})`'s yes; a no is that call's answer, `DECLINED`.

    A reply the person stops (the reply closed, or its task cancelled) while a turn streams
    still leaves the transcript whole: what the turn said so far, then `STOPPED`, as the
    assistant's answer; a model step that fails (it raises: rate limited, cut off) the same,
    with `FAILED`. Otherwise the next request would carry that message unanswered, and the
    model would answer it too, doing the stopped work again before the next one.

    The system prompt (`system.text()`, then the kernel's instructions) is read before each
    message the model reads, in a worker thread, but sent as the conversation began with it: a
    `system` entry in the transcript, the first one. A later reading that differs is kept as
    another `system` entry and told on that message (`prompt.changes`), so the conversation's
    start never changes under a model server's cache. The date is told on the person's message
    instead, when the transcript has told none yet or another day's (`today`, the clock; a test
    gives its own): first on that message, then any change to the instructions, then the message.
    """

    def __init__(
        self,
        model: Model,
        kernel: Python,
        transcript: Transcript,
        approval: Approval,
        max_nudges: int = 2,
        system: System | None = None,
        memory: Memory | None = None,
        today: Callable[[], str] = _today,
    ) -> None:
        self._model = model
        self._kernel = kernel
        self._transcript = transcript
        self._approval = approval
        self._max_nudges = max_nudges
        self._system = system
        self._memory = memory
        self._today = today

    def _prompt(self) -> str:
        """The system prompt as it reads now. Run in a worker thread (`_told`)."""
        parts = [self._system.text() if self._system else "", self._kernel.instructions()]
        return "\n\n".join(part for part in parts if part.strip())

    async def _told(self) -> str:
        """Bring what the transcript says the model was told up to date, before a message it is
        about to read: the first prompt is kept as the conversation's start, a later one that
        reads differently after it, and what changed is returned to go with that message ('' when
        nothing did).

        The prompt is read in a worker thread, off the event loop the TUI shares, and the
        transcript is touched only once it has been, so a reply stopped meanwhile changes nothing.
        The loop awaits each reading, so one runs at a time and the context plugin's caches are
        never used by two threads at once; the exception is a reading a stopped reply left
        running, which finishes in its thread unused while the next may begin."""
        now = await asyncio.to_thread(self._prompt)
        kept = [m for m in self._transcript.messages if m.get("role") == "system"]
        last = str(kept[-1].get("content") or "") if kept else None
        if now == (last or ""):
            return ""
        self._transcript.append({"role": "system", "content": now})
        return changes(last, now) if last is not None else ""

    async def reply(self, message: str) -> AsyncIterator[Json]:
        """Run turns until one is answered, yielding what happens (CONTRACTS.md: event)."""
        today = self._today()
        dated = today if _undated(self._transcript.messages, today) else None
        try:
            note = await self._told()
        except asyncio.CancelledError:
            # stopped while the prompt was read: the message is kept all the same, answered as
            # one stopped in its first model step is
            self._transcript.append(_asked(message, dated, ""))
            self._transcript.append({"role": "assistant", "content": STOPPED})
            raise
        self._transcript.append(_asked(message, dated, note))
        if note:
            yield {"type": "note", "text": _TOLD}
        nudges = 0
        while True:
            turn = _Turn()
            chunks = self._model.complete(request_for(self._transcript.messages), [self._kernel.spec])
            try:
                async for chunk in chunks:
                    if (shown := turn.take(chunk)) is not None:
                        yield shown
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
                answered, running = 0, False  # running: the unanswered call reached the kernel
                result: str | None = None  # the unanswered call's answer, once it has one
                notes: list[str] = []  # and what `memory` said with it
                try:
                    for call in turn.calls:
                        result = refusal(call, self._kernel.spec)
                        request = {"name": call["name"], "input": call["input"]}
                        if result is None and not await self._approval.approve(request):
                            result = DECLINED
                        notes = []
                        if result is None:
                            running = True
                            code = call["input"]["code"]
                            result = await self._kernel.run(code)
                            running = False
                            ran = {"code": code, "result": result, "touched": self._kernel.touched()}
                            # in a worker thread too (an on-touch section reads rule files), over
                            # the functions `memory` holds now. A stop meanwhile waits for them: each
                            # has marked what it told as told, so the answer must carry it
                            asked = asyncio.ensure_future(
                                asyncio.to_thread(remembered, tuple(self._memory or ()), ran)
                            )
                            try:
                                notes = await asyncio.shield(asked)
                            except asyncio.CancelledError:
                                notes = await asked
                                raise
                        note = await self._told()
                        told = "\n\n".join([result, *notes, *([note] if note else [])])
                        self._transcript.append({"role": "tool", "content": told, "call_id": call["id"]})
                        answered, answer, result = answered + 1, result, None
                        yield {
                            "type": "tool_result",
                            "call_id": call["id"],
                            "content": answer,
                            "is_error": False,
                        }
                        for said in notes:
                            first = said.splitlines()[0]
                            yield {"type": "note", "text": _REMEMBERED + first[:_SHOWN]}
                        if note:
                            yield {"type": "note", "text": _TOLD}
                finally:
                    # Interrupted part-way: every call the transcript holds still gets an answer,
                    # or the next request would carry a call no result follows. Only the one in
                    # the kernel when the stop came may have partly run; one stopped after it had
                    # its answer (while its notes were made or the prompt read) gets that answer,
                    # with its notes.
                    for n, call in enumerate(turn.calls[answered:]):
                        said = _NOT_RUN
                        if n == 0 and result is not None:
                            said = "\n\n".join([result, *notes])
                        elif n == 0 and running:
                            said = _INTERRUPTED
                        self._transcript.append({"role": "tool", "content": said, "call_id": call["id"]})
                continue
            yield {"type": "stop", "reason": stop}
            if stop in (ANSWERED, REFUSED) or nudges >= self._max_nudges:
                return
            nudges += 1
            note = await self._told()
            said = f"{FEEDBACK[stop]}\n\n{note}" if note else FEEDBACK[stop]
            self._transcript.append({"role": "user", "content": said, "feedback": stop})
            if note:
                yield {"type": "note", "text": _TOLD}


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
