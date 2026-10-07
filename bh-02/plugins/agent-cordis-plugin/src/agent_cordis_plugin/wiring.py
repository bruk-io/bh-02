"""The rows: the loop, which consumes a model and provides the `loop` value; the transcript;
and `memory`, the broker of what the model is told with an input's result.

The transcript is its own row so the history outlives the loop: replace the `model` row
and the loop reloads against the new provider while the conversation carries on. `memory` is
its own row too, depending on nothing, so neither the loop nor a row adding to it reloads the
other.
"""

from dataclasses import dataclass

from agent_cordis_plugin.loop import Asks, LoopModel, Memory, Model, Python, Remember, System, Transcript
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript
from cordis import Effects, bind, component
from cordis_helpers import Hooks

__all__ = ["LoopConfig", "TranscriptConfig", "loop", "memory", "transcript"]


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
    memory: Memory,
    config: LoopConfig,
) -> Effects:
    """Fills the `loop` row from a raw model: `use = "agent:loop"`. The model's one tool is
    the kernel's `python(code)`; an unconfined kernel's inputs are put to the person through
    `output.confirm` first. After each input, the functions in `memory` may add a note to its
    result. A new ui reloads this row, which holds nothing: the transcript and the kernel's
    namespace are rows of their own."""
    yield bind("loop", LoopModel(model, kernel, transcript, config.max_nudges, system, output, memory))


@component(provides=("memory",))
async def memory() -> Effects:
    """Fills a `memory` row: `use = "agent:memory"`. A broker (CONTRACTS.md: memory): a row
    with something to tell the model about an input `acquire`s `memory.add(fn)`, and the loop
    calls each `fn({"code", "result", "touched"}) -> str` after every input it runs, in a worker
    thread. Each adds a note or says nothing ('' ); none changes the result, so they compose in
    any order."""
    yield bind("memory", Hooks[Remember]())
