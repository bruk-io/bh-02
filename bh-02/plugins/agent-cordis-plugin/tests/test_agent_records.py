"""What the loop records on a transcript's entries: when a message came, and a step's timing, model, usage
and settings (decision-0009). The clock is a fake the model moves as its chunks stream, so every time and
duration is exact."""

import asyncio
import datetime
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_cordis_plugin import (
    FAILED,
    STOPPED,
    Clock,
    FileTranscript,
    LoopModel,
    MemoryTranscript,
    ToolBroker,
    stamp,
    summed,
)
from agent_cordis_plugin.loop import request_for
from agent_cordis_plugin.records import settings_to_record, step_record
from agent_cordis_plugin.testing import Stepped, noon

type Json = Mapping[str, Any]

START = "2026-10-18T03:47:12.345Z"  # what `Stepped` reads before it is moved
PYTHON: Json = {
    "name": "python",
    "description": "Run Python.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
}
SETTINGS: Json = {"model": "work/opus", "provider": "claude-code"}


def text(said: str) -> Json:
    return {"type": "text", "text": said}


def usage(**counts: Any) -> Json:
    return {"type": "usage", "input_tokens": 0, "output_tokens": 0} | counts


def call(id: str, code: str) -> Json:
    return {"type": "tool_call", "id": id, "name": "python", "input": {"code": code}}


type Timed = tuple[float, Json]  # the seconds before a chunk, and the chunk


class Timing:
    """A `model` that plays one scripted step per request: the test's clock moves by each chunk's
    seconds before the chunk is yielded. It keeps what each request held: the messages, the tools
    offered, and how many entries the transcript had when the loop handed it over."""

    def __init__(self, stepped: Stepped, transcript: MemoryTranscript, *steps: Sequence[Timed]) -> None:
        self.stepped, self.transcript, self.steps = stepped, transcript, list(steps)
        self.requests: list[tuple[int, tuple[Json, ...], tuple[Json, ...]]] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.requests.append((len(self.transcript.messages), tuple(messages), tuple(tools)))
        for seconds, chunk in self.steps.pop(0):
            self.stepped.advance(seconds)
            yield chunk


class Configured(Timing):
    """`Timing`, and the `settings` a provider exposes (CONTRACTS.md: model), which a test changes."""

    def __init__(self, *args: Any, settings: Mapping[str, Any], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.settings = settings


class Listing(Timing):
    """`Timing` of a model that wants its tools offered as the transcript last recorded them."""

    tool_changes = "listed"


class Approved:
    async def approve(self, question: Json) -> bool:
        return True


class Prompt:
    """A `system` whose prompt reads the same as the one the conversation began with."""

    def text(self) -> str:
        return "the prompt"


class Reading:
    """A `system` whose prompt takes a second and a half to read, as a big project's would."""

    def __init__(self, stepped: Stepped) -> None:
        self.stepped = stepped

    def text(self) -> str:
        self.stepped.advance(1.5)
        return "the prompt"


def tools() -> ToolBroker:
    broker = ToolBroker()

    async def run(input: Json) -> Json:
        return {"content": str(input["code"]).upper()}

    broker.register(PYTHON, run)
    return broker


def steps(*chunks: Timed) -> Sequence[Timed]:
    return chunks


def loop(model: Any, transcript: MemoryTranscript, stepped: Stepped, **kwargs: Any) -> LoopModel:
    return LoopModel(model, tools(), transcript, Approved(), clock=stepped.clock, **kwargs)


async def reply(model: LoopModel, message: str) -> list[Json]:
    return [event async for event in model.reply(message)]


def entries(transcript: MemoryTranscript, role: str) -> list[Json]:
    return [m for m in transcript.messages if m["role"] == role]


def test_a_time_is_utc_to_the_millisecond_with_z_and_sorts_as_text() -> None:
    moment = datetime.datetime(2026, 10, 18, 3, 47, 12, 345678, tzinfo=datetime.UTC)
    assert stamp(moment) == START
    elsewhere = moment.astimezone(datetime.timezone(datetime.timedelta(hours=-7)))
    assert stamp(elsewhere) == START  # the same instant, written the same
    assert stamp(moment.replace(microsecond=0)) == "2026-10-18T03:47:12.000Z"
    assert stamp(moment) < stamp(moment + datetime.timedelta(milliseconds=1)) < stamp(noon("2026-12-01"))


def test_the_real_clock_reads_aware_utc_and_a_monotonic_count_of_seconds() -> None:
    clock = Clock()
    moment = clock.now()
    assert moment.utcoffset() == datetime.timedelta(0)
    assert abs((datetime.datetime.now(datetime.UTC) - moment).total_seconds()) < 5
    assert clock.monotonic() <= clock.monotonic()


async def test_the_person_s_message_has_the_time_it_came_not_the_time_its_prompt_was_read() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(stepped, transcript, steps((0.0, text("hi"))))
    await reply(loop(model, transcript, stepped, system=Reading(stepped)), "hello")
    (user,) = entries(transcript, "user")
    assert user["at"] == START
    (answer,) = entries(transcript, "assistant")
    assert answer["step"]["at"] == "2026-10-18T03:47:13.845Z"  # 1.5 s later: when its request was handed over


async def test_a_step_records_when_it_began_its_first_chunk_its_last_the_model_and_the_usage() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(
        stepped,
        transcript,
        steps(
            (0.25, text("hel")),
            (0.5, text("lo")),
            (0.125, usage(input_tokens=100, output_tokens=7, cost_usd=0.5, model="claude-opus-5-5")),
            (0.0, {"type": "stop", "reason": "end_turn"}),
        ),
    )
    await reply(loop(model, transcript, stepped), "hello")
    (answer,) = entries(transcript, "assistant")
    assert answer["step"] == {
        "at": START,
        "first_chunk": 0.25,
        "took": 0.875,
        "model": "claude-opus-5-5",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 7,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cost_usd": 0.5,
        },
    }


