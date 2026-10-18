"""The loop over a scripted model and a fake Python process, and the transcript outliving a model swap."""

import asyncio
import errno
import gc
import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_cordis_plugin import (
    DECLINED,
    FAILED,
    STOPPED,
    Answer,
    Asked,
    Clock,
    FileTranscript,
    LoopModel,
    MemoryTranscript,
    OneAtATime,
    ToolBroker,
    asides,
    changes,
    classify,
    executor,
    latest,
    loop,
    malformed,
    refusal,
    stamp,
    transcript,
)
from agent_cordis_plugin.testing import noon, on
from cordis import Effects, Inspection, Runtime, bind, component
from cordis_helpers import Hooks

type Json = Mapping[str, Any]


class Scripted:
    """A `model` that plays one scripted step per call and records what it was asked."""

    def __init__(self, *steps: Sequence[Json]) -> None:
        self.steps = list(steps)
        self.requests: list[tuple[tuple[Json, ...], tuple[str, ...]]] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.requests.append((tuple(messages), tuple(str(t["name"]) for t in tools)))
        if not self.steps:
            raise ScriptError("script", "the script ran out")
        for chunk in self.steps.pop(0):
            yield chunk


class ScriptError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind, self.message = kind, message


PYTHON: Json = {
    "name": "python",
    "description": "Run Python.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
}


class Shouting:
    """A stand-in for the python row's value (`PythonProcess`): its inputs upper-case their code
    and touch `/p/<code>.py`, and `as_tool` registers it as the `python` tool."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    @property
    def spec(self) -> Json:
        return PYTHON

    async def run(self, code: str) -> str:
        self.ran.append(code)
        return code.upper()

    def instructions(self) -> str:
        return ""

    def touched(self) -> tuple[str, ...]:
        return (f"/p/{self.ran[-1].lower()}.py",) if self.ran else ()


def as_tool(shouting: Shouting) -> ToolBroker:
    """The `tools` value with `shouting`'s `python` registered, as the python row registers it: a
    call runs its `code` as an input, answering with the files it touched, and is shown as code."""
    tools = ToolBroker()

    async def run(input: Json) -> Json:
        content = await shouting.run(str(input["code"]))
        return {"content": content, "touched": list(shouting.touched())}

    def show(input: Json) -> Json:
        return {"title": "Run this python code?", "lines": str(input["code"]).splitlines()}

    tools.register(shouting.spec, run, show=show)
    return tools


class Confined:
    """An approval over a runner that confines the Python process: every input runs, nobody is
    asked. The loop's own (`approve`), and the `approval` rule and `output` a row binds."""

    async def approve(self, question: Json) -> Answer:
        return Answer.UNASKED

    def unasked(self, question: Json) -> bool:
        return True

    async def confirm(self, question: Json) -> bool:
        raise AssertionError("nobody is asked about a call that runs unasked")


class Person:
    """An approval over no jail: the person answers each question in turn (no once the answers
    run out), it keeps what it was asked, and it can be told to wait on a question for ever. The
    loop's own (`approve`), and an `output`'s `confirm`."""

    def __init__(self, *answers: bool, hang: bool = False) -> None:
        self.answers = list(answers)
        self.hang = hang
        self.asked: list[Json] = []

    async def confirm(self, question: Json) -> bool:
        self.asked.append(question)
        if self.hang:
            await asyncio.Event().wait()
        return self.answers.pop(0) if self.answers else False

    async def approve(self, question: Json) -> Answer:
        return Answer.YES if await self.confirm(question) else Answer.NO


def text(s: str) -> Json:
    return {"type": "text", "text": s}


def _bare(entry: Json) -> dict[str, Any]:
    """An entry without the records the loop adds to it (`at`, `step`, `call`): what the model was told."""
    return {key: value for key, value in entry.items() if key not in ("at", "step", "call")}


def call(id: str, name: str, **input: Any) -> Json:
    return {"type": "tool_call", "id": id, "name": name, "input": input}


async def _collect(model: LoopModel, message: str) -> str:
    """The reply's text, the part a person reads as the answer."""
    return "".join([str(e["text"]) async for e in model.reply(message) if e["type"] == "text"])


async def test_a_reply_shows_each_call_and_its_result_in_order() -> None:
    scripted = Scripted([text("let me "), call("c1", "python", code="quiet")], [text("done")])
    events = [
        e async for e in LoopModel(scripted, as_tool(Shouting()), MemoryTranscript(), Confined()).reply("go")
    ]
    assert [e["type"] for e in events] == ["text", "tool_call", "tool_result", "text", "stop"]
    assert events[-1] == {"type": "stop", "reason": "answered"}
    assert events[2] == {"type": "tool_result", "call_id": "c1", "content": "QUIET", "is_error": False}


async def test_a_text_reply_is_one_model_step_and_two_transcript_entries() -> None:
    scripted, transcript = Scripted([text("hel"), text("lo")]), MemoryTranscript()
    assert (
        await _collect(
            LoopModel(scripted, as_tool(Shouting()), transcript, Confined(), clock=on("2026-10-07")), "hi"
        )
        == "hello"
    )
    # the list it began with, then the message and its answer
    assert [m["role"] for m in transcript.messages] == ["tools", "user", "assistant"]
    ((messages, offered),) = scripted.requests
    assert offered == ("python",)  # the one tool, offered through tool calling
    at = stamp(noon("2026-10-07"))
    assert messages == (
        {"role": "user", "content": "(Today's date: 2026-10-07.)\n\nhi", "today": "2026-10-07", "at": at},
    )


async def test_a_tool_step_runs_the_call_as_an_input_and_asks_again() -> None:
    scripted = Scripted([text("let me "), call("c1", "python", code="quiet")], [text("QUIET it is")])
    transcript = MemoryTranscript()
    assert (
        await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "shout for me")
        == "let me QUIET it is"
    )
    assert [m["role"] for m in transcript.messages] == ["tools", "user", "assistant", "tool", "assistant"]
    assert _bare(transcript.messages[3]) == {
        "role": "tool",
        "content": "QUIET",
        "call_id": "c1",
        "asides": [],
    }
    assert scripted.requests[1][0][-1]["content"] == "QUIET"  # the result went back to the model


