"""The broker, the operator over a fake loader, and the rows on a runtime."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from commands_cordis_plugin import (
    Commands,
    Operator,
    OperatorConfig,
    model_list,
    operator,
    parse,
    perform,
    registry,
    rows_table,
    set_model,
    shadowing,
)
from cordis import Effects, Row, Runtime, bind, component
from cordis.loader import read_layer


def test_a_command_is_a_slash_a_name_and_the_rest() -> None:
    assert parse("/model haiku") == ("model", "haiku")
    assert parse("  /rows  ") == ("rows", "")
    assert parse("/explain  loop ") == ("explain", "loop")
    assert parse("/tmp/app.py is broken") is None and parse("hello") is None


async def test_the_broker_runs_what_is_registered_and_help_lists_it() -> None:
    commands = Commands()

    async def echo(args: str) -> str:
        return f"echo {args}"

    async def broken(args: str) -> str:
        raise RuntimeError("nope")

    remove = commands.register({"name": "echo", "help": "say it back", "usage": "TEXT"}, echo)
    commands.register({"name": "broken", "help": "fails", "usage": ""}, broken)
    assert await commands.run("/echo hi there") == "echo hi there"
    assert await commands.run("/broken") == "/broken failed: nope"
    assert await commands.run("/nope") == "unknown command /nope; /help lists them"
    help = await commands.run("/help")
    assert "/echo TEXT  say it back" in help and "/help" in help and "/exit" in help
    assert "Ctrl-D" not in help  # the key that leaves is each ui's own to say
    remove()  # a row that leaves takes its commands with it
    assert await commands.run("/echo hi") == "unknown command /echo; /help lists them"


def test_the_broker_says_which_lines_are_the_harness_s() -> None:
    """`claims` is how the chat row tells a command from a message: a slash command, known or
    not (so a typo never reaches the model), or a line starting with a claimed prefix."""
    commands = Commands()
    for line in ("/help", "  /model haiku ", "/new-thing x", "/Model", "/nope"):
        assert commands.claims(line), line
    for line in ("/tmp/x.py", "/", "hi /help", "/2fast", "", "   ", "!ls", "hello"):
        assert not commands.claims(line), line

    async def shell(args: str) -> str:
        return f"ran {args}"

    remove = commands.claim("!", {"name": "shell", "help": "run it", "usage": "COMMAND"}, shell)
    assert commands.claims("!ls") and commands.claims("  ! git status") and commands.claims("!")
    assert not commands.claims("hi !ls") and not commands.claims("/tmp/x.py")
    remove()
    assert not commands.claims("!ls")


async def test_a_claimed_prefix_takes_its_lines_one_character_each_and_never_twice() -> None:
    commands = Commands()
    asked: list[str] = []

    async def shell(args: str) -> str:
        asked.append(args)
        return f"ran {args}"

    async def broken(args: str) -> str:
        raise RuntimeError("no shell")

    spec = {"name": "shell", "help": "run COMMAND as you", "usage": "COMMAND"}
    remove = commands.claim("!", spec, shell)  # type: ignore[arg-type]
    assert await commands.run("  ! git status ") == "ran git status"  # the rest of the line
    assert asked == ["git status"]
    assert commands.specs() == []  # a prefix is typed, not chosen from the palette
    assert "!COMMAND  run COMMAND as you" in await commands.run("/help")
    # a second claim on the same character is refused, as a second command of one name is
    with pytest.raises(ValueError, match="a prefix named '!' is already registered"):
        commands.claim("!", spec, shell)  # type: ignore[arg-type]
    for bad, said in [
        ("!!", "a prefix is one character, such as '!'; got '!!'"),
        ("", "a prefix is one character, such as '!'; got ''"),
        ("/", "'/' starts the slash commands; claim another character, such as '!'"),
        ("a", "a line can start with 'a' by chance"),
        ("7", "a line can start with '7' by chance"),
        (" ", "a line can start with ' ' by chance"),
    ]:
        with pytest.raises(ValueError) as refused:
            commands.claim(bad, spec, shell)  # type: ignore[arg-type]
        assert said in str(refused.value)
    remove()
    assert await commands.run("!ls") == "'!ls' is not a command; /help lists them"  # unclaimed now
    commands.claim("!", spec, broken)  # type: ignore[arg-type]
    assert await commands.run("!ls") == "! (shell) failed: no shell"


async def test_what_a_command_leaves_for_the_model_is_held_here_until_taken_or_cleared() -> None:
    """`for_model` is held by the broker, which never reloads, not by the chat row, which a
    `/model` switch reloads: it is answered to nobody, and taken once, in the order it came;
    a new conversation (`cleared`) drops it, and says so."""
    commands = Commands()

    async def shell(args: str) -> list[dict[str, str]]:
        return [{"type": "note", "text": f"{args} said"}, {"type": "for_model", "text": f"$ {args}"}]

    async def clear(args: str) -> list[dict[str, str]]:
        return [{"type": "cleared"}, {"type": "note", "text": "cleared"}]

    commands.claim("!", {"name": "shell", "help": "", "usage": "COMMAND"}, shell)
    commands.register({"name": "clear", "help": "", "usage": ""}, clear)
    assert commands.take_for_model() == []
    assert await commands.run("!ls") == [{"type": "note", "text": "ls said"}]  # shown, not held
    assert await commands.run("/help") != ""  # other commands keep it
    await commands.run("!pwd")
    assert commands.take_for_model() == ["$ ls", "$ pwd"]
    assert commands.take_for_model() == []  # taken once
    await commands.run("!ls")
    await commands.run("!pwd")
    assert await commands.run("/clear") == [
        {"type": "cleared"},
        {"type": "note", "text": "cleared"},
        {
            "type": "note",
            "text": "2 commands' output, which was waiting for your next message, is dropped "
            "with the old conversation",
        },
    ]
    assert commands.take_for_model() == []
    assert await commands.run("/clear") == [{"type": "cleared"}, {"type": "note", "text": "cleared"}]


@dataclass
class Entry:
    id: str
    use: str
    config: dict[str, Any] | None = None


class Loader:
    def __init__(self) -> None:
        self.restarted: list[str] = []
        self.batches: list[tuple[str, ...]] = []
        self.reloads = 0
        self.rows = {"loop": "active", "model": "active", "kernel": "active", "fs": "active"}

    def status(self) -> dict[str, str]:
        return dict(self.rows)

    def explain(self, rid: str) -> str:
        return f"{rid}: all about it"

    async def restart(self, *rids: str) -> None:
        self.restarted.extend(rids)
        self.batches.append(rids)

    async def reload(self) -> None:
        self.reloads += 1

    def entries(self) -> Sequence[Entry]:
        return [
            Entry("loop", "agent:loop", {"max_nudges": 2}),
            Entry("model", "models:model", {"default": "haiku"}),
            Entry("kernel", "kernel:kernel"),
        ]


class Models:
    """The `models` value: two Claude models and a local one, haiku the model row's now."""

    path = "/home/me/.config/bh-02/models.toml"

    def __init__(self) -> None:
        self.now = "haiku"
        self.broken = False
        self.problem: str | None = None  # why the models file is not read (it is in the project)

    def listed(self) -> list[dict[str, Any]]:
        if self.broken:
            raise ValueError("the models file is not TOML")
        return [
            {"name": "sonnet", "provider": "claude-code", "id": "sonnet", "current": self.now == "sonnet"},
            {"name": "haiku", "provider": "claude-code", "id": "haiku", "current": self.now == "haiku"},
            {
                "name": "llama",
                "provider": "openai",
                "id": "llama3.2",
                "current": False,
                "where": "http://localhost:11434/v1",
            },
            {
                "name": "typo",
                "provider": "",
                "id": "",
                "current": False,
                "problem": "model 'typo' names no provider",
            },
        ]

    def current(self) -> dict[str, str]:
        return {"name": self.now, "provider": "claude-code"}

    def check(self, name: str) -> str | None:
        known = {m["name"]: m for m in self.listed()}
        if name not in known:
            return f"no model named {name!r}"
        return known[name].get("problem")


