"""The `approval` value: the rule that decides what the model asked for runs unasked, the same
for every row that runs some.

The rule: a call runs without asking when it runs in the runner (`runs`, "jail" when the question
says nothing) and the runner confines it (`is_confined`: it enforces writes and the network);
otherwise (an unconfined runner, or a tool that runs in bh-02's own process, "host") it is put to
the person first. One kind of call is never put to the person: `runs` "memory", bh-02's own
memory tool, whatever the runner confines. It runs in bh-02's process, outside the jail, but it
writes only beneath `host.auto_memory`, through no link (`host_paths.write_beneath`), and the
jailed model can already write that directory without being asked, so asking would protect
nothing there; and a jailed program per save would be a whole process for a small file write. That
safety is the tool's and `host_paths`' to keep, not this rule's to check, so a tool takes the
value only in a layer's row, and every other "host" call is still asked.

Asking is not the rule's: the loop asks about each call, the extensions row about each extension
it loads, each through `output.confirm`, and the python tool reads `confined` to tell the model
whether its inputs are asked about. So one place decides.

It answers about code bh-02 is about to hand to the runner, not about each effect a component
yields: that seam is cordis's, and not built yet.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = ["Approval", "Graded", "is_confined"]

# The grades each axis a runner must hold for what runs in it to count as confined may have.
# `fs_write` may be best-effort, but only with bh-02's own `host_undo` axis at `tripwired`: brig
# grades it best-effort while the jail holds a path with a mount the host can undo, and bh-02's
# policy always holds some (the layer files, `.git/hooks`); what makes that count is that the
# runner armed a tripwire over every such mount, which ends the jail when the host undoes one
# (`runner_cordis_plugin.tripwire`). Brig does not grade that, so a report from a runner that
# did not say it (any other, or a start that armed none) is not confined on best-effort writes.
_CONFINING = {"fs_write": ("enforced", "best_effort"), "network": ("enforced",)}
_HOST_UNDO = "host_undo"  # the report's axis for it (`jail.HOST_UNDO`)
_TRIPWIRED = "tripwired"
_JAIL = "jail"  # where a call runs when its question says nothing (CONTRACTS.md: tools, `runs`)
# bh-02's own tool that reaches only the jail and bh-02's own state: asked exactly as the jail's are
_HARNESS = "harness"
# bh-02's own tool that writes only beneath host.auto_memory, through no link: never asked, jailed or not
_MEMORY = "memory"
_UNASKED_WHEN_CONFINED = (_JAIL, _HARNESS)
_UNASKED = (_MEMORY,)


@runtime_checkable
class Graded(Protocol):
    """What approval needs of the `runner` value (CONTRACTS.md: runner): its grade for each axis."""

    def report(self) -> Mapping[str, str]: ...


def is_confined(report: Mapping[str, str]) -> bool:
    """Whether a runner's report says what runs in it can write only where it was allowed
    (`fs_write` enforced, or best-effort with `host_undo` `tripwired`: the host undoing a mount
    ends the jail) and reach no network (`network` enforced)."""
    if report.get("fs_write") == "best_effort" and report.get(_HOST_UNDO) != _TRIPWIRED:
        return False
    return all(report.get(axis) in grades for axis, grades in _CONFINING.items())


@dataclass(frozen=True, slots=True)
class Approval:
    """Implements `approval` (CONTRACTS.md): `confined`, read from the runner each time, and
    `unasked(question)`."""

    runner: Graded

    @property
    def confined(self) -> bool:
        """Whether the runner confines what runs in it, so nothing that runs there is asked about."""
        return is_confined(self.runner.report())

    def unasked(self, question: Mapping[str, Any]) -> bool:
        """Whether what `question` asks for runs without asking the person: it is bh-02's own
        memory tool (`question["runs"]` `"memory"`, which writes only beneath `host.auto_memory`
        through no link, which the jailed model can already write), whatever the runner confines;
        or it runs in the runner (the runner when `runs` says nothing) or is bh-02's own tool
        bounded to the jail and bh-02's own state (`"harness"`), and the runner confines it.
        `"host"` is never."""
        runs = question.get("runs", _JAIL)
        return runs in _UNASKED or (runs in _UNASKED_WHEN_CONFINED and self.confined)
