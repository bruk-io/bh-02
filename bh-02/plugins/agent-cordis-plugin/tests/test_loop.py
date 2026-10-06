"""The loop over a scripted model and a fake kernel, and the transcript outliving a model swap."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import pytest

from agent_cordis_plugin import (
    DECLINED,
    FAILED,
    STOPPED,
    LoopModel,
    MemoryTranscript,
    classify,
    loop,
    refusal,
    transcript,
)
from cordis import Effects, Inspection, Runtime, bind, component

type Json = Mapping[str, Any]


class Scripted:
    """A `model` that plays one scripted turn per call and records what it was asked."""

    def __init__(self, *turns: Sequence[Json]) -> None:
        self.turns = list(turns)
        self.requests: list[tuple[tuple[Json, ...], tuple[str, ...]]] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.requests.append((tuple(messages), tuple(str(t["name"]) for t in tools)))
        if not self.turns:
            raise ScriptError("script", "the script ran out")
        for chunk in self.turns.pop(0):
            yield chunk


class ScriptError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind, self.message = kind, message


PYTHON: Json = {"name": "python", "description": "Run Python.", "parameters": {"type": "object"}}


class Shouting:
    """A `kernel` value whose inputs upper-case their code, confined unless told otherwise; the
    loop needs only `spec`, `confined`, `instructions()` and `run()`."""

    def __init__(self, confined: bool = True) -> None:
        self.confined = confined
        self.ran: list[str] = []

    @property
    def spec(self) -> Json:
        return PYTHON

    async def run(self, code: str) -> str:
        self.ran.append(code)
        return code.upper()

    def instructions(self) -> str:
        return ""


class Person:
    """An `output` that answers each question in turn (no once the answers run out), keeps what
    it was asked, and can be told to wait on a question for ever."""

    def __init__(self, *answers: bool, hang: bool = False) -> None:
        self.answers = list(answers)
        self.hang = hang
        self.asked: list[Json] = []

    async def confirm(self, request: Json) -> bool:
        self.asked.append(request)
        if self.hang:
            await asyncio.Event().wait()
        return self.answers.pop(0) if self.answers else False


def text(s: str) -> Json:
    return {"type": "text", "text": s}


def call(id: str, name: str, **input: Any) -> Json:
    return {"type": "tool_call", "id": id, "name": name, "input": input}


async def _collect(model: LoopModel, message: str) -> str:
    """The reply's text, the part a person reads as the answer."""
    return "".join([str(e["text"]) async for e in model.reply(message) if e["type"] == "text"])


async def test_a_turn_shows_each_call_and_its_result_in_order() -> None:
    scripted = Scripted([text("let me "), call("c1", "python", code="quiet")], [text("done")])
    events = [e async for e in LoopModel(scripted, Shouting(), MemoryTranscript()).reply("go")]
    assert [e["type"] for e in events] == ["text", "tool_call", "tool_result", "text", "stop"]
    assert events[-1] == {"type": "stop", "reason": "answered"}
    assert events[2] == {"type": "tool_result", "call_id": "c1", "content": "QUIET", "is_error": False}


async def test_a_text_turn_is_one_model_step_and_two_transcript_entries() -> None:
    scripted, history = Scripted([text("hel"), text("lo")]), MemoryTranscript()
    assert await _collect(LoopModel(scripted, Shouting(), history), "hi") == "hello"
    assert [m["role"] for m in history.messages] == ["user", "assistant"]
    ((messages, offered),) = scripted.requests
    assert offered == ("python",)  # the one tool, offered through tool calling
    assert messages == ({"role": "user", "content": "hi"},)


async def test_a_tool_turn_runs_the_call_as_an_input_and_asks_again() -> None:
    scripted = Scripted([text("let me "), call("c1", "python", code="quiet")], [text("QUIET it is")])
    history = MemoryTranscript()
    assert await _collect(LoopModel(scripted, Shouting(), history), "shout for me") == "let me QUIET it is"
    assert [m["role"] for m in history.messages] == ["user", "assistant", "tool", "assistant"]
    assert history.messages[2] == {"role": "tool", "content": "QUIET", "call_id": "c1"}
    assert scripted.requests[1][0][-1]["content"] == "QUIET"  # the result went back to the model


async def test_an_unconfined_input_is_put_to_the_person_and_a_no_runs_nothing() -> None:
    scripted = Scripted([call("c1", "python", code="x"), call("c2", "python", code="y")], [text("fine")])
    kernel, person, history = Shouting(confined=False), Person(False, True), MemoryTranscript()
    assert await _collect(LoopModel(scripted, kernel, history, output=person), "go") == "fine"
    assert person.asked == [
        {"name": "python", "input": {"code": "x"}},
        {"name": "python", "input": {"code": "y"}},
    ]
    assert [m["content"] for m in history.messages if m["role"] == "tool"] == [DECLINED, "Y"]
    assert kernel.ran == ["y"]  # the no reached the model as text, and the yes ran


