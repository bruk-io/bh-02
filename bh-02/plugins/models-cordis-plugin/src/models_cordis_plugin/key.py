"""A model's `key` as the models file says it: where its key comes from (`KeySpec`), and the name of
the variable the Claude Code CLI reads its subscription token from. A leaf module: the providers
and the models file both name them."""

import shlex
from dataclasses import dataclass
from typing import Final

__all__ = ["API_KEY_VARIABLE", "TOKEN_VARIABLE", "KeySpec"]

TOKEN_VARIABLE: Final = "CLAUDE_CODE_OAUTH_TOKEN"
# What the CLI reads an Anthropic API key from. bh-02 sets it in the CLI child's environment alone,
# and always (empty on the subscription), so one exported in a shell never reaches the CLI.
API_KEY_VARIABLE: Final = "ANTHROPIC_API_KEY"


@dataclass(frozen=True, slots=True)
class KeySpec:
    """Where an endpoint's key comes from, as its `key` table says (`key_spec`): `source` is `env`
    (`value` names a variable of bh-02's process environment), `cmd` (`value` is a shell command that
    prints the key) or `op` (`value` is a 1Password reference, read by `op read`), and `ttl_ms` is how
    long a printed key is used (None when unset; only `cmd` and `op` take one). The key itself is
    never in it."""

    source: str
    value: str
    ttl_ms: int | None = None

    @property
    def command(self) -> str | None:
        """The shell command that prints the key: the `cmd` as written, `op read <reference>` for an
        `op` (the reference quoted, as it reaches a shell); None for an `env`, which prints nothing."""
        if self.source == "cmd":
            return self.value
        if self.source == "op":
            return f"op read {shlex.quote(self.value)}"
        return None

    @property
    def label(self) -> str:
        """What names this source in a cache (`openai.ListingKey`): never the key."""
        return f"{self.source}:{self.value}"
