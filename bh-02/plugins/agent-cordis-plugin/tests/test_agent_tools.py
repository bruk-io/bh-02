"""The tools broker, and the loop over it: any row's tool offered and run, CodeAct's `python` one
registration among others, never something the loop knows of."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from agent_cordis_plugin import (
    DECLINED,
    FAILED,
    LoopConfig,
    LoopModel,
    MemoryTranscript,
    ToolBroker,
    Unstarted,
    called,
    executor,
    loop,
    notes,
    shown,
    tools,
    transcript,
)
from cordis import Effects, Inspection, Runtime, acquire, bind, component
from cordis.loader import resolve
from cordis.testing import drive

type Json = dict[str, Any]


def _spec(name: str, **properties: str) -> Json:
    """A tool spec whose input has `properties`, each of the JSON Schema type given, all required."""
    return {
        "name": name,
        "description": f"The {name} tool.",
        "parameters": {
            "type": "object",
            "properties": {key: {"type": kind} for key, kind in properties.items()},
            "required": list(properties),
        },
    }


ECHO = _spec("echo", text="string")


async def _echo(input: Any) -> Json:
    return {"content": f"echo: {input['text']}", "touched": ["/p/said.txt"]}


class _Scripted:
    """A `model` that plays one scripted step per request and records the tools it was offered."""

    def __init__(self, *steps: Sequence[Json]) -> None:
        self.steps = list(steps)
        self.offered: list[tuple[str, ...]] = []

    async def complete(self, messages: Sequence[Any], tools: Sequence[Any]) -> AsyncIterator[Json]:
        self.offered.append(tuple(str(t["name"]) for t in tools))
        for chunk in self.steps.pop(0):
            yield chunk


def _call(id: str, name: str, **input: Any) -> Json:
    return {"type": "tool_call", "id": id, "name": name, "input": input}


def _text(said: str) -> Json:
    return {"type": "text", "text": said}


class _Approval:
    """An `approval` rule that lets nothing run unasked, and an `output` whose person says
    `answer` (yes) to everything; it keeps what was asked."""

    def __init__(self, answer: bool = True) -> None:
        self.asked: list[Any] = []
        self.answer = answer

    def unasked(self, request: Any) -> bool:
        return False

    async def confirm(self, request: Any) -> bool:
        self.asked.append(request)
        return self.answer

    async def approve(self, request: Any) -> bool:  # the loop's own, as `Asked` gives it
        return self.unasked(request) or await self.confirm(request)


class _Nowhere:
    """A `system` value that tells nothing."""

    def text(self) -> str:
        return ""


def test_the_specs_come_in_name_order_whatever_order_rows_registered_them() -> None:
    """The tool list is the start of what a model server caches, so a row registering again after
    a restart (python on `/clear`) gives the same list, not one with its tool moved to the end."""
    broker = ToolBroker()
    remove_zeta = broker.register(_spec("zeta"), _echo)
    broker.register(_spec("alpha"), _echo)
    broker.register(ECHO, _echo)
    before = broker.specs()
    assert [s["name"] for s in before] == ["alpha", "echo", "zeta"]
    remove_zeta()
    broker.register(_spec("zeta"), _echo)
    assert broker.specs() == before


def test_a_name_is_one_tool_and_a_remover_takes_only_its_own() -> None:
    broker = ToolBroker()
    remove = broker.register(ECHO, _echo)
    with pytest.raises(ValueError, match="a tool named 'echo' is already registered"):
        broker.register(ECHO, _echo)
    remove()
    remove()  # idempotent
    again = broker.register(ECHO, _echo)
    remove()  # the first registration's remover leaves the second
    assert broker.get("echo") is not None
    again()
    assert broker.get("echo") is None and broker.specs() == []


def test_a_registration_says_its_name_and_where_its_calls_run() -> None:
    broker = ToolBroker()
    with pytest.raises(ValueError, match="a tool's spec needs a `name`"):
        broker.register({"description": "nameless"}, _echo)
    with pytest.raises(ValueError, match="say 'jail' .* or 'host'"):
        broker.register(ECHO, _echo, runs="cloud")
    broker.register(ECHO, _echo, runs="host")
    tool = broker.get("echo")
    assert tool is not None and tool.runs == "host" and tool.spec is ECHO


async def test_ready_waits_for_a_tool_to_register_and_names_those_that_never_do() -> None:
    broker = ToolBroker()
    assert await broker.ready((), 0) == ()
    assert await broker.ready(["echo", "python"], 0.05) == ("echo", "python")

    async def later() -> None:
        await asyncio.sleep(0.02)
        broker.register(ECHO, _echo)

    task = asyncio.create_task(later())
    assert await broker.ready(["echo"], 5) == ()
    await task


async def test_the_tools_row_binds_an_empty_broker() -> None:
    effects = await drive(tools())
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "tools")]
    assert isinstance(effects[0].args[1], ToolBroker) and effects[0].args[1].specs() == []


async def test_a_call_answers_what_its_tool_said_and_a_tool_s_fault_is_the_model_s_to_read() -> None:
    broker = ToolBroker()

    async def fails(input: Any) -> Json:
        raise OSError("disk gone")

    async def mumbles(input: Any) -> Any:
        return "not a mapping"

    broker.register(ECHO, _echo)
    broker.register(_spec("fails"), fails)
    broker.register(_spec("mumbles"), mumbles)

    def tool(name: str) -> Any:
        return broker.get(name)

    assert await called(tool("echo"), "echo", {"text": "hi"}) == ("echo: hi", ("/p/said.txt",), False)
    assert await called(tool("fails"), "fails", {}) == (
        "error: the fails tool failed (OSError: disk gone); tell the person",
        (),
        True,
    )
    content, touched, failed = await called(tool("mumbles"), "mumbles", {})
    assert content.startswith("error: the mumbles tool answered with something other than its result")
    assert touched == () and failed


def test_a_call_is_shown_as_its_tool_says_else_as_its_input() -> None:
    broker = ToolBroker()

    def broken(input: Any) -> Json:
        raise KeyError("code")

    broker.register(ECHO, _echo)
    broker.register(
        _spec("python", code="string"), _echo, show=lambda i: {"title": "Run?", "lines": [i["code"]]}
    )
    broker.register(_spec("broken"), _echo, show=broken)
    plain = broker.get("echo")
    assert plain is not None
    assert shown(plain, "echo", {"text": "hi"}) == {
        "title": "Call echo with this input?",
        "lines": ["{", '  "text": "hi"', "}"],
        "language": "json",
    }
    python = broker.get("python")
    assert python is not None
    assert shown(python, "python", {"code": "1 + 1"}) == {"title": "Run?", "lines": ["1 + 1"]}
    failing = broker.get("broken")
    assert failing is not None and shown(failing, "broken", {})["language"] == "json"


def _composition(
    steps: Sequence[Sequence[Json]], *, requires: Sequence[str], wait: float = 5.0
) -> tuple[Runtime, _Scripted, _Approval]:
    """The agent's rows as a layer mounts them, with no python row: a model playing `steps`, and
    the loop over `tools`, requiring `requires`."""
    model, approval = _Scripted(*steps), _Approval()

    @component(provides=("model", "system", "approval", "output"))
    async def around() -> Effects:
        yield bind("model", model)
        yield bind("system", _Nowhere())
        yield bind("approval", approval)
        yield bind("output", approval)

    rt = Runtime()
    rt.mount(around, id="around")
    rt.mount(transcript, id="transcript")
    rt.mount(notes, id="notes")
    rt.mount(executor, id="executor")
    rt.mount(tools, id="tools")
    rt.mount(loop, id="loop", config=LoopConfig(requires=requires, wait=wait))
    return rt, model, approval


@component
async def _echo_row(*, tools: Any) -> Effects:
    """A layer's row offering the `echo` tool, in bh-02's own process."""
    yield acquire(tools.register, ECHO, _echo, runs="host")


async def _reply(rt: Runtime, message: str) -> list[Json]:
    return [event async for event in rt.root.get("loop").reply(message)]


async def test_without_a_kernel_row_another_row_s_tool_runs_a_turn_end_to_end() -> None:
    """CodeAct is the shipped default, not a requirement: the loop depends on `tools`, never on
    `kernel`, and a composition whose only tool is a layer row's runs a turn through it."""
    rt, model, approval = _composition([[_call("c1", "echo", text="hi")], [_text("done")]], requires=["echo"])
    rt.mount(_echo_row, id="echo")
    await rt.settle()
    events = await _reply(rt, "say hi")
    assert model.offered == [("echo",), ("echo",)]
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["content"] == "echo: hi"
    assert approval.asked[0]["runs"] == "host" and approval.asked[0]["title"] == "Call echo with this input?"
    assert "kernel" not in resolve("agent:loop").inject and "tools" in resolve("agent:loop").inject


