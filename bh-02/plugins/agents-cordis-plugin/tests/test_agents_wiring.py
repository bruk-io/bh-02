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
from collections.abc import AsyncIterator, Mapping, Sequence
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
        self.closed = 0
        self.prompts: list[str] = []

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        system = str(messages[0].get("content", "")) if messages else ""
        self.prompts.append(system)
        script = self.child if _CHILD in system else self.parent
        if isinstance(script, dict):  # a script for each child, by the name its prompt gives
            script = script[next(name for name in script if f"You are agent {name}" in system)]
        step = script.pop(0)
        if step == _HANG:
            try:
                self.hanging.set()
                await asyncio.Event().wait()
            finally:
                self.closed += 1
        for chunk in step:
            yield chunk


class _Screen:
    """The parent's `output`: the person says `answer` to every question, which it keeps."""

    def __init__(self, answer: bool = True) -> None:
        self.asked: list[Json] = []
        self.answer = answer

    async def confirm(self, request: Json) -> bool:
        self.asked.append(request)
        return self.answer


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


def _rows(model: _Model, screen: _Screen, path: Path | None = None, **more: Any) -> list[Row]:
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
                _call("1", "agent", prompt="p", type="explore"),
                _call("2", "agent", prompt="p", type="general"),
            ],
            _text("ok"),
        ],
        child=[_text("fine")],
    )
    booted = await _booted(_rows(model, _Screen(), tmp_path / "transcript.jsonl"))
    unknown, report = _results(await _reply(booted.runtime, "go"))
    assert unknown == "error: there is no agent type 'explore'; the types are general"
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
