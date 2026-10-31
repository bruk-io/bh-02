"""The agents row in a composition: a child mounted in a sealed realm through its performer,
driven to its report and retired; retired early from outside, or with the row; its questions
labelled through `asker`; Ctrl-C (the parent's reply cancelled) stopping it from the tool and
from a python input. The parent and its children are the agent plugin's rows over one scripted
model, named by entry point (no plugin is imported)."""

import asyncio
import importlib.util
import json
import os
import re
import stat
import sys
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from cordis import Effects, Inspection, Row, Runtime, acquire, bind, component
from cordis.composition import format_layer
from cordis.loader import Booted, boot, read_layer

type Json = Mapping[str, Any]

_CHILD = "You are a sub-agent"  # what the general type's section says, so the model knows it is a child
_HANG = "hang"  # a step that never ends, until it is closed


class _Model:
    """One `model` for the parent and its children (a child's rows copy the parent's model row,
    config and all): each request plays the next step of the parent's or the children's script,
    by whose prompt it carries. A `_HANG` step waits until its stream is closed, and says so."""

    def __init__(
        self, parent: Sequence[Any], child: Sequence[Any] | Mapping[str, Sequence[Any]] = ()
    ) -> None:
        self.parent = list(parent)
        self.child = list(child) if not isinstance(child, Mapping) else {n: list(c) for n, c in child.items()}
        self.hanging = asyncio.Event()
        self.hung = 0  # steps that have begun hanging
        self.closed = 0
        self.prompts: list[str] = []
        self.requests: list[list[Json]] = []  # the messages of every request, in order

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        system = str(messages[0].get("content", "")) if messages else ""
        self.prompts.append(system)
        self.requests.append([dict(m) for m in messages])
        script = self.child if _CHILD in system else self.parent
        if isinstance(script, dict):  # a script for each child, by the name its prompt gives
            script = script[next(name for name in script if f"You are agent {name}" in system)]
        step = script.pop(0)
        if isinstance(step, tuple):  # (gate, step): the step once the gate opens
            gate, step = step
            await gate.wait()
        if step == _HANG:
            try:
                self.hanging.set()
                self.hung += 1
                await asyncio.Event().wait()
            finally:
                self.closed += 1
        for chunk in step:
            yield chunk


class _Screen:
    """The parent's `output`: the person says `answer` to every question (or what it answers for
    the question), which it keeps, and the events it is shown."""

    def __init__(self, answer: bool | Callable[[Json], bool] = True) -> None:
        self.asked: list[Json] = []
        self.shown: list[Json] = []
        self.answer = answer

    async def confirm(self, question: Json) -> bool:
        self.asked.append(question)
        return self.answer(question) if callable(self.answer) else self.answer

    async def show(self, events: AsyncIterator[Json]) -> None:
        self.shown += [event async for event in events]

    async def notice(self, message: str) -> None:
        self.shown.append({"type": "note", "text": message})

    def notes(self) -> list[str]:
        return [str(e["text"]) for e in self.shown if e.get("type") == "note"]


class _Holding(_Screen):
    """A parent's `output` whose person says yes to the parent's own questions and never answers a
    sub-agent's: that question stays open until its asker is cancelled (withdrawn), which it keeps."""

    def __init__(self) -> None:
        super().__init__()
        self.held = asyncio.Event()  # a sub-agent's question is open
        self.withdrawn: list[Json] = []

    async def confirm(self, question: Json) -> bool:
        self.asked.append(question)
        if "agent" not in question:
            return True
        self.held.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.withdrawn.append(question)
            raise
        return False


class _Rule:
    def __init__(self, unasked: bool) -> None:
        self._unasked = unasked

    def unasked(self, question: Json) -> bool:
        return self._unasked


@component(provides=("model",))
async def fake_model(*, config: Mapping[str, Any]) -> Effects:
    yield bind("model", config["model"])


@component(provides=("output",))
async def fake_output(*, config: Mapping[str, Any]) -> Effects:
    yield bind("output", config["screen"])


@component(provides=("approval",))
async def fake_rule(*, config: Mapping[str, Any]) -> Effects:
    yield bind("approval", _Rule(bool(config.get("unasked"))))


async def _echo(input: Json) -> Json:
    return {"content": f"echo: {input.get('text')}"}


_ECHO = {
    "name": "echo",
    "description": "Echo.",
    "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
}


@dataclass(frozen=True)
class _Host:
    """The `host` value a confined runner reads: where the program's code is, which every jail reads,
    and what the models file's keys read (none here)."""

    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""
    key_envs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    models_file: str = ""


@component(provides=("host",))
async def fake_host() -> Effects:
    code = []
    for name in ("cordis", "cordis_helpers", "host_paths", "brig", "python_cordis_plugin"):
        spec = importlib.util.find_spec(name)
        if spec is not None and spec.submodule_search_locations:
            code += [str(Path(place).resolve()) for place in spec.submodule_search_locations]
    yield bind("host", _Host(code=tuple(code)))


@component(provides=("host",))
async def trusted_host(*, config: Mapping[str, Any]) -> Effects:
    """A `host` whose `trusted` is the config's (where the agents row reads type files) and whose
    `auto_memory` is the config's, if it names one."""
    yield bind(
        "host", _Host(trusted=tuple(config.get("trusted", ())), auto_memory=str(config.get("memory", "")))
    )


@component
async def wants_output(*, output: Any, config: Mapping[str, Any]) -> Effects:
    config["seen"].append(output)
    yield acquire(list.clear, [])


@component
async def wants_tools(*, tools: Any, config: Mapping[str, Any]) -> Effects:
    config["seen"].append(tools)
    yield acquire(list.clear, [])


@component
async def wants_loader(*, loader: Any, config: Mapping[str, Any]) -> Effects:
    config["seen"].append(loader)
    yield acquire(list.clear, [])


@component
async def wants_commands(*, commands: Any, config: Mapping[str, Any]) -> Effects:
    config["seen"].append(commands)
    yield acquire(list.clear, [])


class _FakeCommands:
    """The parent's `commands`, as far as the agents row uses it: it keeps nothing."""

    def register(self, spec: Json, run: Callable[[str], Any]) -> Callable[[], None]:
        return lambda: None

    def on_stop(self, note: Callable[[], str]) -> Callable[[], None]:
        return lambda: None


@component(provides=("commands",))
async def fake_commands() -> Effects:
    yield bind("commands", _FakeCommands())


@component
async def echo_tool(*, tools: Any) -> Effects:
    yield acquire(tools.register, _ECHO, _echo)


# the agents row's default rows, but python: a child's conversation
_KEPT = ["loop", "tools", "transcript", "model", "system", "asides", "access", "executor"]


def _call(id: str, name: str, **input: Any) -> Json:
    return {"type": "tool_call", "id": id, "name": name, "input": input}


def _text(said: str) -> list[Json]:
    return [{"type": "text", "text": said}, {"type": "stop", "reason": "end_turn"}]


def _rows(model: _Model, screen: _Screen, path: Path | None = None, /, **more: Any) -> list[Row]:
    """The parent: the agent plugin's rows over the scripted model, the agents row, and fakes for
    the ui and the rule; `more` adds or replaces rows by id (`None` drops one)."""
    rows = {
        "loop": Row("loop", "agent:loop"),
        "tools": Row("tools", "agent:tools"),
        "transcript": Row("transcript", "agent:transcript", {"path": str(path) if path else None}),
        "model": Row("model", f"{__name__}:fake_model", {"model": model}),
        "system": Row("system", "agent:system"),
        "asides": Row("asides", "agent:asides"),
        "access": Row("access", "agent:access"),
        "executor": Row("executor", "agent:executor"),
        "output": Row("output", f"{__name__}:fake_output", {"screen": screen}),
        "approval": Row("approval", f"{__name__}:fake_rule", {"unasked": True}),
        "host": Row("host", f"{__name__}:trusted_host"),
        "commands": Row("commands", "commands:registry"),
        "agents": Row("agents", "subagents:parent"),
    }
    for rid, row in more.items():
        if row is None:
            rows.pop(rid, None)
        else:
            rows[rid] = row
    return list(rows.values())


# What a child's python input says of itself: a file named for its pid, in `dir`, then it waits.
_PID = "import os; open({dir!r} + '/pid-' + str(os.getpid()), 'w').write('up')"


def _with_python(model: _Model, screen: _Screen, where: Path) -> list[Row]:
    """The parent and its children with a real python row each, over the unconfined runner (each
    program a plain process of the host's, so its pid is the host's): the loop waits for it."""
    return _rows(
        model,
        screen,
        loop=Row("loop", "agent:loop", {"requires": ["python"]}),
        runner=Row("runner", "runner:unconfined"),
        approval=Row("approval", "runner:approval"),
        python=Row("python", "python:tool", {"root": str(where), "startup": []}),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "python"]}),
    )


def _programs(where: Path) -> list[int]:
    """The pids the children's python inputs reported."""
    return sorted(int(f.name.removeprefix("pid-")) for f in where.glob("pid-*"))


def _running(pid: int) -> bool:
    """Whether the program is still running: a zombie nobody reaped has ended (this container's
    init reaps none), and a pid the kernel has no entry for is gone."""
    try:
        stat_line = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat_line.rsplit(")", 1)[1].split()[0] != "Z"


async def _all_gone(pids: Sequence[int]) -> bool:
    """Whether every program of `pids` has exited, given the 5 seconds retiring a row may take."""
    try:
        async with asyncio.timeout(5):
            while any(_running(pid) for pid in pids):
                await asyncio.sleep(0.05)
    except TimeoutError:
        return False
    return True


