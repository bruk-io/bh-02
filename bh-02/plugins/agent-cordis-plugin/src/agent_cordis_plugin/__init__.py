"""A harness-owned agent loop: a `model` plus the kernel's one tool, `python`, provided as a `loop`.

Also the transcript row, so the history outlives the loop; `memory`, what the model is told with
an input's result; `executor`, where the loop reads the prompt and asks `memory`, one call at a
time across the loop's reloads; and `/compact`, which begins a new conversation from the model's
summary of it."""

from agent_cordis_plugin.compact import (
    CompactConfig,
    Unsummarised,
    asked,
    compact_conversation,
    kept_in,
    seeded,
    summarise,
)
from agent_cordis_plugin.executor import OneAtATime
from agent_cordis_plugin.loop import (
    DECLINED,
    FAILED,
    STOPPED,
    Approval,
    Executor,
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
from agent_cordis_plugin.wiring import (
    LoopConfig,
    TranscriptConfig,
    compact,
    executor,
    loop,
    memory,
    transcript,
)

__all__ = [
    "DECLINED",
    "FAILED",
    "STOPPED",
    "Approval",
    "CompactConfig",
    "Executor",
    "Model",
    "FileTranscript",
    "LoopConfig",
    "LoopModel",
    "Memory",
    "MemoryTranscript",
    "OneAtATime",
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
    "executor",
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
