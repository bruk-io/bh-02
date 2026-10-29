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

An API key endpoint (`auth = "api-key"`) that names a `base_url` gets the same kind of layer with
the URL alone (`api_settings`): bh-02 reads the key and hands it to the CLI's environment as
`ANTHROPIC_API_KEY` (`child_env`), and the CLI sends it there.

The token is never held in a named local of a long-lived frame nor in anything whose repr
shows it: Textual prints a crash with every frame's locals, and `ChildEnv`'s repr names its keys
only. An error about the credential names the variable or the command, never a value.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from models_cordis_plugin.key import API_KEY_VARIABLE, TOKEN_VARIABLE

__all__ = [
    "API_KEY_VARIABLE",
    "TOKEN_VARIABLE",
    "ChildEnv",
    "Gateway",
    "api_settings",
    "child_env",
    "gateway_env",
    "gateway_settings",
]


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
    env = _routed(gateway.base_url, gateway.experimental_betas)
    if gateway.ttl_ms is not None:
        env["CLAUDE_CODE_API_KEY_HELPER_TTL_MS"] = str(gateway.ttl_ms)
    return json.dumps({"apiKeyHelper": gateway.command, "env": env})


def api_settings(base_url: str, *, experimental_betas: bool = True) -> str:
    """The settings layer, as JSON, that sends the CLI's requests to `base_url` (an API key
    endpoint's: Anthropic's API, or one compatible with it) with the key in its environment."""
    return json.dumps({"env": _routed(base_url, experimental_betas)})


def _routed(base_url: str, experimental_betas: bool) -> dict[str, str]:
    """A settings layer's `env` naming where the CLI sends its requests, and whether it may send
    Anthropic's experimental beta headers."""
    env = {"ANTHROPIC_BASE_URL": base_url}
    if not experimental_betas:
        env["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] = "1"
    return env


def gateway_env(config_dir: str) -> ChildEnv:
    """The CLI child's environment through a gateway: Claude Code's own state in `config_dir`, the
    fixed settings, and both credential variables empty (the gateway's key comes from its helper)."""
    env = ChildEnv(_FIXED)
    env["CLAUDE_CONFIG_DIR"] = config_dir
    env[TOKEN_VARIABLE] = ""
    env[API_KEY_VARIABLE] = ""
    return env


class ChildEnv(dict[str, str]):
    """The CLI child's explicit environment: a dict whose repr names its keys, never a value."""

    def __repr__(self) -> str:
        return f"ChildEnv({sorted(self)!r})"

    __str__ = __repr__


def child_env(secret: str, config_dir: str, *, api_key: bool = False) -> ChildEnv:
    """The CLI child's environment: `secret`, Claude Code's own state in `config_dir`
    (`CLAUDE_CONFIG_DIR`), and the fixed settings. `secret` is the subscription token, or with
    `api_key` an Anthropic API key. Both credential variables are always set and the one not chosen
    is empty, so only the chosen credential can be used: the SDK merges bh-02's own environment
    under this one, and an empty value here is what overrides a variable a shell exported."""
    env = ChildEnv(_FIXED)
    env["CLAUDE_CONFIG_DIR"] = config_dir
    env[TOKEN_VARIABLE] = "" if api_key else secret
    env[API_KEY_VARIABLE] = secret if api_key else ""
    return env