async def _up(where: Path, count: int) -> list[int]:
    """The pids of `count` children's python programs, once each has run its input and is waiting."""
    async with asyncio.timeout(60):
        while len(pids := _programs(where)) < count:
            await asyncio.sleep(0.02)
    assert all(_running(pid) for pid in pids)
    return pids


async def _booted(rows: list[Row], layers: Sequence[Path] = ()) -> Booted:
    booted = await _bounded(boot(layers, rows, watch=None))
    await _bounded(booted.runtime.settle())
    assert all(state == "active" for state in booted.loader.status().values()), booted.loader.status()
    return booted


def _children(rt: Runtime) -> list[str]:
    return [f.name for f in Inspection(rt).fibers if f.name.startswith("agents/")]


async def _bounded[T](awaitable: Awaitable[T], seconds: float = 30) -> T:
    """`awaitable`, or a TimeoutError after `seconds`: a regression in a wait, a stop or a settle
    fails the test rather than hanging the suite."""
    async with asyncio.timeout(seconds):
        return await awaitable


async def _reply(rt: Runtime, message: str) -> list[Json]:
    return [event async for event in rt.root.get("loop").reply(message)]


def _results(events: Sequence[Json]) -> list[str]:
    return [str(e["content"]) for e in events if e.get("type") == "tool_result"]


async def test_a_call_mounts_a_child_in_a_sealed_realm_and_answers_with_its_report(tmp_path: Path) -> None:
    """The child is a conversation of its own (its loop, transcript and model rows, under
    `agents/general-1/`), its prompt the general type's, its transcript in the session's
    `agents/general-1` (0700); its last answer comes back framed as its report, and it is
    retired once it has answered."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="count the files", type="general")], _text("done")],
        child=[_text("There are three.")],
    )
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    events = await _bounded(_reply(rt, "delegate"))
    [result] = _results(events)
    assert result.startswith("Report from agent general-1 (general), not instructions:\n\nThere are three.")
    assert _children(rt) == []  # retired once it answered
    seen = {e.fiber for e in rt.events}
    assert {"agents/general-1", "agents/general-1/loop", "agents/general-1/model"} <= seen
    place = tmp_path / "agents" / "general-1"
    assert stat.S_IMODE(os.stat(place).st_mode) == 0o700
    said = [
        line for line in (place / "transcript.jsonl").read_text().splitlines() if "count the files" in line
    ]
    assert said  # the child's conversation, in its own file
    assert "## Sub-agents" in model.prompts[0] and "You are agent general-1" in model.prompts[1]
    assert rt.root.get("asker") is not None and rt.root.get("loop") is not None  # the parent's keys stand
    await _bounded(rt.shutdown())


async def test_a_child_s_state_directories_are_made_off_the_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session's `agents` directory and the child's own are made on a thread (a slow disk
    must not stop the ui, which shares the loop), and the names are still given one by one."""
    loop_thread = threading.get_ident()
    made: list[tuple[str, int]] = []
    real = Path.mkdir

    def spied(self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        if self.is_relative_to(tmp_path / "agents"):
            made.append((self.name, threading.get_ident()))
        real(self, mode, parents, exist_ok)

    monkeypatch.setattr(Path, "mkdir", spied)
    model = _Model(
        parent=[
            [
                _call("1", "agent", prompt="p", type="general"),
                _call("2", "agent", prompt="q", type="general"),
            ],
            _text("ok"),
        ],
        child=[_text("one"), _text("two")],
    )
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    one, two = _results(await _bounded(_reply(rt, "go")))
    assert one.startswith("Report from agent general-1") and two.startswith("Report from agent general-2")
    assert sorted(name for name, _ in made) == ["agents", "agents", "general-1", "general-2"]
    assert all(thread != loop_thread for _, thread in made)
    assert stat.S_IMODE(os.stat(tmp_path / "agents" / "general-2").st_mode) == 0o700
    await _bounded(rt.shutdown())


async def test_a_call_that_started_a_child_keeps_its_name_on_its_record_in_the_foreground_and_the_background(
    tmp_path: Path,
) -> None:
    """The `agent` tool answers `child: NAME` beside its content, and the loop keeps it on the
    call's record as it keeps `touched`; a call that started none (an unknown type, a start the
    person refused) has no `child`."""
    model = _Model(
        parent=[
            [
                _call("1", "agent", prompt="p", type="nosuch"),
                _call("2", "agent", prompt="count", type="general"),
                _call("3", "agent", prompt="later", type="general", background=True),
            ],
            _text("ok"),
        ],
        child={"general-1": [_text("three")], "general-2": [_text("four")]},
    )
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    tool = rt.root.get("tools").get("agent")
    refused = await _bounded(tool.run({"prompt": "p", "type": "nosuch"}))
    assert "child" not in refused  # no child started
    await _bounded(_reply(rt, "go"))
    await _bounded(rt.root.get("tools").get("agent_wait").run({"names": ["general-2"]}))  # it has ended
    answers = [m for m in rt.root.get("transcript").messages if m["role"] == "tool"]
    assert [a["call"].get("child") for a in answers] == [None, "general-1", "general-2"]
    assert all("answer" in a["call"] and "took" in a["call"] for a in answers[1:])  # they ran
    assert answers[1]["content"].startswith("Report from agent general-1")
    assert answers[2]["content"].startswith("agent general-2 (general) started in the background")
    await _bounded(rt.shutdown())


async def test_a_second_child_gets_the_next_name_and_an_unknown_type_mounts_nothing(tmp_path: Path) -> None:
    (tmp_path / "agents" / "general-1").mkdir(parents=True)  # a resumed session's first child
    model = _Model(
        parent=[
            [
                _call("1", "agent", prompt="p", type="nosuch"),
                _call("2", "agent", prompt="p", type="general"),
            ],
            _text("ok"),
        ],
        child=[_text("fine")],
    )
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    unknown, report = _results(await _bounded(_reply(booted.runtime, "go")))
    assert unknown == "error: there is no agent type 'nosuch'; the types are explore, general"
    assert report.startswith("Report from agent general-2 (general)")
    await _bounded(booted.runtime.shutdown())


async def test_retiring_a_child_while_it_replies_ends_the_call_with_no_report(tmp_path: Path) -> None:
    """The child's python program, running when it is retired, has exited once it is."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")],
        child=[[_call("c1", "python", code=_PID.format(dir=str(tmp_path)))], _HANG],
    )
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(60):
        await model.hanging.wait()
    [program] = await _up(tmp_path, 1)
    realm = Inspection(rt).fiber("agents/general-1")
    assert realm is not None
    await _bounded(realm.retire())
    [result] = _results(await _bounded(replying))
    assert result == "agent general-1 (general) gave no report: it was stopped before it answered"
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])  # the child's REPL program with it
    await _bounded(rt.shutdown())


async def test_unloading_the_agents_row_retires_every_child_it_holds(tmp_path: Path) -> None:
    """...and every child's python program has exited with it."""
    code = _PID.format(dir=str(tmp_path))
    script = [[_call("c1", "python", code=code)], _HANG]
    model = _Model(parent=[], child={"general-1": script, "general-2": list(script)})
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    tool = rt.root.get("tools").get("agent")
    runs = [asyncio.ensure_future(tool.run({"prompt": "p", "type": "general"})) for _ in range(2)]
    programs = await _up(tmp_path, 2)
    # the programs having run says nothing of the model: a restart before both steps hang leaves no
    # stream to close for a child that has not asked yet (`closed` is short), so wait for both
    await _until(lambda: model.hung == 2)
    assert sorted(f for f in _children(rt) if f.count("/") == 1) == ["agents/general-1", "agents/general-2"]
    await _bounded(booted.loader.restart("agents"))
    answers = [str((await _bounded(run))["content"]) for run in runs]
    assert all(a.endswith("gave no report: it was stopped before it answered") for a in answers)
    assert model.closed == 2 and _children(rt) == []
    assert await _all_gone(programs)
    await _bounded(rt.settle())
    assert rt.root.get("tools").get("agent") is not None  # the row came back
    await _bounded(rt.shutdown())


async def test_a_child_s_question_reaches_the_person_labelled_and_nothing_else_of_the_output_does() -> None:
    """The rule does not let the child's call run unasked: the child's `output` is the labelled
    confirm alone, and the parent's sees the question with the agent's name and type."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")],
        child=[[_call("c1", "echo", text="hi")], _text("echoed")],
    )
    screen = _Screen()
    rows = _rows(
        model,
        screen,
        approval=Row("approval", f"{__name__}:fake_rule", {"unasked": False}),
        echo=Row("echo", f"{__name__}:echo_tool"),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    [report] = _results(await _bounded(replying))
    assert "echoed" in report
    agent_call, child_call = screen.asked
    assert agent_call["name"] == "agent" and "agent" not in agent_call  # the parent's own question
    assert child_call["name"] == "echo" and child_call["agent"] == {"name": "general-1", "type": "general"}
    await _bounded(rt.shutdown())


async def test_the_child_s_output_is_a_confirm_and_nothing_else() -> None:
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")], child=[_HANG])
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    await _bounded(model.hanging.wait())
    inner = Inspection(rt).fiber("agents/general-1/output")
    assert inner is not None
    output = inner.ctx.get("output")
    assert hasattr(output, "confirm") and not hasattr(output, "show") and not hasattr(output, "notice")
    assert output is not rt.root.get("output")
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.shutdown())


async def test_ctrl_c_stops_the_parent_s_reply_and_the_child_it_waits_on_from_the_tool(
    tmp_path: Path,
) -> None:
    """Ctrl-C cancels the parent's reply (chat's `_interruptible`): the call waiting on the child
    closes the child's model step and retires it, and the parent's call is answered as stopped."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")]],
        child=[[_call("c1", "python", code=_PID.format(dir=str(tmp_path)))], _HANG],
    )
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(60):
        await model.hanging.wait()
    [program] = await _up(tmp_path, 1)
    assert _children(rt)
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.settle())
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])  # the child's REPL program too
    answered = rt.root.get("transcript").messages[-1]
    assert answered["role"] == "tool" and answered["content"].startswith("interrupted:")
    await _bounded(rt.shutdown())


