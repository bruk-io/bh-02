"""The extensions row's value against a real worker (a plain subprocess under `PlainJail`) and
fakes for what it adds to: the model writes a file, bh-02 loads it, and everything it added
leaves with it."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cordis.testing import drive
from extensions_cordis_plugin import Extensions, ExtensionsConfig, extensions
from extensions_cordis_plugin.testing import PlainJail

type Remover = Callable[[], None]

_TODO = """
from cordis import Effects, acquire, component

@component
async def todo(*, commands, frame, system) -> Effects:
    items: list[str] = []

    async def run(args: str) -> str:
        if args:
            items.append(args)
        return ", ".join(items) or "nothing to do"

    yield acquire(commands.register, {"name": "todo", "help": "Keep a list", "usage": "/todo [ITEM]"}, run)
    yield acquire(frame.status, "count", "todo: 0")
    yield acquire(system.add, "The person keeps a to-do list with /todo.")
"""


class _Commands:
    def __init__(self) -> None:
        self.runs: dict[str, Callable[[str], Awaitable[Any]]] = {}

    def register(self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]) -> Remover:
        name = str(spec["name"])
        if name in self.runs:
            raise ValueError(f"a command named {name!r} is already registered")
        self.runs[name] = run
        return lambda: self.runs.pop(name, None) and None


class _Frame:
    def __init__(self) -> None:
        self._pushed: dict[object, tuple[str, str]] = {}

    def status(self, field: str, text: str, *shorter: str) -> Remover:
        token = object()
        self._pushed[token] = (field, text)
        return lambda: self._pushed.pop(token, None) and None

    def fields(self) -> dict[str, str]:
        return dict(self._pushed.values())


class _System:
    def __init__(self) -> None:
        self._sections: dict[object, Callable[[], str]] = {}

    def add(self, section: Callable[[], str]) -> Remover:
        token = object()
        self._sections[token] = section
        return lambda: self._sections.pop(token, None) and None

    def texts(self) -> list[str]:
        return [section() for section in self._sections.values()]


@dataclass
class _Output:
    answer: bool = True
    asked: list[Mapping[str, Any]] = field(default_factory=list)

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        self.asked.append(request)
        return self.answer


@dataclass
class _Harness:
    root: Path
    jail: PlainJail
    commands: _Commands
    frame: _Frame
    system: _System
    output: _Output
    extensions: Extensions

    def write(self, name: str, source: str) -> None:
        self.root.joinpath(".bh-02", "plugins").mkdir(parents=True, exist_ok=True)
        path = self.root / ".bh-02" / "plugins" / f"{name}.py"
        before = path.stat().st_mtime_ns if path.exists() else 0
        path.write_text(source)
        while path.stat().st_mtime_ns == before:  # a coarse clock: make the change visible
            path.write_text(source)

    def status(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads((self.root / ".bh-02" / "plugins" / "status.json").read_text())
        return loaded


@contextlib.asynccontextmanager
async def _running(root: Path, *, confined: bool = True, answer: bool = True) -> AsyncIterator[_Harness]:
    jail, commands, frame, system, output = (
        PlainJail(confined=confined),
        _Commands(),
        _Frame(),
        _System(),
        _Output(answer),
    )
    config = ExtensionsConfig(root=str(root), watch=3600)  # the test looks itself
    async with Extensions(jail, commands, frame, system, output, config) as running:
        yield _Harness(root, jail, commands, frame, system, output, running)


async def test_an_extension_the_model_writes_is_loaded_and_what_it_adds_reaches_bh_02(tmp_path: Path) -> None:
    async with _running(tmp_path) as h:
        assert h.jail.started == []  # nothing to load, so no worker
        h.write("todo", _TODO)
        await h.extensions.look()
        assert h.extensions.statuses["todo"].ok
        assert await h.commands.runs["todo"]("milk") == "milk"
        assert await h.commands.runs["todo"]("") == "milk"  # its state lives in the worker
        assert h.frame.fields() == {"todo:count": "todo: 0", "extensions": "ext: todo ✓"}
        assert h.system.texts() == ["The person keeps a to-do list with /todo."]
        assert h.extensions.section().endswith(
            "Extensions here: todo. How each one is, is in .bh-02/plugins/status.json."
        )
        assert h.status()["todo"] == {
            "state": "active",
            "rows": {"todo.todo": "active"},
            "error": None,
            "commands": ["/todo"],
            "problems": [],
        }
    # leaving takes back everything the extensions added, and stops the worker
    assert h.commands.runs == {} and h.frame.fields() == {} and h.system.texts() == []
    assert h.jail.started[0].process.returncode is not None


async def test_a_changed_extension_is_loaded_afresh_and_a_deleted_one_unloaded(tmp_path: Path) -> None:
    async with _running(tmp_path) as h:
        h.write("todo", _TODO)
        await h.extensions.look()
        await h.commands.runs["todo"]("milk")
        h.write("todo", _TODO.replace('"todo", "help"', '"tasks", "help"'))
        await h.extensions.look()
        assert set(h.commands.runs) == {"tasks"}  # the old command went with the old version
        assert await h.commands.runs["tasks"]("") == "nothing to do"  # a fresh component, fresh state
        (tmp_path / ".bh-02" / "plugins" / "todo.py").unlink()
        await h.extensions.look()
        assert h.commands.runs == {} and h.system.texts() == [] and h.extensions.statuses == {}
        assert h.frame.fields() == {} and h.status() == {}
        assert len(h.jail.started) == 1  # one worker throughout


async def test_what_kept_an_extension_from_loading_is_said_where_the_model_reads_it(tmp_path: Path) -> None:
    async with _running(tmp_path) as h:
        h.write("broken", "def (\n")
        h.write("empty", "x = 1\n")
        h.write(
            "half",
            "from cordis import Effects, bind, component\n\n"
            "@component\nasync def up(*, frame) -> Effects:\n    yield bind('ready', True)\n\n"
            "@component\nasync def waits(*, nobody_binds_this) -> Effects:\n    yield bind('x', 1)\n\n"
            "@component\nasync def fails(*, ready) -> Effects:\n    raise RuntimeError('boom')\n    yield\n",
        )
        await h.extensions.look()
        status = h.status()
        assert status["broken"]["state"] == "failed" and "SyntaxError" in status["broken"]["error"]
        assert "defines no component" in status["empty"]["error"]
        half = status["half"]
        assert half["state"] == "partly up" and half["rows"]["half.up"] == "active"
        assert half["rows"]["half.waits"].startswith("waiting on: nobody_binds_this")
        assert (
            half["rows"]["half.fails"].startswith("failed:")
            and "RuntimeError: boom" in half["rows"]["half.fails"]
        )
        assert 'half.py", line 13, in fails' in half["rows"]["half.fails"]  # the model's own frame
        assert "Extensions here: broken, empty, half." in h.extensions.section()
        assert h.frame.fields()["extensions"] == "ext: broken ✗ empty ✗ half ✗"


async def test_background_work_updates_a_field_and_what_it_pushed_leaves_with_it(tmp_path: Path) -> None:
    ticking = (
        "import asyncio\n"
        "from cordis import Effects, background, component\n\n"
        "@component\n"
        "async def ticks(*, frame) -> Effects:\n"
        "    async def tick() -> None:\n"
        "        n, remove = 0, None\n"
        "        while True:\n"
        "            n += 1\n"
        "            pushed = frame.status('n', f'tick {n}')\n"  # not through acquire
        "            if remove:\n"
        "                remove()\n"
        "            remove = pushed\n"
        "            await asyncio.sleep(0.02)\n\n"
        "    yield background(tick())\n"
    )
    async with _running(tmp_path) as h:
        h.write("ticks", ticking)
        await h.extensions.look()
        assert h.extensions.statuses["ticks"].ok
        async with asyncio.timeout(10):
            while h.frame.fields().get("ticks:n") in (None, "tick 1", "tick 2"):
                await asyncio.sleep(0.02)
        (tmp_path / ".bh-02" / "plugins" / "ticks.py").unlink()
        await h.extensions.look()
        assert h.frame.fields() == {}  # the last push, never acquired, went with its extension


async def test_a_command_name_bh_02_already_has_is_refused_and_said(tmp_path: Path) -> None:
    async with _running(tmp_path) as h:
        h.commands.runs["model"] = lambda args: asyncio.sleep(0, "the real /model")
        h.write("clash", _TODO.replace('"todo", "help"', '"model", "help"'))
        await h.extensions.look()
        assert await h.commands.runs["model"]("") == "the real /model"
        problems = h.status()["clash"]["problems"]
        assert problems == ["/model was not added: a command named 'model' is already registered"]
        assert h.status()["clash"]["state"] == "partly up"


async def test_unjailed_each_extension_is_put_to_the_person_with_its_source(tmp_path: Path) -> None:
    async with _running(tmp_path, confined=False, answer=False) as h:
        h.write("todo", _TODO)
        await h.extensions.look()
        (asked,) = h.output.asked
        assert asked["title"] == "Load the model's extension todo into bh-02, unjailed?"
        assert asked["input"] == {"code": _TODO}
        assert h.commands.runs == {} and h.jail.started == []  # declined: nothing ran
        assert h.status()["todo"]["error"] == "the person declined to load it"
        assert "each is shown to the person" in h.extensions.section()
        await h.extensions.look()
        assert len(h.output.asked) == 1  # not asked again until the file changes
        h.output.answer = True
        h.write("todo", _TODO + "\n")
        await h.extensions.look()
        assert "todo" in h.commands.runs and h.extensions.statuses["todo"].ok


async def test_an_extension_that_ends_the_worker_is_not_loaded_again_until_something_changes(
    tmp_path: Path,
) -> None:
    async with _running(tmp_path) as h:
        h.write("todo", _TODO)
        await h.extensions.look()
        h.write("exits", "import os\nos._exit(3)\n")
        await h.extensions.look()
        assert h.commands.runs == {}  # the worker took every extension down with it
        status = h.status()
        assert "worker ended" in status["exits"]["error"] and "worker ended" in status["todo"]["error"]
        for _ in range(3):
            await h.extensions.look()
        assert len(h.jail.started) == 1  # no worker started again for an unchanged directory
        (tmp_path / ".bh-02" / "plugins" / "exits.py").unlink()
        await h.extensions.look()
        assert len(h.jail.started) == 2 and h.extensions.statuses["todo"].ok
        assert await h.commands.runs["todo"]("again") == "again"


async def test_the_row_enters_the_extensions_and_adds_what_the_model_is_told() -> None:
    effects = await drive(
        extensions(
            jail=PlainJail(),
            commands=_Commands(),
            frame=_Frame(),
            system=_System(),
            output=_Output(),
            config=ExtensionsConfig(),
        ),
        [SimpleNamespace(section=lambda: "told")],  # what entering would have given back
    )
    assert [effect.name for effect in effects] == ["enter", "acquire"]
    assert isinstance(effects[0].args[0], Extensions) and effects[1].args[1]() == "told"
