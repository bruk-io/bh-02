"""Tests for brig.core.probes: Verdict, ProbeShape, ProbeOutcome, ProbeReport,
Battery.

SPEC.md §12 (the three-way verdict, the three probe shapes), §4 (plain Enum,
never StrEnum -- Verdict inherits that posture), §13 (the vocabulary lives in
core so run can name ProbeReport and probe can read it without a run<->probe
import cycle).
"""

import pytest

from brig.core.grades import Axis
from brig.core.probes import BatteryVerdict, ProbeOutcome, ProbeReport, ProbeShape, Verdict


@pytest.mark.unit
def test_verdict_is_a_plain_enum_not_a_str_enum() -> None:
    """AC #6: Verdict inherits SPEC.md §4's Enum posture (applied here to
    the probe vocabulary): comparing a Verdict member to a bare string is
    False, never accidentally True through str-mixin equality."""
    assert not issubclass(Verdict, str)
    not_a_verdict: object = "PASS"
    assert not_a_verdict != Verdict.PASS


@pytest.mark.unit
def test_a_denial_pass_without_a_matched_signature_does_not_construct() -> None:
    """AC #7: a DENIAL-shaped PASS with matched_signature=None is a lie --
    SPEC.md §12 says PASS "requires a declared signature to match" -- and
    ProbeOutcome refuses to construct it, the same posture Graded(BEST_EFFORT,
    "") takes in report.py.

    Two controls in the same test:
    - the SAME outcome WITH a matched_signature constructs fine, proving the
      refusal is about the missing signature and not, say, the PASS verdict
      or the DENIAL shape in isolation.
    - an ABSENCE PASS with matched_signature=None constructs fine, proving
      the refusal is specific to DENIAL (SPEC.md §12: "An ABSENCE PASS
      carries no matched signature, and that is its correct shape rather
      than a missing field").
    """
    with pytest.raises(ValueError, match="matched_signature"):
        ProbeOutcome(
            probe_name="fs_write_escape",
            axis=Axis.FS_WRITE,
            shape=ProbeShape.DENIAL,
            verdict=Verdict.PASS,
            subject="Read-only file system\nexit:1",
            matched_signature=None,
        )

    # Control 1: the same DENIAL PASS, but WITH a matched_signature, constructs.
    denial_with_signature = ProbeOutcome(
        probe_name="fs_write_escape",
        axis=Axis.FS_WRITE,
        shape=ProbeShape.DENIAL,
        verdict=Verdict.PASS,
        subject="Read-only file system\nexit:1",
        matched_signature="Read-only file system",
    )
    assert denial_with_signature.matched_signature == "Read-only file system"

    # Control 2: an ABSENCE PASS with matched_signature=None constructs --
    # that shape's PASS carries no signature by design.
    absence_pass = ProbeOutcome(
        probe_name="env_scrub_absence",
        axis=Axis.ENV,
        shape=ProbeShape.ABSENCE,
        verdict=Verdict.PASS,
        subject="SECRET_TOKEN not present in environment dump",
        matched_signature=None,
    )
    assert absence_pass.matched_signature is None


@pytest.mark.unit
def test_probe_outcome_fields_round_trip() -> None:
    """A plain construct/read check: every field lands where it's named."""
    outcome = ProbeOutcome(
        probe_name="cpu_limit_trip",
        axis=Axis.LIMITS,
        shape=ProbeShape.DENIAL,
        verdict=Verdict.PASS,
        subject="\nsignal:SIGXCPU",
        matched_signature="signal:SIGXCPU",
        detail="rlimits cpu cap",
    )
    assert outcome.probe_name == "cpu_limit_trip"
    assert outcome.axis is Axis.LIMITS
    assert outcome.shape is ProbeShape.DENIAL
    assert outcome.verdict is Verdict.PASS
    assert outcome.subject == "\nsignal:SIGXCPU"
    assert outcome.matched_signature == "signal:SIGXCPU"
    assert outcome.detail == "rlimits cpu cap"


@pytest.mark.unit
def test_probe_report_is_an_accessor_over_its_outcomes() -> None:
    """ProbeReport "computes no policy" (its Deliverable docstring): it just
    holds what it was built with. `battery_verdict` is `BatteryVerdict`
    (task-053/decision-104's rename), never `Verdict` reused -- see
    `test_the_two_vocabularies_are_separate_types` below."""
    outcome = ProbeOutcome(
        probe_name="control_write",
        axis=Axis.FS_WRITE,
        shape=ProbeShape.CONTROL,
        verdict=Verdict.PASS,
        subject="",
    )
    report = ProbeReport(
        outcomes=(outcome,),
        battery_name="fs_write_battery",
        battery_verdict=BatteryVerdict.CONSISTENT,
        contradictions=(),
    )
    assert report.outcomes == (outcome,)
    assert report.battery_name == "fs_write_battery"
    assert report.battery_verdict is BatteryVerdict.CONSISTENT
    assert report.contradictions == ()