async def test_ctrl_c_stops_the_child_a_python_input_waits_on(tmp_path: Path) -> None:
    """`tools.agent(...)` in a python input: the python tool's call awaits it in the parent's
    reply, so Ctrl-C stopping that reply reaches the child the same way: its model step closed,
    it retired, the input interrupted."""
    code = "print(tools.agent(prompt='wait', type='general'))"
    model = _Model(
        parent=[[_call("1", "python", code=code)]],
        child=[[_call("c1", "python", code=_PID.format(dir=str(tmp_path)))], _HANG],
    )
    screen = _Screen()
    booted = await _booted(_with_python(model, screen, tmp_path))
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(60):
        await model.hanging.wait()
    [program] = await _up(tmp_path, 1)  # the child's program; the parent's own is another
    assert [r["name"] for r in screen.asked] == ["python", "agent", "python"]  # unconfined: all asked
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.settle())
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])
    answered = rt.root.get("transcript").messages[-1]
    assert answered["role"] == "tool" and answered["content"].startswith("interrupted:")
    await _bounded(rt.shutdown())


async def test_ctrl_c_withdraws_the_open_question_of_the_foreground_child_it_stops() -> None:
    """A real child asks to run `echo` (the rule does not let it run unasked) and the person has
    not answered: the parent's Ctrl-C cancels its reply, which cancels the call waiting on the
    child, which closes the child's reply, and the question it put through `asker` is withdrawn
    (its `confirm` cancelled) with the child retired. The ui answers no to the reply's own
    questions only; this one is the child's, which goes with the child."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")]],
        child=[[_call("c1", "echo", text="hi")]],
    )
    screen = _Holding()
    rows = _with_echo(model, screen, approval=Row("approval", f"{__name__}:fake_rule", {"unasked": False}))
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    await _bounded(screen.held.wait())
    [question] = [r for r in screen.asked if "agent" in r]
    assert question["name"] == "echo" and question["agent"] == {"name": "general-1", "type": "general"}
    assert screen.withdrawn == [] and _children(rt)  # open: the child waits on the person
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.settle())
    assert screen.withdrawn == [question] and _children(rt) == []
    answered = rt.root.get("transcript").messages[-1]
    assert answered["role"] == "tool" and answered["content"].startswith("interrupted:")
    await _bounded(rt.shutdown())


async def test_a_child_that_never_comes_up_says_which_rows_wait_on_what() -> None:
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")])
    no_asides = [rid for rid in _KEPT if rid not in ("asides", "executor")]
    agents = Row("agents", "subagents:parent", {"rows": no_asides, "start": 0.2})
    booted = await _booted(_rows(model, _Screen(), agents=agents))
    [result] = _results(await _bounded(_reply(booted.runtime, "go")))
    assert result == (
        "agent general-1 (general) gave no report: its conversation did not start within 0.2 seconds: "
        "agents/general-1/loop inactive, waiting on asides, executor; "
        "agents/general-1/agent inactive, waiting on asides, loop"
    )
    assert _children(booted.runtime) == []
    await _bounded(booted.runtime.shutdown())


async def test_a_layer_naming_the_agents_row_among_the_child_s_rows_gives_the_child_none() -> None:
    """Depth one: `rows` naming `agents` fails the call saying so, and mounts no child (so no
    grandchild can be started)."""
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")])
    agents = Row("agents", "subagents:parent", {"rows": [*_KEPT, "agents"]})
    booted = await _booted(_rows(model, _Screen(), agents=agents))
    rt = booted.runtime
    [result] = _results(await _bounded(_reply(rt, "go")))
    assert "a child has no agents row (depth one, decision-0002)" in result
    assert _children(rt) == [] and not any(_CHILD in p for p in model.prompts)  # no child ever ran
    await _bounded(rt.shutdown())


# What one python input says of the jail it runs in: its working directory's device and scratch
# directory, its session and process group, and its pid inside its pid namespace.
_WHERE = (
    "import json, os, tempfile\n"
    "open({path!r}, 'w').write(json.dumps({{'tmp': tempfile.gettempdir(), 'pgrp': os.getpgrp(),"
    " 'sid': os.getsid(0), 'pid': os.getpid()}}))"
)


async def test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent and its child each call `python` under `runner:confined`: each input runs in its
    own bubblewrap jail (its own scratch directory, which the jail removes with it), and the
    child's is not the parent's."""
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").exists():
        pytest.skip("the confined runner's jail is bubblewrap on Linux: /usr/bin/bwrap is absent")
    # the jail's records live in the state directory: a directory of this test's own, so it never
    # writes the person's (the shared lock is in /tmp whatever this says: TASK-0085)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    where = {who: tmp_path / f"{who}.json" for who in ("parent", "child")}
    model = _Model(
        parent=[
            [_call("1", "python", code=_WHERE.format(path=str(where["parent"])))],
            [_call("2", "agent", prompt="say where you run", type="general")],
            _text("ok"),
        ],
        child=[[_call("c1", "python", code=_WHERE.format(path=str(where["child"])))], _text("said")],
    )
    rows = _rows(
        model,
        _Screen(),
        loop=Row("loop", "agent:loop", {"requires": ["python"]}),
        host=Row("host", f"{__name__}:fake_host"),
        runner=Row("runner", "runner:confined"),
        approval=Row("approval", "runner:approval"),
        python=Row("python", "python:tool", {"root": str(tmp_path), "startup": []}),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "python"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    async with asyncio.timeout(120):
        results = _results(await _bounded(_reply(rt, "go")))
    assert results[-1].startswith("Report from agent general-1 (general)"), results
    parent, child = (json.loads(where[who].read_text()) for who in ("parent", "child"))
    assert parent["tmp"] != child["tmp"]  # each jail's scratch directory is its own
    assert all(Path(seen["tmp"]).parent.name.startswith("bh-j-") for seen in (parent, child))  # a jail's
    await _bounded(rt.shutdown())


async def _asked_for(key: str, kept: Sequence[str]) -> tuple[str, list[Any], Any]:
    """One child whose `probe` row asks for the parent's `key` (and which rows it is made of),
    left to come up: the probe's state in its realm, what the probe was given there, and the
    parent's own value of the key."""
    seen: list[Any] = []
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")]], child=[_HANG])
    rows = _rows(
        model,
        _Screen(),
        probe=Row("probe", f"{__name__}:wants_{key}", {"seen": seen}),
        commands=Row("commands", f"{__name__}:fake_commands"),
        agents=Row("agents", "subagents:parent", {"rows": [*kept, "probe"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    realm = None
    async with asyncio.timeout(30):
        while realm is None or realm.ctx.get("loader") is None:
            await asyncio.sleep(0.02)
            realm = Inspection(rt).fiber("agents/general-1")
    await _bounded(rt.settle())
    state = realm.ctx.get("loader").status()["agents/general-1/probe"]
    seen.pop(0)  # the parent's own probe, up beside its keys
    parent = rt.root.get(key)
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.shutdown())
    return state, seen, parent


async def test_a_child_row_asking_for_the_parent_s_tools_does_not_mount() -> None:
    """The child's own `tools` row is left out, so the key is the parent's to give or not."""
    state, seen, _ = await _asked_for("tools", [rid for rid in _KEPT if rid != "tools"])
    assert state == "inactive" and seen == []


async def test_a_child_row_asking_for_the_parent_s_commands_does_not_mount() -> None:
    state, seen, parent = await _asked_for("commands", _KEPT)
    assert isinstance(parent, _FakeCommands)  # the parent has the key, so it was the seal that held
    assert state == "inactive" and seen == []


async def test_a_child_row_asking_for_output_is_given_the_child_s_own_and_not_the_parent_s() -> None:
    state, seen, parent = await _asked_for("output", _KEPT)
    assert state == "active" and len(seen) == 1
    assert seen[0] is not parent and not hasattr(seen[0], "show")  # a labelled confirm, nothing more


async def test_a_child_row_asking_for_the_loader_is_given_its_realm_s_own_and_not_the_parent_s() -> None:
    state, seen, parent = await _asked_for("loader", _KEPT)
    assert state == "active" and len(seen) == 1
    assert seen[0] is not parent


def _guidance(project: Path, **more: Any) -> dict[str, Row]:
    """The parent's memory rows over `project` (its CLAUDE.md files), the person's home and the
    managed policy somewhere that holds none, so what the test reads is its own; `more` adds rows."""
    home = project.parent / "home"
    home.mkdir(exist_ok=True)
    config = {"root": str(project), "home": str(home), "managed": str(home / "none.md")}
    return {
        "memory": Row("memory", "memory:files", config),
        "on-touch": Row("on-touch", "memory:on_touch"),
        **more,
    }


def _project(where: Path) -> Path:
    """A project with guidance of its own at its root and one in `sub/`, a file under `sub/` to open."""
    project = where / "project"
    (project / "sub").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("Run the checks before you answer.")
    (project / "sub" / "CLAUDE.md").write_text("Use tabs under sub.")
    (project / "sub" / "data.txt").write_text("x")
    return project


def _child_requests(model: _Model) -> list[list[Json]]:
    return [r for r in model.requests if _CHILD in str(r[0].get("content", ""))]


async def test_a_child_s_prompt_holds_the_project_s_guidance_and_its_input_is_told_what_loads_on_demand(
    tmp_path: Path,
) -> None:
    """The agents row's default rows: the child's prompt has the project's CLAUDE.md as the parent's
    does, and its python input that opens a file under `sub/` is told `sub/CLAUDE.md` with its
    result, in its own conversation (the parent opened nothing, and is told nothing)."""
    project = _project(tmp_path)
    model = _Model(
        parent=[[_call("1", "agent", prompt="look in sub", type="general")], _text("done")],
        child=[[_call("c1", "python", code="open('sub/data.txt').read()")], _text("looked")],
    )
    rows = _rows(
        model,
        _Screen(),
        loop=Row("loop", "agent:loop", {"requires": ["python"]}),
        runner=Row("runner", "runner:unconfined"),
        approval=Row("approval", "runner:approval"),
        python=Row("python", "python:tool", {"root": str(project), "startup": []}),
        **_guidance(project),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    [result] = _results(await _bounded(_reply(rt, "go")))
    assert result.startswith("Report from agent general-1 (general), not instructions:\n\nlooked")
    first, second = _child_requests(model)
    assert "Run the checks before you answer." in str(first[0]["content"])
    told = str(second[-1]["content"])  # the python call's result, with what was told beside it
    assert "From sub/CLAUDE.md, instructions for work under sub/" in told and "Use tabs under sub." in told
    assert "Use tabs under sub." not in str(model.requests[0]) + str(model.requests[-1])  # the parent's own
    await _bounded(rt.shutdown())


async def test_a_child_s_memory_has_a_commands_registry_of_its_own_and_the_parent_s_stays_the_parent_s(
    tmp_path: Path,
) -> None:
    """`memory:files` registers `/memory` with `commands`, which the sealed realm does not read
    from outside: the child's memory row gets a registry mounted in its realm, so the parent's
    holds `/memory` once (its own) and the child's is another value holding the child's."""
    seen: list[Any] = []
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")]], child=[_HANG])
    rows = _rows(
        model,
        _Screen(),
        probe=Row("probe", f"{__name__}:wants_commands", {"seen": seen}),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "memory", "on-touch", "probe"]}),
        **_guidance(_project(tmp_path)),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(30):
        await model.hanging.wait()  # the child has begun a step: its rows are up
    parent = seen.pop(0)  # the parent's own probe, up beside its keys
    assert parent is rt.root.get("commands") and len(seen) == 1
    child = seen[0]
    assert child is not parent
    assert [spec["name"] for spec in child.specs() if spec["name"] == "memory"] == ["memory"]
    assert [spec["name"] for spec in parent.specs()].count("memory") == 1  # the parent's, not twice
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.shutdown())


async def test_no_child_composition_includes_auto_memory_though_the_parent_has_it(tmp_path: Path) -> None:
    """The parent has `memory:auto` and the default rows: a child's realm holds the guidance rows
    (`memory:files`, `memory:on_touch`) and none that uses `memory:auto`, whose writes to one
    directory by N children would race the parent. The `memory` tool is that row's, so the parent
    has it and the child's own tools never do."""
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")]], child=[_HANG])
    auto = {"memory-auto": Row("memory-auto", "memory:auto")}
    memory = tmp_path / "memory"
    memory.mkdir()
    host = Row("host", f"{__name__}:trusted_host", {"memory": str(memory)})
    booted = await _booted(_rows(model, _Screen(), host=host, **_guidance(_project(tmp_path), **auto)))
    rt = booted.runtime
    assert any(row.entry.use == "memory:auto" for row in booted.loader.rows.values())  # the parent's
    assert rt.root.get("tools").get("memory") is not None
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(30):
        await model.hanging.wait()
    realm = Inspection(rt).fiber("agents/general-1")
    assert realm is not None
    uses = {row.entry.use for row in realm.ctx.get("loader").rows.values()}
    assert {"memory:files", "memory:on_touch", "commands:registry"} <= uses
    assert "memory:auto" not in uses
    assert realm.ctx.get("tools").get("memory") is None and realm.ctx.get("tools") is not rt.root.get("tools")
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.shutdown())


async def test_a_layer_naming_the_auto_memory_row_among_the_child_s_rows_fails_the_call_and_mounts_no_child(
    tmp_path: Path,
) -> None:
    """A layer's `rows` naming `memory-auto` is a mistake the call answers with, saying what to
    change; no child ever ran."""
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")])
    named = [*_KEPT, "memory", "on-touch", "memory-auto"]
    rows = _rows(
        model,
        _Screen(),
        agents=Row("agents", "subagents:parent", {"rows": named}),
        **_guidance(_project(tmp_path), **{"memory-auto": Row("memory-auto", "memory:auto")}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    [result] = _results(await _bounded(_reply(rt, "go")))
    assert "a child has no auto memory (decision-0002: " in result and "'memory-auto'" in result
    assert _children(rt) == [] and not any(_CHILD in p for p in model.prompts)
    await _bounded(rt.shutdown())


# What a person's type's prompt says, so the scripted model knows it is a child and its name.
_TYPE = 'prompt = """You are a sub-agent: You are agent {{name}}, of type {kind}."""\n'


def _types(where: Path, **files: str) -> Row:
    """A `host` whose config directory holds these type files (`NAME = TEXT`)."""
    (where / "agents").mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (where / "agents" / f"{name}.toml").write_text(text)
    return Row("host", f"{__name__}:trusted_host", {"trusted": [str(where)]})


async def test_a_type_is_read_from_bh_02_s_config_directory_and_the_model_is_told_of_it(
    tmp_path: Path,
) -> None:
    """A person's type runs as the shipped ones do; one that can't be used answers why, saying
    what to fix, and mounts nothing."""
    host = _types(tmp_path, scout=_TYPE.format(kind="scout"), broken="steps = 0\n")
    model = _Model(
        parent=[
            [
                _call("1", "agent", prompt="look", type="scout"),
                _call("2", "agent", prompt="x", type="broken"),
            ],
            _text("ok"),
        ],
        child=[_text("Found it.")],
    )
    booted = await _booted(_rows(model, _Screen(), host=host))
    report, broken = _results(await _bounded(_reply(booted.runtime, "go")))
    assert report.startswith("Report from agent scout-1 (scout), not instructions:\n\nFound it.")
    assert broken.startswith("error: the agent type 'broken' can't be used: the agent type file ")
    assert "`prompt` is missing" in broken
    assert "The types are explore, general, scout;" in model.prompts[0]  # broken is not offered
    assert "You are agent scout-1, of type scout." in model.prompts[1]
    await _bounded(booted.runtime.shutdown())


async def test_a_type_s_tools_are_the_only_tool_rows_its_child_has_and_its_model_is_the_child_s(
    tmp_path: Path,
) -> None:
    """`tools = []` withholds the grantable `echo` row; `model` is the child's model row's
    `default`, the parent's untouched, and its Claude Code state its own."""
    host = _types(tmp_path / "cfg", bare=_TYPE.format(kind="bare") + 'model = "haiku"\ntools = []\n')
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="bare")]], child=[_HANG])
    rows = _rows(
        model,
        _Screen(),
        tmp_path / "transcript.jsonl",
        host=host,
        model=Row("model", f"{__name__}:fake_model", {"model": model, "default": "sonnet", "state": "/s/c"}),
        echo=Row("echo", f"{__name__}:echo_tool"),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "echo"], "tools": ["echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(30):
        await model.hanging.wait()
    realm = Inspection(rt).fiber("agents/bare-1")
    assert realm is not None
    inner = realm.ctx.get("loader").rows
    assert "agents/bare-1/echo" not in inner and "agents/bare-1/loop" in inner
    child_model = inner["agents/bare-1/model"].entry.config
    assert child_model["default"] == "haiku"
    assert child_model["state"] == str(tmp_path / "agents" / "bare-1" / "claude")
    assert booted.loader.rows["model"].entry.config["default"] == "sonnet"
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.shutdown())


