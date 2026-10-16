"""An endpoint's `key_command`: the key it prints, what is said when it gives none (never what it
printed), the openai provider keeping its headers for `key_ttl_ms` and dropping them when the server
refuses them, discovery asking with it, and a layer's `extra` that may not name one. Each command
is a small shell line printing a stand-in: no real key is ever read."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import Catalog, ModelsError, Named, combined, find, problem
from models_cordis_plugin.key_command import command_key
from models_cordis_plugin.openai import OpenAIModel, Reply, headers_for
from models_cordis_plugin.openai.testing import FakeGet, StubServer

_TOOL = {"name": "python", "description": "run Python", "parameters": {"type": "object", "properties": {}}}


async def test_the_key_is_what_the_command_prints_trimmed() -> None:
    assert await command_key("work", "printf ' sk-printed \\n'") == "sk-printed"


@pytest.mark.parametrize(
    ("command", "said"),
    [
        ("echo sk-leaked-on-failure; exit 3", "exited with 3"),
        ("true", "printed nothing"),
        ("printf '  \\n'", "printed nothing"),
    ],
)
async def test_a_command_that_gives_no_key_names_itself_never_what_it_printed(
    command: str, said: str
) -> None:
    with pytest.raises(ModelsError) as raised:
        await command_key("work", command)
    message = raised.value.message
    assert raised.value.kind == "authentication_failed" and said in message
    assert f"'work''s key_command `{command}`" in message and "Run it in a terminal" in message
    assert "sk-leaked" not in message.replace(command, "")


async def test_a_command_that_runs_past_its_deadline_is_ended_and_said() -> None:
    with pytest.raises(ModelsError, match=r"printed no key within 0\.2 s"):
        await command_key("work", "sleep 5", deadline=0.2)


def _named(base_url: str, command: str, **more: Any) -> Named:
    endpoint = {"provider": "openai", "base_url": base_url, "key_command": command, **more}
    found = find(
        "work/stub", combined({"work": {**endpoint, "models": {"stub": {"id": "stub-1"}}}}, "/c/m.toml", {})
    )
    assert found is not None and problem(found) is None
    return found


async def _step(model: OpenAIModel, messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(chunk) async for chunk in model.complete(messages, [_TOOL])]


def _counting(tmp_path: Path, key_file: Path) -> tuple[str, Path]:
    """A command printing `key_file`'s text, and the file each run adds a line to."""
    runs = tmp_path / "runs"
    return f"echo run >> {runs} && cat {key_file}", runs


def _runs(runs: Path) -> int:
    return len(runs.read_text().splitlines()) if runs.exists() else 0


async def test_an_openai_model_sends_the_printed_key_and_runs_the_command_again_after_its_ttl(
    tmp_path: Path,
) -> None:
    key = tmp_path / "key"
    key.write_text("sk-stand-in\n")
    command, runs = _counting(tmp_path, key)
    now = [100.0]
    with StubServer(key="sk-stand-in") as stub:
        async with OpenAIModel(
            _named(stub.base_url, command, key_ttl_ms=60_000), clock=lambda: now[0]
        ) as model:
            await _step(model, [{"role": "user", "content": "one"}])
            await _step(model, [{"role": "user", "content": "two"}])
            assert _runs(runs) == 1  # kept for its ttl: the command ran once for both steps
            now[0] += 61
            await _step(model, [{"role": "user", "content": "three"}])
            assert _runs(runs) == 2
    assert [request["authorization"] for request in stub.requests] == ["Bearer sk-stand-in"] * 3


async def test_a_refused_printed_key_is_dropped_and_the_next_step_runs_the_command_again(
    tmp_path: Path,
) -> None:
    key = tmp_path / "key"
    key.write_text("sk-stale\n")
    command, runs = _counting(tmp_path, key)
    with StubServer(key="sk-fresh") as stub:
        async with OpenAIModel(_named(stub.base_url, command)) as model:
            with pytest.raises(ModelsError) as raised:
                await _step(model, [{"role": "user", "content": "one"}])
            assert raised.value.kind == "authentication_failed"
            assert "check what model 'work/stub''s key_command prints (run `echo run" in raised.value.message
            assert "sk-stale" not in raised.value.message
            key.write_text("sk-fresh\n")  # the helper has a new key now
            said = await _step(model, [{"role": "user", "content": "two"}])
    assert any(chunk["type"] == "text" for chunk in said) and _runs(runs) == 2


async def test_a_printed_key_a_header_can_not_carry_is_said_without_it() -> None:
    named = _named("http://127.0.0.1:1/v1", "printf 'sk-one\\nsk-two'")
    with pytest.raises(ModelsError) as raised:
        await headers_for(named, None)
    assert "printed something a request header can't carry" in raised.value.message
    assert "sk-one" not in raised.value.message.replace("printf 'sk-one\\nsk-two'", "")


@pytest.mark.parametrize("named", ["key_command", "discover"])
def test_a_layer_s_extra_may_not_name_a_key_command_or_discover(named: str) -> None:
    table = {
        "provider": "openai",
        "base_url": "https://h/v1",
        "models": {"x": {"id": "x"}},
        named: "print-a-token" if named == "key_command" else True,
    }
    (endpoint,) = [m for m in combined({}, "/c/m.toml", {"work": table}) if m.name == "work"]
    assert f"{named} is read only from the models file, never from a layer" in str(problem(endpoint))


class _Entry:
    def __init__(self, config: dict[str, Any]) -> None:
        self.id, self.use, self.config = "model", "models:model", config


class _Loader:
    def __init__(self, entry: _Entry) -> None:
        self.entry = entry

    def entries(self) -> list[_Entry]:
        return [self.entry]


async def test_discovery_asks_with_the_key_the_command_prints(tmp_path: Path) -> None:
    models = tmp_path / "models.toml"
    models.write_text(
        '[work]\nprovider = "openai"\nbase_url = "https://h/v1"\ndiscover = true\n'
        'key_command = "printf sk-stand-in"\n[work.models.named]\nid = "m-named"\n'
    )
    get = FakeGet({"https://h/v1/models": Reply(200, b'{"data": [{"id": "m-named"}, {"id": "m-listed"}]}')})
    values = Catalog(_Loader(_Entry({"models": str(models)})), get=get)
    await values.refresh()
    ((url, headers),) = get.calls
    assert url == "https://h/v1/models" and headers["Authorization"] == "Bearer sk-stand-in"
    # the named model first, then what the server listed that no named model already is
    assert [m["name"] for m in values.listed()] == ["work/named", "work/m-listed"]
