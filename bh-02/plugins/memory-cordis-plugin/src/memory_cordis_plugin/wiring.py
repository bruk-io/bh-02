"""The rows: memory, bound under `memory`, which adds what loads at launch to the system prompt
(`system.add`) and offers `/memory`; what loads on demand for the files an input opened, added
to `notes`; and auto memory, a section of the system prompt for each conversation."""

from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component
from memory_cordis_plugin.auto import AutoMemory
from memory_cordis_plugin.listing import SPEC, listing
from memory_cordis_plugin.memory import Memory, MemoryConfig
from memory_cordis_plugin.touch import Memory as Touched
from memory_cordis_plugin.touch import Notes, OnTouch, Transcript

__all__ = ["auto", "memory", "on_touch"]


@runtime_checkable
class _System(Protocol):
    """What the memory row needs of the `system` value (CONTRACTS.md: system): a section added
    to the prompt, and its remover back."""

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]: ...


@runtime_checkable
class _Layers(Protocol):
    """What the memory rows need of the `layers` value (CONTRACTS.md: layers): the project's auto
    memory directory, which the jail lets an input write ('' for none)."""

    @property
    def memory(self) -> str: ...


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value (CONTRACTS.md: commands)."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@component(provides=("memory",))
async def memory(*, system: _System, commands: _Registrar, layers: _Layers, config: MemoryConfig) -> Effects:
    """Fills a `memory` row: `use = "memory:memory"`. Claude Code's memory: the CLAUDE.md files
    (and AGENTS.md, imports and rules) that load at launch, a section of the system prompt read
    fresh before each message the model reads; and `/memory`, which lists them, the auto memory
    index among them. It depends on `system`, `commands` and `layers`, none of which a new
    conversation reloads."""
    found = Memory(config, layers.memory)
    yield bind("memory", found)
    yield acquire(system.add, "memory", found.text)

    async def run(args: str) -> str:
        root, home = found.places()
        return listing(found.listed(), root, home, found.instruction_files)

    yield acquire(commands.register, SPEC, run)


@component
async def on_touch(*, memory: Touched, notes: Notes, transcript: Transcript) -> Effects:
    """Fills an `on-touch` row: `use = "memory:on_touch"`. After each input, what loads on demand
    for the files it opened (a subdirectory's CLAUDE.md, a rule whose `paths` match) goes to the
    model with its result, each once a conversation (`OnTouch`). It depends on `transcript` for
    its lifetime and what it says: a new conversation (`/clear`) starts a new row, which tells
    each again, and a resumed one is not told again what its transcript says it was told. A row
    of its own, not the memory row, so a new conversation never takes the memory section out of
    the prompt and puts it back."""
    yield acquire(notes.add, OnTouch(memory, transcript))


@component
async def auto(*, system: _System, layers: _Layers, transcript: Transcript) -> Effects:
    """Fills a `memory-auto` row: `use = "memory:auto"`. Claude Code's auto memory: how the model
    keeps notes of its own across conversations, in the project's auto memory directory
    (`layers.memory`, which the jail lets an input write), and its MEMORY.md index, a section of
    the system prompt read at a conversation's first reading of the prompt and kept for the rest
    of it (`AutoMemory`). It depends on `transcript` for that lifetime: a new conversation
    (`/clear`, `/compact`) starts a new row, which reads the index afresh. Disabling the row turns
    auto memory off; with no directory it adds nothing."""
    del transcript  # its lifetime is this row's; nothing of it is read
    if layers.memory:
        directory = Path(layers.memory)
        home = Path.home()
        named = f"~/{directory.relative_to(home)}" if directory.is_relative_to(home) else str(directory)
        yield acquire(system.add, "memory: auto", AutoMemory(directory, named))
