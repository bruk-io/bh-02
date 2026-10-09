"""A harness-owned agent loop: a `model` plus the kernel's one tool, `python`, provided as a `loop`.

Also the transcript row, so the history outlives the loop; `system`, the system prompt rows add
sections to; `notes`, what the model is told with an input's result; `executor`, where the loop
reads the prompt and asks `notes`, one call at a time across the loop's reloads; and `/compact`,
which begins a new conversation from the model's summary of it."""

from agent_cordis_plugin.compact import (
    CompactConfig,
    Unchanged,
    asked,
    compact_conversation,
    kept_in,
    seeded,
    summarise,
    unrestarted,
)
from agent_cordis_plugin.executor import OneAtATime
from agent_cordis_plugin.loop import (
    DECLINED,
    FAILED,
    STOPPED,
    Approval,
    Executor,
    LoopModel,
    Model,
    Notes,
    Python,
    System,
    Transcript,
    noted,
    refusal,
)
from agent_cordis_plugin.prompt import changes, edits, latest
from agent_cordis_plugin.stops import classify
from agent_cordis_plugin.system import SystemConfig, SystemPrompt, branch_of, describe
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript, rewrite
from agent_cordis_plugin.wiring import (
    LoopConfig,
    TranscriptConfig,
    compact,
    executor,
    loop,
    notes,
    system,
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
    "Notes",
    "MemoryTranscript",
    "OneAtATime",
    "Python",
    "System",
    "SystemConfig",
    "SystemPrompt",
    "Transcript",
    "TranscriptConfig",
    "Unchanged",
    "asked",
    "branch_of",
    "changes",
    "classify",
    "compact",
    "compact_conversation",
    "describe",
    "edits",
    "executor",
    "kept_in",
    "latest",
    "loop",
    "notes",
    "refusal",
    "noted",
    "rewrite",
    "seeded",
    "summarise",
    "system",
    "transcript",
    "unrestarted",
]
