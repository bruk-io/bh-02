"""`/grants`: the command that lists the grants (each on the line `Entry` is) and revokes one."""

from typing import Protocol, runtime_checkable

from runner_cordis_plugin import store
from runner_cordis_plugin.broker import Entry, Unknown
from runner_cordis_plugin.prompting import revoked as revoked_words

__all__ = ["Listing", "grants_command"]


@runtime_checkable
class Listing(Protocol):
    """What `/grants` needs of the `grants` value (CONTRACTS.md: grants)."""

    async def list(self) -> tuple[Entry, ...]: ...
    async def revoke(self, id: str) -> Entry: ...
    def problem(self) -> str: ...


async def grants_command(grants: Listing, args: str) -> str:
    """`/grants` lists each grant on a line of its own (`Entry`'s text); `/grants revoke ID` takes
    one back and says which. What can't be done is said in a line, never raised."""
    words = args.split()
    if not words:
        entries = await grants.list()
        lines = [*map(str, entries), *filter(None, [grants.problem()])]
        return "\n".join(lines) if lines else "nothing is granted"
    if words[0] != "revoke" or len(words) != 2:
        return "usage: /grants, or /grants revoke ID (the id is the first column of /grants)"
    try:
        revoked = await grants.revoke(words[1])
    except (Unknown, store.Refused) as error:
        return str(error)
    return " ".join(filter(None, [f"revoked: {revoked}", revoked_words(revoked.request.grant)]))
