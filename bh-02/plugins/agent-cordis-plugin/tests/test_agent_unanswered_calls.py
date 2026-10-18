"""A call a crash left unanswered is answered when the session resumes (decision-0009, TASK-0142).

The loop appends a step's assistant entry, with its calls, before it runs them, and a reply that ends
answers every call. A process that dies mid-call answers none, so the transcript a resume reads holds
a call with no result after it, which a provider rejects or the model answers again. The next reply
answers such a call before anything else, so the conversation is whole before its first request."""

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_cordis_plugin import Answer, FileTranscript, LoopModel, ToolBroker
from agent_cordis_plugin.loop import request_for
from agent_cordis_plugin.testing import Stepped

type Json = Mapping[str, Any]

START = "2026-10-18T03:47:12.345Z"  # what `Stepped` reads before it is moved
PYTHON: Json = {
    "name": "python",
    "description": "Run Python.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
}


class Recording:
    """A `model` that answers every request with `fine`, and keeps the messages it was sent."""

    def __init__(self) -> None:
        self.requests: list[tuple[Json, ...]] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.requests.append(tuple(messages))
        yield {"type": "text", "text": "fine"}


class Approved:
    async def approve(self, question: Json) -> Answer:
        return Answer.YES


class Prompt:
    """A `system` whose prompt reads the same as the one the conversation began with."""

    def text(self) -> str:
        return "the prompt"


def conversation() -> list[Json]:
    """The entries a conversation begins with, as the loop writes them."""
    return [
        {"role": "system", "content": "the prompt"},
        {"role": "tools", "tools": [dict(PYTHON)]},
        {"role": "user", "content": "find x and y", "at": START},
    ]


def asking(*ids: str) -> Json:
    """The assistant entry of a step that asked for the calls `ids`, as the loop writes it."""
    calls = [{"id": id, "name": "python", "input": {"code": id}} for id in ids]
    return {"role": "assistant", "content": "on it", "tool_calls": calls, "step": {"at": START}}


def answered(id: str) -> Json:
    """The tool entry of call `id` that ran: what the loop writes for it."""
    record = {"at": START, "answer": "unasked", "took": 0.25}
    return {"role": "tool", "content": id.upper(), "call_id": id, "asides": [], "call": record}


def cut(*ids: str, answered_ids: Sequence[str] = ()) -> list[Json]:
    """A transcript a process died in, mid-call: a step asked for the calls `ids` and only
    `answered_ids` have their result."""
    return [*conversation(), asking(*ids), *(answered(id) for id in answered_ids)]


def resumed(tmp_path: Path, old: Sequence[Json]) -> tuple[FileTranscript, Stepped]:
    """A transcript over a file holding `old`, as a resume reads it, and the clock it is replied on."""
    path = tmp_path / "transcript.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in old))
    return FileTranscript(str(path)), Stepped()


async def reply(transcript: FileTranscript, stepped: Stepped, model: Recording, message: str) -> None:
    broker = ToolBroker()

    async def run(input: Json) -> Json:
        return {"content": str(input["code"]).upper()}

    broker.register(PYTHON, run)
    loop = LoopModel(model, broker, transcript, Approved(), system=Prompt(), clock=stepped.clock)
    assert [event async for event in loop.reply(message)]


def roles(messages: Sequence[Json]) -> list[str]:
    return [str(m["role"]) for m in messages]


async def test_a_resumed_conversation_answers_the_call_a_crash_left_before_the_first_request(
    tmp_path: Path,
) -> None:
    """One call has its result and one does not: the request the model receives has a result for
    each, in the calls' order, the missing one saying bh-02 stopped before the call finished."""
    old = cut("c1", "c2", answered_ids=["c1"])
    transcript, stepped = resumed(tmp_path, old)
    stepped.advance(600.0)  # the session is resumed ten minutes later
    model = Recording()
    await reply(transcript, stepped, model, "carry on")
    (sent,) = model.requests
    assert roles(sent) == ["system", "user", "assistant", "tool", "tool", "user"]
    assert [c["id"] for c in sent[2]["tool_calls"]] == [m["call_id"] for m in sent[3:5]] == ["c1", "c2"]
    assert sent[3] == old[-1]  # the result it had is as it was
    lost = sent[4]
    assert lost["content"].startswith("interrupted:")
    assert "bh-02 stopped before this call finished" in lost["content"]
    assert lost["content"].endswith("it may have partly run")
    assert lost["asides"] == []
    # when the session resumed, and nothing more: no answer, no wait, no run time was recorded
    assert lost["call"] == {"at": "2026-10-18T03:57:12.345Z"}
    assert sent[5]["content"].endswith("carry on")


async def test_every_call_of_the_step_with_no_result_is_answered_in_the_calls_order(tmp_path: Path) -> None:
    transcript, stepped = resumed(tmp_path, cut("c1", "c2", "c3"))
    model = Recording()
    await reply(transcript, stepped, model, "carry on")
    (sent,) = model.requests
    results = [m for m in sent if m["role"] == "tool"]
    assert [m["call_id"] for m in results] == ["c1", "c2", "c3"]
    assert all(m["content"].startswith("interrupted:") for m in results)
    assert roles(sent)[-5:] == ["assistant", "tool", "tool", "tool", "user"]  # right after the step's entry


async def test_the_answers_are_kept_in_the_file_once_and_a_later_reply_adds_none(tmp_path: Path) -> None:
    old = cut("c1", "c2", answered_ids=["c1"])
    transcript, stepped = resumed(tmp_path, old)
    await reply(transcript, stepped, Recording(), "carry on")
    kept = list(FileTranscript(str(tmp_path / "transcript.jsonl")).messages)
    assert kept == list(transcript.messages)  # flushed: what the next resume reads
    assert [m["call_id"] for m in kept if m["role"] == "tool"] == ["c1", "c2"]
    again = Recording()
    await reply(transcript, stepped, again, "and now?")
    assert [m["call_id"] for m in transcript.messages if m["role"] == "tool"] == ["c1", "c2"]
    assert [m["call_id"] for m in again.requests[0] if m["role"] == "tool"] == ["c1", "c2"]


@pytest.mark.parametrize(
    "old",
    [
        pytest.param(cut("c1", "c2", answered_ids=["c1", "c2"]), id="every result written, no step after"),
        pytest.param(
            [*cut("c1", answered_ids=["c1"]), {"role": "assistant", "content": "x is X"}],
            id="answered",
        ),
        pytest.param(conversation(), id="no calls yet"),
        pytest.param(
            [*conversation(), {"role": "assistant", "content": "nothing to run"}], id="a step with no calls"
        ),
    ],
)
async def test_a_whole_transcript_is_sent_unchanged_and_nothing_is_added_to_it(
    tmp_path: Path, old: list[Json]
) -> None:
    transcript, stepped = resumed(tmp_path, old)
    model = Recording()
    await reply(transcript, stepped, model, "carry on")
    new, answer = transcript.messages[len(old) :]  # the message, and the model's answer: nothing else
    assert new["role"] == "user" and new["content"].endswith("carry on") and answer["content"] == "fine"
    (sent,) = model.requests
    assert list(sent) == [*request_for(old), new]  # the old conversation bit for bit, then the message
    assert transcript.messages[: len(old)] == tuple(old)
    assert not any(str(m.get("content", "")).startswith("interrupted:") for m in transcript.messages)
