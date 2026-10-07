"""A harness-owned agent loop: a `model` plus the kernel's one tool, `python`, provided as a `loop`.

Also the transcript row, so the history outlives the loop, and `/compact`, which begins a new
conversation from the model's summary of it."""

from agent_cordis_plugin.compact import (
    CompactConfig,
    Unsummarised,
    asked,
    compact_conversation,
    kept_in,
    seeded,
    summarise,
)
from agent_cordis_plugin.loop import (
    DECLINED,
    FAILED,
    STOPPED,
    Approval,
    LoopModel,
    Memory,
    Model,
    Python,
    System,
    Transcript,
    refusal,
    remembered,
)
from agent_cordis_plugin.prompt import changes, edits, latest
from agent_cordis_plugin.stops import classify
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript, rewrite
from agent_cordis_plugin.wiring import LoopConfig, TranscriptConfig, compact, loop, memory, transcript

__all__ = [
    "DECLINED",
    "FAILED",
    "STOPPED",
    "Approval",
    "CompactConfig",
    "Model",
    "FileTranscript",
    "LoopConfig",
    "LoopModel",
    "Memory",
    "MemoryTranscript",
    "Python",
    "System",
    "Transcript",
    "TranscriptConfig",
    "Unsummarised",
    "asked",
    "changes",
    "classify",
    "compact",
    "compact_conversation",
    "edits",
    "kept_in",
    "latest",
    "loop",
    "memory",
    "refusal",
    "remembered",
    "rewrite",
    "seeded",
    "summarise",
    "transcript",
]