async def _drain(jobs: asyncio.Queue[Any]) -> None:
    while not jobs.empty():
        await (await jobs.get())()


async def test_the_operator_shows_explains_and_queues_restarts(tmp_path: Path) -> None:
    loader, jobs = Loader(), asyncio.Queue()
    op = Operator(loader, Models(), OperatorConfig(), jobs, lambda *a: None)
    run = {spec["name"]: fn for spec, fn in op.specs}
    assert "loop    agent:loop     active" in await run["rows"]("")
    assert await run["explain"]("loop") == "loop: all about it"
    assert await run["restart"]("nope") == "no row 'nope'; /rows lists them"
    assert await run["restart"]("fs") == "restarting fs" and loader.restarted == []  # queued, not run here
    await _drain(jobs)
    assert loader.restarted == ["fs"]


async def test_clear_forgets_the_history_then_starts_the_rows_that_exist_afresh(tmp_path: Path) -> None:
    history = tmp_path / "transcript.jsonl"
    history.write_text("abc\n")
    loader, jobs = Loader(), asyncio.Queue()
    op = Operator(loader, Models(), OperatorConfig(forget=(str(history),)), jobs, lambda *a: None)
    run = {spec["name"]: fn for spec, fn in op.specs}
    assert await run["clear"]("") == [  # the ui drops the old conversation, then says why
        {"type": "cleared"},
        {"type": "note", "text": "the conversation was cleared; starting afresh: loop, kernel"},
        {"type": "restarting", "rows": ["loop", "kernel"]},  # a line typed meanwhile waits for them
    ]  # no transcript row here
    await _drain(jobs)
    assert history.read_text() == "" and loader.batches == [("loop", "kernel")]  # together: one reload each