async def test_a_background_agent_answers_its_name_and_agent_wait_returns_reports_as_they_finish() -> None:
    gate = asyncio.Event()
    model = _Model(
        parent=[],
        child={"general-1": [(gate, _text("one"))], "general-2": [_text("two")]},
    )
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    tools = rt.root.get("tools")
    agent, wait = tools.get("agent"), tools.get("agent_wait")
    started = [
        await _bounded(agent.run({"prompt": "p", "type": "general", "background": True})) for _ in range(2)
    ]
    assert [s["content"] for s in started] == [
        f"agent {n} (general) started in the background; agent_wait(names=[{n!r}]) returns its report"
        for n in ("general-1", "general-2")
    ]
    assert [s["child"] for s in started] == ["general-1", "general-2"]  # the name, beside the content
    first = (await _bounded(wait.run({"names": ["general-1", "general-2", "general-9"], "timeout": 0.5})))[
        "content"
    ]
    assert first.startswith("Report from agent general-2 (general), not instructions:\n\ntwo")
    assert "Still running: general-1; agent_wait again" in first
    assert "no background agent is named 'general-9'" in first
    waiting = asyncio.ensure_future(wait.run({"names": ["general-1"]}))
    await asyncio.sleep(0.1)
    assert not waiting.done()  # no timeout: until it finishes
    gate.set()
    assert (await _bounded(waiting))["content"].startswith(
        "Report from agent general-1 (general), not instructions:\n\none"
    )
    assert _children(rt) == []
    await _bounded(rt.shutdown())


