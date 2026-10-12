"""The agents row in a composition: a child mounted in a sealed realm through its performer,
driven to its report and retired; retired early from outside, or with the row; its questions
labelled through `asker`; Ctrl-C (the parent's reply cancelled) stopping it from the tool and
from a python input. The parent and its children are the agent plugin's rows over one scripted
model, named by entry point (no plugin is imported)."""

import asyncio
import importlib.util
import json
import os
import stat
import sys
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cordis import Effects, Inspection, Row, Runtime, acquire, bind, component
from cordis.loader import Booted, boot

type Json = Mapping[str, Any]

_CHILD = "You are a sub-agent"  # what the general type's section says, so the model knows whose turn
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

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        system = str(messages[0].get("content", "")) if messages else ""
        self.prompts.append(system)
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

    async def confirm(self, request: Json) -> bool:
        self.asked.append(request)
        return self.answer(request) if callable(self.answer) else self.answer

    async def show(self, events: AsyncIterator[Json]) -> None:
        self.shown += [event async for event in events]

    def notes(self) -> list[str]:
        return [str(e["text"]) for e in self.shown if e.get("type") == "note"]


class _Rule:
    def __init__(self, unasked: bool) -> None:
        self._unasked = unasked

    def unasked(self, request: Json) -> bool:
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
    """The `host` value a confined runner reads: where the program's code is, which every jail reads."""

    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""


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
    """A `host` whose `trusted` is the config's: where the agents row reads type files."""
    yield bind("host", _Host(trusted=tuple(config.get("trusted", ()))))


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


@component(provides=("commands",))
async def fake_commands() -> Effects:
    yield bind("commands", "the parent's commands")


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
        "agents": Row("agents", "agents:agents"),
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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "python"]}),
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


async def _booted(rows: list[Row]) -> Booted:
    booted = await boot([], rows, watch=None)
    await booted.runtime.settle()
    assert all(state == "active" for state in booted.loader.status().values()), booted.loader.status()
    return booted


def _children(rt: Runtime) -> list[str]:
    return [f.name for f in Inspection(rt).fibers if f.name.startswith("agents/")]


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
    events = await _reply(rt, "delegate")
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
    await rt.shutdown()


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
    unknown, report = _results(await _reply(booted.runtime, "go"))
    assert unknown == "error: there is no agent type 'nosuch'; the types are explore, general"
    assert report.startswith("Report from agent general-2 (general)")
    await booted.runtime.shutdown()


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
    await realm.retire()
    [result] = _results(await replying)
    assert result == "agent general-1 (general) gave no report: it was stopped before it answered"
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])  # the child's REPL program with it
    await rt.shutdown()


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
    assert sorted(f for f in _children(rt) if f.count("/") == 1) == ["agents/general-1", "agents/general-2"]
    await booted.loader.restart("agents")
    answers = [str((await run)["content"]) for run in runs]
    assert all(a.endswith("gave no report: it was stopped before it answered") for a in answers)
    assert model.closed == 2 and _children(rt) == []
    assert await _all_gone(programs)
    await rt.settle()
    assert rt.root.get("tools").get("agent") is not None  # the row came back
    await rt.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    [report] = _results(await replying)
    assert "echoed" in report
    agent_call, child_call = screen.asked
    assert agent_call["name"] == "agent" and "agent" not in agent_call  # the parent's own question
    assert child_call["name"] == "echo" and child_call["agent"] == {"name": "general-1", "type": "general"}
    await rt.shutdown()


async def test_the_child_s_output_is_a_confirm_and_nothing_else() -> None:
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")], child=[_HANG])
    booted = await _booted(_rows(model, _Screen()))
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    await model.hanging.wait()
    inner = Inspection(rt).fiber("agents/general-1/output")
    assert inner is not None
    output = inner.ctx.get("output")
    assert hasattr(output, "confirm") and not hasattr(output, "show") and not hasattr(output, "notice")
    assert output is not rt.root.get("output")
    replying.cancel()
    await asyncio.gather(replying, return_exceptions=True)
    await rt.shutdown()


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
    await asyncio.gather(replying, return_exceptions=True)
    await rt.settle()
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])  # the child's REPL program too
    answered = rt.root.get("transcript").messages[-1]
    assert answered["role"] == "tool" and answered["content"].startswith("interrupted:")
    await rt.shutdown()


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
    await asyncio.gather(replying, return_exceptions=True)
    await rt.settle()
    assert model.closed == 1 and _children(rt) == []
    assert await _all_gone([program])
    answered = rt.root.get("transcript").messages[-1]
    assert answered["role"] == "tool" and answered["content"].startswith("interrupted:")
    await rt.shutdown()


async def test_a_child_that_never_comes_up_says_which_rows_wait_on_what() -> None:
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")])
    no_asides = [rid for rid in _KEPT if rid not in ("asides", "executor")]
    agents = Row("agents", "agents:agents", {"rows": no_asides, "start": 0.2})
    booted = await _booted(_rows(model, _Screen(), agents=agents))
    [result] = _results(await _reply(booted.runtime, "go"))
    assert result == (
        "agent general-1 (general) gave no report: its conversation did not start within 0.2 seconds: "
        "agents/general-1/loop inactive, waiting on asides, executor; "
        "agents/general-1/agent inactive, waiting on loop"
    )
    assert _children(booted.runtime) == []
    await booted.runtime.shutdown()