async def test_the_first_message_waits_for_the_tools_the_loop_requires() -> None:
    """After `/clear` the loop and the kernel restart together: a message typed at once waits for
    `python` (here `echo`) to register again rather than begin a conversation without it."""
    rt, model, _ = _composition([[_text("hello")]], requires=["echo"])
    await rt.settle()
    task = asyncio.create_task(_reply(rt, "hi"))
    await asyncio.sleep(0.05)
    assert not task.done() and model.offered == []
    rt.mount(_echo_row, id="echo")
    await rt.settle()
    events = await task
    assert events[0] == {"type": "note", "text": "waiting for `echo` to start before the model is asked"}
    assert model.offered == [("echo",)]


async def test_a_required_tool_that_never_registers_fails_the_message_saying_which() -> None:
    rt, model, _ = _composition([[_text("never")]], requires=["echo"], wait=0.05)
    await rt.settle()
    with pytest.raises(Unstarted) as raised:
        await _reply(rt, "hi")
    assert raised.value.kind == "tools_missing"
    assert raised.value.message.startswith("`echo` did not start within 0.05 seconds")
    assert "/rows" in raised.value.message
    history = rt.root.get("transcript")
    assert [m["content"] for m in history.messages][-1] == FAILED  # kept, answered as a failed step
    assert model.offered == []


