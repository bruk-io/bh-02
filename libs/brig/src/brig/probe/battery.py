"""`Probe`, `Expectation`, and `Battery`: the canned violation-attempt
vocabulary a battery is built from (SPEC.md §12).

SPEC.md §12, verbatim:

    Every battery includes **positive controls** (an action that must succeed
    -- write inside the workspace, dial the declared channel) so a broken
    probe mechanism cannot impersonate a perfect jail.

SPEC.md §2 law 10, verbatim:

    **Prove gates by planting violations.** A probe or test that observes a
    clean run proves nothing. Every enforcement claim has a probe that
    attempts the violation and a positive control that proves the probe
    mechanism itself works.

`doc-013` §10 ask 1 (decision-097), verbatim:

    *"Every denial ships a control"* should stop being a convention an
    orchestrator enforces and become something the engine **structurally
    cannot omit** -- a battery whose control is missing should not construct.

`Battery.__post_init__` below is ask 1 made structural: a `Battery` whose
`probes` carry no `ProbeShape.CONTROL`-shaped probe raises `ValueError` at
construction, naming the battery and its axis, rather than shipping a
battery an orchestrator has to remember to police.

This module is pure: no I/O, no clock, no randomness, no subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass

from brig.core.grades import Axis
from brig.core.probes import ProbeReport, ProbeShape


@dataclass(frozen=True, slots=True)
class Expectation:
    """The pure predicate data a probe's shape needs to be classified
    (SPEC.md §12): for `ABSENCE`/`CONTROL`, the token that must be absent
    from, or present in, the observation's stdout. `DENIAL` carries none --
    its evidence is a denial-signature match against the normalized denial
    subject (SPEC.md §6), never a stdout token.

    Attributes:
        token: The stdout substring `classify` checks for. `None` for a
            `DENIAL` probe; for `ABSENCE` the token that must be absent, for
            `CONTROL` the token that must be present.
    """

    token: str | None = None


@dataclass(frozen=True, slots=True)
class Probe:
    """One canned probe within a `Battery` (SPEC.md §12).

    Attributes:
        name: This probe's identifier within its battery.
        shape: `DENIAL`, `ABSENCE`, or `CONTROL` -- what the probe does, and
            therefore what evidence can earn `PASS` (`brig.core.probes`).
        axis: Which of the seven axes (`brig.core.grades.Axis`) this probe
            is about. Must equal its battery's `axis` -- `Battery` refuses
            construction otherwise.
        argv: The command this probe runs inside the jail.
        expect: The predicate data `classify` needs for this probe's shape.
    """

    name: str
    shape: ProbeShape
    axis: Axis
    argv: tuple[str, ...]
    expect: Expectation


@dataclass(frozen=True, slots=True)
class Battery:
    """A canned set of probes against one axis (SPEC.md §12).

    Construction refuses, with a named `ValueError`, when:

    - `probes` is empty.
    - Two probes share a `name`.
    - Any probe's `axis` differs from the battery's own `axis`.
    - No probe in `probes` has `shape is ProbeShape.CONTROL` -- ask 1, made
      structural (decision-097): the positive control SPEC.md §12 requires
      is not a convention a later reader can forget, it is a condition this
      type will not construct without.

    `run` (task-050) delegates to `brig.probe.runner.run_battery`, imported
    LOCALLY inside the method rather than at module level -- `runner.py`
    imports `Battery` and `Probe` from THIS module to type its own
    signature, so a module-level import in the other direction would close
    a `battery.py <-> runner.py` cycle pypeeker's `no-import-cycles` rule
    catches (only a function-local import is exempt -- same idiom
    `brig/run/exec_.py`'s own docstring documents for the identical
    shape of tension). This is what makes `Battery` satisfy
    `core.probes.Battery`'s `Protocol`.
    """

    name: str
    axis: Axis
    probes: tuple[Probe, ...]

    def __post_init__(self) -> None:
        if len(self.probes) == 0:
            raise ValueError(
                f"Battery {self.name!r} (axis {self.axis.value!r}): probes must not be empty"
            )

        seen_names: dict[str, None] = {}
        for probe in self.probes:
            if probe.name in seen_names:
                raise ValueError(
                    f"Battery {self.name!r} (axis {self.axis.value!r}): duplicate "
                    f"probe name {probe.name!r}"
                )
            seen_names[probe.name] = None

            if probe.axis is not self.axis:
                raise ValueError(
                    f"Battery {self.name!r} (axis {self.axis.value!r}): probe "
                    f"{probe.name!r} claims axis {probe.axis.value!r}, not the "
                    "battery's own axis"
                )

        if not any(probe.shape is ProbeShape.CONTROL for probe in self.probes):
            raise ValueError(
                f"Battery {self.name!r} (axis {self.axis.value!r}): no positive "
                "control (SPEC.md §12: every battery includes a CONTROL-shaped "
                "probe so a broken probe mechanism cannot impersonate a perfect "
                "jail)"
            )

    def run(self, handle: object) -> ProbeReport:
        """Run this battery's probes against `handle` (SPEC.md §12) --
        `handle` stays `object`-typed here, matching
        `core.probes.Battery`'s `Protocol` shape exactly, which is why
        `brig.probe.runner.run_battery` accepts the same `object` (widened
        to `Any` there for the reason its own docstring gives) rather than
        `brig.run.handle.Handle`: narrowing it here would only move the
        mismatch onto this call instead of resolving it.

        Delegates to `brig.probe.runner.run_battery`, imported locally --
        see this class's own docstring for why."""
        from brig.probe.runner import run_battery

        return run_battery(handle, self)


__all__ = (
    "Battery",
    "Expectation",
    "Probe",
)