async def test_a_steps_usage_is_its_usage_chunks_summed_as_compact_sums_its_own() -> None:
    parts = [
        usage(input_tokens=90, cache_read_input_tokens=80, cost_usd=0.25, partial=True, model="m-1"),
        usage(input_tokens=10, output_tokens=7, cache_creation_input_tokens=3, cost_usd=0.5, model="m-1"),
    ]
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(stepped, transcript, steps((0.0, text("ok")), *((0.0, part) for part in parts)))
    await reply(loop(model, transcript, stepped), "hi")
    (answer,) = entries(transcript, "assistant")
    assert (
        answer["step"]["usage"]
        == summed(parts)
        == {
            "input_tokens": 100,
            "output_tokens": 7,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 3,
            "cost_usd": 0.75,
        }
    )
    assert summed([]) is None
    assert summed(parts[:1]) == {  # a step stopped before its output was counted stays `partial`
        "input_tokens": 90,
        "output_tokens": 0,
        "cache_read_input_tokens": 80,
        "cache_creation_input_tokens": 0,
        "cost_usd": 0.25,
        "partial": True,
    }


async def test_a_provider_that_reports_no_usage_or_model_leaves_both_out() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(stepped, transcript, steps((0.5, text("ok"))))
    await reply(loop(model, transcript, stepped), "hi")
    (answer,) = entries(transcript, "assistant")
    assert answer["step"] == {"at": START, "first_chunk": 0.5, "took": 0.5}


async def test_every_step_of_a_reply_has_its_own_record_and_a_feedback_message_has_the_time() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(
        stepped,
        transcript,
        steps((1.0, text("")), (0.0, {"type": "stop", "reason": "end_turn"})),  # said nothing: fed back
        steps((2.0, text("let me see")), (0.0, call("c1", "x"))),
        steps((4.0, text("done"))),
    )
    await reply(loop(model, transcript, stepped), "go")
    assistants = entries(transcript, "assistant")
    assert [(a["step"]["at"], a["step"]["first_chunk"]) for a in assistants] == [
        (START, 1.0),
        ("2026-10-18T03:47:13.345Z", 2.0),
        ("2026-10-18T03:47:15.345Z", 4.0),
    ]
    users = entries(transcript, "user")
    assert [u["at"] for u in users] == [START, "2026-10-18T03:47:13.345Z"]  # the nudge, when it was fed back
    assert users[1]["feedback"] == "silent"


