"""The credential, and the environment the Claude Code CLI is started with.

On the subscription, the token is a Claude Code OAuth token (`claude setup-token` makes one), which
the endpoint's `key` says where to get (`env`, `cmd` or `op`: the provider resolves it when it
starts the CLI). bh-02 hands the value to the CLI child alone, through the SDK options' `env`
(`child_env`): it never writes it into its own `os.environ`, so no other child (the Python
process, the jail) gets it from bh-02.

Through a gateway (a claude-code endpoint with `base_url` and a `key` of `cmd` or `op`), bh-02 holds
no credential at all: the CLI is given a settings layer of its own (`gateway_settings`, the SDK's
`settings`, which is `--settings`) naming the gateway as `ANTHROPIC_BASE_URL` and the command (the
`cmd`, or `op read <reference>`) as its `apiKeyHelper`, which the CLI runs and runs again when the
key's `ttl_ms` is up. The
token's variable is set empty (`gateway_env`), so a token in bh-02's own environment never reaches
that CLI. The layer is all the CLI reads of settings: the person's own still are not.

The token is never held in a named local of a long-lived frame nor in anything whose repr
shows it: Textual prints a crash with every frame's locals, and `ChildEnv`'s repr names its keys
only. An error about the credential names the variable or the command, never a value.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from models_cordis_plugin.key import TOKEN_VARIABLE

__all__ = ["TOKEN_VARIABLE", "ChildEnv", "Gateway", "child_env", "gateway_env", "gateway_settings"]


# What the CLI is told besides the token (the spike's measurements; README.md):
_FIXED: Final[Mapping[str, str]] = {
    "ENABLE_CLAUDEAI_MCP_SERVERS": "0",  # the account's claude.ai connectors stay out
    "DISABLE_AUTO_COMPACT": "1",  # agent:loop owns the conversation; Claude Code never rewrites it
    "MAX_MCP_OUTPUT_TOKENS": "1000000",  # a large tool result reaches the model, not a file it can't read
    "MCP_TOOL_TIMEOUT": "86400000",  # a parked call waits as long as the person takes to approve it (ms)
    # a stream that fails mid-step is an error the step reads, never a non-streaming retry it can't see
    "CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK": "1",
}


@dataclass(frozen=True, slots=True)
class Gateway:
    """Where the CLI sends its requests instead of Anthropic (`base_url`, an Anthropic-compatible
    API), the command that prints its key (`command`: the `key`'s `cmd`, or `op read <reference>`;
    Claude Code's `apiKeyHelper`), how long a key is used (`ttl_ms`; Claude Code's own default,
    300000, when None), and whether the CLI may send
    Anthropic's experimental beta headers (`experimental_betas`: false for a gateway that refuses
    them)."""

    base_url: str
    command: str
    ttl_ms: int | None = None
    experimental_betas: bool = True


def gateway_settings(gateway: Gateway) -> str:
    """The settings layer, as JSON, that sends the CLI's requests through `gateway`."""
    env = {"ANTHROPIC_BASE_URL": gateway.base_url}
    if gateway.ttl_ms is not None:
        env["CLAUDE_CODE_API_KEY_HELPER_TTL_MS"] = str(gateway.ttl_ms)
    if not gateway.experimental_betas:
        env["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] = "1"
    return json.dumps({"apiKeyHelper": gateway.command, "env": env})


def gateway_env(config_dir: str) -> ChildEnv:
    """The CLI child's environment through a gateway: Claude Code's own state in `config_dir`, the
    fixed settings, and the token's variable empty (the gateway's key comes from its helper)."""
    env = ChildEnv(_FIXED)
    env["CLAUDE_CONFIG_DIR"] = config_dir
    env[TOKEN_VARIABLE] = ""
    return env


class ChildEnv(dict[str, str]):
    """The CLI child's explicit environment: a dict whose repr names its keys, never a value."""

    def __repr__(self) -> str:
        return f"ChildEnv({sorted(self)!r})"

    __str__ = __repr__


def child_env(token: str, config_dir: str) -> ChildEnv:
    """The CLI child's environment: `token`, Claude Code's own state in `config_dir`
    (`CLAUDE_CONFIG_DIR`), and the fixed settings."""
    env = ChildEnv(_FIXED)
    env["CLAUDE_CONFIG_DIR"] = config_dir
    env[TOKEN_VARIABLE] = token
    return env
