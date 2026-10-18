"""The rows driven by hand."""

from pathlib import Path

from agent_cordis_plugin import (
    FileTranscript,
    LoopConfig,
    LoopModel,
    MemoryTranscript,
    OneAtATime,
    ToolBroker,
    TranscriptConfig,
    asides,
    executor,
    loop,
    transcript,
)
from cordis.testing import drive
from cordis_helpers import Hooks


async def test_transcript_binds_an_empty_conversation() -> None:
    effects = await drive(transcript(config=TranscriptConfig()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "transcript")]
    assert isinstance(effects[0].args[1], MemoryTranscript) and effects[0].args[1].messages == ()


async def test_loop_binds_a_model_over_what_it_was_given() -> None:
    model, transcript = object(), MemoryTranscript()
    effects = await drive(
        loop(
            model=model,
            tools=ToolBroker(),
            transcript=transcript,
            system=object(),
            approval=object(),
            output=object(),
            asides=Hooks(),
            executor=OneAtATime(),
            config=LoopConfig(),
        )  # type: ignore[arg-type]
    )
    assert [e.name for e in effects] == ["bind", "acquire"]
    looped = effects[0].args[1]
    assert effects[0].args[0] == "loop" and isinstance(looped, LoopModel)
    assert effects[1].args[1] == looped.nested  # serves the calls an input makes (`tools.serve`)


async def test_asides_binds_an_empty_broker() -> None:
    effects = await drive(asides())
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "asides")]
    assert isinstance(effects[0].args[1], Hooks) and list(effects[0].args[1]) == []


async def test_executor_binds_one_that_runs_a_call_at_a_time() -> None:
    effects = await drive(executor())
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "executor")]
    assert isinstance(effects[0].args[1], OneAtATime)


async def test_a_transcript_with_a_path_is_kept_in_the_file_and_read_back(tmp_path: Path) -> None:
    path = str(tmp_path / "transcript.jsonl")
    effects = await drive(transcript(config=TranscriptConfig(path=path)))
    # entered, so the row's leaving writes what is queued and closes the file; then bound
    assert [e.name for e in effects] == ["enter", "bind"]
    key, first = effects[1].args
    assert key == "transcript" and effects[0].args[0] is first
    assert isinstance(first, FileTranscript)
    first.append({"role": "user", "content": "hi"})
    first.append({"role": "assistant", "content": "hello", "provider": {"role": "assistant", "x": 1}})
    await first.flush()  # appended in memory at once, in the file once its thread has written it
    again = FileTranscript(path)  # a resumed session
    assert again.messages == first.messages
