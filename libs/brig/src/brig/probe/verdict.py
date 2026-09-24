"""`classify`: SPEC.md §12's three-way verdict, decided per probe shape.

SPEC.md §12, verbatim (the `DENIAL` shape, unamended by the shape fold):

    - `PASS` -- the attempt failed *with a denial signature* declared by the
      mechanism claiming that axis.
    - `FAIL` -- the attempt succeeded; the claim is false.
    - `VACUOUS` -- the attempt failed *without* a denial signature (wrong
      path, missing file, broken probe). A vacuous probe is a warning, never
      a pass.

    **A verdict is decided against §6's classification subject**, not against
    raw output: the probe engine builds the normalized denial string ... A
    mechanism declaring the empty tuple has no way to reach `PASS` by
    signature at all, which is correct: its axis is proved by the battery's
    positive controls, and every probe against it that merely fails is
    `VACUOUS`.

SPEC.md §12, the `ABSENCE` and `CONTROL` shapes, verbatim:

    - **`ABSENCE`** -- perform a **permitted** observation and assert a
      policy-derived absence in its output. `PASS` requires the observation
      to exit **cleanly** *and* the asserted absence to hold; **a non-zero
      exit is `VACUOUS`, never `PASS`**, because an observation that did not
      run observed nothing. An `ABSENCE` `PASS` carries no matched signature,
      and that is its correct shape rather than a missing field.
    - **`CONTROL`** -- the positive control. `PASS` iff it succeeded.

MILESTONES.md M4 EC4, verbatim:

    Verdict classification: a probe that fails for a non-policy reason (e.g.
    command not found) lands VACUOUS, never PASS -- unit-tested against the
    signature matcher.

For a `DENIAL` probe, whether `claim` carries a signature list that misses
every pattern or carries the empty tuple (decision-067/decision-099: a
routing fact, not a gap) is a single outcome -- `VACUOUS` -- reached at one
terminus below; only the recorded `detail` distinguishes the two cases, never
the verdict.

This module is pure: no I/O, no clock, no randomness, and it spawns nothing.
`re` is a closed, deterministic stdlib module used only via already-compiled
patterns handed in on `claim`.
"""

from __future__ import annotations

from brig.core.probes import ProbeOutcome, ProbeShape, Verdict
from brig.core.signatures import AxisClaim, denial_subject
from brig.probe.battery import Probe


def classify(
    probe: Probe,
    returncode: int,
    stdout: str,
    stderr: str,
    claim: AxisClaim | None,
) -> ProbeOutcome:
    """Decide `probe`'s `ProbeOutcome` from one attempt's observed result.

    `claim` is the calling mechanism's `AxisClaim` (`brig.core.signatures`)
    for `probe.axis`, or `None` when nothing on file claims that axis --
    only `DENIAL` reads it; `ABSENCE` and `CONTROL` decide from `returncode`
    and `stdout` alone.
    """
    if probe.shape is ProbeShape.DENIAL:
        return _classify_denial(probe, returncode, stderr, claim)
    if probe.shape is ProbeShape.ABSENCE:
        return _classify_absence(probe, returncode, stdout)
    return _classify_control(probe, returncode, stdout)


def _classify_denial(
    probe: Probe, returncode: int, stderr: str, claim: AxisClaim | None
) -> ProbeOutcome:
    subject = denial_subject(stderr, returncode)

    if returncode == 0:
        return ProbeOutcome(
            probe_name=probe.name,
            axis=probe.axis,
            shape=ProbeShape.DENIAL,
            verdict=Verdict.FAIL,
            subject=subject,
            detail="the attempt succeeded; the claim is false (SPEC.md §12)",
        )

    if claim is None:
        return ProbeOutcome(
            probe_name=probe.name,
            axis=probe.axis,
            shape=ProbeShape.DENIAL,
            verdict=Verdict.VACUOUS,
            subject=subject,
            detail="no signature claim is on file for this probe's axis",
        )

    for pattern in claim.signatures:
        if pattern.search(subject) is not None:
            return ProbeOutcome(
                probe_name=probe.name,
                axis=probe.axis,
                shape=ProbeShape.DENIAL,
                verdict=Verdict.PASS,
                subject=subject,
                matched_signature=pattern.pattern,
            )

    # No declared pattern matched -- reached whether `claim.signatures` held
    # patterns that all searched false, or was the empty tuple to begin with
    # (the loop above then simply iterated zero times). Both are `VACUOUS`
    # by SPEC.md §12; only `detail` distinguishes decision-067's routing
    # fact from a genuine miss, never the verdict.
    if claim.signatures == ():
        detail = (
            f"{claim.mechanism!r} declares no denial signature by design "
            "(SPEC.md §12: a routing fact, not a gap -- its axis is proved "
            "by the battery's positive controls instead)"
        )
    else:
        detail = f"failed, but no signature declared by {claim.mechanism!r} matched"
    return ProbeOutcome(
        probe_name=probe.name,
        axis=probe.axis,
        shape=ProbeShape.DENIAL,
        verdict=Verdict.VACUOUS,
        subject=subject,
        detail=detail,
    )


def _classify_absence(probe: Probe, returncode: int, stdout: str) -> ProbeOutcome:
    if returncode != 0:
        return ProbeOutcome(
            probe_name=probe.name,
            axis=probe.axis,
            shape=ProbeShape.ABSENCE,
            verdict=Verdict.VACUOUS,
            subject=stdout,
            detail=("the observation did not exit cleanly, so it observed nothing (SPEC.md §12)"),
        )

    token = probe.expect.token
    token_present = token is not None and token in stdout
    if token_present:
        return ProbeOutcome(
            probe_name=probe.name,
            axis=probe.axis,
            shape=ProbeShape.ABSENCE,
            verdict=Verdict.FAIL,
            subject=stdout,
            detail=f"expected {token!r} absent from stdout, but it is present",
        )
    return ProbeOutcome(
        probe_name=probe.name,
        axis=probe.axis,
        shape=ProbeShape.ABSENCE,
        verdict=Verdict.PASS,
        subject=stdout,
    )


def _classify_control(probe: Probe, returncode: int, stdout: str) -> ProbeOutcome:
    token = probe.expect.token
    if returncode == 0 and token is not None and token in stdout:
        return ProbeOutcome(
            probe_name=probe.name,
            axis=probe.axis,
            shape=ProbeShape.CONTROL,
            verdict=Verdict.PASS,
            subject=stdout,
        )
    return ProbeOutcome(
        probe_name=probe.name,
        axis=probe.axis,
        shape=ProbeShape.CONTROL,
        verdict=Verdict.FAIL,
        subject=stdout,
        detail="the positive control did not succeed",
    )


__all__ = ("classify",)