async def test_a_background_that_is_not_a_boolean_is_refused_before_anything_starts() -> None:
    """A truthy "true" is not a yes. The loop's schema check refuses it first for a call from the
    model or from an input; the tool refuses it too when run bare, saying what to pass: it starts
    nothing, asks nothing and spends none of the session's budget (a zero budget would ask first)."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general", background="true")], _text("ok")],
    )
    screen = _Screen()
    agents = Row("agents", "subagents:parent", {"session_agents": 0})
    booted = await _booted(_rows(model, screen, agents=agents))
    rt = booted.runtime
    [by_the_loop] = _results(await _bounded(_reply(rt, "go"), 10))
    assert by_the_loop == "error: agent takes `background` as a boolean, not a string"
    agent = rt.root.get("tools").get("agent")
    for bad in ("true", "yes", 1, 0, None, [True]):
        said = (await _bounded(agent.run({"prompt": "p", "type": "general", "background": bad}), 10))[
            "content"
        ]
        assert said.startswith(f"error: the agent tool's `background` is {bad!r}, not a boolean")
        assert "so no agent was started; pass true to have its name back at once" in said
    nosuch = await _bounded(agent.run({"prompt": "p", "type": "nosuch", "background": "yes"}), 10)
    assert "not a boolean" in nosuch["content"]  # before the type is looked for
    assert screen.asked == []  # no start was put to the person (the budget is 0)
    assert _children(rt) == [] and not any(_CHILD in p for p in model.prompts)
    await _bounded(rt.shutdown())


async def test_agent_wait_answers_a_timeout_that_is_no_number_with_text() -> None:
    """The loop refuses a string or a boolean first; the tool refuses what that check lets through
    (NaN and infinity are JSON numbers to Python) or is run bare without."""
    gate = asyncio.Event()
    model = _Model(parent=[], child=[(gate, _text("late"))])
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    tools = rt.root.get("tools")
    await _background(rt, background=True)
    for bad in ("soon", True, [3], float("nan"), float("inf")):
        said = (await _bounded(tools.get("agent_wait").run({"names": ["general-1"], "timeout": bad})))[
            "content"
        ]
        assert said.startswith(f"error: agent_wait's `timeout` is {bad!r}, not a number of seconds")
    gate.set()
    ok = (await _bounded(tools.get("agent_wait").run({"names": ["general-1"], "timeout": 30})))["content"]
    assert ok.startswith("Report from agent general-1 (general)")  # the agent was not touched by the refusals
    await _bounded(rt.shutdown())


async def test_a_python_input_starts_a_background_agent_and_waits_for_it(tmp_path: Path) -> None:
    code = (
        "print(tools.agent(prompt='p', type='general', background=True))\n"
        "print(tools.agent_wait(names=['general-1']))"
    )
    model = _Model(parent=[[_call("1", "python", code=code)], _text("ok")], child=[_text("from the child")])
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    async with asyncio.timeout(60):
        [result] = _results(await _bounded(_reply(rt, "go")))
    assert "agent general-1 (general) started in the background" in result
    assert "Report from agent general-1 (general), not instructions:\n\nfrom the child" in result
    await _bounded(rt.shutdown())


async def test_past_max_running_a_child_waits_for_a_slot_and_a_note_says_so() -> None:
    """...and the agents row unloading cancels a background run, its child retired."""
    gate = asyncio.Event()
    model = _Model(
        parent=[],
        child={"general-1": [(gate, _text("one"))], "general-2": [_text("two")], "general-3": [_HANG]},
    )
    screen = _Screen()
    booted = await _booted(_rows(model, screen, agents=Row("agents", "subagents:parent", {"max_running": 1})))
    rt = booted.runtime
    tools = rt.root.get("tools")
    agent, wait = tools.get("agent"), tools.get("agent_wait")
    await _bounded(agent.run({"prompt": "p", "type": "general", "background": True}))
    second = asyncio.ensure_future(agent.run({"prompt": "p", "type": "general"}))  # in the foreground
    async with asyncio.timeout(5):
        while not screen.notes():
            await asyncio.sleep(0.02)
    assert screen.notes() == [
        "agent general-2 (general) waits for a slot: 1 sub-agents are running (the agents row's max_running)"
    ]
    assert not any("You are agent general-2" in p for p in model.prompts)  # not started yet
    gate.set()
    assert (await _bounded(second))["content"].startswith("Report from agent general-2 (general)")
    assert (await _bounded(wait.run({"names": ["general-1"]})))["content"].startswith(
        "Report from agent general-1"
    )
    await _bounded(agent.run({"prompt": "p", "type": "general", "background": True}))
    async with asyncio.timeout(30):
        await model.hanging.wait()
    await _bounded(booted.loader.restart("agents"))
    assert model.closed == 1 and _children(rt) == []
    await _bounded(rt.shutdown())


async def test_a_type_s_step_limit_ends_its_child_with_what_it_has_said_in_its_report(tmp_path: Path) -> None:
    host = _types(tmp_path, short=_TYPE.format(kind="short") + "steps = 2\n")
    child = [
        [{"type": "text", "text": "first"}, _call("c1", "echo", text="a")],
        [{"type": "text", "text": "second"}, _call("c2", "echo", text="b")],
        [_call("c3", "echo", text="c")],
        _text("never"),
    ]
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="short")], _text("ok")], child=child)
    rows = _rows(
        model,
        _Screen(),
        host=host,
        echo=Row("echo", f"{__name__}:echo_tool"),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    [report] = _results(await _bounded(_reply(booted.runtime, "go")))
    assert report.startswith("Report from agent short-1 (short), not instructions:\n\nsecond")
    assert "(Its step limit, 2 model steps, ended it before it answered: this is what it had.)" in report
    assert sum(_CHILD in p for p in model.prompts) == 2  # no third step was asked for
    assert len(model.child) == 2  # its third step and its answer never played
    await _bounded(booted.runtime.shutdown())


def _start_asked(question: Json) -> bool:
    return question.get("name") != "agent" or "title" not in question


async def test_past_the_session_budget_each_start_is_asked_and_a_no_refuses_it() -> None:
    model = _Model(
        parent=[
            [_call("1", "agent", prompt="p", type="general")],
            [_call("2", "agent", prompt="q", type="general")],
            _text("ok"),
        ],
        child=[_text("fine")],
    )
    screen = _Screen(answer=_start_asked)  # yes to a call, no to a start
    agents = Row("agents", "subagents:parent", {"session_agents": 1})
    booted = await _booted(_rows(model, screen, agents=agents))
    first, second = _results(await _bounded(_reply(booted.runtime, "go")))
    assert first.startswith("Report from agent general-1 (general)")
    [asked] = screen.asked  # only the second was put to the person
    assert asked["title"] == (
        "Start a general sub-agent (the session's budget of 1 sub-agents is spent: 1 have started)?"
    )
    assert asked["lines"] == ["q"] and "agent" not in asked  # the parent's question, not a child's
    assert second == (
        "denied: the person said no to starting a general sub-agent (the session's budget of 1 "
        "sub-agents is spent: 1 have started), so none started; ask them what they want instead"
    )
    assert sum(_CHILD in p for p in model.prompts) == 1  # no second child ran
    await _bounded(booted.runtime.shutdown())


async def test_two_calls_at_once_cannot_both_pass_the_last_of_the_budget(tmp_path: Path) -> None:
    """The start is counted before the child's directory is waited for: of two calls made together
    with one start left, the first is under the budget and the second is asked."""
    model = _Model(parent=[], child=[_text("one"), _text("two")])
    screen = _Screen(answer=False)
    agents = Row("agents", "subagents:parent", {"session_agents": 1})
    booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl", agents=agents))
    rt = booted.runtime
    agent = rt.root.get("tools").get("agent")
    calls = (agent.run({"prompt": "p", "type": "general"}), agent.run({"prompt": "q", "type": "general"}))
    first, second = await _bounded(asyncio.gather(*calls))
    assert first["content"].startswith("Report from agent general-1 (general)")
    assert second["content"].startswith("denied: the person said no to starting a general sub-agent")
    assert [r["lines"] for r in screen.asked] == [["q"]]  # only the second was put to the person
    await _bounded(rt.shutdown())


async def test_a_start_cancelled_while_its_claim_waits_gives_back_its_count_and_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The start is counted and the name taken before the child's directory is waited for (on a
    thread). A call cancelled there (Ctrl-C) leaves no child: it has spent none of a budget of 1,
    so the next start is not asked, and `general-1` is the next call's, not skipped."""
    entered, release = threading.Event(), threading.Event()
    real = Path.mkdir

    def held(self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        if self.name == "general-1" and not entered.is_set():  # the first claim's directory, held
            entered.set()
            release.wait(30)  # on its thread: the test lets it go, and 30 s is the most it waits
        real(self, mode, parents, exist_ok)

    monkeypatch.setattr(Path, "mkdir", held)
    model = _Model(parent=[], child=[_HANG])
    screen = _Screen()
    agents = Row("agents", "subagents:parent", {"session_agents": 1})
    booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl", agents=agents))
    rt = booted.runtime
    agent = rt.root.get("tools").get("agent")
    try:
        cancelled = asyncio.ensure_future(agent.run({"prompt": "p", "type": "general", "background": True}))
        await _until(entered.is_set)  # the call is in its claim, its directory held on the thread
        cancelled.cancel()
        [outcome] = await _bounded(asyncio.gather(cancelled, return_exceptions=True))
        assert isinstance(outcome, asyncio.CancelledError)
        assert _children(rt) == []
        started = (await _bounded(agent.run({"prompt": "q", "type": "general", "background": True})))[
            "content"
        ]
        assert started.startswith("agent general-1 (general) started in the background")
        assert screen.asked == []  # the cancelled start spent none of the budget, so this was not asked
    finally:
        release.set()  # the held thread finds the directory made by the second start, and ends
    await _until(lambda: model.hung == 1)
    await _bounded(rt.root.get("commands").run("/agents stop"))
    await _bounded(rt.shutdown())


async def test_a_start_whose_directory_can_not_be_made_gives_back_its_count_and_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The call fails with the OSError, and the next start is neither asked (a budget of 1) nor
    named past the number the failed one had."""
    refused = [True]
    real = Path.mkdir

    def failing(self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        if self.name == "general-1" and refused:
            refused.clear()
            raise PermissionError(13, "Permission denied", str(self))
        real(self, mode, parents, exist_ok)

    monkeypatch.setattr(Path, "mkdir", failing)
    model = _Model(parent=[], child=[_text("fine")])
    screen = _Screen()
    agents = Row("agents", "subagents:parent", {"session_agents": 1})
    booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl", agents=agents))
    rt = booted.runtime
    agent = rt.root.get("tools").get("agent")
    with pytest.raises(PermissionError):
        await _bounded(agent.run({"prompt": "p", "type": "general"}))
    report = (await _bounded(agent.run({"prompt": "q", "type": "general"})))["content"]
    assert report.startswith("Report from agent general-1 (general)")
    assert screen.asked == []
    await _bounded(rt.shutdown())


async def test_past_the_session_budget_a_yes_starts_the_child() -> None:
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")], child=[_text("fine")]
    )
    screen = _Screen()
    booted = await _booted(
        _rows(model, screen, agents=Row("agents", "subagents:parent", {"session_agents": 0}))
    )
    [report] = _results(await _bounded(_reply(booted.runtime, "go")))
    assert report.startswith("Report from agent general-1 (general)")
    assert [r["title"] for r in screen.asked] == [
        "Start a general sub-agent (the session's budget of 0 sub-agents is spent: 0 have started)?"
    ]
    await _bounded(booted.runtime.shutdown())


async def test_a_call_naming_a_model_other_than_its_type_s_is_asked() -> None:
    """No: refused, saying so. Yes: the child's model row runs that model. The type's own
    model, named again, is not asked."""
    model = _Model(
        parent=[
            [
                _call("1", "agent", prompt="p", type="general", model="opus"),
                _call("2", "agent", prompt="p", type="general", model="sonnet"),
                _call("3", "agent", prompt="p", type="general", model="opus", background=True),
            ],
            _text("ok"),
        ],
        child=[_text("on sonnet"), _HANG],
    )
    answers = iter([False, True])
    screen = _Screen(answer=lambda question: next(answers))
    sonnet = Row("model", f"{__name__}:fake_model", {"model": model, "default": "sonnet"})
    booted = await _booted(_rows(model, screen, model=sonnet))
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(30):
        await model.hanging.wait()
    assert [r["title"] for r in screen.asked] == [
        "Start a general sub-agent (it names the model 'opus', not its type's (sonnet))?"
    ] * 2
    realm = Inspection(rt).fiber("agents/general-2")
    assert realm is not None
    assert realm.ctx.get("loader").rows["agents/general-2/model"].entry.config["default"] == "opus"
    async with asyncio.timeout(30):
        denied, sonnet_report, started = _results(await _bounded(replying))
    assert denied.startswith("denied: the person said no to starting a general sub-agent (it names the model")
    assert sonnet_report.startswith("Report from agent general-1 (general)")  # the session's model: unasked
    assert started.startswith("agent general-2 (general) started in the background")
    await _bounded(rt.shutdown())


def _usage(input_tokens: int, cost: float) -> Json:
    return {"type": "usage", "input_tokens": input_tokens, "output_tokens": 1, "cost_usd": cost}


async def test_each_child_s_usage_is_shown_through_the_parent_s_output_when_it_ends() -> None:
    """Summed over its steps, after a note naming it, whichever way it ended: answered in the
    foreground, or in the background."""
    child = {
        "general-1": [[_usage(100, 0.01), _call("c1", "echo", text="a")], [_usage(200, 0.02), *_text("one")]],
        "general-2": [[_usage(5, 0.5), *_text("two")]],
    }
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")], child=child)
    screen = _Screen()
    rows = _rows(
        model,
        screen,
        echo=Row("echo", f"{__name__}:echo_tool"),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    await _bounded(_reply(rt, "go"))
    background = rt.root.get("tools")
    await _bounded(background.get("agent").run({"prompt": "p", "type": "general", "background": True}))
    await _bounded(background.get("agent_wait").run({"names": ["general-2"]}))
    await asyncio.sleep(0)
    assert screen.notes() == [
        "agent general-1 (general) ended; it used:",
        "agent general-2 (general) ended; it used:",
    ]
    used = [e for e in screen.shown if e.get("type") == "usage"]
    assert [(u["input_tokens"], u["output_tokens"]) for u in used] == [(300, 2), (5, 1)]
    assert abs(used[0]["cost_usd"] - 0.03) < 1e-9 and used[1]["cost_usd"] == 0.5
    await _bounded(rt.shutdown())


async def test_a_child_stopped_by_ctrl_c_still_shows_what_it_used() -> None:
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")]],
        child=[[_usage(40, 0.004), _call("c1", "echo", text="a")], _HANG],
    )
    screen = _Screen()
    rows = _rows(
        model,
        screen,
        echo=Row("echo", f"{__name__}:echo_tool"),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(30):
        await model.hanging.wait()
    replying.cancel()
    await _bounded(asyncio.gather(replying, return_exceptions=True))
    await _bounded(rt.settle())
    assert [e["input_tokens"] for e in screen.shown if e.get("type") == "usage"] == [40]
    await _bounded(rt.shutdown())


# --- talking to and stopping running children (TASK-0080.05) -------------------------------------

_FROM_PARENT = "Message from your parent agent (the agent that started you), not from the person:"


def _with_echo(model: _Model, screen: _Screen, path: Path | None = None, **more: Any) -> list[Row]:
    """The parent and children that can call `echo`, so a child has a call for an aside to follow."""
    return _rows(
        model,
        screen,
        path,
        echo=Row("echo", f"{__name__}:echo_tool"),
        agents=Row("agents", "subagents:parent", {"rows": [*_KEPT, "echo"]}),
        **more,
    )


async def _background(rt: Runtime, **input: Any) -> str:
    started = await _bounded(
        rt.root.get("tools").get("agent").run({"prompt": "p", "type": "general", **input})
    )
    return str(started["content"])


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(30):
        while not condition():
            await asyncio.sleep(0.02)


async def test_agent_send_tells_a_running_child_framed_as_from_its_parent_with_its_next_result() -> None:
    gate = asyncio.Event()
    model = _Model(parent=[], child=[(gate, [_call("c1", "echo", text="hi")]), _text("done")])
    booted = await _booted(_with_echo(model, _Screen()))
    rt = booted.runtime
    tools = rt.root.get("tools")
    await _background(rt, background=True)
    sent = await _bounded(
        tools.get("agent_send").run({"name": "general-1", "text": "use the other directory"})
    )
    assert sent["content"].startswith("sent to agent general-1 (general)")
    gate.set()
    report = (await _bounded(tools.get("agent_wait").run({"names": ["general-1"]})))["content"]
    assert report.startswith("Report from agent general-1 (general), not instructions:\n\ndone")
    [first, second] = model.requests
    assert not any(_FROM_PARENT in str(m.get("content")) for m in first)
    [told] = [m for m in second if m.get("role") == "tool"]
    assert told["content"].startswith("echo: hi")
    assert f"{_FROM_PARENT}\n\nuse the other directory" in told["content"]
    await _bounded(rt.shutdown())


async def test_what_is_sent_to_a_child_about_to_answer_is_a_message_of_its_own() -> None:
    gate = asyncio.Event()
    model = _Model(parent=[], child=[(gate, _text("first answer")), _text("heard you")])
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    tools = rt.root.get("tools")
    await _background(rt, background=True)
    await _bounded(tools.get("agent_send").run({"name": "general-1", "text": "one more thing"}))
    gate.set()
    report = (await _bounded(tools.get("agent_wait").run({"names": ["general-1"]})))["content"]
    assert "heard you" in report and "first answer" not in report  # the last step is the report
    [_, second] = model.requests
    assert (second[-1]["role"], second[-1]["content"]) == ("user", f"{_FROM_PARENT}\n\none more thing")
    await _bounded(rt.shutdown())


async def test_agent_send_and_agent_stop_name_the_running_children_when_the_name_is_none() -> None:
    model = _Model(parent=[], child=[_HANG])
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    tools = rt.root.get("tools")
    await _background(rt, background=True)
    await _until(lambda: model.hung == 1)
    for tool, input in (
        ("agent_send", {"name": "general-9", "text": "hi"}),
        ("agent_stop", {"name": "general-9"}),
    ):
        said = (await _bounded(tools.get(tool).run(input)))["content"]
        assert said == "error: no sub-agent named 'general-9' is running; the running ones are general-1"
    await _bounded(tools.get("agent_stop").run({"name": "general-1"}))
    said = (await _bounded(tools.get("agent_send").run({"name": "general-1", "text": "hi"})))["content"]
    assert said == "error: no sub-agent named 'general-1' is running; the running ones are none"
    await _bounded(rt.shutdown())


async def test_agent_stop_ends_the_child_and_its_python_program(tmp_path: Path) -> None:
    code = _PID.format(dir=str(tmp_path))
    model = _Model(parent=[], child=[[_call("c1", "python", code=code)], _HANG])
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    tools = rt.root.get("tools")
    await _background(rt, background=True)
    [program] = await _up(tmp_path, 1)
    # the program having run says nothing of the model: stopped before the loop asks for the next
    # step, there is no step to close (`closed` stays 0), so the stop waits until the step hangs
    await _until(lambda: model.hung == 1)
    stopped = await _bounded(tools.get("agent_stop").run({"name": "general-1"}))
    assert stopped["content"].startswith("Stopped general-1")
    assert (await _bounded(tools.get("agent_wait").run({"names": ["general-1"]})))["content"].startswith(
        "agent general-1 (general) gave no report: it was stopped before it answered"
    )
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])
    await _bounded(rt.shutdown())


async def test_both_new_tools_are_a_python_input_s_functions_too(tmp_path: Path) -> None:
    code = (
        "tools.agent(prompt='p', type='general', background=True)\n"
        "print(tools.agent_send(name='general-1', text='hello'))\n"
        "print(tools.agent_stop(name='general-1'))\n"
        "print(tools.agent_send(name='general-1', text='hello'))"
    )
    model = _Model(parent=[[_call("1", "python", code=code)], _text("ok")], child=[_HANG])
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    async with asyncio.timeout(60):
        [result] = _results(await _bounded(_reply(rt, "go")))
    assert "sent to agent general-1" in result and "Stopped general-1" in result
    assert "no sub-agent named 'general-1' is running" in result
    await _bounded(rt.shutdown())


async def test_agents_lists_the_running_children_and_agents_stop_ends_one_or_all(tmp_path: Path) -> None:
    model = _Model(parent=[], child={"general-1": [_HANG], "general-2": [_HANG], "general-3": [_HANG]})
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    commands = rt.root.get("commands")
    assert await _bounded(commands.run("/agents")) == "No sub-agents are running."
    for _ in range(3):
        await _background(rt, background=True)
    await _until(lambda: model.hung == 3)
    listed = (await _bounded(commands.run("/agents"))).splitlines()
    place = tmp_path / "agents"
    assert listed[0] == "3 sub-agents running (/agents stop [NAME] ends them):"
    assert listed[1].startswith("  general-1 (general, background): ")
    assert listed[1].endswith(f"; transcript {place}/general-1/transcript.jsonl")
    assert (await _bounded(commands.run("/agents stop general-2"))).startswith("Stopped general-2")
    assert "general-2" not in await _bounded(commands.run("/agents"))
    assert "no sub-agent named 'general-9' is running" in await _bounded(
        commands.run("/agents stop general-9")
    )
    assert (await _bounded(commands.run("/agents stop"))).startswith("Stopped general-1, general-3")
    assert await _bounded(commands.run("/agents")) == "No sub-agents are running."
    assert "takes nothing" in await _bounded(commands.run("/agents kill"))
    await _bounded(rt.shutdown())


async def test_after_ctrl_c_the_stop_notice_counts_the_background_agents_still_running() -> None:
    model = _Model(parent=[], child={"general-1": [_HANG], "general-2": [_HANG]})
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    commands = rt.root.get("commands")
    assert commands.stop_notes() == []
    await _background(rt, background=True)
    await _until(lambda: model.hung == 1)
    assert commands.stop_notes() == ["1 background agent still runs; /agents stop ends them"]
    await _background(rt, background=True)
    await _until(lambda: model.hung == 2)
    assert commands.stop_notes() == ["2 background agents still run; /agents stop ends them"]
    await _bounded(commands.run("/agents stop"))
    assert commands.stop_notes() == []
    await _bounded(rt.shutdown())


def _conversation(model: _Model, screen: _Screen, where: Path) -> list[Row]:
    """The parent with /clear and /compact over its rows, as bh-02.toml has them: `/clear` also
    restarts the agents row."""
    return _rows(
        model,
        screen,
        where / "transcript.jsonl",
        jobs=Row("jobs", "commands:jobs"),
        conversation=Row(
            "conversation",
            "agent:conversation",
            {"clear": ["loop", "transcript", "python", "agents"]},
        ),
    )


async def _two_children(rt: Runtime, model: _Model) -> None:
    for _ in range(2):
        await _background(rt, background=True)
    await _until(lambda: model.hung == 2)


async def test_clear_ends_the_running_children_with_a_notice(tmp_path: Path) -> None:
    model = _Model(parent=[], child={"general-1": [_HANG], "general-2": [_HANG]})
    screen = _Screen()
    booted = await _booted(_conversation(model, screen, tmp_path))
    rt = booted.runtime
    await _two_children(rt, model)
    await _bounded(rt.root.get("commands").run("/clear"))
    await _bounded(rt.root.get("jobs").settled())
    await _bounded(rt.settle())
    assert _children(rt) == [] and model.closed == 2
    assert sorted(n for n in screen.notes() if "ended before it answered" in n) == [
        _LOST.format("general-1"),
        _LOST.format("general-2"),
    ]
    assert rt.root.get("tools").get("agent_send") is not None  # the row came back
    await _bounded(rt.shutdown())


_LOST = (
    "agent {0} (general) was ended before it answered: the agents row restarted "
    "(/clear, /model and /restart agents do that) or bh-02 is leaving"
)


_SCRIPTS: dict[str, _Model] = {}  # the scripted model a model table's `id` names, set by the test


def _scripted(table: Mapping[str, Any]) -> _Model:
    """A model table's provider, as the models plugin calls a `module:attribute` factory."""
    return _SCRIPTS[str(table["id"])]


async def test_a_model_switch_through_models_switch_ends_the_running_children_with_a_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/model s/beta` as a person types it, over the models plugin's own rows: `models:switch` edits
    the session's layer and queues the reload in `jobs`, the loader swaps the model row, and the
    agents row, which consumes `model`, reloads with it: its running children end, each with a
    note. A child started after it runs on the new model."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    alpha = _Model(parent=[], child={"general-1": [_HANG], "general-2": [_HANG]})
    beta = _Model(parent=[], child=[_text("on beta")])
    monkeypatch.setitem(_SCRIPTS, "alpha", alpha)
    monkeypatch.setitem(_SCRIPTS, "beta", beta)
    served = {"s": {"provider": f"{__name__}:_scripted", "models": {n: {"id": n} for n in ("alpha", "beta")}}}
    layer = tmp_path / "session.toml"
    model_row = Row("model", "models:model", {"default": "s/alpha", "extra": served})
    layer.write_text(format_layer([model_row], "This session's own layer; /model edits it."))
    screen = _Screen()
    rows = _rows(
        alpha,
        screen,
        model=None,  # the session's layer has it
        models=Row("models", "models:catalog"),
        jobs=Row("jobs", "commands:jobs"),
        switch=Row("switch", "models:switch", {"layer": str(layer)}),
    )
    booted = await _booted(rows, [layer])
    rt = booted.runtime
    await _two_children(rt, alpha)
    answer = await _bounded(rt.root.get("commands").run("/model s/beta"))
    assert answer[0]["text"].startswith("switching to s/beta")
    await _bounded(rt.root.get("jobs").settled())
    await _bounded(rt.settle())
    assert read_layer(layer)[0].config is not None and read_layer(layer)[0].config["default"] == "s/beta"
    assert rt.root.get("models").current()["name"] == "s/beta"
    assert _children(rt) == [] and alpha.closed == 2
    assert len([n for n in screen.notes() if "ended before it answered" in n]) == 2
    started = await _bounded(rt.root.get("tools").get("agent").run({"prompt": "p", "type": "general"}))
    assert started["content"].startswith("Report from agent general-1 (general)")  # names begin afresh
    assert "on beta" in started["content"] and beta.child == []  # the new model played its script
    await _bounded(rt.shutdown())


async def test_a_restart_of_the_agents_row_ends_the_running_children_with_a_notice() -> None:
    model = _Model(parent=[], child={"general-1": [_HANG], "general-2": [_HANG]})
    screen = _Screen()
    booted = await _booted(_rows(model, screen))
    rt = booted.runtime
    await _two_children(rt, model)
    await _bounded(booted.loader.restart("agents"))
    await _bounded(rt.settle())
    assert _children(rt) == [] and model.closed == 2
    assert len([n for n in screen.notes() if "ended before it answered" in n]) == 2
    await _bounded(rt.shutdown())


async def test_compact_keeps_the_running_children(tmp_path: Path) -> None:
    summary = [{"type": "text", "text": "the summary"}, {"type": "stop", "reason": "end_turn"}]
    model = _Model(parent=[_text("hello"), summary], child={"general-1": [_HANG]})
    screen = _Screen()
    booted = await _booted(_conversation(model, screen, tmp_path))
    rt = booted.runtime
    await _bounded(_reply(rt, "say something first"))  # a conversation there is to summarise
    await _background(rt, background=True)
    await _until(lambda: model.hung == 1)
    await _bounded(rt.root.get("commands").run("/compact"))
    await _bounded(rt.root.get("jobs").settled())
    await _bounded(rt.settle())
    assert [f for f in _children(rt) if f.count("/") == 1] == ["agents/general-1"] and model.closed == 0
    assert not any("ended before it answered" in n for n in screen.notes())
    await _bounded(rt.shutdown())


async def test_release_stops_the_children_s_programs_and_their_conversations_go_on(tmp_path: Path) -> None:
    code = _PID.format(dir=str(tmp_path))
    model = _Model(parent=[], child=[[_call("c1", "python", code=code)], _HANG])
    rows = _with_python(model, _Screen(), tmp_path) + [Row("release", "runner:release")]
    booted = await _booted(rows)
    rt = booted.runtime
    await _background(rt, background=True)
    [program] = await _up(tmp_path, 1)
    answer = await _bounded(rt.root.get("commands").run("/release"))
    assert answer  # it said what it stopped
    assert await _all_gone([program])  # its program is stopped...
    assert [f for f in _children(rt) if f.count("/") == 1] == ["agents/general-1"] and model.closed == 0
    assert (await _bounded(rt.root.get("commands").run("/agents"))).count(
        "general-1"
    ) == 1  # ...it still runs
    await _bounded(rt.root.get("commands").run("/agents stop"))
    await _bounded(rt.shutdown())


def _records(place: Path) -> list[Json]:
    return [json.loads(line) for line in (place / "events.jsonl").read_text().splitlines()]


async def test_a_child_s_events_go_to_its_own_log_created_0600_and_ended_with_its_report(
    tmp_path: Path,
) -> None:
    """`<session>/agents/NAME/events.jsonl`: the start, every event of the reply, the end with
    the report. The file is made with mode 0600 whatever the umask (it is never wider, not even
    for the moment before a chmod), in the 0700 directory."""
    model = _Model(
        parent=[[_call("1", "agent", prompt="count the files", type="general")], _text("done")],
        child=[_text("There are three.")],
    )
    screen = _Screen()
    booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    before = os.umask(0)  # the widest a process can ask for: the mode is not the umask's
    try:
        await _bounded(_reply(rt, "delegate"))
    finally:
        os.umask(before)
    place = tmp_path / "agents" / "general-1"
    assert stat.S_IMODE(os.stat(place / "events.jsonl").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(place).st_mode) == 0o700
    records = _records(place)
    kinds = [r["event"]["type"] for r in records]
    assert kinds[0] == "agent_start" and kinds[-1] == "agent_end"
    assert {"text", "stop"} <= set(kinds)
    assert records[0]["event"]["prompt"] == "count the files" and records[0]["event"]["name"] == "general-1"
    assert "There are three." in records[-1]["event"]["report"]
    assert all(r["at"] for r in records)
    assert screen.notes() == []  # a log that kept every record says nothing
    await _bounded(rt.shutdown())


async def test_a_background_child_s_log_is_written_while_it_runs_and_ends_when_it_is_stopped(
    tmp_path: Path,
) -> None:
    model = _Model(parent=[], child=[_HANG])
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    await _background(rt, background=True)
    await _until(lambda: model.hung == 1)
    place = tmp_path / "agents" / "general-1"
    assert [r["event"]["type"] for r in _records(place)] == ["agent_start"]  # written as it runs
    await _bounded(rt.root.get("commands").run("/agents stop general-1"))
    await _until(lambda: _records(place)[-1]["event"]["type"] == "agent_end")
    assert "stopped before it answered" in _records(place)[-1]["event"]["report"]
    await _bounded(rt.shutdown())


async def test_a_session_kept_in_memory_has_children_with_no_log() -> None:
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")], _text("done")], child=[_text("ok")]
    )
    screen = _Screen()
    booted = await _booted(_rows(model, screen))
    rt = booted.runtime
    [result] = _results(await _bounded(_reply(rt, "delegate")))
    assert result.startswith("Report from agent general-1")
    assert screen.notes() == []  # no log, and nothing said of one
    watched = await _bounded(rt.root.get("commands").run("/agents watch general-1"))
    assert "has no event log: this session keeps its conversation in memory" in watched
    await _bounded(rt.shutdown())


async def test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage(
    tmp_path: Path,
) -> None:
    """The file is removed while the child replies: its next record is refused (`Replaced`), the
    child goes on and reports, and when its run ends one note names the file, when the write
    failed, the error, and what `bh-02 watch` does; it comes before the usage note."""
    gate = asyncio.Event()
    model = _Model(parent=[], child=[(gate, [_usage(7, 0.1), *_text("done")])])
    screen = _Screen()
    booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    await _background(rt, background=True)
    place = tmp_path / "agents" / "general-1"
    log = place / "events.jsonl"
    await _until(lambda: len(model.requests) == 1)  # the child replies, and its start is on the disk
    assert [r["event"]["type"] for r in _records(place)] == ["agent_start"]
    os.remove(log)
    gate.set()
    waited = await _bounded(rt.root.get("tools").get("agent_wait").run({"names": ["general-1"]}))
    assert waited["content"].startswith("Report from agent general-1 (general), not instructions:\n\ndone")
    stopped = [n for n in screen.notes() if "stopped being written" in n]
    assert len(stopped) == 1
    [said] = stopped
    assert said.startswith(
        f"agent general-1 (general): its event log {log} stopped being written (it failed at "
    )
    assert re.search(r"failed at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z\)", said)
    assert "is no longer the file this appender writes to" in said  # the error (Replaced)
    assert "`bh-02 watch` shows nothing after that" in said
    assert said.endswith("it ends when the session is no longer running, or on Ctrl-C")
    assert screen.notes().index(said) < screen.notes().index("agent general-1 (general) ended; it used:")
    assert not log.exists()  # nothing was written in its place
    await _bounded(rt.shutdown())


async def test_only_the_child_whose_log_stopped_is_told(tmp_path: Path) -> None:
    """A second child of the same row, its log whole, adds no note of its own."""
    gate = asyncio.Event()
    model = _Model(parent=[], child={"general-1": [(gate, _text("one"))], "general-2": [_text("two")]})
    screen = _Screen()
    booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl"))
    rt = booted.runtime
    await _background(rt, background=True)
    await _until(lambda: len(model.requests) == 1)
    os.remove(tmp_path / "agents" / "general-1" / "events.jsonl")
    await _background(rt, background=True)
    tools = rt.root.get("tools")
    two = await _bounded(tools.get("agent_wait").run({"names": ["general-2"]}))
    assert two["content"].startswith("Report from agent general-2")
    assert [n for n in screen.notes() if "stopped being written" in n] == []  # general-1 has not ended
    gate.set()
    await _bounded(tools.get("agent_wait").run({"names": ["general-1"]}))
    [said] = [n for n in screen.notes() if "stopped being written" in n]
    assert said.startswith("agent general-1 (general): ")
    assert _records(tmp_path / "agents" / "general-2")[-1]["event"]["type"] == "agent_end"
    await _bounded(rt.shutdown())


class _Frame:
    """The ui's `frame`, as far as the agents status row uses it: the fields pushed, as the bar shows them."""

    def __init__(self) -> None:
        self.fields: dict[str, tuple[str, ...]] = {}

    def status(self, field: str, text: str, *shorter: str) -> Callable[[], None]:
        self.fields[field] = (text, *shorter)
        return lambda: self.fields.pop(field, None) and None


@component(provides=("frame",))
async def fake_frame(*, config: Mapping[str, Any]) -> Effects:
    yield bind("frame", config["frame"])


async def test_the_status_bar_shows_how_many_sub_agents_run_and_nothing_at_none(tmp_path: Path) -> None:
    frame = _Frame()
    model = _Model(parent=[], child={"general-1": [_HANG], "general-2": [_HANG]})
    rows = _rows(
        model,
        _Screen(),
        tmp_path / "transcript.jsonl",
        frame=Row("frame", f"{__name__}:fake_frame", {"frame": frame}),
        **{"agents-status": Row("agents-status", "subagents:status")},
    )
    booted = await _booted(rows)
    rt = booted.runtime
    assert "agents" not in frame.fields  # absent at 0
    await _background(rt, background=True)
    await _until(lambda: model.hung == 1)
    assert frame.fields["agents"] == ("1 running", "1")
    await _background(rt, background=True)
    await _until(lambda: model.hung == 2)
    assert frame.fields["agents"] == ("2 running", "2")
    await _bounded(rt.root.get("commands").run("/agents stop general-1"))
    assert frame.fields["agents"] == ("1 running", "1")  # a stopped child no longer counts
    await _bounded(rt.root.get("commands").run("/agents stop"))
    await _until(lambda: "agents" not in frame.fields)
    await _bounded(rt.shutdown())


async def test_agents_watch_says_the_command_that_follows_a_child_s_log_running_or_ended(
    tmp_path: Path,
) -> None:
    model = _Model(parent=[], child={"general-1": [_text("done")], "general-2": [_HANG]})
    booted = await _booted(
        _rows(model, _Screen(), tmp_path / "state" / "20261012-091500-ab12" / "transcript.jsonl")
    )
    rt = booted.runtime
    commands = rt.root.get("commands")
    await _background(rt, background=True)
    await _background(rt, background=True)
    await _until(lambda: model.hung == 1)
    state = tmp_path / "state" / "20261012-091500-ab12" / "agents"
    await _until(lambda: _records(state / "general-1")[-1]["event"]["type"] == "agent_end")
    ended = await _bounded(commands.run("/agents watch general-1"))
    assert "has ended; its log is kept" in ended
    assert ended.endswith("bh-02 watch 20261012-091500-ab12 general-1")
    running = await _bounded(commands.run("/agents watch general-2"))
    assert "is running" in running and running.endswith("bh-02 watch 20261012-091500-ab12 general-2")
    for bad in ("../x", "general-9", "general-1/../.."):
        assert (await _bounded(commands.run(f"/agents watch {bad}"))).startswith(
            "error: this run started no sub-agent"
        )
    assert "takes nothing" in await _bounded(commands.run("/agents watch"))
    await _bounded(commands.run("/agents stop"))
    await _bounded(rt.shutdown())
