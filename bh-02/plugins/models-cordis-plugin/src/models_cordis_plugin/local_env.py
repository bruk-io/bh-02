"""`local.env`: the git-ignored file of `KEY=value` lines at the repository root that holds
bh-02's credentials: the Claude Code token (`CLAUDE_CODE_OAUTH_TOKEN`) and any key an
OpenAI-compatible model names (`key = "OPENROUTER_API_KEY"`).

The providers read it themselves, one line at a time when a step needs it, and hand the value
only to what uses it (the Claude Code child's `env`, one HTTP request's `Authorization`
header): never into bh-02's own `os.environ`, so no other child (the kernel, the jail) can
inherit it. `parse_env` is pure; `token_file` only looks for the file.

Where the file is looked for is not this package's to decide: the shell names the places, nearest
first, as the `layers` value's `credentials` (CONTRACTS.md: layers), and names every one of them
to the jail as a secret too. So a place the model row searches is always one no jailed input may
read, write or create, whatever directory bh-02 runs in.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

__all__ = ["ENV_FILE", "Credentials", "parse_env", "token_file"]

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


@runtime_checkable
class Credentials(Protocol):
    """What the model rows need of the `layers` value (CONTRACTS.md: layers): where bh-02's
    `local.env` is looked for, nearest first."""

    @property
    def credentials(self) -> tuple[str, ...]: ...


def token_file(explicit: str | None, searched: Sequence[str]) -> Path | None:
    """The credential file to read: `explicit` (the row's `env_file`) when given, else the
    first of `searched` (the `layers` value's `credentials`) that is a regular file. Anything
    else there is passed over: on Linux the jail holds an absent one with an empty directory
    for as long as it runs, and that must never hide the real file further up."""
    if explicit is not None:
        return Path(explicit)
    return next((Path(path) for path in searched if Path(path).is_file()), None)
