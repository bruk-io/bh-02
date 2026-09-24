"""The probe vocabulary: `Verdict`, `BatteryVerdict`, `ProbeShape`,
`ProbeOutcome`, `ProbeReport`, and the `Battery` Protocol.

SPEC.md §12 defines probes and their three-way verdict; §13's layer table
puts the vocabulary in `core` because both `run` (SPEC.md §9:
`Handle.probe(battery) -> ProbeReport`) and the not-yet-built `probe` layer
need to name it, and neither may import the other -- `run` may not import
`probe`, and `probe` may not import `mech` (which is why `Battery.run`'s
`handle` parameter is typed `object` here rather than `run.Handle`: naming
`Handle` would require importing `run`, and this module is `core`). Same
shape already shipped for `Graded` (`brig/core/report.py`) and `Event`
(`brig/core/events.py`): pure data in `core`, built and consumed by higher
layers. This module ships vocabulary only -- no battery, no probe
definition, no argv. See `backlog/docs/doc-014 - M4-plan.md` ambiguity A2.

This module is pure: no I/O, no clock, no randomness, no subprocess.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from brig.core.grades import Axis


class Verdict(Enum):
    """A probe's three-way outcome (SPEC.md §12).

    Plain `Enum`, never `StrEnum` -- SPEC.md §4's posture, which this
    vocabulary inherits: lexical comparison against a bare string is a
    programmer error this type refuses to let compile silently.

    This is the PER-PROBE vocabulary -- a probe asserts a fact about ONE
    attempt, and `PASS` is honest at that altitude. It is untouched by the
    battery-level rename below (decision-104 clause 1): `BatteryVerdict` is
    its own, separate `Enum`, never an extension of this one and never a
    member added to it -- the two vocabularies answer different questions,
    and a single enum would let them be interchanged by accident.
    """

    PASS = "pass"
    FAIL = "fail"
    VACUOUS = "vacuous"


class BatteryVerdict(Enum):
    """A battery's own three-way verdict (SPEC.md §12, decision-104).

    A battery is a **consistency instrument**, not an enforcement oracle:
    its verdict says whether every probe outcome agrees with the report's
    grades, never whether enforcement was "proven". `PASS` is retired at
    this altitude on purpose -- a reader cannot help hearing *enforcement
    proven* in it, while a battery can agree perfectly with a report that
    claims nothing (a `FAIL` probe outcome against an honestly
    `unenforced` grade is exactly the report's own prediction, not a
    contradiction).

    - `CONSISTENT` -- every probe outcome agrees with the report's grades.
      Does NOT mean enforcement was proven.
    - `CONTRADICTED` -- at least one probe outcome contradicts a grade
      (SPEC.md §12: "a probe that contradicts a grade fails the battery
      loudly").
    - `VACUOUS` -- a positive control failed, or a non-control probe
      asserted nothing. Nothing was learned.

    This is its OWN type, never `Verdict` reused or extended -- see that
    class's own docstring.
    """

    CONSISTENT = "consistent"
    CONTRADICTED = "contradicted"
    VACUOUS = "vacuous"


class ProbeShape(Enum):
    """What a probe does, and therefore what evidence can earn `PASS`
    (SPEC.md §12, folded 2026-08-23 by decision-099 on `doc-014` ambiguity
    A1).

    - `DENIAL` -- attempt a violation. `PASS` requires a declared signature
      to match §6's normalized denial subject; a failure without one is
      `VACUOUS`; a success is `FAIL`.
    - `ABSENCE` -- perform a permitted observation and assert a
      policy-derived absence in its output. `PASS` requires the observation
      to exit cleanly *and* the asserted absence to hold; a non-zero exit
      is `VACUOUS`, never `PASS`. An `ABSENCE` `PASS` carries no matched
      signature, and that is correct rather than a missing field.
    - `CONTROL` -- the positive control. `PASS` iff it succeeded.

    Nothing reads this member yet (task-048 is the first reader); it ships
    here, as vocabulary, per this task's Out of scope.
    """

    DENIAL = "denial"
    ABSENCE = "absence"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    """One probe's result.

    `shape` records which of `ProbeShape`'s three kinds this outcome is
    for, because the invariant below reads differently per shape: a
    `DENIAL` `PASS` without a `matched_signature` is not just incomplete
    data, it is dishonest (SPEC.md §12: a `DENIAL` `PASS` "requires a
    declared signature to match"). An `ABSENCE` `PASS` carries no matched
    signature by design -- that shape's evidence is a clean exit plus an
    asserted absence, never a pattern match -- so the same emptiness that
    is a lie for `DENIAL` is simply correct for `ABSENCE`. Same posture as
    `Graded(BEST_EFFORT, "")` in `brig/core/report.py`: a construction-time
    invariant instead of a check some later aggregation might forget.

    Attributes:
        probe_name: This probe's identifier within its battery.
        axis: Which of the seven axes (`brig.core.grades.Axis`) this probe
            is about.
        shape: Which of `ProbeShape`'s three kinds this probe is.
        verdict: `PASS`, `FAIL`, or `VACUOUS`.
        subject: The normalized denial string this verdict was decided
            against (SPEC.md §6: stderr, then the canonical termination
            summary line) -- or, for a non-`DENIAL` shape, whatever the
            probe engine records as its evidence.
        matched_signature: The pattern source (a `str`, since a compiled
            `re.Pattern` is not JSON-serializable) that matched, or `None`
            when nothing matched or the shape carries no signature.
        detail: Free-form explanation.
    """

    probe_name: str
    axis: Axis
    shape: ProbeShape
    verdict: Verdict
    subject: str
    matched_signature: str | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if (
            self.shape is ProbeShape.DENIAL
            and self.verdict is Verdict.PASS
            and self.matched_signature is None
        ):
            raise ValueError(
                "ProbeOutcome: a DENIAL-shaped PASS requires a matched_signature "
                "(SPEC.md §12: PASS requires a declared signature to match the "
                "normalized denial subject)"
            )


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """A battery's full result. Accessors only -- it computes no policy;
    that is the not-yet-built `probe` layer's job (SPEC.md §13).

    Attributes:
        outcomes: Every probe's `ProbeOutcome`, in the order the battery
            ran them.
        battery_name: The battery's identifier.
        battery_verdict: The battery's own overall verdict (`BatteryVerdict`
            -- SPEC.md §12, decision-104: a consistency instrument, never
            `Verdict` reused).
        contradictions: Free-form descriptions of probe outcomes that
            contradict the stack's `EnforcementReport` grades (SPEC.md §12:
            "a probe that contradicts a grade fails the battery loudly").
    """

    outcomes: tuple[ProbeOutcome, ...]
    battery_name: str
    battery_verdict: BatteryVerdict
    contradictions: tuple[str, ...]

    @property
    def observed_by_axis(self) -> Mapping[Axis, tuple[Verdict, ...]]:
        """Per-axis view of the `Verdict`s this report's `outcomes`
        actually observed (decision-104 clause 2: "what actually resisted"
        as first-class data, not an inference from the summary word).

        A COMPUTED property, never a stored field -- so it cannot diverge
        from the evidence it summarises, and no constructor can leave it
        empty while `outcomes` is non-empty. Keys are exactly the axes
        named by `outcomes`; each value is that axis's observed `Verdict`s,
        in the order `outcomes` records them.
        """
        by_axis: dict[Axis, list[Verdict]] = {}
        for outcome in self.outcomes:
            by_axis.setdefault(outcome.axis, []).append(outcome.verdict)
        return {axis: tuple(verdicts) for axis, verdicts in by_axis.items()}


@runtime_checkable
class Battery(Protocol):
    """A canned set of probes against one `Handle` (SPEC.md §12).

    Lives here, in `core`, rather than in `run` alongside `Handle`, so that
    `Handle.probe(battery: Battery) -> ProbeReport` (SPEC.md §9) type-checks
    in `run` with no import from the not-yet-built `probe` layer -- `run`
    may not import `probe` (SPEC.md §13). `handle` is typed `object` for the
    same reason: naming the real `Handle` type here would require `core` to
    import `run`, which SPEC.md §13's layer table forbids (`core` may import
    nothing).
    """

    name: str

    def run(self, handle: object) -> ProbeReport:
        """Run this battery's probes against `handle` and return the result."""
        ...


__all__ = (
    "Battery",
    "BatteryVerdict",
    "ProbeOutcome",
    "ProbeReport",
    "ProbeShape",
    "Verdict",
)
