"""`claude-code-detached`: run Claude Code's CLI in a session of its own, on the subscription only.

A terminal's Ctrl-C signals its whole foreground process group, and the SDK starts the CLI in
bh-02's. The CLI exits on SIGINT, which would end the Claude Code session whenever the person
meant only to stop one reply. bh-02 points the SDK's `cli_path` here: this process leaves the
group (`setsid`) and becomes the CLI (`execve`, same pid), so Ctrl-C reaches bh-02 alone, and
bh-02 stops a step with the SDK's own `interrupt()`.

The SDK always merges bh-02's environment into the child's; its options can override a key but
not remove one. So this is also where the variables that would take the CLI off the
subscription are dropped: every `ANTHROPIC_*` (an API key, a base URL) and every `CLAUDE_*`
(`CLAUDE_CODE_USE_BEDROCK`, `_VERTEX`, `_FOUNDRY`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, ...) but the
few the SDK and bh-02's options set, so a shell's settings can't route, bill or limit the
session, whose one credential is the `CLAUDE_CODE_OAUTH_TOKEN` the options pass. The rest
(PATH, HOME, locale, proxies) passes through.
"""

import importlib.util
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from sys import argv
from typing import Final

from models_cordis_plugin.claude_code.credential import TOKEN_VARIABLE

__all__ = ["main", "scrubbed"]

_DROPPED: Final = ("ANTHROPIC_", "CLAUDE_")
# The `CLAUDE_*` the child is started with on purpose: the options' credential and state
# directory (credential.py), and what the SDK itself sets (its entry point, its version).
_KEPT: Final = frozenset(
    {TOKEN_VARIABLE, "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION"}
)


def scrubbed(environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` without any `ANTHROPIC_*` or `CLAUDE_*` variable but the ones kept on purpose."""
    return {k: v for k, v in environ.items() if k in _KEPT or not k.startswith(_DROPPED)}


def _real_cli() -> str:
    """The CLI the SDK would have run: its bundled binary, else `claude` on PATH."""
    spec = importlib.util.find_spec("claude_agent_sdk")
    if spec is not None and spec.origin is not None:
        bundled = Path(spec.origin).parent / "_bundled" / "claude"
        if bundled.is_file():
            return str(bundled)
    found = shutil.which("claude")
    if found is None:
        raise SystemExit(
            "claude-code-detached: no Claude Code CLI (neither the SDK's bundled one nor `claude` on PATH); "
            "run `uv sync --all-packages`"
        )
    return found


def main() -> None:
    """Leave the terminal's process group, then become the CLI with the same arguments."""
    os.setsid()
    cli = _real_cli()
    os.execve(cli, [cli, *argv[1:]], scrubbed(os.environ))