# ---------------------------------------------------------------------------
# task-053 AC #13 -- the two vocabularies are SEPARATE types.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_two_vocabularies_are_separate_types() -> None:
    """AC #13: `BatteryVerdict` (decision-104) is its own `Enum`, never
    `Verdict` extended or reused. `Verdict`'s members are exactly
    `('PASS', 'FAIL', 'VACUOUS')` and `BatteryVerdict`'s are exactly
    `('CONSISTENT', 'CONTRADICTED', 'VACUOUS')`, both compared against a
    literal tuple so a silently-added member would be caught; and
    `BatteryVerdict.VACUOUS` is NOT `Verdict.VACUOUS` -- the two enums
    sharing a member NAME must not make them interchangeable."""
    assert tuple(m.name for m in Verdict) == ("PASS", "FAIL", "VACUOUS")
    assert tuple(m.name for m in BatteryVerdict) == ("CONSISTENT", "CONTRADICTED", "VACUOUS")

    # `object`-typed locals, not a direct literal-vs-literal `is` check: mypy
    # --strict proves two DIFFERENT enum types' members can never be `is`
    # (comparison-overlap) -- exactly the property under test here, so the
    # assertion is widened to `object` the same way other tests in this repo
    # sidestep a statically-true identity check (see
    # `test_probe_runner.py::test_a_failed_control_dominates_a_contradiction`'s
    # own comment on the identical mypy behavior).
    battery_vacuous: object = BatteryVerdict.VACUOUS
    assert battery_vacuous is not Verdict.VACUOUS

    battery_verdict_type: object = BatteryVerdict
    assert battery_verdict_type is not Verdict


@pytest.mark.unit
def test_probe_report_gains_a_per_axis_observed_outcomes_view() -> None:
    """AC #14: `ProbeReport.observed_by_axis` is a per-axis view of the
    `Verdict`s actually observed, DERIVED FROM `outcomes` -- a computed
    property, never a stored field a constructor could leave empty (the
    shape decision-104 clause 2 and this task's own pre-dispatch AC repair
    require: a stored field lets a hand-built report pass while
    `run_battery` populates it with nothing).

    Built from outcomes spanning TWO axes: the view's key set equals
    exactly those two axes, and each value equals the observed `Verdict`s
    for that axis, in `outcomes` order.

    Control, in the same test: a `ProbeReport` whose `outcomes` span ONE
    axis has a single-key view -- proving the assertion above is capable of
    failing on a view that ignores its input (e.g. one hard-coded to every
    known axis)."""
    env_control = ProbeOutcome(
        probe_name="allowed_name_survives",
        axis=Axis.ENV,
        shape=ProbeShape.CONTROL,
        verdict=Verdict.PASS,
        subject="",
    )
    env_absence = ProbeOutcome(
        probe_name="scrubbed_name_is_absent",
        axis=Axis.ENV,
        shape=ProbeShape.ABSENCE,
        verdict=Verdict.PASS,
        subject="",
    )
    limits_control = ProbeOutcome(
        probe_name="short_command_completes",
        axis=Axis.LIMITS,
        shape=ProbeShape.CONTROL,
        verdict=Verdict.PASS,
        subject="",
    )
    two_axis_report = ProbeReport(
        outcomes=(env_control, env_absence, limits_control),
        battery_name="two-axis",
        battery_verdict=BatteryVerdict.CONSISTENT,
        contradictions=(),
    )
    view = two_axis_report.observed_by_axis
    assert set(view.keys()) == {Axis.ENV, Axis.LIMITS}
    assert view[Axis.ENV] == (Verdict.PASS, Verdict.PASS)
    assert view[Axis.LIMITS] == (Verdict.PASS,)

    # Control: one axis only -> a single-key view, not every known axis.
    one_axis_report = ProbeReport(
        outcomes=(limits_control,),
        battery_name="one-axis",
        battery_verdict=BatteryVerdict.CONSISTENT,
        contradictions=(),
    )
    one_axis_view = one_axis_report.observed_by_axis
    assert set(one_axis_view.keys()) == {Axis.LIMITS}
    assert one_axis_view[Axis.LIMITS] == (Verdict.PASS,)