async def test_each_input_is_put_to_approval_and_a_no_runs_nothing() -> None:
    """Whether the person is asked (unconfined) or nobody is (confined) is the `approval` rule's
    to decide (runner:approval); the loop asks about every call (`Asked`), saying where it runs
    and showing it as its tool's registration says, and runs only what it says yes to."""
    scripted = Scripted([call("c1", "python", code="x"), call("c2", "python", code="y")], [text("fine")])
    shouting, person, transcript = Shouting(), Person(False, True), MemoryTranscript()
    assert await _collect(LoopModel(scripted, as_tool(shouting), transcript, person), "go") == "fine"
    assert person.asked == [
        {
            "name": "python",
            "input": {"code": c},
            "runs": "jail",
            "title": "Run this python code?",
            "lines": [c],
        }
        for c in ("x", "y")
    ]
    assert [m["content"] for m in transcript.messages if m["role"] == "tool"] == [DECLINED, "Y"]
    assert shouting.ran == ["y"]  # the no reached the model as text, and the yes ran


async def test_a_call_runs_unasked_when_the_rule_says_so_else_on_the_person_s_answer() -> None:
    """`Asked`, what the loop row builds from the `approval` rule and the `output`: a call the rule
    lets run unasked never reaches the person; any other is theirs to answer."""

    class Rule:
        def unasked(self, question: Json) -> bool:
            return question.get("runs", "jail") == "jail"

    person = Person(False, True)
    asked = Asked(Rule(), person)
    assert await asked.approve({"name": "python", "input": {}}) is Answer.UNASKED
    assert await asked.approve({"name": "search", "input": {}, "runs": "host"}) is Answer.NO
    assert await asked.approve({"name": "search", "input": {}, "runs": "host"}) is Answer.YES
    assert (
        person.asked == [{"name": "search", "input": {}, "runs": "host"}] * 2
    )  # the unasked one never reached them


async def test_a_call_that_is_not_an_input_is_never_put_to_approval() -> None:
    person = Person(True)
    scripted = Scripted([call("c1", "read_file", path="a")], [text("ok")])
    await _collect(LoopModel(scripted, as_tool(Shouting()), MemoryTranscript(), person), "go")
    assert person.asked == []  # refused as text before anyone is asked


async def test_a_model_failure_propagates_as_the_contract_says() -> None:
    with pytest.raises(ScriptError, match="ran out"):
        await _collect(LoopModel(Scripted(), as_tool(Shouting()), MemoryTranscript(), Confined()), "hi")


async def test_a_failed_step_answers_its_message_so_the_next_request_does_not_ask_it_again() -> None:
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

    failing, transcript = Failing(), MemoryTranscript()
    model = LoopModel(failing, as_tool(Shouting()), transcript, Confined())
    with pytest.raises(ScriptError):
        await _collect(model, "say hi")
    assert _bare(transcript.messages[-1]) == {"role": "assistant", "content": f"Hel\n\n{FAILED}"}
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
    async def shouting_and_system() -> Effects:
        yield bind("tools", as_tool(Shouting()))
        yield bind("system", Nowhere())
        yield bind("approval", Confined())
        yield bind("output", Confined())

    rt = Runtime()
    rt.mount(transcript, id="transcript")
    rt.mount(asides, id="asides")
    executor_fiber = rt.mount(executor, id="executor")
    rt.mount(loop, id="loop")
    shouting_fiber = rt.mount(shouting_and_system, id="shouting")
    row = rt.mount(model_row(first), id="model")
    await rt.settle()
    assert await _collect(rt.root.get("loop"), "first") == "one"

    await row.retire()
    await rt.settle()
    assert rt.root.get("loop") is None  # the loop unloaded with its model
    rt.mount(model_row(second), id="model")
    await rt.settle()
    assert await _collect(rt.root.get("loop"), "second") == "two"
    kept = rt.root.get("transcript")
    # one conversation (its first message told the date first)
    said = [m for m in kept.messages if m["role"] != "tools"]
    assert [m["content"].rpartition("\n\n")[2] for m in said] == ["first", "one", "second", "two"]
    assert Inspection(rt).fiber("shouting") is shouting_fiber  # the shouting row stayed up throughout
    assert Inspection(rt).fiber("executor") is executor_fiber  # and so did the call in flight's
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


async def test_a_truncated_step_is_fed_back_not_read_as_the_answer() -> None:
    scripted = Scripted([text("half an ans"), stop("length")], [text("whole answer"), stop("stop")])
    transcript = MemoryTranscript()
    events = [e async for e in LoopModel(scripted, as_tool(Shouting()), transcript, Confined()).reply("q")]
    assert [e for e in events if e["type"] == "stop"] == [stop("truncated"), stop("answered")]
    feedback = transcript.messages[3]
    assert feedback["role"] == "user" and feedback["feedback"] == "truncated"
    assert "output token limit" in feedback["content"]
    assert scripted.requests[1][0][-1] is feedback  # the model was told, then asked again


async def test_a_cut_off_call_never_runs_and_leaves_no_call_to_answer() -> None:
    scripted = Scripted([call("c1", "python", code="x"), stop("length")], [text("ok"), stop("stop")])
    transcript = MemoryTranscript()
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "go")
    assert "tool_calls" not in transcript.messages[1]
    assert all(m["role"] != "tool" for m in transcript.messages)


async def test_nudges_are_bounded() -> None:
    scripted = Scripted([stop("stop")], [stop("stop")], [stop("stop")])
    events = [
        e
        async for e in LoopModel(
            scripted, as_tool(Shouting()), MemoryTranscript(), Confined(), max_nudges=1
        ).reply("q")
    ]
    assert [e["reason"] for e in events if e["type"] == "stop"] == ["silent", "silent"]
    assert len(scripted.requests) == 2  # asked once, nudged once, then the reply stops


async def test_the_provider_message_rides_on_its_transcript_entry() -> None:
    raw = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "python"}}], "extra": 1}
    scripted = Scripted([call("c1", "python", code="x"), {"type": "message", "message": raw}], [text("done")])
    transcript = MemoryTranscript()
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "go")
    assert transcript.messages[2]["provider"] is raw


async def test_an_answered_step_keeps_its_provider_message_so_its_thinking_is_replayed() -> None:
    raw = {
        "content": [{"type": "thinking", "thinking": "hm", "signature": "s"}, {"type": "text", "text": "hi"}]
    }
    scripted = Scripted([text("hi"), stop("end_turn"), {"type": "message", "message": raw}])
    transcript = MemoryTranscript()
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "go")
    assert transcript.messages[2]["provider"] is raw


