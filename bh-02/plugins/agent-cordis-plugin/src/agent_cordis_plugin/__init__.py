"""A harness-owned agent loop: a `model` plus the tools rows register (`tools`, a broker), provided
as a `loop`.

Also the transcript row, so the history outlives the loop; `system`, the system prompt rows add
sections to; `asides`, what the model is told beside a call's result; `access`, what is asked
before a file is read or written; `executor`, where the loop
reads the prompt and asks `asides`, one call at a time across the loop's reloads; and the
conversation row's `/clear` and `/compact`, which begin a new conversation, empty or from the
model's summary of this one."""

from agent_cordis_plugin.access import READ, WRITE, Access
from agent_cordis_plugin.conversation import (
    ConversationConfig,
    Unchanged,
    asked,
    clear_conversation,
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
    Asides,
    Asked,
    Executor,
    LoopModel,
    Model,
    System,
    Tool,
    Tools,
    Transcript,
    Unstarted,
    asides_for,
    called,
    malformed,
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
    asides,
    conversation,
    executor,
    loop,
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
    "Asides",
    "Asked",
    "ConversationConfig",
    "Executor",
    "Model",
    "FileTranscript",
    "LoopConfig",
    "LoopModel",
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
    "asides",
    "asides_for",
    "asked",
    "branch_of",
    "called",
    "changes",
    "classify",
    "clear_conversation",
    "compact_conversation",
    "conversation",
    "describe",
    "edits",
    "executor",
    "kept_in",
    "latest",
    "loop",
    "malformed",
    "refusal",
    "rewrite",
    "seeded",
    "shown",
    "summarise",
    "system",
    "tools",
    "transcript",
    "unrestarted",
]
