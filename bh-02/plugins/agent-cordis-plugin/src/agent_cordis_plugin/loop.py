"""The loop: a turn is one model step plus the inputs it asked for, until it asks for none.

A plain function of the values it declares its own contracts for (CONTRACTS.md: model,
kernel, transcript, system, output). The model has one tool, the kernel's `python(code)`,
offered through the provider's standard tool calling; every call runs as an input in the kernel.
A kernel that is not `confined` runs with the person's own permissions, so the loop puts each
of its inputs to the person first (`output.confirm`) and runs it only on a yes: one place for
every model provider, and the loop knows whether a stopped call ever reached the kernel.

Every request begins with the system prompt the conversation began with, kept in its transcript,
so a model server's cache of the conversation stays good. When the prompt reads differently (an
extension loaded, the branch switched, CLAUDE.md edited), the new reading is kept after it and
the model is told what changed (`prompt.changes`) on the next message it reads.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.prompt import changes
from agent_cordis_plugin.stops import ACT, ANSWERED, FEEDBACK, REFUSED, classify

__all__ = [
    "DECLINED",
    "FAILED",
    "STOPPED",
    "Asks",
    "Model",
    "LoopModel",
    "Python",
    "System",
    "Transcript",
    "refusal",
]

type Json = Mapping[str, Any]


@runtime_checkable
class Model(Protocol):
    """One turn of a model over a transcript, with tools it may ask for but never runs."""

    def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]: ...


@runtime_checkable
class Python(Protocol):
    """What the loop needs of the `kernel` value: the one tool's spec, what to tell the model
    about it, whether its inputs are confined, and an input run as the model reads it."""

    @property
    def spec(self) -> Json: ...
    @property
    def confined(self) -> bool: ...
    def instructions(self) -> str: ...
    async def run(self, code: str) -> str: ...


@runtime_checkable
class Asks(Protocol):
    """What the loop needs of the `output` value: a yes-or-no question about an input."""

    async def confirm(self, request: Json) -> bool: ...


@runtime_checkable
class System(Protocol):
    """What the loop needs of the `system` value: what to tell the model about where it is."""

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
    model to replay as it was received.

    A reply the person stops (the reply closed, or its task cancelled) while a turn streams
    still leaves the transcript whole: what the turn said so far, then `STOPPED`, as the
    assistant's answer; a model step that fails (it raises: rate limited, cut off) the same,
    with `FAILED`. Otherwise the next request would carry that message unanswered, and the
    model would answer it too, doing the stopped work again before the next one.

    The system prompt (`system.text()`, then the kernel's instructions) is read before each
    message the model reads, but sent as the conversation began with it: a `system` entry in the
    transcript, the first one. A later reading that differs is kept as another `system` entry
    and told on that message (`prompt.changes`), so the conversation's start never changes
    under a model server's cache.
    """

    def __init__(
        self,
        model: Model,
        kernel: Python,
        transcript: Transcript,
        max_nudges: int = 2,
        system: System | None = None,
        output: Asks | None = None,
    ) -> None:
        self._model = model
        self._kernel = kernel
        self._transcript = transcript
        self._max_nudges = max_nudges
        self._system = system
        self._output = output  # none: nobody to ask, so an unconfined input is declined

    async def _approved(self, call: Json) -> bool:
        """Whether an input may run: a confined one always; an unconfined one on the person's yes."""
        if self._kernel.confined:
            return True
        return self._output is not None and await self._output.confirm(
            {"name": call["name"], "input": call["input"]}
        )

    def _prompt(self) -> str:
        """The system prompt as it reads now."""
        parts = [self._system.text() if self._system else "", self._kernel.instructions()]
        return "\n\n".join(part for part in parts if part.strip())

    def _told(self) -> str:
        """Bring what the transcript says the model was told up to date, before a message it is
        about to read: the first prompt is kept as the conversation's start, a later one that
        reads differently after it, and what changed is returned to go with that message ('' when
        nothing did)."""
        now = self._prompt()
        kept = [m for m in self._transcript.messages if m.get("role") == "system"]
        last = str(kept[-1].get("content") or "") if kept else None
        if now == (last or ""):
            return ""
        self._transcript.append({"role": "system", "content": now})
        return changes(last, now) if last is not None else ""

    def _request(self) -> list[Json]:
        """The messages for one request: the prompt the conversation began with, then the
        conversation. The prompts kept after the first were told as notes, so they stay out."""
        messages = self._transcript.messages
        first = next((m for m in messages if m.get("role") == "system"), None)
        head: list[Json] = [{"role": "system", "content": first["content"]}] if first else []
        return [*head, *(m for m in messages if m.get("role") != "system")]

    async def reply(self, message: str) -> AsyncIterator[Json]:
        """Run turns until one is answered, yielding what happens (CONTRACTS.md: event)."""
        note = self._told()
        self._transcript.append({"role": "user", "content": f"{note}\n\n{message}" if note else message})
        if note:
            yield {"type": "note", "text": _TOLD}
        nudges = 0
        while True:
            turn = _Turn()
            chunks = self._model.complete(self._request(), [self._kernel.spec])
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
                try:
                    for call in turn.calls:
                        result = refusal(call, self._kernel.spec)
                        if result is None and not await self._approved(call):
                            result = DECLINED
                        if result is None:
                            running = True
                            result = await self._kernel.run(call["input"]["code"])
                            running = False
                        note = self._told()
                        told = f"{result}\n\n{note}" if note else result
                        self._transcript.append({"role": "tool", "content": told, "call_id": call["id"]})
                        answered += 1
                        yield {
                            "type": "tool_result",
                            "call_id": call["id"],
                            "content": result,
                            "is_error": False,
                        }
                        if note:
                            yield {"type": "note", "text": _TOLD}
                finally:
                    # Interrupted part-way: every call the transcript holds still gets an answer,
                    # or the next request would carry a call no result follows. Only the one in
                    # the kernel when the stop came may have partly run.
                    for n, call in enumerate(turn.calls[answered:]):
                        said = _INTERRUPTED if n == 0 and running else _NOT_RUN
                        self._transcript.append({"role": "tool", "content": said, "call_id": call["id"]})
                continue
            yield {"type": "stop", "reason": stop}
            if stop in (ANSWERED, REFUSED) or nudges >= self._max_nudges:
                return
            nudges += 1
            note = self._told()
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