async def test_model_lists_the_models_and_switches_by_name_in_the_session_s_layer(tmp_path: Path) -> None:
    layer = tmp_path / "session.toml"
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { state = "/s/claude" }\n')
    calls: list[tuple[str, str, str]] = []
    loader, jobs, models = Loader(), asyncio.Queue(), Models()
    op = Operator(loader, models, OperatorConfig(layer=str(layer)), jobs, lambda *a: calls.append(a))
    run = {spec["name"]: fn for spec, fn in op.specs}
    assert (await run["model"]("")).splitlines() == [
        "  sonnet  claude-code  sonnet",
        "● haiku   claude-code  haiku",
        "  llama   openai       llama3.2  at http://localhost:11434/v1",
        "  typo",
        "    model 'typo' names no provider",
        f"/model NAME switches; add models in {models.path}",
    ]
    assert await run["model"]("haiku") == "model: haiku already; nothing to switch"
    assert await run["model"]("gpt-9") == "not switched: no model named 'gpt-9'"
    assert await run["model"]("typo") == "not switched: model 'typo' names no provider"
    assert calls == [] and jobs.empty()  # nothing changed: no reload, no restart announced
    note, restarting = await run["model"]("llama")  # across providers, by name
    assert str(note["text"]).startswith("switching to llama")
    assert restarting == {"type": "restarting", "rows": ["model"]}  # the ui holds lines for it
    assert calls == [(str(layer), "model", "llama")] and loader.reloads == 0  # queued, not run here
    await _drain(jobs)
    assert loader.reloads == 1  # the layers are read again now, not when the watcher next looks
    for bad in ("/model sonnet-x", "/sonnet", "sonnet x"):  # a command typed twice, two words
        assert (await run["model"](bad)).startswith(f"not a model name: {bad!r}; type /model and one name")
    assert calls == [(str(layer), "model", "llama")]  # none of them was recorded
    unsessioned = Operator(Loader(), Models(), OperatorConfig(), asyncio.Queue(), lambda *a: None)
    assert "no session layer" in await dict((s["name"], f) for s, f in unsessioned.specs)["model"]("x")
    set_model(str(layer), "model", "llama")
    (row,) = read_layer(layer)
    assert row == Row("model", config={"state": "/s/claude", "default": "llama"})


async def test_model_refuses_when_a_later_layer_sets_the_model_row_s_config(tmp_path: Path) -> None:
    """A `--patch` that sets the model row's config replaces the session layer's whole: /model
    would record a name that never runs, so it says so and records nothing."""
    base, layer, patch, other = (tmp_path / n for n in ("base.toml", "session.toml", "p.toml", "q.toml"))
    base.write_text('[[plugin]]\nid = "model"\nuse = "models:model"\n')
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { default = "haiku" }\n')
    patch.write_text('[[plugin]]\nid = "model"\nconfig = { env_file = "/x/local.env" }\n')
    other.write_text('[[plugin]]\nid = "model"\ndisabled = false\n')  # no config: shadows nothing
    files = [str(base), str(layer), str(other), str(patch)]
    assert shadowing(files, str(layer), "model") == str(patch)
    assert shadowing(files[:3], str(layer), "model") is None
    assert shadowing([str(patch), str(layer)], str(layer), "model") is None  # before it: overridden by it
    calls: list[tuple[str, str, str]] = []
    jobs: asyncio.Queue[Any] = asyncio.Queue()
    op = Operator(
        Loader(),
        Models(),
        OperatorConfig(layer=str(layer)),
        jobs,
        lambda *a: calls.append(a),
        lambda mine, rid: shadowing(files, mine, rid),
    )
    said = await dict((s["name"], f) for s, f in op.specs)["model"]("llama")
    assert said == (
        f"not switched: {patch} sets the 'model' row's config, which replaces the session's (where "
        "/model records the model) whole, so the model that file names stays. Set "
        "`default = \"llama\"` in that file's 'model' row, or run without it"
    )
    assert calls == [] and jobs.empty()