async def test_a_step_whose_calls_never_ran_drops_its_provider_message() -> None:
    raw = {"content": [{"type": "tool_use", "id": "c1", "name": "python", "input": {}}]}
    cut = [call("c1", "python", code="x"), stop("max_tokens"), {"type": "message", "message": raw}]
    refused = [call("c2", "python", code="x"), stop("refusal"), {"type": "message", "message": raw}]
    scripted = Scripted(cut, refused)
    transcript = MemoryTranscript()
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "go")
    assistant = [m for m in transcript.messages if m["role"] == "assistant"]
    assert len(assistant) == 2 and all("provider" not in m for m in assistant)  # its tool_use has no result


async def test_an_interrupted_call_still_gets_an_answer_in_the_transcript() -> None:
    class Hanging(Shouting):
        async def run(self, code: str) -> str:
            await asyncio.Event().wait()
            return "never"  # pragma: no cover

    scripted = Scripted([call("c1", "python", code="a"), call("c2", "python", code="b")])
    transcript = MemoryTranscript()

    async def run() -> None:
        async for _ in LoopModel(scripted, as_tool(Hanging()), transcript, Confined()).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    tools = [m for m in transcript.messages if m["role"] == "tool"]
    assert [m["call_id"] for m in tools] == ["c1", "c2"]  # both calls answered
    assert tools[0]["content"].startswith("interrupted")  # c1 was in the Python process: may have partly run
    assert tools[1]["content"].startswith("not run")  # c2 never started
    assert [m["asides"] for m in tools] == [[], []]


async def test_a_reply_stopped_at_the_approval_question_says_the_input_never_ran() -> None:
    shouting, transcript = Shouting(), MemoryTranscript()
    scripted = Scripted([call("c1", "python", code="a"), call("c2", "python", code="b")])

    async def run() -> None:
        async for _ in LoopModel(scripted, as_tool(shouting), transcript, Person(hang=True)).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    tools = [m for m in transcript.messages if m["role"] == "tool"]
    assert [m["call_id"] for m in tools] == ["c1", "c2"]
    assert all(m["content"].startswith("not run: the person stopped the reply") for m in tools)
    assert shouting.ran == []


class _Where:
    """A `system` value whose text the test changes, as an extension loading or a branch switch
    would; `sections` follow it, as a tool's row adds what the model is told about its tool."""

    def __init__(self, *sections: str) -> None:
        self.text_now = "in /a"
        self.sections = sections

    def text(self) -> str:
        return "\n\n".join([self.text_now, *self.sections])


class _Guided(Shouting):
    """A `Shouting` whose row tells the model about it (`_SHOUT`, a section of `_Where(_SHOUT)`)."""


async def test_a_conversation_keeps_the_prompt_it_began_with_and_is_told_what_changed() -> None:
    """A model server reuses its work on a conversation only up to the first token that differs,
    so the prompt is sent as the conversation began with it; a change rides on the next message."""
    where, transcript = _Where(_SHOUT), MemoryTranscript()
    scripted = Scripted(*([text(said)] for said in ("one", "two", "three", "four", "five", "six")))
    model = LoopModel(scripted, as_tool(_Guided()), transcript, Confined(), system=where)
    await _collect(model, "first")
    where.text_now = "in /b"
    events = [e async for e in model.reply("second")]
    await _collect(model, "third")
    began = {"role": "system", "content": "in /a\n\nShout when asked."}
    assert [request[0] for request, _ in scripted.requests] == [began, began, began]
    told = scripted.requests[1][0][-1]["content"]
    assert told.startswith("(bh-02: your instructions have changed since this conversation began.")
    assert "\n\nin /b\n\n" in told and told.endswith("\n\nsecond")
    assert '(No longer in them: "in /a".)' in told  # replaced, and not by a part that starts the same
    assert events[0] == {
        "type": "note",
        "text": "told the model its instructions changed since the conversation began",
    }
    assert scripted.requests[2][0][-1]["content"] == "third"  # told once
    assert [m["role"] for m in transcript.messages] == [
        "tools",
        "system",
        "user",
        "assistant",
        "system",
        "user",
        "assistant",
    ] + [
        "user",
        "assistant",
    ]
    # the change is kept as what turns the last reading into this one, not a whole prompt
    assert transcript.messages[4] == {"role": "system", "edits": [{"at": 0, "drop": 1, "add": ["in /b"]}]}
    # a reloaded loop (a new model, a new ui) carries on from what the transcript says it told
    again = LoopModel(scripted, as_tool(_Guided()), transcript, Confined(), system=where)
    await _collect(again, "fourth")
    assert scripted.requests[3][0][0] == began and scripted.requests[3][0][-1]["content"] == "fourth"
    # and a loop goes by what the transcript says it told, not what it told itself: a change
    # another loop over the same transcript told is not told again
    where.text_now = "in /c"
    await _collect(again, "fifth")
    await _collect(model, "sixth")
    assert '"in /b"' in scripted.requests[4][0][-1]["content"]
    assert scripted.requests[5][0][-1]["content"] == "sixth"


_SHOUT = "Shout when asked."  # `_Guided`'s instructions, which none of the changes below touch
_DAY = "2026-10-07"


async def test_several_changes_keep_the_prompt_once_and_each_is_told_against_the_last_told(
    tmp_path: Path,
) -> None:
    """Each change is kept as the edits from the reading before it, not as another whole prompt,
    and told against what the model was last told, not what the conversation began with. A
    resumed session (the transcript read back from its file, a new loop over it) carries on from
    the last reading: it tells nothing that was told already, and the next change against that."""
    path = tmp_path / "transcript.jsonl"
    where = _Where(_SHOUT)
    scripted = Scripted(*([text(f"reply {n}")] for n in range(6)))
    model = LoopModel(
        scripted, as_tool(_Guided()), FileTranscript(str(path)), Confined(), system=where, clock=on(_DAY)
    )
    readings = ["in /a", "in /b", "in /b\n\nExtensions here: sh.", "in /c\n\nExtensions here: sh."]
    for n, reading in enumerate(readings):
        where.text_now = reading
        await _collect(model, f"message {n}")
    # bh-02 ended and resumed: the same file, read back by a new transcript, and a new loop
    resumed = LoopModel(
        scripted, as_tool(_Guided()), FileTranscript(str(path)), Confined(), system=where, clock=on(_DAY)
    )
    await _collect(resumed, "message 4")  # it reads as it was last told
    where.text_now = "in /c"
    await _collect(resumed, "message 5")

    asked = [request for request, _ in scripted.requests]
    began = {"role": "system", "content": f"in /a\n\n{_SHOUT}"}
    for request in asked:  # the start, whole, and no other `system` message: the edits stay home
        assert request[0] == began and [m for m in request if m["role"] == "system"] == [began]
    said = [request[-1]["content"] for request in asked]
    told = [f"{reading}\n\n{_SHOUT}" for reading in [*readings, "in /c"]]
    assert said[0] == f"(Today's date: {_DAY}.)\n\nmessage 0"
    for n in (1, 2, 3):
        assert said[n] == f"{changes(told[n - 1], told[n])}\n\nmessage {n}"
    assert "in /b" not in said[2]  # told already: only the extension is new since
    assert '"in /b"' in said[3] and '"in /a"' not in said[3]  # gone since it was last told
    assert said[4] == "message 4"  # resumed: nothing told twice
    assert said[5] == (
        "(bh-02: your instructions have changed since this conversation began. "
        'No longer in them: "Extensions here: sh.".)\n\nmessage 5'
    )
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    kept = [entry for entry in entries if entry["role"] == "system"]
    assert kept[0] == began and all(set(entry) == {"role", "edits"} for entry in kept[1:])
    assert len(kept) == 5  # the start and four changes: the resume kept none of its own
    assert path.read_text().count(_SHOUT) == 1  # the prompt is in the file once
    assert latest(kept) == told[-1]


