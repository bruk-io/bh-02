"""The rows: the loop, which consumes a model and provides the `loop` value, and the transcript.

The transcript is its own row so the history outlives the loop: replace the `model` row
and the loop reloads against the new provider while the conversation carries on.
"""

from dataclasses import dataclass

from agent_cordis_plugin.loop import Asks, LoopModel, Model, Python, System, Transcript
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript
from cordis import Effects, bind, component

__all__ = ["LoopConfig", "TranscriptConfig", "loop", "transcript"]


@dataclass(frozen=True, slots=True)
class TranscriptConfig:
    """`path`: a JSONL file to keep the conversation in (a session's), or none to keep it in memory."""

    path: str | None = None


@component(provides=("transcript",))
async def transcript(*, config: TranscriptConfig) -> Effects:
    """Fills a `transcript` row: `use = "agent:transcript"`."""
    yield bind("transcript", FileTranscript(config.path) if config.path else MemoryTranscript())


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """`max_nudges`: how many times one reply feeds a truncated, silent or undecodable turn back."""

    max_nudges: int = 2


@component(provides=("loop",))
async def loop(
    *,
    model: Model,
    kernel: Python,
    transcript: Transcript,
    system: System,
    output: Asks,
    config: LoopConfig,
) -> Effects:
    """Fills the `loop` row from a raw model: `use = "agent:loop"`. The model's one tool is
    the kernel's `python(code)`; an unconfined kernel's inputs are put to the person through
    `output.confirm` first. A new ui reloads this row, which holds nothing: the transcript and
    the kernel's namespace are rows of their own."""
    yield bind("loop", LoopModel(model, kernel, transcript, config.max_nudges, system, output))
