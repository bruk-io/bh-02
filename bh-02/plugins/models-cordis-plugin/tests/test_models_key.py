"""An endpoint's `key = { cmd = ... }` or `{ op = ... }`: the key the command prints, what is said when it
gives none (never what it printed), the openai provider keeping its headers for `ttl_ms` and dropping
them when the server refuses them, discovery asking with it, an `op` run as `op read`, a gateway handing
its command to the Claude Code CLI, and a layer's `extra` that may not name a `key`. Each command is a
small shell line printing a stand-in: no real key is ever read.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import (
    Catalog,
    ModelConfig,
    ModelsError,
    Named,
    combined,
    find,
    opened,
    problem,
)
from models_cordis_plugin.claude_code import TOKEN_VARIABLE
from models_cordis_plugin.claude_code.testing import FakeClaudeCode, FakeStep
from models_cordis_plugin.named import KeySpec
from models_cordis_plugin.openai import OpenAIModel, Reply, headers_for
from models_cordis_plugin.openai.testing import FakeGet, StubServer
from models_cordis_plugin.shell_key import command_key

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
    assert f"'work''s key command `{command}`" in message and "Run it in a terminal" in message
    assert "sk-leaked" not in message.replace(command, "")


async def test_a_command_that_runs_past_its_deadline_is_ended_and_said() -> None:
    with pytest.raises(ModelsError, match=r"printed no key within 0\.2 s"):
        await command_key("work", "sleep 5", deadline=0.2)


def _named(base_url: str, command: str, ttl_ms: int | None = None) -> Named:
    key = {"cmd": command} | ({"ttl_ms": ttl_ms} if ttl_ms is not None else {})
    endpoint = {"provider": "openai", "base_url": base_url, "key": key}
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
        async with OpenAIModel(_named(stub.base_url, command, ttl_ms=60_000), clock=lambda: now[0]) as model:
            await _step(model, [{"role": "user", "content": "one"}])
            await _step(model, [{"role": "user", "content": "two"}])
            assert _runs(runs) == 1  # kept for its ttl: the command ran once for both steps
            now[0] += 61
            await _step(model, [{"role": "user", "content": "three"}])
            assert _runs(runs) == 2
    assert [request["authorization"] for request in stub.requests] == ["Bearer sk-stand-in"] * 3


async def test_a_key_with_no_ttl_is_kept_for_300_seconds(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("sk-stand-in\n")
    command, runs = _counting(tmp_path, key)
    now = [100.0]
    with StubServer(key="sk-stand-in") as stub:
        async with OpenAIModel(_named(stub.base_url, command), clock=lambda: now[0]) as model:
            await _step(model, [{"role": "user", "content": "one"}])
            now[0] += 299
            await _step(model, [{"role": "user", "content": "two"}])
            assert _runs(runs) == 1
            now[0] += 2
            await _step(model, [{"role": "user", "content": "three"}])
            assert _runs(runs) == 2


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
            assert "check what model 'work/stub''s key command prints (run `echo run" in raised.value.message
            assert "sk-stale" not in raised.value.message
            key.write_text("sk-fresh\n")  # the helper has a new key now
            said = await _step(model, [{"role": "user", "content": "two"}])
    assert any(chunk["type"] == "text" for chunk in said) and _runs(runs) == 2


async def test_a_printed_key_a_header_can_not_carry_is_said_without_it() -> None:
    named = _named("http://127.0.0.1:1/v1", "printf 'sk-one\\nsk-two'")
    with pytest.raises(ModelsError) as raised:
        await headers_for(named)
    assert "holds a character a request header can't carry" in raised.value.message
    assert "Run it in a terminal to check what it prints" in raised.value.message
    assert "sk-one" not in raised.value.message.replace("printf 'sk-one\\nsk-two'", "")


@pytest.mark.parametrize("named", ["key", "discover"])
def test_a_layer_s_extra_may_not_name_a_key_or_discover(named: str) -> None:
    table = {
        "provider": "openai",
        "base_url": "https://h/v1",
        "models": {"x": {"id": "x"}},
        named: {"env": "SOME_KEY"} if named == "key" else True,
    }
    (endpoint,) = [m for m in combined({}, "/c/m.toml", {"work": table}) if m.name == "work"]
    assert f"{named} is read only from the models file, never from a layer" in str(problem(endpoint))
    (kept,) = [m for m in combined({"work": table}, "/c/m.toml", {}) if m.name == "work"]
    assert problem(kept) is None  # the same table in the models file is trusted


def test_a_claude_code_gateway_in_a_layer_s_extra_may_not_name_a_key_either() -> None:
    table = {
        "provider": "claude-code",
        "base_url": "https://g/anthropic",
        "key": {"cmd": "print-a-token"},
        "models": {"x": {"id": "x"}},
    }
    (endpoint,) = [m for m in combined({}, "/c/m.toml", {"work": table}) if m.name == "work"]
    assert "key is read only from the models file, never from a layer" in str(problem(endpoint))


@pytest.mark.parametrize(
    ("key", "command"),
    [
        (KeySpec("cmd", "my-token-helper get_token", 600_000), "my-token-helper get_token"),
        (KeySpec("op", "op://work/openrouter/key"), "op read op://work/openrouter/key"),
        (KeySpec("op", "op://work/my vault/key; rm -rf x"), "op read 'op://work/my vault/key; rm -rf x'"),
        (KeySpec("env", "OPENROUTER_API_KEY"), None),
    ],
)
def test_a_source_s_command_is_the_cmd_or_op_read_of_the_reference_quoted(
    key: KeySpec, command: str | None
) -> None:
    assert key.command == command


async def test_an_op_key_runs_op_read_as_the_person_and_sends_what_it_prints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stand-in `op` on PATH (the real one needs the person's vault) that prints a key for its
    one reference and nothing for another."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    op = bin_dir / "op"
    op.write_text('#!/bin/sh\n[ "$1 $2" = "read op://work/openrouter/key" ] && echo sk-from-op\n')
    op.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    endpoint = {
        "provider": "openai",
        "base_url": "https://h/v1",
        "key": {"op": "op://work/openrouter/key"},
        "models": {"x": {"id": "x"}},
    }
    named = find("work/x", combined({"work": endpoint}, "/c/m.toml", {}))
    assert named is not None and problem(named) is None
    assert (await headers_for(named))["Authorization"] == "Bearer sk-from-op"


@pytest.mark.parametrize(
    ("key", "helper", "ttl"),
    [
        ({"cmd": "print-a-token", "ttl_ms": 60_000}, "print-a-token", "60000"),
        ({"op": "op://work/gateway/key"}, "op read op://work/gateway/key", None),
    ],
)
async def test_a_gateway_hands_its_command_and_ttl_to_the_claude_code_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: dict[str, Any], helper: str, ttl: str | None
) -> None:
    """`cmd` goes to the CLI as it is, `op` as `op read`, `ttl_ms` as the helper's TTL; bh-02 runs neither
    and the token's variable is empty for that CLI."""
    models = tmp_path / "models.toml"
    models.write_text(_toml(key))
    started: list[FakeClaudeCode] = []

    def open_(options: Any) -> FakeClaudeCode:
        started.append(FakeClaudeCode(options, [FakeStep([{"type": "text", "text": "Hello"}])]))
        return started[-1]

    monkeypatch.setattr("models_cordis_plugin.claude_code.provider.ClaudeSDKClient", open_)
    config = ModelConfig(default="work/x", models=str(models), state=str(tmp_path / "state"))
    async with opened(config) as model:
        [chunk async for chunk in model.complete([{"role": "user", "content": "hi"}], [])]
    (fake,) = started
    settings = json.loads(fake.options.settings)
    assert settings["apiKeyHelper"] == helper
    assert settings["env"].get("CLAUDE_CODE_API_KEY_HELPER_TTL_MS") == ttl
    assert fake.options.env[TOKEN_VARIABLE] == ""


def _toml(key: Mapping[str, Any]) -> str:
    """A models file with the gateway `work` whose key is `key`."""
    written = ", ".join(f"{source} = {json.dumps(value)}" for source, value in key.items())
    return (
        '[work]\nprovider = "claude-code"\nbase_url = "https://g/anthropic"\n'
        f'key = {{ {written} }}\n[work.models.x]\nid = "claude-opus-5-5"\n'
    )


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
        'key = { cmd = "printf sk-stand-in" }\n[work.models.named]\nid = "m-named"\n'
    )
    get = FakeGet({"https://h/v1/models": Reply(200, b'{"data": [{"id": "m-named"}, {"id": "m-listed"}]}')})
    values = Catalog(_Loader(_Entry({"models": str(models)})), get=get)
    await values.refresh()
    ((url, headers),) = get.calls
    assert url == "https://h/v1/models" and headers["Authorization"] == "Bearer sk-stand-in"
    # the named model first, then what the server listed that no named model already is
    assert [m["name"] for m in values.listed()] == ["work/named", "work/m-listed"]
