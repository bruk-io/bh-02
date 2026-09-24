"""`local.env`: the git-ignored file of `KEY=value` lines at the repository root that holds
bh-02's credentials: the Claude Code token (`CLAUDE_CODE_OAUTH_TOKEN`) and any key an
OpenAI-compatible model names (`key = "OPENROUTER_API_KEY"`).

The providers read it themselves, one line at a time when a step needs it, and hand the value
only to what uses it (the Claude Code child's `env`, one HTTP request's `Authorization`
header): never into bh-02's own `os.environ`, so no other child (the kernel, the jail) can
inherit it. `parse_env` is pure; `token_file` only looks for the file.
"""

from collections.abc import Iterable
from pathlib import Path
from sys import prefix
from typing import Final

__all__ = ["ENV_FILE", "candidates", "parse_env", "token_file"]

ENV_FILE: Final = "local.env"


def parse_env(text: str) -> dict[str, str]:
    """`KEY=value` lines as a dict: blank lines and `#` comments skipped, an `export ` prefix and
    one pair of matching quotes around the value removed; a line with no `=` is ignored."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def candidates(anchors: Iterable[Path]) -> tuple[Path, ...]:
    """Where `local.env` may be: in every directory above each anchor, nearest first, so from
    any working directory the workspace's own is found (the same places `layers.secrets` names)."""
    found = (parent / ENV_FILE for anchor in anchors for parent in anchor.resolve().parents)
    return tuple(dict.fromkeys(found))


def token_file(explicit: str | None) -> Path | None:
    """The credential file to read: `explicit` (the row's `env_file`) when given, else the
    first `local.env` above this package or bh-02's environment that exists."""
    if explicit is not None:
        return Path(explicit)
    return next((path for path in candidates([Path(__file__), Path(prefix)]) if path.is_file()), None)
