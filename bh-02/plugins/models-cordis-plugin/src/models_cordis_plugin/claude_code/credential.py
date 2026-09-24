"""The one credential, and the environment the Claude Code CLI is started with.

The token is a Claude Code OAuth token (`claude setup-token` makes one), kept as
`CLAUDE_CODE_OAUTH_TOKEN` in the git-ignored `local.env` at the repository root. bh-02 reads
that file itself (`parse_env`, pure, over one read) and hands the value to the CLI child alone,
through the SDK options' `env`: never into bh-02's own `os.environ`, so no other child (the
kernel, the jail) can inherit it.

The token is never held in a named local of a long-lived frame nor in anything whose repr
shows it: Textual prints a crash with every frame's locals, and `ChildEnv`'s repr names its keys
only. An error about the credential names the variable and the file, never a value.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from models_cordis_plugin.local_env import parse_env

__all__ = ["TOKEN_VARIABLE", "ChildEnv", "child_env"]

TOKEN_VARIABLE: Final = "CLAUDE_CODE_OAUTH_TOKEN"

# What the CLI is told besides the token (the spike's measurements; README.md):
_FIXED: Final[Mapping[str, str]] = {
    "ENABLE_CLAUDEAI_MCP_SERVERS": "0",  # the account's claude.ai connectors stay out
    "DISABLE_AUTO_COMPACT": "1",  # agent:loop owns the conversation; Claude Code never rewrites it
    "MAX_MCP_OUTPUT_TOKENS": "1000000",  # a large tool result reaches the model, not a file it can't read
    "MCP_TOOL_TIMEOUT": "86400000",  # a parked call waits as long as the person takes to approve it (ms)
    # a stream that fails mid-step is an error the step reads, never a non-streaming retry it can't see
    "CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK": "1",
}


class ChildEnv(dict[str, str]):
    """The CLI child's explicit environment: a dict whose repr names its keys, never a value."""

    def __repr__(self) -> str:
        return f"ChildEnv({sorted(self)!r})"

    __str__ = __repr__


def child_env(path: Path | None, config_dir: str) -> ChildEnv | None:
    """The CLI child's environment: the token from `path`, Claude Code's own state in
    `config_dir` (`CLAUDE_CONFIG_DIR`), and the fixed settings; None when there is no token."""
    if path is None or not path.is_file():
        return None
    env = ChildEnv(_FIXED)
    env["CLAUDE_CONFIG_DIR"] = config_dir
    env[TOKEN_VARIABLE] = parse_env(path.read_text(encoding="utf-8")).get(TOKEN_VARIABLE, "")
    return env if env[TOKEN_VARIABLE] else None