async def test_a_transcript_with_an_edits_entry_that_can_t_be_applied_still_answers() -> None:
    """A transcript damaged by hand must not cost a resumed session every message: an `edits`
    entry that can't be applied leaves the reading before it as what the model was last told, so
    the next change is told against that one and kept as the edits from it."""
    began = {"role": "system", "content": f"in /a\n\n{_SHOUT}"}
    transcript = MemoryTranscript()
    for message in (
        began,
        {"role": "user", "content": "first", "today": _DAY},
        {"role": "assistant", "content": "one"},
        {"role": "system", "edits": [{"at": 0}]},
    ):
        transcript.append(message)
    where, scripted = _Where(_SHOUT), Scripted([text("two")])
    where.text_now = "in /b"
    loop = LoopModel(scripted, as_tool(_Guided()), transcript, Confined(), system=where, clock=on(_DAY))
    assert await _collect(loop, "second") == "two"
    in_b = f"in /b\n\n{_SHOUT}"
    assert scripted.requests[0][0][-1]["content"] == f"{changes(began['content'], in_b)}\n\nsecond"
    assert latest([m for m in transcript.messages if m["role"] == "system"]) == in_b


async def test_a_change_made_by_an_input_is_told_with_that_input_s_result() -> None:
    where, transcript = _Where(_SHOUT), MemoryTranscript()

    class Extending(_Guided):
        async def run(self, code: str) -> str:
            where.text_now = "in /a\n\nExtensions here: sh."  # the input wrote one, and it loaded
            return "wrote it"

    scripted = Scripted([call("c1", "python", code="write sh.py")], [text("done")])
    events = [
        e
        async for e in LoopModel(scripted, as_tool(Extending()), transcript, Confined(), system=where).reply(
            "go"
        )
    ]
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["content"] == "wrote it"  # the person sees the input's own output
    assert events[events.index(result) + 1]["type"] == "note"
    sent = scripted.requests[1][0][-1]
    assert sent["role"] == "tool" and sent["content"].startswith("wrote it\n\n(bh-02: your instructions")
    assert "Extensions here: sh." in sent["content"]
    assert scripted.requests[1][0][0] == scripted.requests[0][0][0]  # the start stayed as it was


async def test_a_conversation_with_no_prompt_is_sent_none() -> None:
    scripted, transcript = Scripted([text("hi")]), MemoryTranscript()
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "hello")
    assert [m["role"] for m in scripted.requests[0][0]] == ["user"]
    assert transcript.messages[1]["role"] == "user"


async def test_a_refused_step_never_runs_its_call_and_is_not_asked_again() -> None:
    assert classify("refusal", "", [{"id": "c", "name": "x", "input": {"code": "pri"}}]) == "refused"
    assert classify("model_context_window_exceeded", "half", []) == "truncated"
    scripted = Scripted([text("I can't"), call("c1", "python", code="x"), stop("refusal")])
    transcript = MemoryTranscript()
    events = [e async for e in LoopModel(scripted, as_tool(Shouting()), transcript, Confined()).reply("go")]
    assert [e for e in events if e["type"] == "stop"] == [stop("refused")]
    assert not any(e["type"] == "tool_result" for e in events)
    assert "tool_calls" not in transcript.messages[1] and len(scripted.requests) == 1


async def test_a_stopped_reply_closes_its_model_step_at_once() -> None:
    closed: list[bool] = []

    class Streaming:
        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            try:
                yield text("a")
                yield text("b")
            finally:
                closed.append(True)  # an SDK stream would release its HTTP response here

    reply = LoopModel(Streaming(), as_tool(Shouting()), MemoryTranscript(), Confined()).reply("go")
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
    story, transcript = _Story(), MemoryTranscript()
    model = LoopModel(story, as_tool(Shouting()), transcript, Confined())
    reply = model.reply("tell me a long story")
    assert (await anext(reply)) == text("Once upon")
    await reply.aclose()  # the ui stopped reading and closed the reply: Ctrl-C
    assert _bare(transcript.messages[-1]) == {"role": "assistant", "content": f"Once upon\n\n{STOPPED}"}
    assert await _collect(model, "say NEXT-OK") == "NEXT-OK"
    # the next request answers the stopped message, so the model is not asked it again
    assert _roles(story.requests[1]) == ["user", "assistant", "user"]
    assert story.requests[1][-1]["content"] == "say NEXT-OK"


async def test_a_reply_caninputed_while_its_model_waits_answers_its_message_too() -> None:
    story, transcript = _Story(), MemoryTranscript()
    model = LoopModel(story, as_tool(Shouting()), transcript, Confined())
    shown: list[Json] = []

    async def run() -> None:
        async for event in model.reply("tell me a long story"):
            shown.append(event)

    task = asyncio.create_task(run())
    while not shown:
        await asyncio.sleep(0)
    task.cancel()  # cancelled inside the model step, where it waits for the stream
    await asyncio.gather(task, return_exceptions=True)
    assert _roles(transcript.messages) == ["tools", "user", "assistant"]
    assert transcript.messages[-1]["content"].endswith(STOPPED)
    await _collect(model, "say NEXT-OK")
    assert _roles(story.requests[1]) == ["user", "assistant", "user"]


