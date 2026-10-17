"""The `memory` tool in a composition: the agent plugin's loop, tools and system over a scripted
model, and the runner plugin's approval rule over a runner that reports what it is told, with the
`memory-auto` row and no python tool at all. Rows are named by entry point; no plugin is imported.

The model saves, reads and deletes a memory; none of the three is asked about, whether the runner
confines or not, while another tool run in bh-02's own process (`runs="host"`) is asked in both;
and the next conversation's prompt lists what was saved."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from cordis import Effects, Row, acquire, bind, component
from cordis.loader import Booted, boot

type Json = Mapping[str, Any]

_ENFORCED = {"fs_write": "enforced", "network": "enforced"}
_UNENFORCED = {"fs_write": "unenforced", "network": "unenforced"}


class _Model:
    """A model that plays its script, one step per request, and keeps the tools it was offered."""

    def __init__(self, *steps: Sequence[Json]) -> None:
        self.steps = list(steps)
        self.offered: list[list[str]] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.offered.append([str(tool["name"]) for tool in tools])
        for chunk in self.steps.pop(0):
            yield chunk


class _Screen:
    """The `output`: every question put to the person, and a no to each."""

    def __init__(self) -> None:
        self.asked: list[Json] = []

    async def confirm(self, request: Json) -> bool:
        self.asked.append(request)
        return False

    async def show(self, events: AsyncIterator[Json]) -> None:
        async for _ in events:
            pass


class _Runner:
    def __init__(self, grades: Mapping[str, str]) -> None:
        self.grades = grades

    def report(self) -> Mapping[str, str]:
        return self.grades


class _Host:
    def __init__(self, auto_memory: str) -> None:
        self.auto_memory = auto_memory


@component(provides=("model",))
async def fake_model(*, config: Mapping[str, Any]) -> Effects:
    yield bind("model", config["model"])


@component(provides=("output",))
async def fake_output(*, config: Mapping[str, Any]) -> Effects:
    yield bind("output", config["screen"])


@component(provides=("runner",))
async def fake_runner(*, config: Mapping[str, Any]) -> Effects:
    yield bind("runner", _Runner(config["grades"]))


@component(provides=("host",))
async def fake_host(*, config: Mapping[str, Any]) -> Effects:
    yield bind("host", _Host(config["auto_memory"]))


async def _elsewhere(input: Json) -> Json:
    return {"content": "ran in bh-02's own process"}


@component
async def host_tool(*, tools: Any) -> Effects:
    """Another tool that runs in bh-02's own process: `runs="host"`, which is always asked."""
    spec = {"name": "elsewhere", "description": "Runs on the host.", "parameters": {"type": "object"}}
    yield acquire(tools.register, spec, _elsewhere, runs="host")


def _call(id: str, tool: str, input: Json | None = None) -> Json:
    return {"type": "tool_call", "id": id, "name": tool, "input": input or {}}


_END = [{"type": "text", "text": "done"}, {"type": "stop", "reason": "end_turn"}]
_SAVE = {
    "action": "save",
    "name": "prefers-tabs",
    "type": "feedback",
    "description": "Tabs, not spaces",
    "body": "Use tabs.",
}


async def _booted(
    model: _Model, screen: _Screen, grades: Mapping[str, str], memory: Path | None, *, auto: bool = True
) -> Booted:
    """The composition; `memory` is the host's `auto_memory` (None: it names none), and `auto` is
    whether the `memory-auto` row is in it."""
    rows = [
        Row("loop", "agent:loop"),
        Row("tools", "agent:tools"),
        Row("transcript", "agent:transcript", {"path": None}),
        Row("model", f"{__name__}:fake_model", {"model": model}),
        Row("system", "agent:system", {"root": "."}),
        Row("asides", "agent:asides"),
        Row("access", "agent:access"),
        Row("executor", "agent:executor"),
        Row("output", f"{__name__}:fake_output", {"screen": screen}),
        Row("runner", f"{__name__}:fake_runner", {"grades": grades}),
        Row("approval", "runner:approval"),
        Row("host", f"{__name__}:fake_host", {"auto_memory": str(memory) if memory else ""}),
        Row("elsewhere", f"{__name__}:host_tool"),
        *([Row("memory-auto", "memory:auto")] if auto else []),
    ]
    async with asyncio.timeout(30):
        booted = await boot([], rows, watch=None)
        await booted.runtime.settle()
    assert all(state == "active" for state in booted.loader.status().values()), booted.loader.status()
    return booted


