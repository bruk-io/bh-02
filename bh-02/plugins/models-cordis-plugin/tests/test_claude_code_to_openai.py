"""A conversation that moves from the claude-code provider to the openai one (`/model`): Claude's
turns, made by the real `ClaudeCodeModel` over its fake session (no process, no network), are
sent to an OpenAI-compatible stand-in server (a real socket) rebuilt as that API's messages,
the python call and its result included; Claude's own content blocks never reach it.

The transcript entries are built as agent:loop builds them (`_Turn.entry`): its text, its
calls, and the provider's message from the step's last chunk."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from models_cordis_plugin import Named
from models_cordis_plugin.claude_code import TOKEN_VARIABLE, ClaudeCodeConfig, ClaudeCodeModel
from models_cordis_plugin.claude_code.testing import FakeClaudeCode, FakeStep
from models_cordis_plugin.openai import OpenAIModel
from models_cordis_plugin.openai.testing import StubServer

_SPEC = {
    "name": "python",
    "description": "Run a cell.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
}
_SYSTEM = {"role": "system", "content": "You are a test."}


def _entry(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    calls = [
        {"id": c["id"], "name": c["name"], "input": c["input"]} for c in chunks if c["type"] == "tool_call"
    ]
    entry: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(c["text"] for c in chunks if c["type"] == "text"),
    }
    if calls:
        entry["tool_calls"] = calls
    entry["provider"] = chunks[-1]["message"]
    return entry


async def test_claude_s_turns_reach_an_openai_model_rebuilt_as_its_own_messages(tmp_path: Path) -> None:
    env = tmp_path / "local.env"
    env.write_text(f"{TOKEN_VARIABLE}=sentinel-not-a-real-token\n")
    script = [
        FakeStep(
            [
                {"type": "text", "text": "Let me run it."},
                {"type": "tool_use", "id": "t1", "name": "mcp__bh__python", "input": {"code": "1+1"}},
            ],
            stop="tool_use",
        ),
        FakeStep([{"type": "text", "text": "It is 2."}]),
    ]
    config = ClaudeCodeConfig(state=str(tmp_path / "state"), env_file=str(env), cwd=str(tmp_path))
    claude = ClaudeCodeModel(config, lambda options: FakeClaudeCode(options, script))
    asked = [{"role": "user", "content": "what is 1+1"}]
    first = [dict(c) async for c in claude.complete([_SYSTEM, *asked], [_SPEC])]
    transcript = [*asked, _entry(first), {"role": "tool", "content": "2", "call_id": "t1"}]
    second = [dict(c) async for c in claude.complete([_SYSTEM, *transcript], [_SPEC])]
    await claude.close()
    transcript += [_entry(second), {"role": "user", "content": "and you, stub?"}]
    assert isinstance(transcript[1]["provider"]["content"], list)  # Claude's content blocks

    with StubServer() as stub:
        table = {"provider": "openai", "id": "stub-1", "base_url": stub.base_url}
        async with OpenAIModel(Named("stub", "openai", "stub-1", table, "/c/models.toml")) as model:
            said = [dict(c) async for c in model.complete([_SYSTEM, *transcript], [_SPEC])]
    assert "".join(c["text"] for c in said if c["type"] == "text").strip() == "[stub-1] heard: and you, stub?"
    (request,) = stub.requests
    assert request["body"]["messages"] == [
        _SYSTEM,
        {"role": "user", "content": "what is 1+1"},
        {
            "role": "assistant",
            "content": "Let me run it.",
            "tool_calls": [
                {
                    "id": "t1",
                    "type": "function",
                    "function": {"name": "python", "arguments": json.dumps({"code": "1+1"})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "2"},
        {"role": "assistant", "content": "It is 2."},
        {"role": "user", "content": "and you, stub?"},
    ]