async def test_a_tool_s_row_restarting_reloads_nothing_and_the_list_stays_the_same() -> None:
    """The kernel row re-registers `python` on every restart: the loop, which depends only on the
    broker, stays up, offers the list it began with, and a call runs through the new registration."""
    rt, model, _ = _composition(
        [[_text("first")], [_call("c1", "echo", text="again")], [_text("done")]], requires=["echo"]
    )
    echo = rt.mount(_echo_row, id="echo")
    await rt.settle()
    loop_fiber = Inspection(rt).fiber("loop")
    await _reply(rt, "one")
    await echo.retire()
    await rt.settle()
    rt.mount(_echo_row, id="echo")
    await rt.settle()
    events = await _reply(rt, "two")
    assert Inspection(rt).fiber("loop") is loop_fiber
    assert model.offered == [("echo",), ("echo",), ("echo",)]
    assert next(e for e in events if e["type"] == "tool_result")["content"] == "echo: again"


async def test_a_call_to_a_tool_whose_row_is_restarting_waits_for_it() -> None:
    broker = ToolBroker()
    remove = broker.register(ECHO, _echo)
    model = _Scripted([_text("first")], [_call("c1", "echo", text="later")], [_text("done")])
    history = MemoryTranscript()
    looped = LoopModel(model, broker, history, _Approval(), requires=["echo"], wait=5)
    [e async for e in looped.reply("one")]
    remove()

    async def back() -> None:
        await asyncio.sleep(0.02)
        broker.register(ECHO, _echo)

    task = asyncio.create_task(back())
    events = [e async for e in looped.reply("two")]
    await task
    assert next(e for e in events if e["type"] == "tool_result")["content"] == "echo: later"


