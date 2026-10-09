"""The rows: the loop, which consumes a model and provides the `loop` value; the transcript;
`tools`, the broker of the tools the model is offered; `system`, the system prompt rows add
sections to; `notes`, the broker of what the model is told with a call's result; `access`, the
broker of what is asked before a file is read or written; `executor`, where the loop reads the
prompt and asks `notes`; and the conversation's commands, `/clear` and `/compact`.

The transcript is its own row so the history outlives the loop: replace the `model` row
and the loop reloads against the new provider while the conversation carries on. `notes` is
its own row too, depending on nothing, so neither the loop nor a row adding to it reloads the
other, and `tools`, so a tool's row restarting (the kernel's) reloads neither the loop nor
another tool's row. So is `executor`, so a reloaded loop keeps the call a stopped reply left
running and waits for it. `/clear` and `/compact` are one row's (`conversation`), over the
model, `tools`, the loader, `commands` and `output`, which depends on neither the loop nor the
transcript, which they restart.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.access import Access
from agent_cordis_plugin.conversation import (
    CLEAR,
    COMPACT,
    ConversationConfig,
    Offered,
    Queue,
    Rows,
    Shown,
    clear_conversation,
    compact_conversation,
)
from agent_cordis_plugin.executor import OneAtATime
from agent_cordis_plugin.loop import (
    Approval,
    Executor,
    LoopModel,
    Model,
    Note,
    Notes,
    System,
    Tools,
    Transcript,
)
from agent_cordis_plugin.system import SystemConfig, SystemPrompt
from agent_cordis_plugin.tools import ToolBroker
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript
from cordis import Effects, acquire, bind, component
from cordis_helpers import Hooks

__all__ = [
    "LoopConfig",
    "TranscriptConfig",
    "access",
    "conversation",
    "executor",
    "loop",
    "notes",
    "system",
    "tools",
    "transcript",
]


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
    """`max_nudges`: how many times one reply feeds a truncated, silent or undecodable turn back.
    `requires`: the tools a conversation can't begin without (the shipped layer: `["python"]`),
    waited for at the loop's first request, `wait` seconds at most; a call to a tool restarting
    waits as long."""

    max_nudges: int = 2
    requires: Sequence[str] = ()
    wait: float = 30.0

    def __post_init__(self) -> None:
        if isinstance(self.requires, str):
            raise TypeError(
                f"the loop's `requires` is a list of tool names, not one: write `requires = "
                f"[{self.requires!r}]`"
            )


@component(provides=("loop",))
async def loop(
    *,
    model: Model,
    tools: Tools,
    transcript: Transcript,
    system: System,
    approval: Approval,
    notes: Notes,
    executor: Executor,
    config: LoopConfig,
) -> Effects:
    """Fills the `loop` row from a raw model: `use = "agent:loop"`. The model is offered the
    tools rows register (`tools`), read at the first request once those `requires` names have
    registered; each call runs only on `approval`'s yes (the person's, when it runs anywhere but
    a jail that confines it). After each call, the functions in `notes` may add a note to its
    result. The prompt is read, and `notes` asked, on `executor`. A new ui reloads this row
    (through `approval`), which holds nothing: the transcript, the tools (the kernel's namespace
    among them) and the call in flight on `executor` are rows of their own."""
    yield bind(
        "loop",
        LoopModel(
            model,
            tools,
            transcript,
            approval,
            config.max_nudges,
            system,
            notes,
            executor=executor,
            requires=config.requires,
            wait=config.wait,
        ),
    )


@component(provides=("tools",))
async def tools() -> Effects:
    """Fills a `tools` row: `use = "agent:tools"`. A broker (CONTRACTS.md: tools): a row with a
    tool for the model `acquire`s `tools.register(spec, run)` (and says where a call runs and how
    one is shown), and the loop offers every registered spec, in name order, and runs each call
    through the tool its name has. It depends on nothing, so a tool's row coming, going or
    restarting reloads neither the loop nor another tool's row."""
    yield bind("tools", ToolBroker())


@component(provides=("system",))
async def system(*, config: SystemConfig) -> Effects:
    """Fills a `system` row: `use = "agent:system"`. The system prompt: who the model is, where
    it is working, then the sections rows add (`system.add`): the memory row's instructions, how
    to extend bh-02. A broker (CONTRACTS.md: system), depending on its config alone, so a row
    adding a section, or leaving, reloads nothing."""
    yield bind("system", SystemPrompt(config))


@component(provides=("notes",))
async def notes() -> Effects:
    """Fills a `notes` row: `use = "agent:notes"`. A broker (CONTRACTS.md: notes): a row
    with something to tell the model about a call `acquire`s `notes.add(fn)`, and the loop
    calls each `fn({"name", "input", "result", "touched"}) -> str` after every call it runs, on
    `executor`. Each adds a note or says nothing ('' ); none changes the result, so they compose
    in any order."""
    yield bind("notes", Hooks[Note]())


@component(provides=("access",))
async def access() -> Effects:
    """Fills an `access` row: `use = "agent:access"`. A broker (CONTRACTS.md: access): a row with
    something to say before a file is opened `acquire`s `access.before_read(fn)` or
    `access.before_write(fn)`, and a tool asks (`refusal(kind, path)`) before it opens one for a
    call: the python tool before an input's own Python opens a file in the project. It depends
    on nothing, so neither a tool's row nor a row asking reloads the other."""
    yield bind("access", Access())


@component(provides=("executor",))
async def executor() -> Effects:
    """Fills an `executor` row: `use = "agent:executor"`. Where the loop reads the prompt and
    asks `notes` (CONTRACTS.md: executor): off the event loop, in a daemon thread, one call at
    a time, a call a stopped reply left running waited for before the next begins. It depends
    on nothing, so a loop reloaded by `/clear` or `/model` keeps it, and waits for that call
    rather than starting beside it."""
    yield bind("executor", OneAtATime())


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value (CONTRACTS.md: commands)."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@component
async def conversation(
    *,
    model: Model,
    tools: Offered,
    loader: Rows,
    commands: _Registrar,
    output: Shown,
    jobs: Queue,
    config: ConversationConfig,
) -> Effects:
    """Fills a `conversation` row: `use = "agent:conversation"`. `/clear` and `/compact`, a new
    conversation each, written over the transcript row's file in one step, the old kept beside
    it (`.bak`, `.bak.2`, ...). `/clear`'s is empty, and the loop, the transcript and the kernel
    restart (`config.clear`); `/compact [WHAT TO KEEP]`'s begins from the model's summary (in
    `config.timeout` seconds: Ctrl-C stops only a turn; a note says so as it begins), and the
    loop and the transcript restart, the kernel keeping its namespace.

    It depends on neither the loop nor the transcript, which it restarts. It finds the
    conversation's file from the transcript row as the loader mounted it (`loader.rows`), and
    queues each restart in `jobs`, never running it in the chat row's task, which it reloads; a
    restart that fails is told to the person there: the new conversation is written by then."""
    compacting = partial(
        compact_conversation, model=model, tools=tools, loader=loader, output=output, config=config, jobs=jobs
    )
    yield acquire(
        commands.register, CLEAR, partial(clear_conversation, loader=loader, config=config, jobs=jobs)
    )
    yield acquire(commands.register, COMPACT, compacting)
