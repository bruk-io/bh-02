"""The `approval` value: the rule that decides what the model asked for runs unasked, the same
for every row that runs some.

The rule: a call runs without asking when it runs in the runner (`runs`, "jail" when the request
says nothing) and the runner confines it (`is_confined`: it enforces writes and the network);
otherwise (an unconfined runner, or a tool that runs in bh-02's own process, "host") it is put to
the person first. Asking is not the rule's: the loop asks about each call, the extensions row
about each extension it loads, each through `output.confirm`, and the python tool reads
`confined` to tell the model whether its inputs are asked about. So one place decides.

It answers about code bh-02 is about to hand to the runner, not about each effect a component
yields: that seam is cordis's, and not built yet.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = ["Approval", "Graded", "is_confined"]

_CONFINING = (
    "fs_write",
    "network",
)  # the axes a runner must enforce for what runs in it to count as confined
_JAIL = "jail"  # where a call runs when its request says nothing (CONTRACTS.md: tools, `runs`)


@runtime_checkable
class Graded(Protocol):
    """What approval needs of the `runner` value (CONTRACTS.md: runner): its grade for each axis."""

    def report(self) -> Mapping[str, str]: ...


def is_confined(report: Mapping[str, str]) -> bool:
    """Whether a runner's report says what runs in it can write only where it was allowed and
    reach no network."""
    return all(report.get(axis) == "enforced" for axis in _CONFINING)


@dataclass(frozen=True, slots=True)
class Approval:
    """Implements `approval` (CONTRACTS.md): `confined`, read from the runner each time, and
    `unasked(request)`."""

    runner: Graded

    @property
    def confined(self) -> bool:
        """Whether the runner confines what runs in it, so nothing that runs there is asked about."""
        return is_confined(self.runner.report())

    def unasked(self, request: Mapping[str, Any]) -> bool:
        """Whether what `request` asks for runs without asking the person: it runs in the runner
        (`request["runs"]`, the runner when it says nothing) and the runner confines it."""
        return request.get("runs", _JAIL) == _JAIL and self.confined