def _conversation(history: MemoryTranscript) -> list[Json]:
    """The transcript's `tools` entries: the list the conversation began with, then each change."""
    return [m for m in history.messages if m["role"] == "tools"]


async def _said(looped: LoopModel, message: str) -> list[Json]:
    return [e async for e in looped.reply(message)]


async def test_a_tool_added_mid_conversation_is_told_and_offered_from_the_next_conversation() -> None:
    """The list a conversation began with is in its transcript and every request offers it (a
    provider's default, `fixed`): a tool registered later is told on the next message, with
    what it takes, and kept as a change; a call naming it says it comes with the next
    conversation. A resumed loop over the same transcript offers the same list and tells
    nothing again; a new conversation (/clear, /compact: a fresh transcript) offers it."""
    broker = ToolBroker()
    broker.register(ECHO, _echo)
    model = _Scripted([_text("first")], [_call("c1", "late", text="x")], [_text("done")], [_text("again")])
    history = MemoryTranscript()
    looped = LoopModel(model, broker, history, _Approval())
    await _said(looped, "one")
    broker.register(_spec("late", text="string"), _echo)
    events = await _said(looped, "two")
    assert model.offered == [("echo",), ("echo",), ("echo",)]
    asked = next(m for m in reversed(history.messages) if m["role"] == "user")["content"]
    assert (
        "(bh-02: your tools have changed since this conversation began. Added: `late` (The late tool.)"
        in asked
    )
    assert "taking `text`" in asked and "offered to you from the next conversation" in asked
    assert {"type": "note", "text": "told the model its tools changed since the conversation began"} in events
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["content"].startswith("error: 'late' was added after this conversation began")
    assert _conversation(history) == [
        {"role": "tools", "tools": [ECHO]},
        {"role": "tools", "added": [_spec("late", text="string")]},
    ]
    resumed = LoopModel(model, broker, history, _Approval())  # a resume: the same transcript
    await _said(resumed, "three")
    assert model.offered[-1] == ("echo",) and len(_conversation(history)) == 2  # told once
    fresh = _Scripted([_text("new")])
    await _said(LoopModel(fresh, broker, MemoryTranscript(), _Approval()), "after /clear")
    assert fresh.offered == [("echo", "late")]


async def test_a_tool_removed_or_redefined_is_told_and_a_call_to_a_removed_one_does_not_run() -> None:
    broker = ToolBroker()
    remove_echo = broker.register(ECHO, _echo)
    remove_other = broker.register(_spec("other", text="string"), _echo)
    clock = [0.0]
    model = _Scripted([_text("first")], [_call("c1", "echo", text="x")], [_text("done")], [_text("ok")])
    history = MemoryTranscript()
    looped = LoopModel(model, broker, history, _Approval(), wait=5, clock=lambda: clock[-1])
    await _said(looped, "one")
    remove_echo()
    await _said(looped, "two")  # missing for less than `wait`: restarting, not removed
    assert len(_conversation(history)) == 1
    clock.append(10.0)
    remove_other()
    broker.register(_spec("other", text="string", more="integer"), _echo)
    await _said(looped, "three")
    assert _conversation(history)[1:] == [
        {"role": "tools", "removed": ["echo"], "redefined": [_spec("other", text="string", more="integer")]}
    ]
    told = next(m for m in reversed(history.messages) if m["role"] == "user")["content"]
    assert "Redefined: `other` (The other tool.), taking `text`, `more`." in told
    assert "Removed: `echo`; a call to one does not run." in told
    assert model.offered[-1] == ("echo", "other")  # the list it began with: the cache holds
    resumed = _Scripted([_call("c2", "echo", text="y")], [_text("done")])
    events = await _said(LoopModel(resumed, broker, history, _Approval(), wait=5), "four")
    result = next(e for e in events if e["type"] == "tool_result")
    assert (
        result["content"]
        == "error: the echo tool was removed since this conversation began, so this call did not run"
    )
    assert resumed.offered[0] == ("echo", "other")  # a resume rebuilds the same request
    assert len(_conversation(history)) == 2  # nothing more changed