async def test_a_confined_input_is_never_asked_about_and_with_nobody_to_ask_nothing_runs() -> None:
    person = Person()
    scripted = Scripted([call("c1", "python", code="x")], [text("ok")])
    await _collect(LoopModel(scripted, Shouting(), MemoryTranscript(), output=person), "go")
    assert person.asked == []
    kernel, history = Shouting(confined=False), MemoryTranscript()
    await _collect(LoopModel(Scripted([call("c1", "python", code="x")], [text("ok")]), kernel, history), "go")
    assert kernel.ran == [] and history.messages[2]["content"] == DECLINED


async def test_a_model_failure_propagates_as_the_contract_says() -> None:
    with pytest.raises(ScriptError, match="ran out"):
        await _collect(LoopModel(Scripted(), Shouting(), MemoryTranscript()), "hi")


async def test_a_failed_turn_answers_its_message_so_the_next_request_does_not_ask_it_again() -> None:
    """A 429 on `/model sonnet`, then `/model haiku` and a new question: the model must not
    answer the failed one as well."""

    class Failing:
        def __init__(self) -> None:
            self.requests: list[tuple[Json, ...]] = []

        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            self.requests.append(tuple(messages))
            if len(self.requests) == 1:
                yield text("Hel")
                raise ScriptError("rate_limit", "429")
            yield text("Teal.")

    failing, history = Failing(), MemoryTranscript()
    model = LoopModel(failing, Shouting(), history)
    with pytest.raises(ScriptError):
        await _collect(model, "say hi")
    assert history.messages[-1] == {"role": "assistant", "content": f"Hel\n\n{FAILED}"}
    await _collect(model, "what colour?")
    assert _roles(failing.requests[1]) == ["user", "assistant", "user"]


async def test_swapping_the_model_reloads_the_loop_and_keeps_the_transcript() -> None:
    first, second = Scripted([text("one")]), Scripted([text("two")])

    def model_row(what: object) -> object:
        @component
        async def model() -> Effects:
            yield bind("model", what)

        return model

    class Nowhere:
        def text(self) -> str:
            return ""

    @component
    async def kernel_and_system() -> Effects:
        yield bind("kernel", Shouting())
        yield bind("system", Nowhere())
        yield bind("output", Person())

    rt = Runtime()
    rt.mount(transcript, id="transcript")
    rt.mount(loop, id="loop")
    kernel_fiber = rt.mount(kernel_and_system, id="kernel")
    row = rt.mount(model_row(first), id="model")
    await rt.settle()
    assert await _collect(rt.root.get("loop"), "first") == "one"

    await row.retire()
    await rt.settle()
    assert rt.root.get("loop") is None  # the loop unloaded with its model
    rt.mount(model_row(second), id="model")
    await rt.settle()
    assert await _collect(rt.root.get("loop"), "second") == "two"
    history = rt.root.get("transcript")
    assert [m["content"] for m in history.messages] == ["first", "one", "second", "two"]  # one conversation
    assert Inspection(rt).fiber("kernel") is kernel_fiber  # the kernel's row stayed up throughout
    await rt.shutdown()


def stop(reason: str) -> Json:
    return {"type": "stop", "reason": reason}


def test_no_call_is_three_different_things() -> None:
    assert classify("stop", "the answer", []) == "answered"
    assert classify("stop", "  ", []) == "silent"
    assert classify("length", "half an ans", []) == "truncated"
    assert classify("length", "", [{"id": "c", "name": "x", "input": {}}]) == "truncated"  # cut off mid-call
    assert classify(None, "", [{"id": "c", "name": "x", "input": {}}]) == "act"
    assert classify("stop", "", [{"id": "c", "name": "x", "input": {}, "error": "bad json"}]) == "undecodable"


async def test_a_truncated_turn_is_fed_back_not_read_as_the_answer() -> None:
    scripted = Scripted([text("half an ans"), stop("length")], [text("whole answer"), stop("stop")])
    history = MemoryTranscript()
    events = [e async for e in LoopModel(scripted, Shouting(), history).reply("q")]
    assert [e for e in events if e["type"] == "stop"] == [stop("truncated"), stop("answered")]
    feedback = history.messages[2]
    assert feedback["role"] == "user" and feedback["feedback"] == "truncated"
    assert "output token limit" in feedback["content"]
    assert scripted.requests[1][0][-1] is feedback  # the model was told, then asked again