async def test_a_reply_stopped_before_it_said_anything_is_still_answered() -> None:
    class Silent:
        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            await asyncio.Event().wait()
            yield text("never")  # pragma: no cover

    transcript = MemoryTranscript()

    async def run() -> None:
        async for _ in LoopModel(Silent(), as_tool(Shouting()), transcript, Confined()).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert _bare(transcript.messages[-1]) == {"role": "assistant", "content": STOPPED}


async def test_a_call_that_is_not_an_input_is_answered_as_text_and_runs_nothing() -> None:
    """A model (a small local one, say) that invents a tool, or calls python without code (its
    spec's `required`), reads why in the result; nothing reaches the Python process, nobody is asked, and
    the reply carries on."""
    shouting = Shouting()
    scripted = Scripted([call("c1", "read_file", path="a"), call("c2", "python", source="x")], [text("ok")])
    transcript = MemoryTranscript()
    assert await _collect(LoopModel(scripted, as_tool(shouting), transcript, Confined()), "go") == "ok"
    results = [m["content"] for m in transcript.messages if m["role"] == "tool"]
    assert results == [
        "error: there is no tool named 'read_file'; your tools are python",
        "error: python needs `code`",
    ]
    assert shouting.ran == []


def test_only_a_python_call_with_code_is_a_input() -> None:
    assert refusal({"id": "c", "name": "python", "input": {"code": "1"}}, ["python"]) is None
    assert malformed(PYTHON, {"code": 1}) == "error: python takes `code` as a string, not an integer"
    assert malformed(PYTHON, {"code": True}) == "error: python takes `code` as a string, not a boolean"
    assert malformed(PYTHON, ["x"]) == "error: python takes an object of named arguments, not an array"
    assert malformed(PYTHON, {"code": "1", "extra": None}) is None  # the tool checks the rest
    assert refusal({"id": "c", "name": "write_file", "input": {"code": "1"}}, ["python"]) == (
        "error: there is no tool named 'write_file'; your tools are python"
    )


async def test_memory_s_asides_ride_on_the_input_s_result_and_the_person_sees_each_named() -> None:
    """Each function is given the input's code, result and touched files; its aside goes to the
    model after the result, sorted with the others; one that fails says so and the rest still
    say theirs; an input that never ran asks none of them."""
    given: list[Json] = []

    def rules(input: Json) -> str:
        given.append(input)
        return "Zebra rule: for /p/a.py.\nWhole rule text."

    def quiet(input: Json) -> str:
        return ""

    def broken(input: Json) -> str:
        raise RuntimeError("no rules file")

    asides: Hooks[Callable[[Json], str]] = Hooks()
    for fn in (rules, quiet, broken):
        asides.add(fn)
    transcript = MemoryTranscript()
    scripted = Scripted([call("c1", "python", code="a"), call("c2", "nope", code="b")], [text("done")])
    events = [
        e
        async for e in LoopModel(scripted, as_tool(Shouting()), transcript, Confined(), asides=asides).reply(
            "go"
        )
    ]
    assert given == [
        {"name": "python", "input": {"code": "a"}, "result": "A", "touched": ("/p/a.py",)}
    ]  # c2 never ran
    told = [m["content"] for m in transcript.messages if m["role"] == "tool"]
    assert told[0].startswith("A\n\n(bh-02 could not make an aside with ")
    assert "broken: no rules file. The call's result is whole; tell the person" in told[0]
    assert told[0].endswith("failed.)\n\nZebra rule: for /p/a.py.\nWhole rule text.")
    assert told[1].startswith("error: there is no tool named 'nope'") and "Zebra" not in told[1]
    results = [e for e in events if e["type"] == "tool_result"]
    assert results[0]["content"] == "A"  # the person sees the input's own output
    shown = [e["text"] for e in events if e["type"] == "note"]
    assert "told the model with this result: Zebra rule: for /p/a.py." in shown


async def test_the_asides_told_with_a_result_are_kept_on_its_entry_beside_what_the_model_reads() -> None:
    """The model reads the result, then the asides, sorted, each after a blank line, then any change
    in its instructions; the entry also keeps the asides alone, as a list (`asides`), so a row reading
    a resumed transcript finds what it told without searching the text. Every `tool` entry the loop
    writes has one, `[]` for an input told nothing or never run."""
    where = _Where()

    class Extending(Shouting):
        async def run(self, code: str) -> str:
            where.text_now = "in /b"  # the input changed the instructions
            return await super().run(code)

    functions: Hooks[Callable[[Json], str]] = Hooks()
    for said in ("Zebra: another row's aside.", "From a.md, a rule for *.py:\n\nOne.\n\n(Two.)", ""):
        functions.add(lambda input, said=said: said)
    transcript = MemoryTranscript()
    scripted = Scripted(
        [call("c1", "python", code="a"), call("c2", "nope", code="b"), call("c3", "python", code="c")],
        [text("done")],
    )
    loop = LoopModel(
        scripted, as_tool(Extending()), transcript, Person(True, False), system=where, asides=functions
    )
    await _collect(loop, "go")
    tools = [m for m in transcript.messages if m["role"] == "tool"]
    asides = ["From a.md, a rule for *.py:\n\nOne.\n\n(Two.)", "Zebra: another row's aside."]
    told = "\n\n".join(["A", *asides, changes("in /a", "in /b")])
    assert _bare(tools[0]) == {"role": "tool", "content": told, "call_id": "c1", "asides": asides}
    assert scripted.requests[1][0][-3] == tools[0]  # the model is sent the entry, which it reads as content
    assert [m["asides"] for m in tools[1:]] == [[], []]  # a call that can't run, and one declined
    assert [m["content"] for m in tools[1:]] == [refusal(call("c2", "nope", code="b"), ["python"]), DECLINED]


class _Ticker:
    """A task that counts while the event loop is free to run it, every 10 ms."""

    def __init__(self) -> None:
        self.ticks = 0
        self._task: asyncio.Task[None] | None = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(0.01)
            self.ticks += 1

    def __enter__(self) -> _Ticker:
        self._task = asyncio.create_task(self._run())
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._task is not None
        self._task.cancel()