async def test_a_provider_that_takes_the_list_as_it_reads_now_is_offered_it() -> None:
    """A provider whose cache a changed list does not cost, or that tells a change its own way,
    says so (`tool_changes = "listed"`): each request offers the list as it reads now, and the
    change is still told and kept, so a resume offers the same."""
    broker = ToolBroker()
    broker.register(ECHO, _echo)
    model = _Scripted([_text("first")], [_call("c1", "late", text="x")], [_text("done")])
    model.tool_changes = "listed"  # type: ignore[attr-defined]
    history = MemoryTranscript()
    looped = LoopModel(model, broker, history, _Approval())
    await _said(looped, "one")
    broker.register(_spec("late", text="string"), _echo)
    events = await _said(looped, "two")
    assert model.offered == [("echo",), ("echo", "late"), ("echo", "late")]
    assert next(e for e in events if e["type"] == "tool_result")["content"] == "echo: x"
    told = next(m for m in reversed(history.messages) if m["role"] == "user")["content"]
    assert (
        told.startswith("(bh-02: your tools have changed")
        and "Your tool list reads as they are now.)" in told
    )


async def test_a_conversation_begun_before_the_loop_kept_its_tools_begins_its_list_now() -> None:
    """A resumed transcript with no `tools` entry (kept before the loop kept them) takes the list
    as it reads at its next request, telling nothing."""
    broker = ToolBroker()
    broker.register(ECHO, _echo)
    history = MemoryTranscript()
    history.append({"role": "user", "content": "old"})
    history.append({"role": "assistant", "content": "answer"})
    model = _Scripted([_text("hi")])
    events = await _said(LoopModel(model, broker, history, _Approval()), "new")
    assert _conversation(history) == [{"role": "tools", "tools": [ECHO]}]
    assert not [e for e in events if e["type"] == "note"]


async def test_a_call_a_tool_makes_with_no_loop_serving_fails_saying_so() -> None:
    broker = ToolBroker()
    broker.register(ECHO, _echo)
    assert await broker.call("echo", {"text": "hi"}) == {
        "content": "error: no conversation is running to call echo in",
        "failed": True,
    }


async def test_a_call_a_tool_makes_goes_as_the_model_s_do_its_notes_told_with_the_call_it_came_from() -> None:
    """An input's `tools.echo(...)` (here a tool `outer` whose run calls `echo` through the
    broker): put to `approval` and asked of `notes` as the model's own call is, its notes told
    with the call it was made from; a declined, unknown or malformed one is why it did not run."""
    broker, approval, history = ToolBroker(), _Approval(), MemoryTranscript()
    answers: list[Any] = []

    async def outer(input: Any) -> Json:
        answers.append(await broker.call("echo", {"text": "inside"}))
        answers.append(await broker.call("nothing", {}))
        answers.append(await broker.call("echo", {"words": "no text"}))
        return {"content": "outer done"}

    broker.register(ECHO, _echo)
    broker.register(_spec("outer"), outer)

    def said(call: Any) -> str:
        return f"noted {call['name']}: {call['result']}" if call["touched"] else ""

    model = _Scripted([_call("c1", "outer")], [_text("done")])
    looped = LoopModel(model, broker, history, approval, notes=[said])
    broker.serve(looped.nested)
    await _said(looped, "go")
    assert answers == [
        {"content": "echo: inside", "failed": False},
        {"content": "error: there is no nothing tool now", "failed": True},
        {"content": "error: echo needs `text`", "failed": True},
    ]
    assert [request["name"] for request in approval.asked] == ["outer", "echo"]  # each put to approval
    (answer,) = [m for m in history.messages if m["role"] == "tool"]
    assert answer["notes"] == ["noted echo: echo: inside"]  # told with the call it came from
    assert answer["content"] == "outer done\n\nnoted echo: echo: inside"
    refused = LoopModel(_Scripted(), broker, MemoryTranscript(), _Approval(answer=False))
    assert await refused.nested("echo", {"text": "hi"}) == {"content": DECLINED, "failed": True}