async def test_a_cut_off_call_never_runs_and_leaves_no_call_to_answer() -> None:
    scripted = Scripted([call("c1", "python", code="x"), stop("length")], [text("ok"), stop("stop")])
    history = MemoryTranscript()
    await _collect(LoopModel(scripted, Shouting(), history), "go")
    assert "tool_calls" not in history.messages[1]
    assert all(m["role"] != "tool" for m in history.messages)


async def test_nudges_are_bounded() -> None:
    scripted = Scripted([stop("stop")], [stop("stop")], [stop("stop")])
    events = [e async for e in LoopModel(scripted, Shouting(), MemoryTranscript(), max_nudges=1).reply("q")]
    assert [e["reason"] for e in events if e["type"] == "stop"] == ["silent", "silent"]
    assert len(scripted.requests) == 2  # asked once, nudged once, then the reply stops


async def test_the_provider_message_rides_on_its_transcript_entry() -> None:
    raw = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "python"}}], "extra": 1}
    scripted = Scripted([call("c1", "python", code="x"), {"type": "message", "message": raw}], [text("done")])
    history = MemoryTranscript()
    await _collect(LoopModel(scripted, Shouting(), history), "go")
    assert history.messages[1]["provider"] is raw


async def test_an_answered_turn_keeps_its_provider_message_so_its_thinking_is_replayed() -> None:
    raw = {
        "content": [{"type": "thinking", "thinking": "hm", "signature": "s"}, {"type": "text", "text": "hi"}]
    }
    scripted = Scripted([text("hi"), stop("end_turn"), {"type": "message", "message": raw}])
    history = MemoryTranscript()
    await _collect(LoopModel(scripted, Shouting(), history), "go")
    assert history.messages[1]["provider"] is raw


async def test_a_turn_whose_calls_never_ran_drops_its_provider_message() -> None:
    raw = {"content": [{"type": "tool_use", "id": "c1", "name": "python", "input": {}}]}
    cut = [call("c1", "python", code="x"), stop("max_tokens"), {"type": "message", "message": raw}]
    refused = [call("c2", "python", code="x"), stop("refusal"), {"type": "message", "message": raw}]
    scripted = Scripted(cut, refused)
    history = MemoryTranscript()
    await _collect(LoopModel(scripted, Shouting(), history), "go")
    assistant = [m for m in history.messages if m["role"] == "assistant"]
    assert len(assistant) == 2 and all("provider" not in m for m in assistant)  # its tool_use has no result


async def test_an_interrupted_call_still_gets_an_answer_in_the_transcript() -> None:
    class Hanging(Shouting):
        async def run(self, code: str) -> str:
            await asyncio.Event().wait()
            return "never"  # pragma: no cover

    scripted = Scripted([call("c1", "python", code="a"), call("c2", "python", code="b")])
    history = MemoryTranscript()

    async def run() -> None:
        async for _ in LoopModel(scripted, Hanging(), history).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    tools = [m for m in history.messages if m["role"] == "tool"]
    assert [m["call_id"] for m in tools] == ["c1", "c2"]  # both calls answered
    assert tools[0]["content"].startswith("interrupted")  # c1 was in the kernel: it may have partly run
    assert tools[1]["content"].startswith("not run")  # c2 never started


async def test_a_turn_stopped_at_the_approval_question_says_the_input_never_ran() -> None:
    kernel, history = Shouting(confined=False), MemoryTranscript()
    scripted = Scripted([call("c1", "python", code="a"), call("c2", "python", code="b")])

    async def run() -> None:
        async for _ in LoopModel(scripted, kernel, history, output=Person(hang=True)).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    tools = [m for m in history.messages if m["role"] == "tool"]
    assert [m["call_id"] for m in tools] == ["c1", "c2"]
    assert all(m["content"].startswith("not run: the person stopped the turn") for m in tools)
    assert kernel.ran == []


async def test_the_system_prompt_is_read_fresh_for_every_request_and_never_stored() -> None:
    class Where:
        def __init__(self) -> None:
            self.text_now = "in /a"

        def text(self) -> str:
            return self.text_now

    class Guided(Shouting):
        def instructions(self) -> str:
            return "Shout when asked."

    where, scripted, history = Where(), Scripted([text("one")], [text("two")]), MemoryTranscript()
    model = LoopModel(scripted, Guided(), history, system=where)
    await _collect(model, "first")
    where.text_now = "in /b"
    await _collect(model, "second")
    first, second = scripted.requests[0][0][0], scripted.requests[1][0][0]
    assert first == {"role": "system", "content": "in /a\n\nShout when asked."}
    assert second["content"].startswith("in /b")
    assert all(m["role"] != "system" for m in history.messages)  # the transcript is the conversation only


