"""Against the real Claude Code CLI on the subscription, Sonnet: one answer, then a tool round
trip whose result the model recalls, first from Claude Code's own session and then from one
rebuilt from the transcript alone. It spends subscription usage, so it runs only when asked
for (`-m e2e`), and is skipped without `CLAUDE_CODE_OAUTH_TOKEN` in `local.env` (read the way
the provider reads it; the token is never printed):

    uv run pytest bh-02/plugins/models-cordis-plugin -m e2e -q
"""

import secrets
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin.claude_code import ClaudeCodeConfig, ClaudeCodeModel, child_env
from models_cordis_plugin.local_env import token_file

pytestmark = pytest.mark.e2e

_SYSTEM = {
    "role": "system",
    "content": "You are a terse assistant in a test. Answer in as few words as you can.",
}
_SECRET = {
    "name": "secret",
    "description": "Return the secret value stored under a key.",
    "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
}


@pytest.fixture(autouse=True)
def _asked_for(request: pytest.FixtureRequest) -> None:
    if "e2e" not in str(request.config.getoption("markexpr") or ""):
        pytest.skip("runs against the real service only when asked for: -m e2e")
    if child_env(token_file(None), "") is None:
        pytest.skip("needs CLAUDE_CODE_OAUTH_TOKEN in local.env")


def _config(tmp_path: Path) -> ClaudeCodeConfig:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return ClaudeCodeConfig(model="sonnet", state=str(tmp_path / "claude"), cwd=str(work))


async def _step(
    model: ClaudeCodeModel,
    rest: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    return [dict(c) async for c in model.complete([_SYSTEM, *rest], list(tools))]


def _said(chunks: Sequence[Mapping[str, Any]]) -> str:
    return "".join(c["text"] for c in chunks if c["type"] == "text")


def _entry(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    calls = [
        {"id": c["id"], "name": c["name"], "input": c["input"]} for c in chunks if c["type"] == "tool_call"
    ]
    entry: dict[str, Any] = {"role": "assistant", "content": _said(chunks), "provider": chunks[-1]["message"]}
    return entry | ({"tool_calls": calls} if calls else {})


async def test_an_answer_streams_text_usage_and_the_api_s_stop_reason(tmp_path: Path) -> None:
    async with ClaudeCodeModel(_config(tmp_path)) as model:
        chunks = await _step(model, [{"role": "user", "content": "Say pong."}])
    assert "pong" in _said(chunks).lower()
    used = [c for c in chunks if c["type"] == "usage"]
    assert sum(u["input_tokens"] for u in used) > 0 and sum(u["output_tokens"] for u in used) > 0
    assert {"type": "stop", "reason": "end_turn"} in chunks and chunks[-1]["type"] == "message"


async def test_a_tool_round_trip_is_recalled_from_claude_code_s_session_and_from_a_rebuild(
    tmp_path: Path,
) -> None:
    value = secrets.token_hex(4)
    asked = [{"role": "user", "content": "Call the secret tool with key 'alpha', then tell me the value."}]
    async with ClaudeCodeModel(_config(tmp_path)) as model:
        first = await _step(model, asked, [_SECRET])
        (call,) = [c for c in first if c["type"] == "tool_call"]
        assert call["name"] == "secret" and call["input"] == {"key": "alpha"} and "error" not in call
        assert {"type": "stop", "reason": "tool_use"} in first
        rest = [*asked, _entry(first), {"role": "tool", "content": value, "call_id": call["id"]}]
        second = await _step(model, rest, [_SECRET])
        assert value in _said(second)
        rest = [*rest, _entry(second), {"role": "user", "content": "Repeat the secret value verbatim."}]
        third = await _step(model, rest, [_SECRET])
        assert value in _said(third)
    # a conversation this Claude Code never saw (its state gone): written from the transcript, resumed
    fresh = ClaudeCodeConfig(model="sonnet", state=str(tmp_path / "other"), cwd=str(tmp_path / "work"))
    recall = [*rest, _entry(third), {"role": "user", "content": "Once more: the secret value, verbatim."}]
    async with ClaudeCodeModel(fresh) as rebuilt:
        fourth = await _step(rebuilt, recall, [_SECRET])
    assert value in _said(fourth)