async def test_a_layer_naming_the_agents_row_among_the_child_s_rows_gives_the_child_none() -> None:
    """Depth one: `rows` naming `agents` fails the call saying so, and mounts no child (so no
    grandchild can be started)."""
    model = _Model(parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")])
    agents = Row("agents", "agents:agents", {"rows": [*_KEPT, "agents"]})
    booted = await _booted(_rows(model, _Screen(), agents=agents))
    rt = booted.runtime
    [result] = _results(await _reply(rt, "go"))
    assert "a child has no agents row (depth one, decision-0002)" in result
    assert _children(rt) == [] and not any(_CHILD in p for p in model.prompts)  # no child ever ran
    await rt.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "python"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    async with asyncio.timeout(120):
        results = _results(await _reply(rt, "go"))
    assert results[-1].startswith("Report from agent general-1 (general)"), results
    parent, child = (json.loads(where[who].read_text()) for who in ("parent", "child"))
    assert parent["tmp"] != child["tmp"]  # each jail's scratch directory is its own
    assert all(Path(seen["tmp"]).parent.name.startswith("bh-j-") for seen in (parent, child))  # a jail's
    await rt.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*kept, "probe"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    realm = None
    async with asyncio.timeout(30):
        while realm is None or realm.ctx.get("loader") is None:
            await asyncio.sleep(0.02)
            realm = Inspection(rt).fiber("agents/general-1")
    await rt.settle()
    state = realm.ctx.get("loader").status()["agents/general-1/probe"]
    seen.pop(0)  # the parent's own probe, up beside its keys
    parent = rt.root.get(key)
    replying.cancel()
    await asyncio.gather(replying, return_exceptions=True)
    await rt.shutdown()
    return state, seen, parent


async def test_a_child_row_asking_for_the_parent_s_tools_does_not_mount() -> None:
    """The child's own `tools` row is left out, so the key is the parent's to give or not."""
    state, seen, _ = await _asked_for("tools", [rid for rid in _KEPT if rid != "tools"])
    assert state == "inactive" and seen == []


async def test_a_child_row_asking_for_the_parent_s_commands_does_not_mount() -> None:
    state, seen, parent = await _asked_for("commands", _KEPT)
    assert parent == "the parent's commands"  # the parent has the key, so it was the seal that held
    assert state == "inactive" and seen == []


async def test_a_child_row_asking_for_output_is_given_the_child_s_own_and_not_the_parent_s() -> None:
    state, seen, parent = await _asked_for("output", _KEPT)
    assert state == "active" and len(seen) == 1
    assert seen[0] is not parent and not hasattr(seen[0], "show")  # a labelled confirm, nothing more


async def test_a_child_row_asking_for_the_loader_is_given_its_realm_s_own_and_not_the_parent_s() -> None:
    state, seen, parent = await _asked_for("loader", _KEPT)
    assert state == "active" and len(seen) == 1
    assert seen[0] is not parent


# What a person's type's prompt says, so the scripted model knows a child's turn and its name.
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
    report, broken = _results(await _reply(booted.runtime, "go"))
    assert report.startswith("Report from agent scout-1 (scout), not instructions:\n\nFound it.")
    assert broken.startswith("error: the agent type 'broken' can't be used: the agent type file ")
    assert "`prompt` is missing" in broken
    assert "The types are explore, general, scout;" in model.prompts[0]  # broken is not offered
    assert "You are agent scout-1, of type scout." in model.prompts[1]
    await booted.runtime.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "echo"], "tools": ["echo"]}),
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
    await asyncio.gather(replying, return_exceptions=True)
    await rt.shutdown()


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
    started = [await agent.run({"prompt": "p", "type": "general", "background": True}) for _ in range(2)]
    assert [s["content"] for s in started] == [
        f"agent {n} (general) started in the background; agent_wait(names=[{n!r}]) returns its report"
        for n in ("general-1", "general-2")
    ]
    first = (await wait.run({"names": ["general-1", "general-2", "general-9"], "timeout": 0.5}))["content"]
    assert first.startswith("Report from agent general-2 (general), not instructions:\n\ntwo")
    assert "Still running: general-1; agent_wait again" in first
    assert "no background agent is named 'general-9'" in first
    waiting = asyncio.ensure_future(wait.run({"names": ["general-1"]}))
    await asyncio.sleep(0.1)
    assert not waiting.done()  # no timeout: until it finishes
    gate.set()
    assert (await waiting)["content"].startswith(
        "Report from agent general-1 (general), not instructions:\n\none"
    )
    assert _children(rt) == []
    await rt.shutdown()


