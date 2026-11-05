"""The `grants` row and `/grants` over a real loader: a grant and a requester's remount reload
neither `approval` nor the runner (decision-0012 item 7)."""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_cordis_plugin import ToolBroker
from cordis import Booted, Effects, acquire, bind, boot, component
from cordis.composition import Row
from cordis.loader import resolve
from runner_cordis_plugin.grants import Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.store import read, write

NET = Request(Grant(Kind.NET, "example.com", 443), Asker(Source.ROW, "requester"), "fetch packages")


@dataclass(frozen=True)
class _Host:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""
    grants: str = ""


class _Commands:
    def __init__(self) -> None:
        self.registered: dict[str, Callable[[str], Any]] = {}

    def register(self, spec: Mapping[str, Any], run: Callable[[str], Any]) -> Callable[[], None]:
        name = spec["name"]
        self.registered[name] = run

        def remove() -> None:
            self.registered.pop(name, None)

        return remove


class _Models:
    def key_envs(self) -> Mapping[str, Sequence[str]]:
        return {}


class _Output:
    """The person: answers each choice with the next of `values` ('' once they run out), keeps what
    it was asked, and holds the question open while `holding` (cancelled: it says so)."""

    def __init__(self, values: Sequence[str], holding: bool) -> None:
        self.values = list(values)
        self.asked: list[Mapping[str, Any]] = []
        self.hold = asyncio.Event()
        self.holding = holding
        self.cancelled = False

    async def choose(self, question: Mapping[str, Any]) -> str:
        self.asked.append(question)
        if self.holding:
            try:
                await self.hold.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return self.values.pop(0) if self.values else ""


class _Asides:
    def __init__(self) -> None:
        self.added: list[Callable[[Mapping[str, Any]], str]] = []

    def add(self, fn: Callable[[Mapping[str, Any]], str]) -> Callable[[], None]:
        self.added.append(fn)
        return lambda: self.added.remove(fn)


@dataclass(frozen=True)
class _Said:
    values: tuple[str, ...] = ()
    holding: bool = False


@component(provides=("output",))
async def _output(*, config: _Said) -> Effects:
    yield bind("output", _Output(config.values, config.holding))


class _Sections:
    def __init__(self) -> None:
        self.added: dict[str, Callable[[], str]] = {}

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]:
        self.added[name] = section
        return lambda: self.added.pop(name)


@component(provides=("tools",))
async def _tools() -> Effects:
    yield bind("tools", ToolBroker())


@component(provides=("system",))
async def _system() -> Effects:
    yield bind("system", _Sections())


@component(provides=("asides",))
async def _asides() -> Effects:
    yield bind("asides", _Asides())


@component(provides=("host",))
async def _host(*, config: _Host) -> Effects:
    yield bind("host", config)


@component(provides=("commands",))
async def _commands() -> Effects:
    yield bind("commands", _Commands())


@component(provides=("models",))
async def _models() -> Effects:
    yield bind("models", _Models())


@component
async def _requester(*, grants: Any) -> Effects:
    """A row with a standing need, as a plugin's would be."""
    yield acquire(grants.need, NET)


def _row(id: str, name: str, **config: Any) -> Row:
    return Row(id, f"{__name__}:{name}", config=config or None)


async def _settled() -> None:
    """Let a restart, a store read on a thread and a question finish."""
    await asyncio.sleep(0.3)


async def _booted(
    store: Path, *values: str, holding: bool = False, runner: str = "confined", agent: str = ""
) -> Booted:
    """The rows over a store; the person answers `values` in turn (the first is the answer to a
    row's need, asked as the prompt is served), or holds each question open."""
    booted = await boot(
        [],
        overrides=[
            _row("host", "_host", grants=str(store)),
            _row("commands", "_commands"),
            _row("models", "_models"),
            _row("output", "_output", values=values, holding=holding),
            _row("asides", "_asides"),
            _row("tools", "_tools"),
            _row("system", "_system"),
            _row("requester", "_requester"),
            Row("grants", "runner_cordis_plugin.wiring:grants"),
            Row("grant-prompt", "runner_cordis_plugin.wiring:grant_prompt"),
            Row(
                "grant", "runner_cordis_plugin.wiring:grant_tool", config={"agent": agent} if agent else None
            ),
            Row("runner", f"runner_cordis_plugin.wiring:{runner}"),
            Row("approval", "runner_cordis_plugin.wiring:approval"),
        ],
        watch=None,
    )
    await _settled()
    assert set(booted.loader.status().values()) == {"active"}, booted.loader.status()
    return booted