async def test_the_prompt_and_memory_are_read_off_the_event_loop_which_keeps_running() -> None:
    """The TUI runs on cordis's event loop: a section function that walks a big tree, or a
    asides function that reads rule files, must not freeze it. Each runs in a worker thread,
    and the event loop goes on ticking while it does."""
    during: list[int] = []  # ticks counted while each slow call ran
    threads: list[int] = []

    def slowly(ticker: _Ticker) -> None:
        threads.append(threading.get_ident())
        before = ticker.ticks
        time.sleep(0.3)
        during.append(ticker.ticks - before)

    with _Ticker() as ticker:

        class Slow:
            def text(self) -> str:
                slowly(ticker)
                return "in /a"

        def rules(input: Json) -> str:
            slowly(ticker)
            return "a rule"

        asides: Hooks[Callable[[Json], str]] = Hooks()
        asides.add(rules)
        scripted = Scripted([call("c1", "python", code="a")], [text("done")])
        loop = LoopModel(
            scripted, as_tool(Shouting()), MemoryTranscript(), Confined(), system=Slow(), asides=asides
        )
        assert await _collect(loop, "go") == "done"
    assert len(during) == 3  # the prompt with the message, asides, the prompt with the result
    assert all(ticks >= 10 for ticks in during), during  # ~30 each when the loop runs free; 0 blocked
    assert threading.get_ident() not in threads


async def test_a_reply_stopped_while_an_input_s_asides_are_made_answers_it_with_them() -> None:
    started = threading.Event()

    def slow(input: Json) -> str:
        started.set()
        time.sleep(0.2)
        return "a rule"

    asides: Hooks[Callable[[Json], str]] = Hooks()
    asides.add(slow)
    shouting, transcript = Shouting(), MemoryTranscript()
    scripted = Scripted([call("c1", "python", code="a"), call("c2", "python", code="b")])
    task = asyncio.create_task(
        _collect(LoopModel(scripted, as_tool(shouting), transcript, Confined(), asides=asides), "go")
    )
    while not started.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    tools = [m for m in transcript.messages if m["role"] == "tool"]
    assert [m["call_id"] for m in tools] == ["c1", "c2"]
    assert tools[0]["content"] == "A\n\na rule"  # it ran to the end: its result and its aside
    assert tools[0]["asides"] == ["a rule"]
    assert tools[1]["content"].startswith("not run") and tools[1]["asides"] == []
    assert shouting.ran == ["a"]


async def test_a_reply_stopped_while_the_prompt_is_read_keeps_the_message_answered_as_stopped() -> None:
    started = threading.Event()

    class Slow:
        def text(self) -> str:
            started.set()
            time.sleep(0.2)
            return "in /a"

    transcript = MemoryTranscript()
    loop = LoopModel(
        Scripted([text("never")]),
        as_tool(Shouting()),
        transcript,
        Confined(),
        system=Slow(),
        clock=on("2026-10-07"),
    )
    task = asyncio.create_task(_collect(loop, "go"))
    while not started.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert tuple(m for m in transcript.messages if m["role"] != "tools") == (
        {
            "role": "user",
            "content": "(Today's date: 2026-10-07.)\n\ngo",
            "today": "2026-10-07",
            "at": stamp(noon("2026-10-07")),
        },
        {"role": "assistant", "content": STOPPED},  # the model was never asked: no step to record
    )


async def test_the_date_is_told_with_a_conversation_s_first_message_and_the_first_of_each_day(
    tmp_path: Path,
) -> None:
    """Not in the prompt, which would then change every midnight: told on the person's message,
    and kept on its entry as `today`, so a resumed session (the transcript is a file) does not
    tell it again the same day, and a cleared one (an empty transcript) does."""
    day = ["2026-10-07"]
    clock = Clock(now=lambda: noon(day[-1]))
    path = str(tmp_path / "transcript.jsonl")
    transcript = FileTranscript(path)
    scripted = Scripted([text("one")], [text("two")], [text("three")], [text("four")], [text("five")])
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined(), clock=clock), "first")
    await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined(), clock=clock), "second")
    day.append("2026-10-08")  # past midnight
    model = LoopModel(scripted, as_tool(Shouting()), transcript, Confined(), clock=clock)
    await _collect(model, "third")
    await _collect(
        LoopModel(scripted, as_tool(Shouting()), FileTranscript(path), Confined(), clock=clock),
        "fourth",
    )
    one, two = stamp(noon("2026-10-07")), stamp(noon("2026-10-08"))
    assert [m for m in FileTranscript(path).messages if m["role"] == "user"] == [
        {"role": "user", "content": "(Today's date: 2026-10-07.)\n\nfirst", "today": "2026-10-07", "at": one},
        {"role": "user", "content": "second", "at": one},
        {"role": "user", "content": "(Today's date: 2026-10-08.)\n\nthird", "today": "2026-10-08", "at": two},
        {"role": "user", "content": "fourth", "at": two},  # resumed the same day
    ]
    cleared = MemoryTranscript()
    await _collect(LoopModel(scripted, as_tool(Shouting()), cleared, Confined(), clock=clock), "after /clear")
    assert cleared.messages[1]["content"] == "(Today's date: 2026-10-08.)\n\nafter /clear"


async def test_on_a_new_day_with_new_instructions_the_date_comes_first_then_what_changed() -> None:
    where, day = _Where(_SHOUT), ["2026-10-07"]
    clock = Clock(now=lambda: noon(day[-1]))
    scripted, transcript = Scripted([text("one")], [text("two")]), MemoryTranscript()
    model = LoopModel(scripted, as_tool(_Guided()), transcript, Confined(), system=where, clock=clock)
    await _collect(model, "first")
    where.text_now, day[0] = "in /b", "2026-10-08"
    events = [e async for e in model.reply("second")]
    sent = scripted.requests[1][0][-1]
    assert sent["content"].startswith("(Today's date: 2026-10-08.)\n\n(bh-02: your instructions have changed")
    assert sent["content"].endswith("(End of what changed.)\n\nsecond") and sent["today"] == "2026-10-08"
    assert scripted.requests[1][0][0] == scripted.requests[0][0][0]  # the prompt it began with
    assert [e["text"] for e in events if e["type"] == "note"] == [
        "told the model its instructions changed since the conversation began"
    ]


async def test_a_reply_stopped_after_an_input_s_asides_were_made_still_tells_them() -> None:
    """An asides function marks what it told as told, so a stop while the prompt is read after
    the input must not lose its aside: the call is answered with its result and the aside."""
    reading = threading.Event()

    class SlowSecond:
        reads = 0

        def text(self) -> str:
            self.reads += 1
            if self.reads == 2:  # the reading after the input
                reading.set()
                time.sleep(0.2)
            return "in /a"

    asides: Hooks[Callable[[Json], str]] = Hooks()
    asides.add(lambda input: "a rule, told once")
    transcript = MemoryTranscript()
    loop = LoopModel(
        Scripted([call("c1", "python", code="a")]),
        as_tool(Shouting()),
        transcript,
        Confined(),
        system=SlowSecond(),
        asides=asides,
    )
    task = asyncio.create_task(_collect(loop, "go"))
    while not reading.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    tools = [m["content"] for m in transcript.messages if m["role"] == "tool"]
    assert tools == ["A\n\na rule, told once"]


