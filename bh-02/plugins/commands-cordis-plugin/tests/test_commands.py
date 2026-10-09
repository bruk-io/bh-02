"""The broker, the operator over a fake loader, and the rows on a runtime."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from commands_cordis_plugin import Commands, Operator, operator, parse, registry, rows_table
from cordis import Effects, Runtime, bind, component


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


async def test_a_conversation_carried_on_from_a_summary_keeps_what_is_held_for_the_model() -> None:
    """`/compact`'s `cleared` is `compacted`: the summary was written from what the model read,
    which never held `!`'s output, so it is kept for the person's next message, unannounced."""
    commands = Commands()

    async def shell(args: str) -> list[dict[str, str]]:
        return [{"type": "for_model", "text": f"$ {args}"}]

    async def compact(args: str) -> list[dict[str, Any]]:
        return [{"type": "cleared", "compacted": True}, {"type": "note", "text": "compacted"}]

    commands.claim("!", {"name": "shell", "help": "", "usage": "COMMAND"}, shell)
    commands.register({"name": "compact", "help": "", "usage": ""}, compact)
    await commands.run("!pytest")
    assert await commands.run("/compact") == [
        {"type": "cleared", "compacted": True},
        {"type": "note", "text": "compacted"},
    ]
    assert commands.take_for_model() == ["$ pytest"]


@dataclass
class Entry:
    id: str
    use: str
    config: dict[str, Any] | None = None


class Loader:
    def __init__(self) -> None:
        self.restarted: list[str] = []
        self.batches: list[tuple[str, ...]] = []
        self.rows = {"loop": "active", "model": "active", "kernel": "active", "fs": "active"}

    def status(self) -> dict[str, str]:
        return dict(self.rows)

    def explain(self, rid: str) -> str:
        return f"{rid}: all about it"

    async def restart(self, *rids: str) -> None:
        self.restarted.extend(rids)
        self.batches.append(rids)

    def entries(self) -> Sequence[Entry]:
        return [
            Entry("loop", "agent:loop", {"max_nudges": 2}),
            Entry("model", "models:model", {"default": "haiku"}),
            Entry("kernel", "kernel:kernel"),
        ]


async def _drain(jobs: asyncio.Queue[Any]) -> None:
    while not jobs.empty():
        await (await jobs.get())()


async def test_the_operator_shows_explains_and_queues_restarts(tmp_path: Path) -> None:
    loader, jobs = Loader(), asyncio.Queue()
    op = Operator(loader, jobs)
    run = {spec["name"]: fn for spec, fn in op.specs}
    assert "loop    agent:loop     active" in await run["rows"]("")
    assert await run["explain"]("loop") == "loop: all about it"
    assert await run["restart"]("nope") == "no row 'nope'; /rows lists them"
    assert await run["restart"]("fs") == "restarting fs" and loader.restarted == []  # queued, not run here
    await _drain(jobs)
    assert loader.restarted == ["fs"]


def test_rows_line_up() -> None:
    table = rows_table({"loop": "active", "kernel": "failed: x"}, {"loop": "a:b", "kernel": "kernel:kernel"})
    assert table.splitlines() == ["kernel  kernel:kernel  failed: x", "loop    a:b            active"]


class _Output:
    """An `output` value that keeps the notices it is given."""

    def __init__(self) -> None:
        self.notices: list[str] = []

    async def notice(self, message: str) -> None:
        self.notices.append(message)


def _operator_on(rt: Runtime, loader: object) -> _Output:
    """Mount the operator and fakes of the rows it depends on (no `models`, no `model`); the
    output fake back."""
    told = _Output()

    @component
    async def fake_loader() -> Effects:
        yield bind("loader", loader)

    @component
    async def fake_output() -> Effects:
        yield bind("output", told)

    rt.mount(registry, id="commands")
    rt.mount(fake_loader, id="loader")
    rt.mount(fake_output, id="output")
    return told


async def test_the_operator_row_registers_its_commands_and_takes_them_when_it_leaves() -> None:
    """With no `models:catalog` (nor any model) in the composition, /rows, /explain and /restart
    are there: `/model` is the models plugin's, `/clear` and `/compact` the agent plugin's."""
    loader = Loader()
    rt = Runtime()
    told = _operator_on(rt, loader)
    row = rt.mount(operator, id="operator")
    await rt.settle()
    commands = rt.root.get("commands")
    assert [s["name"] for s in commands.specs()] == ["rows", "explain", "restart"]
    assert "loop    agent:loop     active" in await commands.run("/rows")
    assert await commands.run("/restart fs") == "restarting fs"
    await asyncio.sleep(0.01)
    assert loader.restarted == ["fs"]  # the row's own background work ran it
    assert told.notices == []  # a restart that worked tells nothing more
    await row.retire()
    await rt.settle()
    assert commands.specs() == []
    await rt.shutdown()


class _Failing(Loader):
    async def restart(self, *rids: str) -> None:
        raise RuntimeError(f"{rids[0]} would not start")


async def test_a_restart_that_fails_after_the_command_answered_is_told_to_the_person() -> None:
    """/restart answers, then its restart runs as the row's own background work: one that fails
    must reach the person, not vanish."""
    rt = Runtime()
    told = _operator_on(rt, _Failing())
    rt.mount(operator, id="operator")
    await rt.settle()
    assert await rt.root.get("commands").run("/restart fs") == "restarting fs"
    await asyncio.sleep(0.01)
    (notice,) = told.notices
    assert notice.startswith("a command's restart failed (RuntimeError: fs would not start)")
    assert "/restart ROW tries again" in notice
    await rt.shutdown()