async def test_a_need_is_asked_once_applied_while_held_and_neither_it_nor_a_grant_reloads_approval(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store, holding=True)  # the need's question is up, unanswered
    rt, loader = booted.runtime, booted.loader
    reloaded: list[str] = []
    rt.listeners.append(lambda event: reloaded.append(event.fiber) if event.kind == "reload" else None)
    grants, approval, runner = rt.root.get("grants"), rt.root.get("approval"), rt.root.get("runner")
    output = rt.root.get("output")
    assert len(await grants.granted()) == 0  # held, but nobody has answered
    assert len(output.asked) == 1

    output.values[:] = ["once"]
    output.hold.set()
    await _settled()
    assert (await grants.granted()).items == (NET.grant,)

    # the requester remounts: remembered, not asked again, applied again
    await loader.restart("requester")
    await _settled()
    assert "requester" in reloaded and len(output.asked) == 1
    assert (await grants.granted()).items == (NET.grant,)

    # another asker's grant, answered once
    other = Request(Grant(Kind.READ, "/data/in"), Asker(Source.INPUT, "python"), "reads the data")
    output.values[:] = ["once"]
    assert await grants.ask(other) == "once"

    # the requester leaves with its row: its need is no longer applied, the other's still is
    await loader.apply([entry for entry in loader.entries() if entry.id != "requester"])
    await _settled()
    assert (await grants.granted()).items == (other.grant,)

    # no row reloaded for any of it but the requester's own
    assert {row for row in reloaded if row != "requester"} == set()
    assert rt.root.get("grants") is grants
    assert rt.root.get("approval") is approval and rt.root.get("runner") is runner
    await rt.shutdown()


async def test_an_always_grant_reloads_no_row(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store, holding=True)
    rt = booted.runtime
    reloaded: list[str] = []
    rt.listeners.append(lambda event: reloaded.append(event.fiber) if event.kind == "reload" else None)
    output = rt.root.get("output")
    output.values[:] = ["always"]
    output.hold.set()
    await _settled()
    assert read(store) == (NET,)
    assert reloaded == []
    await rt.shutdown()