class _Held:
    """A `system` whose every reading waits until `release` is set (5 s at most), keeping count
    of the readings begun, how many run now and the most that ran at once, and the threads they
    ran in. The first `failing` readings raise once released."""

    def __init__(self, *, failing: int = 0) -> None:
        self.release = threading.Event()
        self.failing = failing
        self.begun = 0
        self.running = 0
        self.most = 0
        self.threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def text(self) -> str:
        with self._lock:
            self.begun += 1
            failing = self.begun <= self.failing
            self.running += 1
            self.most = max(self.most, self.running)
            self.threads.append(threading.current_thread())
        self.release.wait(5)
        with self._lock:
            self.running -= 1
        if failing:
            raise OSError("the project went away")
        return "in /a"


async def test_replies_stopped_over_and_over_while_the_prompt_is_read_leave_one_reading_running() -> None:
    """Ctrl-C again and again while a slow section function reads the project: a reading can't
    be stopped part-way, so each new reply waits for the one a stopped reply left running
    instead of starting its own beside it. Each stop used to leave one more thread reading."""
    held, transcript = _Held(), MemoryTranscript()
    loop = LoopModel(Scripted([text("at last")]), as_tool(Shouting()), transcript, Confined(), system=held)
    try:
        for n in range(4):
            task = asyncio.create_task(_collect(loop, f"go {n}"))
            while not held.begun:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)  # time enough for this reply's own reading to begin, were it to
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert (held.begun, held.running, held.most) == (1, 1, 1)
    finally:
        held.release.set()
    assert await _collect(loop, "go on") == "at last"
    assert (held.begun, held.most) == (2, 1)  # read afresh, once the one left behind was done
    replies = [m["content"] for m in transcript.messages if m["role"] == "assistant"]
    assert replies == [STOPPED] * 4 + ["at last"]  # every stopped message answered as stopped


async def test_loops_sharing_an_executor_leave_one_reading_running_however_often_the_loop_reloads() -> None:
    """/clear and /model reload the loop, a new `LoopModel` each time, but not `system`, whose
    caches take no lock, nor the `executor` row the loop reads the prompt on: a new loop waits
    for the reading the last one's stopped reply left running, rather than starting its own
    beside it. A loop that kept the call in flight itself started one more reading per reload."""
    held, shared = _Held(), OneAtATime()

    def reloaded(said: str) -> LoopModel:
        """The loop as the `loop` row builds it again, over the same `system` and `executor`."""
        return LoopModel(
            Scripted([text(said)]),
            as_tool(Shouting()),
            MemoryTranscript(),
            Confined(),
            system=held,
            executor=shared,
        )

    try:
        for n in range(4):
            task = asyncio.create_task(_collect(reloaded("never"), f"go {n}"))
            while not held.begun:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)  # time enough for this reply's own reading to begin, were it to
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert (held.begun, held.running, held.most) == (1, 1, 1)
    finally:
        held.release.set()
    assert await _collect(reloaded("at last"), "go on") == "at last"
    assert (held.begun, held.most) == (2, 1)  # read afresh, once the one left behind was done


async def test_a_stopped_reply_s_reading_that_fails_costs_the_next_reply_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nobody waits for what a reading a stopped reply left running says, nor for what it
    raised: the next reply reads afresh, and nothing is logged (an error asyncio logged would
    reach the terminal once the app has let go of it)."""
    held = _Held(failing=1)  # the one left behind fails; the next reads
    loop = LoopModel(
        Scripted([text("fine")]), as_tool(Shouting()), MemoryTranscript(), Confined(), system=held
    )
    task = asyncio.create_task(_collect(loop, "go"))
    while not held.begun:
        await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    held.release.set()
    assert await _collect(loop, "again") == "fine"
    assert held.begun == 2
    del task
    gc.collect()  # a future whose exception was never retrieved says so as it is collected
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_a_reading_a_stopped_reply_left_running_does_not_hold_bh_02_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bh-02 runs in `asyncio.run`, which joins the default executor's threads as it ends, and
    the interpreter joins them again at exit: a reading a stopped reply left there kept bh-02
    from leaving until it finished. The loop reads in a daemon thread of its own, which neither
    waits for, and whose answer to an event loop that has closed meanwhile goes nowhere."""
    escaped: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: escaped.append(args.exc_value))
    held = _Held()

    async def stop_one_reply() -> None:
        loop = LoopModel(Scripted(), as_tool(Shouting()), MemoryTranscript(), Confined(), system=held)
        task = asyncio.create_task(_collect(loop, "go"))
        while not held.begun:
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(stop_one_reply())
        assert held.running == 1  # asyncio.run ended without waiting for it
        assert [thread.daemon for thread in held.threads] == [True]  # nor will the interpreter
    finally:
        held.release.set()
    held.threads[0].join(5)
    assert not held.threads[0].is_alive() and escaped == []


class _Flushing(MemoryTranscript):
    """A transcript that writes behind the loop, as `FileTranscript` does: what the loop has
    appended when each flush came, and no more than that was in it."""

    def __init__(self) -> None:
        super().__init__()
        self.flushed: list[int] = []

    async def flush(self) -> None:
        await asyncio.sleep(0)  # the writes take their turn, as a thread's do
        self.flushed.append(len(self.messages))


async def test_the_transcript_is_flushed_once_a_reply_that_answered_has_appended_its_last_entry() -> None:
    transcript = _Flushing()
    model = LoopModel(Scripted([text("hi")]), as_tool(Shouting()), transcript, Confined())
    events = model.reply("go")
    assert (await anext(events)) == text("hi")
    assert (
        transcript.flushed == []
    )  # not before the reply is done: a flush per entry would be a write per entry
    assert [e async for e in events] == [{"type": "stop", "reason": "answered"}]
    assert transcript.flushed == [len(transcript.messages)] == [3]