def test_the_model_command_offers_each_usable_model_as_a_choice() -> None:
    models = Models()
    op = Operator(Loader(), models, OperatorConfig(), asyncio.Queue(), lambda *a: None)
    spec = next(spec for spec, _ in op.specs if spec["name"] == "model")
    choices = spec["choices"]()
    assert [c["args"] for c in choices] == ["sonnet", "haiku", "llama"]  # not the one with a problem
    assert choices[0]["help"] == "switch to sonnet (claude-code: sonnet)"
    assert choices[1]["help"] == "the model now (claude-code: haiku)"
    models.broken = True
    assert spec["choices"]() == []  # read each time; a broken file offers none, /model says why


def test_the_model_list_marks_a_shadowed_built_in() -> None:
    listed = [
        {
            "name": "sonnet",
            "provider": "openai",
            "id": "x",
            "current": True,
            "shadows": "shadows the built-in 'sonnet' (f)",
        }
    ]
    assert model_list(listed, "f").splitlines()[:2] == [
        "● sonnet  openai  x",
        "    shadows the built-in 'sonnet' (f)",
    ]


async def test_the_model_list_says_why_the_models_file_is_not_read_instead_of_where_to_add() -> None:
    """A models file in the project is not read: /model says so where it would say to add models
    there, and still lists the models there are."""
    models = Models()
    models.problem = "the models file /p/.config/bh-02/models.toml is not read: it is in the project (/p)"
    op = Operator(Loader(), models, OperatorConfig(), asyncio.Queue(), lambda *a: None)
    said = (await dict((s["name"], f) for s, f in op.specs)["model"]("")).splitlines()
    assert said[0] == "  sonnet  claude-code  sonnet"
    assert said[-1] == f"/model NAME switches; {models.problem}" and "add models in" not in said[-1]


async def test_a_failed_job_is_reported_and_the_next_one_still_runs() -> None:
    jobs: asyncio.Queue[Any] = asyncio.Queue()
    ran, failures = [], []

    async def fails() -> None:
        raise RuntimeError("boom")

    async def works() -> None:
        ran.append("ok")

    await jobs.put(fails)
    await jobs.put(works)
    worker = asyncio.create_task(perform(jobs, failures.append))
    await asyncio.sleep(0.01)
    worker.cancel()
    assert failures == ["RuntimeError: boom"] and ran == ["ok"]


def test_rows_line_up() -> None:
    table = rows_table({"loop": "active", "kernel": "failed: x"}, {"loop": "a:b", "kernel": "kernel:kernel"})
    assert table.splitlines() == ["kernel  kernel:kernel  failed: x", "loop    a:b            active"]


async def test_the_operator_row_registers_its_commands_and_takes_them_when_it_leaves() -> None:
    loader = Loader()

    @component
    async def fake_loader() -> Effects:
        yield bind("loader", loader)

    @component
    async def fake_models() -> Effects:
        yield bind("models", Models())

    rt = Runtime()
    rt.mount(registry, id="commands")
    rt.mount(fake_loader, id="loader")
    rt.mount(fake_models, id="models")
    row = rt.mount(operator, id="operator")
    await rt.settle()
    commands = rt.root.get("commands")
    assert [s["name"] for s in commands.specs()] == ["rows", "explain", "restart", "clear", "model"]
    assert await commands.run("/restart fs") == "restarting fs"
    await asyncio.sleep(0.01)
    assert loader.restarted == ["fs"]  # the row's own background work ran it
    await row.retire()
    await rt.settle()
    assert commands.specs() == []
    await rt.shutdown()
