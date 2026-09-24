"""`limits_battery`: a probe battery for the limits axis, cpu only
(SPEC.md §6, §12).

`rlimits` (SPEC.md §6) declares one denial signature, `signal:SIGXCPU`,
matched against §6's normalized denial subject -- stderr followed by the
canonical termination line, never raw stdout (`brig/mech/rlimits.py`'s own
docstring). This battery's spin-loop probe is `ProbeShape.DENIAL`: a `PASS`
here is attributable to `rlimits`' OWN declared signature actually matching
the workload's own observed termination, never to the mere fact that the
attempt failed (SPEC.md §12: "A vacuous probe is a warning, never a pass").

`memory`/`tasks`/`wall`/`output` are the four `limits` axis fields
`rlimits` does not reach (its own `_BEST_EFFORT_DETAIL`) -- this battery
probes cpu only, the one field a mechanism actually claims, same posture as
`fs.py`/`network.py` probing exactly what their mechanisms claim and no
more.

This module is pure: no I/O, no clock, no randomness, and it spawns
nothing of its own -- it only returns data describing argv for a caller to
run.
"""

from __future__ import annotations

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import Spec
from brig.probe.battery import Battery, Expectation, Probe


def limits_battery(spec: Spec) -> Battery:
    """A battery for the limits axis (cpu only).

    Probes:
    - short_command_completes (CONTROL): must succeed -- a command that
      finishes almost instantly must not be caught by the cpu limit.
    - cpu_spin_is_killed (DENIAL): a busy-spin shell loop must be killed by
      `rlimits`' own `SIGXCPU` signature.

    Args:
        spec: A Spec whose `limits.cpu_seconds` is a positive int. Raises
            ValueError, naming `cpu_seconds`, when it is `0` (SPEC.md §5:
            "0 = uncapped") -- an uncapped limit has nothing to prove and
            no denial to expect.

    Returns:
        A Battery on Axis.LIMITS with two probes.
    """
    if spec.limits.cpu_seconds == 0:
        raise ValueError(
            "limits_battery (axis limits): Limits.cpu_seconds is 0 (uncapped, "
            "SPEC.md §5), nothing to prove -- no cpu denial to expect"
        )

    probes = (
        Probe(
            name="short_command_completes",
            shape=ProbeShape.CONTROL,
            axis=Axis.LIMITS,
            argv=("/bin/sh", "-c", "printf brig-ok"),
            expect=Expectation(token="brig-ok"),
        ),
        Probe(
            name="cpu_spin_is_killed",
            shape=ProbeShape.DENIAL,
            axis=Axis.LIMITS,
            argv=("/bin/sh", "-c", "while :; do :; done"),
            expect=Expectation(),
        ),
    )

    return Battery(name="limits", axis=Axis.LIMITS, probes=probes)


__all__ = ("limits_battery",)