async def test_the_transcript_is_flushed_after_a_reply_whose_model_failed() -> None:
    transcript = _Flushing()
    model = LoopModel(Scripted(), as_tool(Shouting()), transcript, Confined())
    with pytest.raises(ScriptError, match="ran out"):
        await _collect(model, "hi")
    assert _bare(transcript.messages[-1]) == {"role": "assistant", "content": FAILED}
    assert transcript.flushed == [len(transcript.messages)]  # the entry the failure appended too


async def test_the_transcript_is_flushed_after_a_reply_the_ui_closed_mid_stream() -> None:
    transcript = _Flushing()
    reply = LoopModel(_Story(), as_tool(Shouting()), transcript, Confined()).reply("tell me a long story")
    assert (await anext(reply)) == text("Once upon")
    await reply.aclose()  # Ctrl-C: chat closes the reply, which awaits the flush before it ends
    assert transcript.messages[-1]["content"].endswith(STOPPED)
    assert transcript.flushed == [len(transcript.messages)]


async def test_the_transcript_is_flushed_after_a_reply_cancelled_with_a_call_running() -> None:
    class Hanging(Shouting):
        async def run(self, code: str) -> str:
            await asyncio.Event().wait()
            return "never"  # pragma: no cover

    transcript = _Flushing()
    scripted = Scripted([call("c1", "python", code="a"), call("c2", "python", code="b")])

    async def run() -> None:
        async for _ in LoopModel(scripted, as_tool(Hanging()), transcript, Confined()).reply("go"):
            pass

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert [m["role"] for m in transcript.messages][-2:] == ["tool", "tool"]  # both answered
    assert transcript.flushed == [len(transcript.messages)]  # after the answers the stop appended


class _Checking(_Flushing):
    """A transcript whose file can be replaced under it, as `FileTranscript` is: what the loop had
    appended each time it was asked to `check`, and `refuses` what it is told of a replaced file."""

    def __init__(self, *, refuses: Exception | None = None) -> None:
        super().__init__()
        self.checked: list[int] = []
        self._refuses = refuses

    async def check(self) -> None:
        await asyncio.sleep(0)  # the writer's look takes its turn, as a thread's does
        self.checked.append(len(self.messages))
        if self._refuses is not None:
            raise self._refuses


async def test_a_reply_asks_the_transcript_to_check_its_file_first_and_flushes_it_once() -> None:
    """The check is the first thing a reply does, before it appends anything, and it is no flush:
    the flush stays one, at the end of the reply, however many steps the reply has."""
    transcript = _Checking()
    scripted = Scripted([text("let me "), call("c1", "python", code="a")], [text("done")], [text("again")])
    model = LoopModel(scripted, as_tool(Shouting()), transcript, Confined())
    assert await _collect(model, "go") == "let me done"
    first = len(transcript.messages)
    assert transcript.checked == [0]  # once, before the reply appended anything
    assert transcript.flushed == [first]  # once, with every entry of the reply in
    assert await _collect(model, "and again") == "again"
    assert transcript.checked == [0, first]  # the next reply checks as the conversation stood
    assert transcript.flushed == [first, len(transcript.messages)]


async def test_a_transcript_that_refuses_at_the_check_is_never_asked_a_model_step_or_an_entry() -> None:
    refusal = OSError(errno.ESTALE, "the file was replaced")
    transcript = _Checking(refuses=refusal)
    scripted = Scripted([text("an answer nobody should read")])
    model = LoopModel(scripted, as_tool(Shouting()), transcript, Confined())
    with pytest.raises(OSError, match="the file was replaced"):
        await _collect(model, "go")
    assert scripted.requests == [] and transcript.messages == ()
    assert transcript.checked == [0]


async def test_a_transcript_that_keeps_the_conversation_in_memory_needs_no_flush() -> None:
    assert (
        await _collect(
            LoopModel(Scripted([text("hi")]), as_tool(Shouting()), MemoryTranscript(), Confined()), "go"
        )
        == "hi"
    )


class _SlowDisk:
    """Every write to a file takes its time, on the thread that makes it."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
        self.threads: set[int] = set()
        real = os.write

        def write(fd: int, data: bytes | memoryview) -> int:
            self.threads.add(threading.get_ident())
            time.sleep(seconds)
            return real(fd, data)

        monkeypatch.setattr(os, "write", write)


async def test_a_reply_over_a_slow_disk_ends_with_every_entry_in_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writes are off the event loop and still behind it when the model has finished: it is
    the flush at the end of the reply that makes the file whole, so whatever reads it next (a
    /clear, a /compact, a resume) finds every entry, the last included."""
    path = tmp_path / "transcript.jsonl"
    disk = _SlowDisk(monkeypatch, 0.05)
    scripted = Scripted([text("let me "), call("c1", "python", code="a")], [text("done")])
    async with FileTranscript(str(path)) as transcript:
        await _collect(LoopModel(scripted, as_tool(Shouting()), transcript, Confined()), "go")
        entries = [json.loads(line) for line in path.read_text().splitlines()]
        assert entries == list(transcript.messages) and len(entries) == 5
    assert threading.get_ident() not in disk.threads  # none of it was written on the event loop


async def test_a_reply_costs_the_event_loop_no_stat_of_the_file_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check a reply makes of the file is the writing thread's stat: the event loop is free
    while it runs and makes no stat of its own, as it makes no write."""
    path = tmp_path / "transcript.jsonl"
    path.touch()  # a file there to look at: a resumed session's, or the one an earlier reply made
    seen: set[int] = set()
    real = os.stat

    def stat(file: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if str(file) == str(path):
            seen.add(threading.get_ident())
        return real(file, *args, **kwargs)

    async with FileTranscript(str(path)) as transcript:  # made before the stat is watched: its own
        monkeypatch.setattr(os, "stat", stat)
        await _collect(LoopModel(Scripted([text("hi")]), as_tool(Shouting()), transcript, Confined()), "go")
        monkeypatch.undo()
    assert seen and threading.get_ident() not in seen


async def test_a_reply_whose_entries_could_not_be_written_raises_it_rather_than_end_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(fd: int, data: bytes | memoryview) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "write", full)
    transcript = FileTranscript(str(tmp_path / "transcript.jsonl"))
    model = LoopModel(Scripted([text("hi")]), as_tool(Shouting()), transcript, Confined())
    with pytest.raises(OSError, match="No space left"):
        await _collect(model, "go")
    with pytest.raises(OSError, match="No space left"):  # and so does the next message's first entry
        transcript.append({"role": "user", "content": "again"})
    monkeypatch.undo()  # room again: nothing after the failed write is written, the file closes
    with pytest.raises(OSError, match="No space left"):
        async with transcript:
            pass
