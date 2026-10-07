"""The rows driven by hand."""

from pathlib import Path

from agent_cordis_plugin import (
    FileTranscript,
    LoopConfig,
    LoopModel,
    MemoryTranscript,
    TranscriptConfig,
    loop,
    memory,
    transcript,
)
from cordis.testing import drive
from cordis_helpers import Hooks


async def test_transcript_binds_an_empty_history() -> None:
    effects = await drive(transcript(config=TranscriptConfig()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "transcript")]
    assert isinstance(effects[0].args[1], MemoryTranscript) and effects[0].args[1].messages == ()


async def test_loop_binds_a_model_over_what_it_was_given() -> None:
    model, kernel, history = object(), object(), MemoryTranscript()
    effects = await drive(
        loop(
            model=model,
            kernel=kernel,
            transcript=history,
            system=object(),
            approval=object(),
            memory=Hooks(),
            config=LoopConfig(),
        )  # type: ignore[arg-type]
    )
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "loop")]
    assert isinstance(effects[0].args[1], LoopModel)


async def test_memory_binds_an_empty_broker() -> None:
    effects = await drive(memory())
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "memory")]
    assert isinstance(effects[0].args[1], Hooks) and list(effects[0].args[1]) == []


async def test_a_transcript_with_a_path_is_kept_in_the_file_and_read_back(tmp_path: Path) -> None:
    path = str(tmp_path / "transcript.jsonl")
    effects = await drive(transcript(config=TranscriptConfig(path=path)))
    first = effects[0].args[1]
    assert isinstance(first, FileTranscript)
    first.append({"role": "user", "content": "hi"})
    first.append({"role": "assistant", "content": "hello", "provider": {"role": "assistant", "x": 1}})
    again = FileTranscript(path)  # a resumed session
    assert again.messages == first.messages
