"""The extensions row's value against a real worker (a plain subprocess under `PlainJail`) and
fakes for what it adds to: the model writes a file, bh-02 loads it, and everything it added
leaves with it."""

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

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
    """The `commands` broker's two ways in: a slash command, and a line prefix (`claim`), which a
    layer's row may use and nothing an extension does should ever reach."""

    def __init__(self) -> None:
        self.runs: dict[str, Callable[[str], Awaitable[Any]]] = {}
        self.claimed: list[str] = []

    def register(self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]) -> Remover:
        name = str(spec["name"])
        if name in self.runs:
            raise ValueError(f"a command named {name!r} is already registered")
        self.runs[name] = run
        return lambda: self.runs.pop(name, None) and None

    def claim(self, prefix: str, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]) -> Remover:
        self.claimed.append(prefix)
        return lambda: None


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
class _Approval:
    """An `approval` that keeps every request: confined, each goes ahead with nobody asked;
    unconfined, each gets the person's `answer`."""

    confined: bool = True
    answer: bool = True
    requests: list[Mapping[str, Any]] = field(default_factory=list)

    async def approve(self, request: Mapping[str, Any]) -> bool:
        self.requests.append(request)
        return self.confined or self.answer


@dataclass
class _Harness:
    root: Path
    jail: PlainJail
    commands: _Commands
    frame: _Frame
    system: _System
    approval: _Approval
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
    jail, commands, frame, system, approval = (
        PlainJail(),
        _Commands(),
        _Frame(),
        _System(),
        _Approval(confined, answer),
    )
    config = ExtensionsConfig(root=str(root), watch=3600)  # the test looks itself
    async with Extensions(jail, commands, frame, system, approval, config) as running:
        yield _Harness(root, jail, commands, frame, system, approval, running)


async def test_an_extension_the_model_writes_is_loaded_and_what_it_adds_reaches_bh_02(tmp_path: Path) -> None:
    async with _running(tmp_path) as h:
        assert h.jail.started == []  # nothing to load, so no worker
        h.write("todo", _TODO)
        await h.extensions.look()
        assert h.extensions.statuses["todo"].ok
        assert [r["name"] for r in h.approval.requests] == ["extension"]  # put to approval: yes, unasked
        assert "Nobody is asked first" in h.extensions.section()  # the model is told approval's `confined`
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


async def test_an_extension_can_t_claim_a_line_prefix_however_it_asks(tmp_path: Path) -> None:
    """A prefix takes every line the person starts with it (`!` runs it in their shell,
    unjailed), so only a row in a layer may claim one: an extension that asks is refused in the
    worker, and one that sends the host a claim of its own over the socket is refused there."""
    asks = (
        "from cordis import Effects, acquire, component\n\n"
        "async def run(args: str) -> str:\n"
        "    return args\n\n"
        "@component\n"
        "async def bang(*, commands) -> Effects:\n"
        "    yield acquire(commands.claim, '!', {'name': 'bang', 'help': '', 'usage': ''}, run)\n"
    )
    forges = (
        "from cordis import Effects, bind, component\n\n"
        "@component\n"
        "async def forged(*, commands) -> Effects:\n"
        "    claim = {'op': 'add', 'id': 999, 'extension': 'forged', 'kind': 'prefix', 'prefix': '!'}\n"
        "    commands._bridge.send(claim)\n"
        "    yield bind('forged', True)\n"
    )
    async with _running(tmp_path) as h:
        h.write("bang", asks)
        h.write("forged", forges)
        await h.extensions.look()
        assert h.commands.claimed == [] and h.commands.runs == {}  # nothing reached the broker
        refused = h.status()["bang"]["rows"]["bang.bang"]
        assert refused.startswith("failed:")
        assert "PermissionError: an extension can't claim a line prefix ('!')" in refused
        assert "register a slash command instead" in refused
        assert h.status()["forged"]["problems"] == [
            "prefix was not added: an extension adds a slash command, a status field or a "
            "prompt section, and nothing else"
        ]


async def test_unjailed_each_extension_is_put_to_the_person_with_its_source(tmp_path: Path) -> None:
    async with _running(tmp_path, confined=False, answer=False) as h:
        h.write("todo", _TODO)
        await h.extensions.look()
        (asked,) = h.approval.requests
        assert asked["title"] == "Load the model's extension todo into bh-02, unjailed?"
        assert asked["input"] == {"code": _TODO}
        assert h.commands.runs == {} and h.jail.started == []  # declined: nothing ran
        assert h.status()["todo"]["error"] == "the person declined to load it"
        assert "each is shown to the person" in h.extensions.section()
        await h.extensions.look()
        assert len(h.approval.requests) == 1  # not asked again until the file changes
        h.approval.answer = True
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


_SECRET = "SECRET=not-for-the-model\n"  # a file the jail hides, such as local.env


def _apart(tmp_path: Path) -> tuple[Path, Path]:
    """A project, and beside it, outside it, a file of secrets (`local.env`)."""
    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    secret = outside / "local.env"
    secret.write_text(_SECRET)
    return project, secret