async def test_a_step_that_failed_or_was_stopped_has_a_record_of_what_came_before_it() -> None:
    class Failing(Timing):
        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            self.stepped.advance(0.5)
            yield text("Hel")
            self.stepped.advance(0.25)
            raise RuntimeError("429")

    stepped, transcript = Stepped(), MemoryTranscript()
    with pytest.raises(RuntimeError):
        await reply(loop(Failing(stepped, transcript), transcript, stepped), "hi")
    (answer,) = entries(transcript, "assistant")
    assert answer["content"].endswith(FAILED)
    assert answer["step"] == {
        "at": START,
        "first_chunk": 0.5,
        "took": 0.5,
    }  # up to the last chunk, not the error

    class Silent(Timing):
        async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
            await asyncio.Event().wait()
            yield text("never")  # pragma: no cover

    stepped, transcript = Stepped(), MemoryTranscript()
    task = asyncio.create_task(reply(loop(Silent(stepped, transcript), transcript, stepped), "hi"))
    await asyncio.sleep(0.01)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    (answer,) = entries(transcript, "assistant")
    assert answer["content"] == STOPPED and answer["step"] == {"at": START}  # no chunk came


async def test_a_reply_that_ends_before_the_model_is_asked_keeps_the_message_time_and_no_step() -> None:
    class Slow:
        def text(self) -> str:
            raise asyncio.CancelledError  # stopped while the prompt is read

    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(stepped, transcript)
    with pytest.raises(asyncio.CancelledError):
        await reply(loop(model, transcript, stepped, system=Slow()), "hi")
    (user,) = entries(transcript, "user")
    (answer,) = entries(transcript, "assistant")
    assert user["at"] == START and answer == {"role": "assistant", "content": STOPPED}


async def test_each_step_receives_the_requests_entries_and_the_tools_it_offered_with_the_new_fields() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(
        stepped,
        transcript,
        steps((0.25, text("let me see")), (0.0, call("c1", "x")), (0.0, usage(model="m-1"))),
        steps((0.5, text("done")), (0.0, usage(model="m-1"))),
    )
    await reply(loop(model, transcript, stepped, system=Reading(stepped)), "go")
    offered = [dict(PYTHON)]
    assert len(model.requests) == 2
    for held, messages, given in model.requests:
        # exactly request_for over the entries before the step, and the tools that step offered
        assert list(messages) == request_for(transcript.messages[:held])
        assert list(given) == offered
    (_, second, _) = model.requests[1]
    carried = [m for m in second if m["role"] == "assistant"]
    assert carried[0]["step"]["model"] == "m-1" and carried[0]["step"]["first_chunk"] == 0.25
    assert [m["at"] for m in second if m["role"] == "user"] == [START]  # the new fields are in the request
    assert "step" in entries(transcript, "assistant")[1] and "at" in entries(transcript, "user")[0]


def test_settings_are_recorded_for_a_conversation_s_first_step_and_when_they_differ_from_the_last() -> None:
    other = {"model": "work/sonnet", "provider": "claude-code"}
    sampled = {"model": "local/llama", "provider": "openai", "max_tokens": 4096, "temperature": 0.2}
    assert settings_to_record(SETTINGS, []) == SETTINGS  # a conversation's first step
    assert settings_to_record(None, []) is None and settings_to_record("opus", []) is None
    assert settings_to_record({"other": 1}, []) is None  # none of what a transcript records
    assert settings_to_record({"model": "work/opus"}, []) is None  # no provider: not a `Settings`
    recorded = [{"role": "assistant", "content": "", "step": {"at": START, "settings": SETTINGS}}]
    later = [*recorded, {"role": "user", "content": "x"}, {"role": "assistant", "step": {"at": START}}]
    assert settings_to_record(SETTINGS, recorded) is None  # unchanged
    assert settings_to_record(SETTINGS, later) is None  # unchanged, found past steps that recorded none
    assert settings_to_record(other, later) == other  # the model changed
    assert settings_to_record(sampled, later) == sampled
    assert settings_to_record(sampled | {"temperature": 0.3}, [{"step": {"settings": sampled}}]) == {
        **sampled,
        "temperature": 0.3,
    }
    assert settings_to_record(SETTINGS, [{"step": {"settings": sampled}}]) == SETTINGS  # a key gone


async def test_a_model_s_settings_are_recorded_on_the_first_step_and_on_a_change_only() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Configured(
        stepped,
        transcript,
        steps((0.0, text("a")), (0.0, call("c1", "x"))),  # the first reply's first step
        steps((0.0, text("b"))),  # its second step: unchanged
        steps((0.0, text("c"))),  # a second reply: unchanged
        steps((0.0, text("d"))),  # after the model's settings changed
        steps((0.0, text("e"))),  # and after they were set back
        settings=SETTINGS,
    )
    runner = loop(model, transcript, stepped)
    await reply(runner, "one")
    await reply(runner, "two")
    changed = {"model": "work/opus", "provider": "claude-code", "max_tokens": 1000}
    model.settings = changed
    await reply(runner, "three")
    model.settings = SETTINGS
    await reply(runner, "four")
    recorded = [a["step"].get("settings") for a in entries(transcript, "assistant")]
    assert recorded == [SETTINGS, None, None, changed, SETTINGS]


