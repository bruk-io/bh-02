"""The `grants` row and `/grants` over a real loader: a grant and a requester's remount reload
neither `approval` nor the runner (decision-0012 item 7)."""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cordis import Booted, Effects, acquire, bind, boot, component
from cordis.composition import Row
from cordis.loader import resolve
from runner_cordis_plugin.grants import Answer, Asker, Grant, Kind, Request, Source
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


class _Prompt:
    def __init__(self, answer: Answer) -> None:
        self.answer = answer
        self.asked: list[Request] = []

    async def __call__(self, request: Request) -> Answer | None:
        self.asked.append(request)
        return self.answer


async def _booted(store: Path) -> Booted:
    booted = await boot(
        [],
        overrides=[
            _row("host", "_host", grants=str(store)),
            _row("commands", "_commands"),
            _row("models", "_models"),
            _row("requester", "_requester"),
            Row("grants", "runner_cordis_plugin.wiring:grants"),
            Row("grant-prompt", "runner_cordis_plugin.wiring:grant_prompt"),
            Row("runner", "runner_cordis_plugin.wiring:confined"),
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
    booted = await _booted(store)
    rt, loader = booted.runtime, booted.loader
    reloaded: list[str] = []
    rt.listeners.append(lambda event: reloaded.append(event.fiber) if event.kind == "reload" else None)
    grants, approval, runner = rt.root.get("grants"), rt.root.get("approval"), rt.root.get("runner")
    assert len(await grants.granted()) == 0  # held, but nobody has been asked

    prompt = _Prompt(Answer.ONCE)
    grants.serve(prompt)
    await _settled()
    assert prompt.asked == [NET]
    assert (await grants.granted()).items == (NET.grant,)

    # the requester remounts: remembered, not asked again, applied again
    await loader.restart("requester")
    await _settled()
    assert "requester" in reloaded and prompt.asked == [NET]
    assert (await grants.granted()).items == (NET.grant,)

    # another asker's grant, answered once
    other = Request(Grant(Kind.READ, "/data/in"), Asker(Source.INPUT, "python"), "reads the data")
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
    booted = await _booted(store)
    rt = booted.runtime
    reloaded: list[str] = []
    rt.listeners.append(lambda event: reloaded.append(event.fiber) if event.kind == "reload" else None)
    grants = rt.root.get("grants")
    grants.serve(_Prompt(Answer.ALWAYS))
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
    assert resolve("runner:grant_prompt").inject == frozenset({"grants", "commands"})