async def _reply(booted: Booted, message: str) -> list[str]:
    """What the tools answered to the message, in order."""
    async with asyncio.timeout(30):
        events = [event async for event in booted.runtime.root.get("loop").reply(message)]
    return [str(e["content"]) for e in events if e.get("type") == "tool_result"]


@pytest.mark.parametrize("grades", [_ENFORCED, _UNENFORCED], ids=["jailed", "no-jail"])
async def test_the_model_saves_reads_and_deletes_a_memory_unasked_with_no_python_tool_at_all(
    tmp_path: Path, grades: Mapping[str, str]
) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    model = _Model(
        [_call("1", "memory", _SAVE), _call("2", "memory", {"action": "read", "name": "prefers-tabs"})],
        _END,
        [_call("3", "memory", {"action": "delete", "name": "prefers-tabs"}), _call("4", "elsewhere")],
        _END,
    )
    screen = _Screen()
    booted = await _booted(model, screen, grades, memory)
    saved, read = await _reply(booted, "remember that I like tabs")
    assert saved.startswith("saved the memory 'prefers-tabs'") and "Use tabs." in read
    assert (memory / "MEMORY.md").read_text() == "- [prefers-tabs](prefers-tabs.md): Tabs, not spaces\n"
    assert "memory" in model.offered[0] and "python" not in model.offered[0]
    deleted, elsewhere = await _reply(booted, "forget it")
    assert deleted.startswith("deleted the memory 'prefers-tabs'")
    assert (
        sorted(p.name for p in memory.iterdir()) == ["MEMORY.md"] and not (memory / "MEMORY.md").read_text()
    )
    # the memory tool was never put to the person; the other host tool was, and a no ran nothing
    assert [request["name"] for request in screen.asked] == ["elsewhere"]
    assert screen.asked[0]["runs"] == "host" and elsewhere.startswith("denied")
    await booted.runtime.shutdown()


async def test_the_next_conversation_s_prompt_lists_a_saved_memory_in_the_index(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    model = _Model([_call("1", "memory", _SAVE)], _END)
    booted = await _booted(model, _Screen(), _ENFORCED, memory)
    system = booted.runtime.root.get("system")
    before = system.text()
    assert "MEMORY.md is not there yet" in before
    [saved] = await _reply(booted, "remember that I like tabs")
    assert saved.startswith("saved")
    assert "prefers-tabs" not in system.text()  # this conversation's prompt is fixed
    async with asyncio.timeout(30):
        await booted.loader.restart("memory-auto")  # `/clear`: a new conversation
        await booted.runtime.settle()
    assert "Auto memory:" in system.text()
    assert "- [prefers-tabs](prefers-tabs.md): Tabs, not spaces" in system.text()
    await booted.runtime.shutdown()


@pytest.mark.parametrize(("auto", "named"), [(False, True), (True, False)], ids=["no-row", "no-directory"])
async def test_without_the_memory_auto_row_or_a_directory_for_it_there_is_no_memory_tool(
    tmp_path: Path, auto: bool, named: bool
) -> None:
    """The tool is the row's: a composition without the row (a sub-agent's is one, always) has
    none, and so has one whose host names no auto memory directory."""
    booted = await _booted(_Model(_END), _Screen(), _ENFORCED, tmp_path if named else None, auto=auto)
    assert booted.runtime.root.get("tools").get("memory") is None
    await booted.runtime.shutdown()