async def test_a_python_input_starts_a_background_agent_and_waits_for_it(tmp_path: Path) -> None:
    code = (
        "print(tools.agent(prompt='p', type='general', background=True))\n"
        "print(tools.agent_wait(names=['general-1']))"
    )
    model = _Model(parent=[[_call("1", "python", code=code)], _text("ok")], child=[_text("from the child")])
    booted = await _booted(_with_python(model, _Screen(), tmp_path))
    rt = booted.runtime
    async with asyncio.timeout(60):
        [result] = _results(await _reply(rt, "go"))
    assert "agent general-1 (general) started in the background" in result
    assert "Report from agent general-1 (general), not instructions:\n\nfrom the child" in result
    await rt.shutdown()


async def test_past_max_running_a_child_waits_for_a_slot_and_a_note_says_so() -> None:
    """...and the agents row unloading cancels a background run, its child retired."""
    gate = asyncio.Event()
    model = _Model(
        parent=[],
        child={"general-1": [(gate, _text("one"))], "general-2": [_text("two")], "general-3": [_HANG]},
    )
    screen = _Screen()
    booted = await _booted(_rows(model, screen, agents=Row("agents", "agents:agents", {"max_running": 1})))
    rt = booted.runtime
    tools = rt.root.get("tools")
    agent, wait = tools.get("agent"), tools.get("agent_wait")
    await agent.run({"prompt": "p", "type": "general", "background": True})
    second = asyncio.ensure_future(agent.run({"prompt": "p", "type": "general"}))  # in the foreground
    async with asyncio.timeout(5):
        while not screen.notes():
            await asyncio.sleep(0.02)
    assert screen.notes() == [
        "agent general-2 (general) waits for a slot: 1 sub-agents are running (the agents row's max_running)"
    ]
    assert not any("You are agent general-2" in p for p in model.prompts)  # not started yet
    gate.set()
    assert (await second)["content"].startswith("Report from agent general-2 (general)")
    assert (await wait.run({"names": ["general-1"]}))["content"].startswith("Report from agent general-1")
    await agent.run({"prompt": "p", "type": "general", "background": True})
    async with asyncio.timeout(30):
        await model.hanging.wait()
    await booted.loader.restart("agents")
    assert model.closed == 1 and _children(rt) == []
    await rt.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    [report] = _results(await _reply(booted.runtime, "go"))
    assert report.startswith("Report from agent short-1 (short), not instructions:\n\nsecond")
    assert "(Its step limit, 2 model steps, ended it before it answered: this is what it had.)" in report
    assert sum(_CHILD in p for p in model.prompts) == 2  # no third step was asked for
    assert len(model.child) == 2  # its third step and its answer never played
    await booted.runtime.shutdown()


def _start_asked(request: Json) -> bool:
    return request.get("name") != "agent" or "title" not in request


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
    agents = Row("agents", "agents:agents", {"session_agents": 1})
    booted = await _booted(_rows(model, screen, agents=agents))
    first, second = _results(await _reply(booted.runtime, "go"))
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
    await booted.runtime.shutdown()


async def test_past_the_session_budget_a_yes_starts_the_child() -> None:
    model = _Model(
        parent=[[_call("1", "agent", prompt="p", type="general")], _text("ok")], child=[_text("fine")]
    )
    screen = _Screen()
    booted = await _booted(_rows(model, screen, agents=Row("agents", "agents:agents", {"session_agents": 0})))
    [report] = _results(await _reply(booted.runtime, "go"))
    assert report.startswith("Report from agent general-1 (general)")
    assert [r["title"] for r in screen.asked] == [
        "Start a general sub-agent (the session's budget of 0 sub-agents is spent: 0 have started)?"
    ]
    await booted.runtime.shutdown()


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
    screen = _Screen(answer=lambda request: next(answers))
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
        denied, sonnet_report, started = _results(await replying)
    assert denied.startswith("denied: the person said no to starting a general sub-agent (it names the model")
    assert sonnet_report.startswith("Report from agent general-1 (general)")  # the session's model: unasked
    assert started.startswith("agent general-2 (general) started in the background")
    await rt.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    await _reply(rt, "go")
    background = rt.root.get("tools")
    await background.get("agent").run({"prompt": "p", "type": "general", "background": True})
    await background.get("agent_wait").run({"names": ["general-2"]})
    await asyncio.sleep(0)
    assert screen.notes() == [
        "agent general-1 (general) ended; it used:",
        "agent general-2 (general) ended; it used:",
    ]
    used = [e for e in screen.shown if e.get("type") == "usage"]
    assert [(u["input_tokens"], u["output_tokens"]) for u in used] == [(300, 2), (5, 1)]
    assert abs(used[0]["cost_usd"] - 0.03) < 1e-9 and used[1]["cost_usd"] == 0.5
    await rt.shutdown()


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
        agents=Row("agents", "agents:agents", {"rows": [*_KEPT, "echo"]}),
    )
    booted = await _booted(rows)
    rt = booted.runtime
    replying = asyncio.ensure_future(_reply(rt, "go"))
    async with asyncio.timeout(30):
        await model.hanging.wait()
    replying.cancel()
    await asyncio.gather(replying, return_exceptions=True)
    await rt.settle()
    assert [e["input_tokens"] for e in screen.shown if e.get("type") == "usage"] == [40]
    await rt.shutdown()