async def test_slash_grants_lists_and_revokes_and_a_revoked_always_grant_is_gone_at_the_next_start(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    write(store, [NET])
    booted = await _booted(store)
    rt = booted.runtime
    grants = rt.root.get("grants")
    command = rt.root.get("commands").registered["grants"]
    listing = await command("")
    (entry,) = await grants.list()
    assert entry.id in listing and "net example.com:443" in listing and "always (project)" in listing
    assert "row requester" in listing and "fetch packages" in listing

    assert (await command("revoke deadbeef")).startswith("no grant has id 'deadbeef'")
    assert (await command("revoke")).startswith("usage:")
    assert (await command(f"revoke {entry.id}")).startswith("revoked: ")
    assert read(store) == () and len(await grants.granted()) == 0
    assert await command("") == "nothing is granted"
    await rt.shutdown()


def test_the_broker_depends_on_host_alone_and_approval_on_neither_it_nor_a_requester() -> None:
    """What a row depends on is what reloads it: the broker never reloads (the shell pins `host`), and
    `approval` reads the runner alone, so a grant, which changes the broker's value and not its
    binding, reloads no row (the tests above watch it not)."""
    assert resolve("runner:grants").inject == frozenset({"host"})
    assert resolve("runner:approval").inject == frozenset({"runner"})
    assert resolve("runner:grant_prompt").inject == frozenset({"grants", "output", "asides", "commands"})
    # a sub-agent's realm reads only these from the parent's; the tool needs nothing else from outside
    assert resolve("runner:grant_tool").inject == frozenset(
        {"grants", "tools", "system", "runner", "approval"}
    )
    # the rows that take `grants` for a need or a restart take the binding, which never reloads
    assert "grants" in resolve("python:tool").inject and "grants" in resolve("extensions:process").inject
    # what the prompt reads is not what approval or the runner read, so none of it reloads them
    assert not {"output", "asides", "grant-prompt"} & resolve("runner:approval").inject
    assert not {"output", "asides", "grant-prompt"} & resolve("runner_cordis_plugin.wiring:confined").inject


def _other(target: str) -> Request:
    return Request(Grant(Kind.READ, target), Asker(Source.INPUT, "python"), "reads the data")


async def test_each_answer_is_kept_as_decided_and_a_withdrawn_one_records_nothing(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt = booted.runtime
    grants, output = rt.root.get("grants"), rt.root.get("output")
    output.asked.clear()  # the requester's need was asked as the prompt was served, and withdrawn
    once, always, no, withdrawn = _other("/d/once"), _other("/d/always"), _other("/d/no"), _other("/d/w")

    output.values[:] = ["once", "always", "no", ""]
    assert await grants.ask(once) == "once"
    assert await grants.ask(always) == "always"
    assert await grants.ask(no) == "no"
    assert await grants.ask(withdrawn) == "no"  # withdrawn answers no to its asker, and records nothing

    assert read(store) == (always,)  # always: in the store, and only that
    assert (await grants.granted()).items == (always.grant, once.grant)  # once: this session
    listed = {entry.request.grant: (entry.answer, entry.scope) for entry in await grants.list()}
    assert listed == {
        always.grant: ("always", "project"),
        once.grant: ("once", "session"),
        no.grant: ("no", "session"),
    }
    asked = len(output.asked)
    assert await grants.ask(no) == "no" and await grants.ask(once) == "standing"  # not asked again
    assert len(output.asked) == asked

    output.values[:] = ["once"]
    assert await grants.ask(withdrawn) == "once"  # a withdrawn question is asked again
    assert len(output.asked) == asked + 1
    await rt.shutdown()


async def test_the_question_is_the_prompting_words_and_the_model_is_told_each_answer_once(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt = booted.runtime
    grants, output, asides = rt.root.get("grants"), rt.root.get("output"), rt.root.get("asides")
    (aside,) = asides.added
    output.asked.clear()  # the requester's need was asked as the prompt was served, and withdrawn
    assert aside({"name": "python"}) == ""  # nothing decided yet

    output.values[:] = ["once", "no", ""]
    await grants.ask(_other("/d/in"))
    await grants.ask(Request(Grant(Kind.NET, "example.org", 443), Asker(Source.AGENT, "scout"), "docs"))
    await grants.ask(_other("/d/withdrawn"))
    shown = output.asked[0]
    assert shown["title"] == "Allow read /d/in?" and shown["escape"] == "no"
    assert [c["value"] for c in shown["choices"]] == ["once", "always", "no"]

    told = aside({"name": "python"}).splitlines()
    assert len(told) == 2  # the withdrawn one is not told
    assert told[0].startswith("The person granted read /d/in") and "for this session" in told[0]
    assert told[1].startswith("The person declined net example.org:443 (asked by agent scout)")
    assert aside({"name": "python"}) == ""  # told once
    await rt.shutdown()


async def test_a_reload_of_the_prompt_withdraws_the_question_under_way_and_reloads_no_other_row(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt, loader = booted.runtime, booted.loader
    grants, output = rt.root.get("grants"), rt.root.get("output")
    approval, runner = rt.root.get("approval"), rt.root.get("runner")
    reloaded: list[str] = []
    rt.listeners.append(lambda event: reloaded.append(event.fiber) if event.kind == "reload" else None)

    output.asked.clear()
    output.holding = True
    asking = asyncio.ensure_future(grants.ask(_other("/d/held")))
    await _settled()
    assert not asking.done() and len(output.asked) == 1
    await loader.restart("grant-prompt")
    await _settled()
    assert output.cancelled  # the question was taken down, not left up
    assert await asyncio.wait_for(asking, 1) == "no"  # its asker is answered no, nothing recorded
    assert len(await grants.list()) == 0
    assert "grant-prompt" in reloaded
    assert not {"approval", "runner"} & set(reloaded)
    assert rt.root.get("approval") is approval and rt.root.get("runner") is runner

    # the prompt is served again after its reload, and asks what the requester still needs first
    output.holding = False
    output.hold.set()
    output.values[:] = ["once", "once"]
    await _settled()
    assert (await grants.granted()).items == (NET.grant,)
    assert await grants.ask(_other("/d/held")) == "once"
    await rt.shutdown()


async def test_revoking_a_session_answer_a_need_still_holds_asks_the_need_again(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt = booted.runtime
    grants, output = rt.root.get("grants"), rt.root.get("output")
    output.asked.clear()  # the need was asked as the prompt was served, and withdrawn
    output.values[:] = ["once"]
    assert await grants.ask(NET) == "once"
    assert (await grants.granted()).items == (NET.grant,)
    asked = len(output.asked)

    (entry,) = await grants.list()
    command = rt.root.get("commands").registered["grants"]
    output.values[:] = ["no"]
    assert (await command(f"revoke {entry.id}")).startswith("revoked: ")
    await _settled()
    assert len(output.asked) == asked + 1  # the holder is not left silently without it: asked again
    assert len(await grants.granted()) == 0  # and the answer is no this time
    await rt.shutdown()


async def test_what_the_runner_told_the_broker_reaches_the_model_on_the_next_call_once(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt = booted.runtime
    grants, asides = rt.root.get("grants"), rt.root.get("asides")
    (aside,) = asides.added
    grants.tell("A connection the program made to nowhere.test:443 was refused: it did not resolve.")
    assert (
        aside({"name": "python"})
        == "A connection the program made to nowhere.test:443 was refused: it did not resolve."
    )
    assert aside({"name": "python"}) == ""  # told once
    await rt.shutdown()


async def test_revoking_a_net_grant_through_the_command_says_open_connections_stay_open(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store, "always")
    rt = booted.runtime
    grants, commands = rt.root.get("grants"), rt.root.get("commands")
    await _settled()
    (entry,) = [each for each in await grants.list() if each.request.grant == NET.grant]
    said = await commands.registered["grants"](f"revoke {entry.id}")
    assert said.startswith("revoked: ") and "connections already open" in said
    await rt.shutdown()


async def _grant_tool(rt: Any) -> Any:
    registered = rt.root.get("tools").get("grant")
    assert registered is not None
    return registered


async def test_grant_is_a_harness_tool_that_tells_the_model_of_itself_in_a_system_section_only(
    tmp_path: Path,
) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt = booted.runtime
    registered = await _grant_tool(rt)
    assert registered.runs == "harness"  # approval asks exactly what it asks of a call in the jail
    spec = registered.spec
    assert spec["name"] == "grant" and spec["parameters"]["required"] == ["kind", "target", "reason"]
    assert "restart" not in spec["description"] and "once" not in spec["description"]  # the section's words
    told = rt.root.get("system").added["grants"]()
    assert "tools.grant(kind=..., target=..., reason=...)" in told and "starts again" in told
    await rt.shutdown()


async def test_a_call_is_asked_as_the_input_and_says_when_each_kind_holds(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    data = tmp_path / "data"
    data.mkdir()
    booted = await _booted(store)
    rt = booted.runtime
    grants, output = rt.root.get("grants"), rt.root.get("output")
    output.asked.clear()
    run = (await _grant_tool(rt)).run

    output.values[:] = ["once", "always"]
    before = grants.generation()
    path = await run({"kind": "read", "target": str(data), "reason": "reads the data"})
    assert path["content"].startswith(f"Granted for this session: read: {data}; it holds from the next input")
    assert grants.generation() != before  # the Python process starts again before its next input
    assert output.asked[0]["lines"][1] == "Asked by: input python, because: reads the data"

    net = await run({"kind": "net", "target": "example.com", "port": 443, "reason": "fetches docs"})
    assert net["content"].startswith("Granted for this project: net: example.com:443; it holds now")
    again = await run({"kind": "read", "target": str(data), "reason": "reads the data"})
    assert "is already granted" in again["content"] and len(output.asked) == 2  # not asked twice
    await rt.shutdown()


async def test_a_sub_agent_s_call_is_asked_as_the_agent_by_its_label(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store, agent="general-1 (general)")
    rt = booted.runtime
    output = rt.root.get("output")
    output.asked.clear()
    output.values[:] = ["once"]
    said = await (await _grant_tool(rt)).run(
        {"kind": "net", "target": "example.com", "port": 443, "reason": "docs"}
    )
    assert said["content"].startswith("Granted for this session: net: example.com:443")
    assert output.asked[0]["lines"][1] == "Asked by: agent general-1 (general), because: docs"
    await rt.shutdown()


async def test_a_call_a_floor_refuses_or_that_is_not_a_request_asks_nobody(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store)
    rt = booted.runtime
    output = rt.root.get("output")
    output.asked.clear()
    run = (await _grant_tool(rt)).run
    refused = await run({"kind": "read", "target": str(store), "reason": "look at the grants"})
    assert refused["content"].startswith("Not granted, and nobody was asked")  # the store is on the floor
    for bad in (
        {"kind": "sudo", "target": "/", "reason": "x"},
        {"kind": "read", "target": "relative", "reason": "x"},
        {"kind": "net", "target": "example.com", "reason": "no port"},
        {"kind": "read", "target": "/d", "port": 80, "reason": "a port on a path"},
        {"kind": "env", "target": "HTTP_PROXY", "reason": "x"},
        {"kind": "read", "target": "/d"},
    ):
        said = (await run(bad))["content"]
        assert said.startswith(("error:", "Not granted, and nobody was asked")), said
    assert output.asked == []
    await rt.shutdown()


async def test_with_nothing_confining_there_is_nothing_to_grant_and_nobody_is_asked(tmp_path: Path) -> None:
    store = tmp_path / "grants"
    store.mkdir(mode=0o700)
    booted = await _booted(store, runner="unconfined")
    rt = booted.runtime
    output = rt.root.get("output")
    output.asked.clear()
    said = await (await _grant_tool(rt)).run({"kind": "read", "target": "/d", "reason": "x"})
    assert "nothing to grant" in said["content"] and output.asked == []
    assert "`--no-jail`" in rt.root.get("system").added["grants"]()
    await rt.shutdown()