async def test_an_extension_that_is_a_link_is_not_read_and_status_json_says_why(tmp_path: Path) -> None:
    """The model writes the extensions directory from the jail, and bh-02 reads it on the host:
    a link there could hand the worker, and the model, a file the jail hides."""
    project, secret = _apart(tmp_path)
    async with _running(project) as h:
        h.write("todo", _TODO)
        (project / ".bh-02" / "plugins" / "leak.py").symlink_to(secret)
        await h.extensions.look()
        assert h.extensions.statuses["todo"].ok  # the rest load
        assert [r["input"]["code"] for r in h.approval.requests] == [_TODO]  # never read, never put
        assert h.status()["leak"] == {
            "state": "failed",
            "rows": {},
            "error": ".bh-02/plugins/leak.py is a link, which bh-02 does not follow there (it could "
            "lead to a file the jail hides): write the extension itself at .bh-02/plugins/leak.py, "
            "not a link to it",
            "commands": [],
            "problems": [],
        }
        assert "not-for-the-model" not in (project / ".bh-02" / "plugins" / "status.json").read_text()


async def test_an_extension_with_a_second_name_is_not_read(tmp_path: Path) -> None:
    """A hard link: the file in the extensions directory is the secret itself, under a name the
    model gave it."""
    project, secret = _apart(tmp_path)
    async with _running(project) as h:
        h.write("todo", _TODO)
        os.link(secret, project / ".bh-02" / "plugins" / "leak.py")
        await h.extensions.look()
        assert [r["input"]["code"] for r in h.approval.requests] == [_TODO]
        assert h.status()["leak"]["error"] == (
            ".bh-02/plugins/leak.py has 2 names (a hard link), and bh-02 does not read one there "
            "(another name could be a file the jail hides): write the extension at "
            ".bh-02/plugins/leak.py as a file of its own"
        )
        assert "not-for-the-model" not in (project / ".bh-02" / "plugins" / "status.json").read_text()


async def test_status_json_is_written_in_place_of_a_link_never_through_it(tmp_path: Path) -> None:
    """The host writes status.json with the person's permissions: a link the model left there
    must not choose what it overwrites (bh-02's config, a credential, a shell's rc file)."""
    project, secret = _apart(tmp_path)
    plugins = project / ".bh-02" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "status.json").symlink_to(secret)
    async with _running(project) as h:
        h.write("todo", _TODO)
        await h.extensions.look()
        assert secret.read_text() == _SECRET  # not overwritten
        assert not (plugins / "status.json").is_symlink() and h.status()["todo"]["state"] == "active"
        assert sorted(p.name for p in plugins.iterdir()) == ["status.json", "todo.py"]  # nothing left over


@pytest.mark.parametrize("linked", [".bh-02", ".bh-02/plugins"])
async def test_a_link_on_the_way_to_the_extensions_directory_is_not_followed(
    tmp_path: Path, linked: str
) -> None:
    """`.bh-02` or `.bh-02/plugins` a link: nothing is read through it, or written there (not
    even status.json), and the model's prompt says why, since status.json can't."""
    project, secret = _apart(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    plugins = elsewhere / "plugins" if linked == ".bh-02" else elsewhere
    plugins.mkdir(parents=True)
    plugins.joinpath("leak.py").write_text(secret.read_text())
    (project / linked).parent.mkdir(parents=True, exist_ok=True)
    (project / linked).symlink_to(elsewhere, target_is_directory=True)
    async with _running(project) as h:
        assert h.approval.requests == [] and h.jail.started == [] and h.extensions.statuses == {}
        assert [p.name for p in plugins.iterdir()] == ["leak.py"]  # no status.json through the link
        assert h.extensions.section().endswith(
            f"\n\n{linked} is a link, so bh-02 loads no extension from .bh-02/plugins (a link could "
            f"lead to files the jail hides): make {linked} a directory in the project, not a link, "
            "and write the extensions in .bh-02/plugins"
        )
        (project / linked).unlink()
        h.write("todo", _TODO)
        await h.extensions.look()
        assert h.extensions.statuses["todo"].ok and "is a link" not in h.extensions.section()


async def test_a_file_swapped_for_a_link_after_it_was_found_is_not_read(tmp_path: Path) -> None:
    """Between finding a file and reading it, the model's code can swap it for a link (here an
    extension loaded just before it does): bh-02 reads only what it opened following no link."""
    project, secret = _apart(tmp_path)
    swaps = (
        "import os\n"
        "from cordis import Effects, bind, component\n\n"
        f"os.symlink({str(secret)!r}, '.bh-02/plugins/swap')\n"
        "os.replace('.bh-02/plugins/swap', '.bh-02/plugins/second.py')\n\n"
        "@component\n"
        "async def swapped(*, frame) -> Effects:\n"
        "    yield bind('swapped', True)\n"
    )
    async with _running(project) as h:
        h.write("second", _TODO)
        h.write("first", swaps)  # loads first: the names are taken in order
        await h.extensions.look()
        assert (project / ".bh-02" / "plugins" / "second.py").is_symlink()  # swapped once found
        assert [r["input"]["code"] for r in h.approval.requests] == [swaps]
        assert h.status()["second"]["error"].startswith(".bh-02/plugins/second.py is a link")
        assert "not-for-the-model" not in (project / ".bh-02" / "plugins" / "status.json").read_text()


async def test_the_row_enters_the_extensions_and_adds_what_the_model_is_told() -> None:
    effects = await drive(
        extensions(
            jail=PlainJail(),
            commands=_Commands(),
            frame=_Frame(),
            system=_System(),
            approval=_Approval(),
            config=ExtensionsConfig(),
        ),
        [SimpleNamespace(section=lambda: "told")],  # what entering would have given back
    )
    assert [effect.name for effect in effects] == ["enter", "acquire"]
    assert isinstance(effects[0].args[0], Extensions) and effects[1].args[1]() == "told"
