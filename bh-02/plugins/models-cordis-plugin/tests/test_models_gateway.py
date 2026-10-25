"""Claude Code through a gateway: the settings layer that sends the CLI's requests there with its
key from a command (`key = { cmd }` or `{ op }`), the environment with no token in it, the provider
starting the CLI with both over a fake session, and what a refused key says. No process, no network,
no credential."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from models_cordis_plugin.claude_code import (
    TOKEN_VARIABLE,
    ClaudeCodeConfig,
    ClaudeCodeModel,
    Gateway,
    failure_of,
    gateway_env,
    gateway_settings,
    scrubbed,
)
from models_cordis_plugin.claude_code.testing import FakeClaudeCode, FakeStep

_GATEWAY = Gateway("https://gateway.example/anthropic", "print-a-token", 60_000, experimental_betas=False)


def test_the_settings_layer_names_the_gateway_its_helper_and_what_the_table_says() -> None:
    assert json.loads(gateway_settings(_GATEWAY)) == {
        "apiKeyHelper": "print-a-token",
        "env": {
            "ANTHROPIC_BASE_URL": "https://gateway.example/anthropic",
            "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "60000",
            "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
        },
    }
    plain = json.loads(gateway_settings(Gateway("https://g/anthropic", "c")))
    assert plain["env"] == {"ANTHROPIC_BASE_URL": "https://g/anthropic"}  # Claude Code's own ttl and betas


def test_the_environment_through_a_gateway_holds_no_token_even_one_bh_02_was_started_with() -> None:
    env = gateway_env("/state/config")
    assert env[TOKEN_VARIABLE] == "" and env["CLAUDE_CONFIG_DIR"] == "/state/config"
    assert env["DISABLE_AUTO_COMPACT"] == "1" and not any(key.startswith("ANTHROPIC_") for key in env)
    # the SDK merges bh-02's environment under the options' env, then the launcher scrubs it
    child = scrubbed({TOKEN_VARIABLE: "sentinel-not-a-real-token", "ANTHROPIC_BASE_URL": "x", **env})
    assert child[TOKEN_VARIABLE] == "" and "ANTHROPIC_BASE_URL" not in child


def _said(chunks: Sequence[Mapping[str, Any]]) -> str:
    return "".join(c["text"] for c in chunks if c["type"] == "text")


async def test_the_provider_starts_claude_code_with_the_layer_and_needs_no_local_env(tmp_path: Path) -> None:
    config = ClaudeCodeConfig(
        model="claude-opus-5-5",
        state=str(tmp_path / "state"),
        env_file=str(tmp_path / "absent.env"),  # no credential file: a gateway needs none
        cwd=str(tmp_path),
        gateway=_GATEWAY,
    )
    opened: list[FakeClaudeCode] = []

    def open_(options: Any) -> FakeClaudeCode:
        opened.append(FakeClaudeCode(options, [FakeStep([{"type": "text", "text": "Hello"}])]))
        return opened[-1]

    model = ClaudeCodeModel(config, open_)
    said = [dict(c) async for c in model.complete([{"role": "user", "content": "hi"}], [])]
    assert _said(said) == "Hello"
    (fake,) = opened
    assert fake.options.settings == gateway_settings(_GATEWAY)
    assert fake.options.setting_sources == []  # still none of the person's own settings
    assert fake.options.env[TOKEN_VARIABLE] == "" and fake.options.model == "claude-opus-5-5"


def test_a_refused_key_through_a_gateway_names_its_command_not_the_subscription_token() -> None:
    error = failure_of("authentication_failed", "Invalid API key", _GATEWAY)
    assert error.kind == "authentication_failed"
    assert "https://gateway.example/anthropic refused the key its `key` command printed" in error.message
    assert "`print-a-token`" in error.message and "setup-token" not in error.message
