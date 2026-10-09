"""A harness-owned agent loop: a `model` plus the tools rows register (`tools`, a broker), provided
as a `loop`.

Also the transcript row, so the history outlives the loop; `system`, the system prompt rows add
sections to; `notes`, what the model is told with a call's result; `access`, what is asked
before a file is read or written; `executor`, where the loop
reads the prompt and asks `notes`, one call at a time across the loop's reloads; and `/compact`,
which begins a new conversation from the model's summary of it."""

from agent_cordis_plugin.access import READ, WRITE, Access
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
    System,
    Tool,
    Tools,
    Transcript,
    Unstarted,
    called,
    malformed,
    noted,
    refusal,
    shown,
)
from agent_cordis_plugin.prompt import changes, edits, latest
from agent_cordis_plugin.stops import classify
from agent_cordis_plugin.system import SystemConfig, SystemPrompt, branch_of, describe
from agent_cordis_plugin.tools import HOST, JAIL, ToolBroker
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript, rewrite
from agent_cordis_plugin.wiring import (
    LoopConfig,
    TranscriptConfig,
    access,
    compact,
    executor,
    loop,
    notes,
    system,
    tools,
    transcript,
)

__all__ = [
    "DECLINED",
    "FAILED",
    "HOST",
    "JAIL",
    "READ",
    "STOPPED",
    "WRITE",
    "Access",
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
    "System",
    "SystemConfig",
    "SystemPrompt",
    "Tool",
    "ToolBroker",
    "Tools",
    "Transcript",
    "TranscriptConfig",
    "Unchanged",
    "Unstarted",
    "access",
    "asked",
    "branch_of",
    "called",
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
    "malformed",
    "notes",
    "refusal",
    "noted",
    "rewrite",
    "seeded",
    "shown",
    "summarise",
    "system",
    "tools",
    "transcript",
    "unrestarted",
]
