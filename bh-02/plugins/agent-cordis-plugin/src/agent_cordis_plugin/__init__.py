"""A harness-owned agent loop: a `model` plus the kernel's one tool, `python`, provided as a `loop`.

Also the transcript row, so the history outlives the loop."""

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
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript
from agent_cordis_plugin.wiring import LoopConfig, TranscriptConfig, loop, memory, transcript

__all__ = [
    "DECLINED",
    "FAILED",
    "STOPPED",
    "Approval",
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
    "changes",
    "classify",
    "edits",
    "latest",
    "loop",
    "memory",
    "refusal",
    "remembered",
    "transcript",
]
