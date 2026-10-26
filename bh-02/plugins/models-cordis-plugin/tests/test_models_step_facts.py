"""What each provider tells the loop's step record (CONTRACTS.md: model): the id that answered, on its
`usage` chunk, and its `settings`; and that neither provider's wire sends a field the loop records."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models_cordis_plugin import ModelsError, Named
from models_cordis_plugin.claude_code import ClaudeCodeConfig, ClaudeCodeModel, records_for
from models_cordis_plugin.claude_code.testing import FAKE_TOKEN_KEY, FakeClaudeCode, FakeStep
from models_cordis_plugin.named import ModelConfig
from models_cordis_plugin.openai import Fold, OpenAIModel, replayed
from models_cordis_plugin.openai.testing import StubServer
from models_cordis_plugin.providers import opened, resolved

_SPEC = {
    "name": "python",
    "description": "run Python",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
}
_FILE = """
default = "work/opus"

[work]
provider = "claude-code"

[work.models.opus]
id = "claude-opus-5-5"

[local]
provider = "openai"
base_url = "http://localhost:11434/v1"
max_tokens = 4096

[local.models.llama]
id = "llama3.2"
temperature = 0.2

[local.models.plain]
id = "plain-1"
"""


def _named(table: dict[str, Any]) -> Named:
    return Named("local/llama", "openai", "llama3.2", {"provider": "openai", **table}, "/c/models.toml")


def _config(tmp_path: Path, **more: Any) -> ClaudeCodeConfig:
    return ClaudeCodeConfig(state=str(tmp_path / "state"), token=FAKE_TOKEN_KEY, cwd=str(tmp_path), **more)


def test_openai_names_the_model_the_server_answered_with_on_its_usage_chunk() -> None:
    fold = Fold()
    fold.take({"model": "gpt-4o-2026-08-06", "choices": [{"delta": {"content": "hi"}}]})
    fold.take(
        {"model": "gpt-4o-2026-08-06", "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
    )
    (usage,) = [c for c in fold.finish() if c["type"] == "usage"]
    assert usage == {"type": "usage", "input_tokens": 10, "output_tokens": 2, "model": "gpt-4o-2026-08-06"}
    bare = Fold()  # a server that names none
    bare.take({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    assert "model" not in next(c for c in bare.finish() if c["type"] == "usage")


async def test_openai_reports_the_model_from_a_real_response_and_exposes_its_settings() -> None:
    with StubServer() as stub:
        table = {"provider": "openai", "id": "stub-1", "base_url": stub.base_url}
        named = Named(
            "stub/one", "openai", "stub-1", table | {"max_tokens": 99, "temperature": 0.5}, "/c/m.toml"
        )
        async with OpenAIModel(named) as model:
            chunks = [dict(c) async for c in model.complete([{"role": "user", "content": "hello"}], [_SPEC])]
    (usage,) = [c for c in chunks if c["type"] == "usage"]
    assert usage["model"] == "stub-1"  # the id the server's events named
    assert model.settings == {"model": "stub/one", "provider": "openai", "max_tokens": 99, "temperature": 0.5}


def test_openai_settings_hold_only_what_its_requests_send() -> None:
    plain = OpenAIModel(_named({"id": "llama3.2", "base_url": "http://h/v1"}))
    assert plain.settings == {"model": "local/llama", "provider": "openai"}  # none set: none named
    sampled = OpenAIModel(_named({"id": "llama3.2", "base_url": "http://h/v1", "temperature": 0.0}))
    assert sampled.settings == {"model": "local/llama", "provider": "openai", "temperature": 0.0}
    unset = OpenAIModel(_named({"id": "llama3.2", "base_url": "http://h/v1", "max_tokens": None}))
    assert "max_tokens" not in unset.settings  # as `request_for` leaves it out


async def test_claude_code_reports_the_model_that_answered_on_both_its_usage_chunks(tmp_path: Path) -> None:
    model = ClaudeCodeModel(
        _config(tmp_path), lambda options: FakeClaudeCode(options, [FakeStep([_text("hi")])])
    )
    chunks = [dict(c) async for c in model.complete([{"role": "system", "content": "s"}, _user()], [_SPEC])]
    usage = [c for c in chunks if c["type"] == "usage"]
    assert len(usage) == 2 and {u["model"] for u in usage} == {"claude-sonnet-5"}
    await model.close()


def test_claude_code_settings_name_the_model_and_the_provider_and_no_sampling(tmp_path: Path) -> None:
    named = ClaudeCodeModel(_config(tmp_path, model="claude-opus-5-5", name="work/opus"))
    assert named.settings == {"model": "work/opus", "provider": "claude-code"}  # Claude Code sends neither
    unnamed = ClaudeCodeModel(_config(tmp_path, model="sonnet"))
    assert unnamed.settings == {"model": "sonnet", "provider": "claude-code"}  # built with no name: the id


async def test_the_row_s_providers_expose_the_named_model_as_settings(tmp_path: Path) -> None:
    models = tmp_path / "models.toml"
    models.write_text(_FILE)
    cwd = tmp_path / "work"
    cwd.mkdir()
    for name, expected in {
        "work/opus": {"model": "work/opus", "provider": "claude-code"},
        "local/llama": {"model": "local/llama", "provider": "openai", "max_tokens": 4096, "temperature": 0.2},
        "local/plain": {"model": "local/plain", "provider": "openai", "max_tokens": 4096},
    }.items():
        config = ModelConfig(default=name, models=str(models), cwd=str(cwd), state=str(tmp_path / "s"))
        assert resolved(config).name == name
        async with opened(config) as value:
            assert not isinstance(value, ModelsError) and value.settings == expected


# What the loop records on an entry is the loop's own: neither provider sends it.
_RECORDED = {
    "at": "2026-10-18T03:47:12.345Z",
    "seed": {"keep": "the API's endpoints"},  # a compacted conversation's first entry
    "step": {
        "at": "2026-10-18T03:47:12.345Z",
        "first_chunk": 0.25,
        "took": 1.5,
        "model": "m-1",
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "settings": {"model": "work/opus", "provider": "claude-code"},
        "tool_changes": "listed",
    },
}


def test_the_openai_wire_does_not_send_what_the_loop_records() -> None:
    conversation: list[dict[str, Any]] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "python", "input": {}}]},
        {"role": "assistant", "content": "x", "provider": {"role": "assistant", "content": "x"}},
        {"role": "tool", "content": "42", "call_id": "c1"},
    ]
    for entry in conversation:
        recorded = {**entry, **{k: v for k, v in _RECORDED.items() if entry["role"] != "tool" or k == "at"}}
        assert replayed(recorded) == replayed(entry)


def test_the_claude_code_records_do_not_hold_what_the_loop_records() -> None:
    entries = [
        {"role": "user", "content": "run it", "today": "2026-09-23"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "t1", "name": "python", "input": {"code": "1"}}],
            "provider": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "mcp__bh__python", "input": {}}],
            },
        },
        {"role": "tool", "content": "1", "call_id": "t1"},
        {"role": "assistant", "content": "done"},
    ]
    recorded = [{**entry, **_RECORDED} for entry in entries]
    now, ids = datetime(2026, 9, 23, 12, 0, tzinfo=UTC), [f"id-{n}" for n in range(len(entries))]
    plain = records_for(entries, session="s1", cwd="/w", model="claude-sonnet-5", now=now, ids=ids)
    given = records_for(recorded, session="s1", cwd="/w", model="claude-sonnet-5", now=now, ids=ids)
    assert given == plain
    text = json.dumps(given)
    assert "first_chunk" not in text and "2026-10-18T03:47:12.345Z" not in text and "tool_changes" not in text
    assert "endpoints" not in text


def _text(said: str) -> dict[str, Any]:
    return {"type": "text", "text": said}


def _user() -> dict[str, Any]:
    return {"role": "user", "content": "hi"}
