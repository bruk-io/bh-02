"""`bh_02.trajectory` reads what the agent plugin writes: bh_02 imports no plugin, so it declares the
entries' shape of its own, and this test holds the two to one. A transcript is written by the plugin's
own loop (over a fake model and a clock the model moves), `/compact`'s rewrite and its own record
builders, then read back from the bytes."""

import datetime
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_cordis_plugin import Answer, FileTranscript, LoopModel, ToolBroker, rewrite, seeded
from agent_cordis_plugin.records import call_record, nested_record, step_record
from agent_cordis_plugin.testing import Stepped
from bh_02.trajectory import Transcript, rendered, trajectory

type Json = Mapping[str, Any]

PYTHON: Json = {
    "name": "python",
    "description": "Run Python.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
}
SETTINGS: Json = {"model": "work/opus", "provider": "claude-code", "max_tokens": 4096, "temperature": 0.5}
UTC = datetime.UTC


class Model:
    """A model that plays one scripted step per request, the clock moving by each chunk's seconds."""

    settings = SETTINGS

    def __init__(self, stepped: Stepped, *steps: Sequence[tuple[float, Json]]) -> None:
        self.stepped, self.steps = stepped, list(steps)

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        for seconds, chunk in self.steps.pop(0):
            self.stepped.advance(seconds)
            yield chunk


class Person:
    """An approval that takes 4.2 seconds to say yes."""

    def __init__(self, stepped: Stepped) -> None:
        self.stepped = stepped

    async def approve(self, question: Json) -> Answer:
        self.stepped.advance(4.2)
        return Answer.YES


def tools(stepped: Stepped) -> ToolBroker:
    broker = ToolBroker()

    async def run(input: Json) -> Json:
        stepped.advance(0.8)
        return {"content": str(input["code"]).upper()}

    broker.register(PYTHON, run)
    return broker


def read(path: Path, name: str) -> Transcript:
    return Transcript(None, name, path.stat().st_mtime, path.read_bytes())


async def test_a_conversation_the_loop_wrote_and_a_compact_began_is_read_back_with_every_record(
    tmp_path: Path,
) -> None:
    stepped, path = Stepped(), tmp_path / "transcript.jsonl"
    usage = {
        "type": "usage",
        "input_tokens": 1200,
        "output_tokens": 212,
        "cost_usd": 0.0312,
        "model": "claude-opus-5-5",
    }
    async with FileTranscript(str(path)) as transcript:
        model = Model(
            stepped,
            [
                (1.2, {"type": "text", "text": "let me "}),
                (0.0, {"type": "tool_call", "id": "c1", "name": "python", "input": {"code": "x"}}),
                (3.4, usage),
            ],
            [(0.5, {"type": "text", "text": "done"})],
        )
        loop = LoopModel(model, tools(stepped), transcript, Person(stepped), clock=stepped.clock)
        _ = [event async for event in loop.reply("fix it")]
    # /compact: the summary step's record, and the file replaced by the seed, the old one kept
    summary = step_record(
        stepped.now(), 0.0, 2.0, 9.0, [{**usage, "output_tokens": 400, "cost_usd": 0.5}], SETTINGS, "fixed"
    )
    rewrite(str(path), seeded("the summary", "the todo list", summary))
    async with FileTranscript(str(path)) as transcript:
        model = Model(stepped, [(0.25, {"type": "text", "text": "carrying on"})])
        loop = LoopModel(model, tools(stepped), transcript, Person(stepped), clock=stepped.clock)
        _ = [event async for event in loop.reply("next")]

    backup = path.with_name("transcript.jsonl.bak")
    laid = trajectory([read(path, path.name), read(backup, backup.name)])
    first, second = laid.conversations
    assert first.name == "transcript.jsonl.bak" and second.name == "transcript.jsonl"

    reply = first.replies[0]
    assert (reply.message, reply.at) == (
        "fix it",
        datetime.datetime(2026, 10, 18, 3, 47, 12, 345000, tzinfo=UTC),
    )
    step, last = reply.items
    assert step.at == datetime.datetime(2026, 10, 18, 3, 47, 12, 345000, tzinfo=UTC)
    assert (step.first_chunk, step.took, step.model) == (1.2, 4.6, "claude-opus-5-5")
    assert (step.usage.input_tokens, step.usage.output_tokens, step.usage.cost_usd) == (1200, 212, 0.0312)
    assert (step.settings.model, step.settings.provider, step.settings.max_tokens) == (
        "work/opus",
        "claude-code",
        4096,
    )
    assert last.settings is None  # recorded when new to the conversation only
    (call,) = step.calls
    assert (call.tool, call.recorded, call.answer, call.waited, call.took) == (
        "python",
        True,
        "yes",
        4.2,
        0.8,
    )

    assert second.seed is not None and second.seed.keep == "the todo list"
    assert second.seed.step is not None
    assert (second.seed.step.first_chunk, second.seed.step.took, second.seed.step.usage.cost_usd) == (
        2.0,
        9.0,
        0.5,
    )
    assert [r.message for r in second.replies] == ["next"]
    shown = [line.text for line in rendered(laid, UTC)]
    assert any("begun by /compact, asked to keep: the todo list" in text for text in shown)
    assert any(text.strip().startswith("summary step") and "cost $0.5000" in text for text in shown)


def test_the_records_the_plugin_builds_for_a_call_with_nested_calls_and_a_sub_agent_are_read() -> None:
    at = datetime.datetime(2026, 10, 18, 3, 47, 17, tzinfo=UTC)
    inner = nested_record("agent", call_record(at, Answer.UNASKED, None, 12.0, "general-1", ()))
    outer = call_record(at, Answer.NO, 1.5, None, None, [inner])
    entries = [
        {"role": "user", "content": "go", "at": "2026-10-18T03:47:12.000Z"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "python", "input": {}}],
            "step": step_record(at, 0.0, 0.1, 0.2, [], None, "listed"),
        },
        {"role": "tool", "content": "denied", "call_id": "c1", "asides": [], "call": outer},
    ]
    data = b"".join(json.dumps(entry).encode() + b"\n" for entry in entries)
    child = b'{"role": "user", "content": "count", "at": "2026-10-18T03:47:18.000Z"}\n'
    laid = trajectory(
        [
            Transcript(None, "transcript.jsonl", 0.0, data),
            Transcript("general-1", "transcript.jsonl", 0.0, child),
        ]
    )
    ((call,),) = [item.calls for item in laid.conversations[0].replies[0].items]
    assert (call.answer, call.waited, call.took) == ("no", 1.5, None)
    (nested,) = call.nested
    assert (nested.tool, nested.answer, nested.took, nested.child) == ("agent", "unasked", 12.0, "general-1")
    assert nested.agent is not None and laid.unlinked == ()  # a sub-agent a nested call started is linked too
