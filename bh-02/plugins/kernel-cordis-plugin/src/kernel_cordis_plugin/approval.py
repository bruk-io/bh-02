"""The `approval` value: whether code the model wrote may run, decided by one rule for every row
that runs some.

The rule: code runs without asking when the jail confines it (`is_confined`: the jail enforces
writes and the network); otherwise it is put to the person first (`output.confirm`) and runs
only on a yes, a no when there is nobody to ask. The loop asks about each input, the extensions
row about each extension it loads. The kernel reads `is_confined` itself, to tell the model
whether its inputs are asked about.

It answers about code bh-02 is about to hand to the jail, not about each effect a component
yields: that seam is cordis's, and not built yet.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = ["Approval", "Asks", "Graded", "is_confined"]

_CONFINING = ("fs_write", "network")  # the axes a jail must enforce for what runs in it to count as confined


@runtime_checkable
class Graded(Protocol):
    """What approval needs of the `jail` value (CONTRACTS.md: jail): its grade for each axis."""

    def report(self) -> Mapping[str, str]: ...


@runtime_checkable
class Asks(Protocol):
    """What approval needs of the `output` value: the person's yes or no about some code."""

    async def confirm(self, request: Mapping[str, Any]) -> bool: ...


def is_confined(report: Mapping[str, str]) -> bool:
    """Whether a jail's report says what runs in it can write only where it was allowed and
    reach no network."""
    return all(report.get(axis) == "enforced" for axis in _CONFINING)


@dataclass(frozen=True, slots=True)
class Approval:
    """Implements `approval` (CONTRACTS.md): `confined`, read from the jail each time, and
    `approve(request)`. With no `output` there is nobody to ask, so unconfined code never runs."""

    jail: Graded
    output: Asks | None = None

    @property
    def confined(self) -> bool:
        """Whether the jail confines what runs in it, so nothing is asked."""
        return is_confined(self.jail.report())

    async def approve(self, request: Mapping[str, Any]) -> bool:
        """Whether the code `request` carries may run: yes at once when the jail confines it;
        otherwise the person's answer (`output.confirm(request)`), or no with nobody to ask."""
        if self.confined:
            return True
        return self.output is not None and await self.output.confirm(request)
