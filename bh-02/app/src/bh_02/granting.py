"""`bh-02 grants`: what the project's grants are, and taking one back, outside a session.

The grants are the runner plugin's (decision-0012), and the app imports no plugin
(`plugin-layering`): it boots a composition of two rows, the shell's `host` row (naming the
project's grants store) and the plugin's `grants` row, by name, and talks to the broker the row
binds through `Grants`, a Protocol of its own. Nothing else of the harness starts: no ui, no jail.
The store is the broker's to read and write, so a revoke here is gone at the next start of a
session, which reads it fresh.
"""

import contextlib
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from cordis import Row, boot

__all__ = ["Unreadable", "listed", "revoked"]

#: The rows of the composition: the host row `run()` pins (`bh_02.bootstrap:host`) and the broker's.
_HOST = "bh_02.bootstrap:host"
_GRANTS = "runner:grants"


@runtime_checkable
class _Grants(Protocol):
    """What this command needs of the `grants` value (CONTRACTS.md: grants): each grant as a
    line of text (`list`, one per grant, the project's first), `revoke(id)` (the line of what was
    revoked; raises a `LookupError` for an id no grant has, or a `ValueError` for a store that
    can't be used, each saying what to do) and `problem()` (the words of a store it could not
    read, or '')."""

    async def list(self) -> Sequence[object]: ...
    async def revoke(self, id: str) -> object: ...
    def problem(self) -> str: ...


class Unreadable(Exception):
    """The grants could not be asked of the composition: the message says what to do."""


@contextlib.asynccontextmanager
async def _broker(directory: Path) -> AsyncIterator[_Grants]:
    """The `grants` value of a composition of the host row and the grants row alone, for the
    body; the rows are unwound after.

    Raises:
        Unreadable: the runner plugin is not installed, or its row did not come up.
    """
    booted = await boot(
        [],
        overrides=[Row("host", _HOST, config={"grants": str(directory)}), Row("grants", _GRANTS)],
        watch=None,
    )
    try:
        broker = booted.runtime.root.get("grants")
        if not isinstance(broker, _Grants):
            status = booted.loader.status() if booted.loader is not None else {}
            raise Unreadable(
                f"the grants row did not come up ({status.get('grants', 'not mounted')}): "
                "the runner plugin must be installed, since it keeps the grants"
            )
        yield broker
    finally:
        await booted.runtime.shutdown()


async def listed(directory: Path) -> list[str]:
    """The project's grants in `directory`, one line each, then the words of a store that can't be
    read; none when there is none yet.

    Raises:
        Unreadable: the broker did not come up.
    """
    if not directory.is_dir():
        return []
    async with _broker(directory) as grants:
        lines = [str(entry) for entry in await grants.list()]
        return [*lines, *filter(None, [grants.problem()])]


async def revoked(directory: Path, id: str) -> str:
    """Take back the grant `id` names (its first column in `listed`) and say what was revoked.

    Raises:
        Unreadable: the broker did not come up, or the project has no grants.
        LookupError: no grant has that id (the message lists the ids there are).
        ValueError: the store can't be used (the message says what to fix).
    """
    if not directory.is_dir():
        raise Unreadable("the project has no grants yet, so there is nothing to revoke")
    async with _broker(directory) as grants:
        return str(await grants.revoke(id))