async def test_a_resumed_conversation_records_settings_only_when_they_differ_from_its_last() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    first = Configured(stepped, transcript, steps((0.0, text("a"))), settings=SETTINGS)
    await reply(loop(first, transcript, stepped), "one")
    assert entries(transcript, "assistant")[0]["step"]["settings"] == SETTINGS
    same = Configured(stepped, transcript, steps((0.0, text("b"))), settings=SETTINGS)
    await reply(loop(same, transcript, stepped), "two")  # a new loop over the same transcript
    other = {"model": "work/sonnet", "provider": "claude-code"}
    switched = Configured(stepped, transcript, steps((0.0, text("c"))), settings=other)
    await reply(loop(switched, transcript, stepped), "three")  # /model, then a new loop
    assert [a["step"].get("settings") for a in entries(transcript, "assistant")] == [SETTINGS, None, other]


async def test_a_model_with_no_settings_records_none() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    model = Timing(stepped, transcript, steps((0.0, text("a"))), steps((0.0, text("b"))))
    runner = loop(model, transcript, stepped)
    await reply(runner, "one")
    await reply(runner, "two")
    assert all("settings" not in a["step"] for a in entries(transcript, "assistant"))


async def test_tool_changes_are_recorded_only_when_the_model_wants_the_list_as_it_reads_now() -> None:
    stepped, transcript = Stepped(), MemoryTranscript()
    await reply(loop(Timing(stepped, transcript, steps((0.0, text("a")))), transcript, stepped), "one")
    (fixed,) = entries(transcript, "assistant")
    assert "tool_changes" not in fixed["step"]  # absent means fixed
    stepped, transcript = Stepped(), MemoryTranscript()
    await reply(loop(Listing(stepped, transcript, steps((0.0, text("a")))), transcript, stepped), "one")
    (listing,) = entries(transcript, "assistant")
    assert listing["step"]["tool_changes"] == "listed"


def test_a_step_record_holds_only_what_it_was_given() -> None:
    at = datetime.datetime(2026, 10, 18, 3, 47, 12, 345000, tzinfo=datetime.UTC)
    assert step_record(at, 10.0, None, None, [], None, "fixed") == {"at": START}
    whole = step_record(at, 10.0, 10.0004, 12.34567, [usage(model="m-1")], None, "listed")
    assert whole["first_chunk"] == 0.0 and whole["took"] == 2.346  # rounded to the millisecond
    assert whole["model"] == "m-1" and whole["tool_changes"] == "listed"


async def test_a_transcript_from_before_the_records_resumes_and_is_sent_exactly_as_it_was(
    tmp_path: Path,
) -> None:
    """Nothing is added to the entries already there: the model is sent the old conversation as it
    was written, and the new message after it, which has its own records."""
    path = tmp_path / "transcript.jsonl"
    old: list[Json] = [
        {"role": "system", "content": "the prompt"},
        {"role": "tools", "tools": [dict(PYTHON)]},
        {"role": "user", "content": "(Today's date: 2026-10-06.)\n\nfind x", "today": "2026-10-06"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "python", "input": {"code": "x"}}],
            "provider": {"role": "assistant", "content": None},
        },
        {"role": "tool", "content": "X", "call_id": "c1", "asides": []},
        {"role": "assistant", "content": "x is X"},
    ]
    path.write_text("".join(json.dumps(entry) + "\n" for entry in old))
    stepped = Stepped()
    transcript = FileTranscript(str(path))
    model = Configured(stepped, transcript, steps((0.5, text("fine"))), settings=SETTINGS)
    await reply(loop(model, transcript, stepped, system=Prompt()), "and now?")
    new, answer = transcript.messages[-2:]
    ((held, messages, offered),) = model.requests
    assert list(messages) == [old[0], *old[2:], new]  # the old conversation bit for bit, then the message
    assert held == len(old) + 1 and list(offered) == [dict(PYTHON)]
    assert new["at"] == START and answer["step"]["settings"] == SETTINGS  # none recorded in it yet: now
    await transcript.flush()
    assert list(FileTranscript(str(path)).messages[: len(old)]) == old  # the file keeps them as they were