async def test_a_refused_turn_never_runs_its_call_and_is_not_asked_again() -> None:
    assert classify("refusal", "", [{"id": "c", "name": "x", "input": {"code": "pri"}}]) == "refused"
    assert classify("model_context_window_exceeded", "half", []) == "truncated"
    scripted = Scripted([text("I can't"), call("c1", "python", code="x"), stop("refusal")])
    history = MemoryTranscript()
    events = [e async for e in LoopModel(scripted, Shouting(), history).reply("go")]
    assert [e for e in events if e["type"] == "stop"] == [stop("refused")]
    assert not any(e["type"] == "tool_result" for e in events)
    assert "tool_calls" not in history.messages[1] and len(scripted.requests) == 1


async def test_a_stopped_reply_closes_its_model_step_at_once() -> None:
    closed: list[bool] = []

    class Streaming:
        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            try:
                yield text("a")
                yield text("b")
            finally:
                closed.append(True)  # an SDK stream would release its HTTP response here

    reply = LoopModel(Streaming(), Shouting(), MemoryTranscript()).reply("go")
    assert (await anext(reply)) == text("a")
    await reply.aclose()  # the person pressed Ctrl-C: chat closes the reply
    assert closed == [True]


class _Story:
    """A model that says a word, then streams on until it is stopped; then one that answers."""

    def __init__(self) -> None:
        self.requests: list[tuple[Json, ...]] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.requests.append(tuple(messages))
        if len(self.requests) > 1:
            yield text("NEXT-OK")
            return
        yield text("Once upon")
        await asyncio.Event().wait()  # a long reply, still streaming
        yield text("never")  # pragma: no cover


def _roles(messages: Sequence[Json]) -> list[str]:
    return [str(m["role"]) for m in messages]


async def test_a_reply_closed_mid_stream_answers_its_message_with_what_it_said_and_that_it_stopped() -> None:
    story, history = _Story(), MemoryTranscript()
    model = LoopModel(story, Shouting(), history)
    reply = model.reply("tell me a long story")
    assert (await anext(reply)) == text("Once upon")
    await reply.aclose()  # the ui stopped reading and closed the reply: Ctrl-C
    assert history.messages[-1] == {"role": "assistant", "content": f"Once upon\n\n{STOPPED}"}
    assert await _collect(model, "say NEXT-OK") == "NEXT-OK"
    # the next request answers the stopped message, so the model is not asked it again
    assert _roles(story.requests[1]) == ["user", "assistant", "user"]
    assert story.requests[1][-1]["content"] == "say NEXT-OK"


async def test_a_reply_caninputed_while_its_model_waits_answers_its_message_too() -> None:
    story, history = _Story(), MemoryTranscript()
    model = LoopModel(story, Shouting(), history)
    shown: list[Json] = []

    async def run() -> None:
        async for event in model.reply("tell me a long story"):
            shown.append(event)

    task = asyncio.create_task(run())
    while not shown:
        await asyncio.sleep(0)
    task.cancel()  # cancelled inside the model step, where it waits for the stream
    await asyncio.gather(task, return_exceptions=True)
    assert _roles(history.messages) == ["user", "assistant"]
    assert history.messages[-1]["content"].endswith(STOPPED)
    await _collect(model, "say NEXT-OK")
    assert _roles(story.requests[1]) == ["user", "assistant", "user"]


async def test_a_reply_stopped_before_it_said_anything_is_still_answered() -> None:
    class Silent:
        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            await asyncio.Event().wait()
            yield text("never")  # pragma: no cover

    history = MemoryTranscript()

    async def run() -> None:
        async for _ in LoopModel(Silent(), Shouting(), history).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert history.messages[-1] == {"role": "assistant", "content": STOPPED}


async def test_a_call_that_is_not_an_input_is_answered_as_text_and_runs_nothing() -> None:
    """A model (a small local one, say) that invents a tool, or calls python without code, reads
    why in the result; nothing reaches the kernel and the reply carries on."""
    kernel = Shouting()
    scripted = Scripted([call("c1", "read_file", path="a"), call("c2", "python", source="x")], [text("ok")])
    history = MemoryTranscript()
    assert await _collect(LoopModel(scripted, kernel, history), "go") == "ok"
    results = [m["content"] for m in history.messages if m["role"] == "tool"]
    assert results == [
        "error: there is no tool named 'read_file'; your one tool is python(code)",
        "error: python takes `code`, the Python to run, as a string",
    ]
    assert kernel.ran == []


def test_only_a_python_call_with_code_is_a_input() -> None:
    assert refusal({"id": "c", "name": "python", "input": {"code": "1"}}, PYTHON) is None
    assert refusal({"id": "c", "name": "python", "input": {"code": 1}}, PYTHON) is not None
    assert refusal({"id": "c", "name": "write_file", "input": {"code": "1"}}, PYTHON) is not None
