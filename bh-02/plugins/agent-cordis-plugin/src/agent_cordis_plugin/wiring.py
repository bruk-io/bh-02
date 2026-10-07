"""The rows: the loop, which consumes a model and provides the `loop` value; the transcript;
`memory`, the broker of what the model is told with an input's result; `executor`, where the
loop reads the prompt and asks `memory`; and `/compact`.

The transcript is its own row so the history outlives the loop: replace the `model` row
and the loop reloads against the new provider while the conversation carries on. `memory` is
its own row too, depending on nothing, so neither the loop nor a row adding to it reloads the
other. So is `executor`, so a reloaded loop keeps the call a stopped reply left running and waits
for it. `/compact` is a row of its own over the model, the kernel's tool spec, the loader,
`commands` and `output`, and depends on neither the loop nor the transcript, which it restarts.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.compact import (
    SPEC,
    CompactConfig,
    Offered,
    Rows,
    Shown,
    compact_conversation,
    unrestarted,
)
from agent_cordis_plugin.executor import OneAtATime
from agent_cordis_plugin.loop import (
    Approval,
    Executor,
    LoopModel,
    Memory,
    Model,
    Python,
    Remember,
    System,
    Transcript,
)
from agent_cordis_plugin.transcript import FileTranscript, MemoryTranscript
from cordis import Effects, acquire, background, bind, component
from cordis_helpers import Hooks, Job, perform

__all__ = ["LoopConfig", "TranscriptConfig", "compact", "executor", "loop", "memory", "transcript"]


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
    approval: Approval,
    memory: Memory,
    executor: Executor,
    config: LoopConfig,
) -> Effects:
    """Fills the `loop` row from a raw model: `use = "agent:loop"`. The model's one tool is
    the kernel's `python(code)`; each input runs only on `approval`'s yes (the person's, when
    the jail does not confine the kernel). After each input, the functions in `memory` may add a
    note to its result. The prompt is read, and `memory` asked, on `executor`. A new ui reloads
    this row (through `approval`), which holds nothing: the transcript, the kernel's namespace
    and the call in flight on `executor` are rows of their own."""
    yield bind(
        "loop",
        LoopModel(model, kernel, transcript, approval, config.max_nudges, system, memory, executor=executor),
    )


@component(provides=("memory",))
async def memory() -> Effects:
    """Fills a `memory` row: `use = "agent:memory"`. A broker (CONTRACTS.md: memory): a row
    with something to tell the model about an input `acquire`s `memory.add(fn)`, and the loop
    calls each `fn({"code", "result", "touched"}) -> str` after every input it runs, on
    `executor`. Each adds a note or says nothing ('' ); none changes the result, so they compose
    in any order."""
    yield bind("memory", Hooks[Remember]())


@component(provides=("executor",))
async def executor() -> Effects:
    """Fills an `executor` row: `use = "agent:executor"`. Where the loop reads the prompt and
    asks `memory` (CONTRACTS.md: executor): off the event loop, in a daemon thread, one call at
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
async def compact(
    *, model: Model, kernel: Offered, loader: Rows, commands: _Registrar, output: Shown, config: CompactConfig
) -> Effects:
    """Fills a `compact` row: `use = "agent:compact"`. `/compact [WHAT TO KEEP]` asks the model
    for a summary of the conversation (in `config.timeout` seconds: Ctrl-C stops only a turn;
    a note says so as it begins), writes the new conversation it begins over the transcript
    row's file (the old kept beside it), and restarts the loop and the transcript; the kernel
    keeps its namespace.

    It depends on neither the loop nor the transcript: the restart would reload this row too,
    cancelling its own work half-way. It finds the conversation's file from the transcript row
    as the loader mounted it (`loader.rows`), and its restart is its own background work,
    never run in the chat row's task, which the restart reloads. A restart that fails is told
    to the person (`output.notice`): the new conversation is written by then."""
    jobs: asyncio.Queue[Job] = asyncio.Queue()
    worker = yield background(perform(jobs, lambda why: output.notice(unrestarted(config, why))))
    run = partial(
        compact_conversation,
        model=model,
        kernel=kernel,
        loader=loader,
        output=output,
        config=config,
        jobs=jobs,
        worker=worker,
    )
    yield acquire(commands.register, SPEC, run)
