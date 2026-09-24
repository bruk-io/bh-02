"""Tests for brig.probe.verdict.classify -- the ten-row shape table
(SPEC.md §12), MILESTONES.md M4 EC4, decision-067/decision-099's empty
denial-signature-tuple rule.
"""

import re
import signal

import pytest

from brig.core.grades import Axis
from brig.core.probes import ProbeShape, Verdict
from brig.core.signatures import AxisClaim
from brig.probe.battery import Expectation, Probe
from brig.probe.verdict import classify

# rlimits' own denial signature, quoted here as a literal -- probe may not
# import mech (SPEC.md §13), and this test is about brig.probe, not
# brig.mech. Source of truth: brig/mech/rlimits.py's
# `_DENIAL_SIGNATURE = re.compile(r"signal:SIGXCPU")`.
_RLIMITS_SIGNATURE = re.compile(r"signal:SIGXCPU")

_RLIMITS_CLAIM = AxisClaim(axis=Axis.LIMITS, mechanism="rlimits", signatures=(_RLIMITS_SIGNATURE,))
_NO_SIGNATURE_CLAIM = AxisClaim(axis=Axis.LIMITS, mechanism="rlimits", signatures=())

_DENIAL_PROBE = Probe(
    name="exceed_cpu_limit",
    shape=ProbeShape.DENIAL,
    axis=Axis.LIMITS,
    argv=("nope",),
    expect=Expectation(),
)

_ABSENCE_PROBE = Probe(
    name="env_dump_absent_secret",
    shape=ProbeShape.ABSENCE,
    axis=Axis.ENV,
    argv=("env",),
    expect=Expectation(token="SECRET_TOKEN"),
)

_CONTROL_PROBE = Probe(
    name="write_inside_workspace",
    shape=ProbeShape.CONTROL,
    axis=Axis.FS_WRITE,
    argv=("touch", "workspace/ok"),
    expect=Expectation(token="ok"),
)


@pytest.mark.unit
def test_a_failure_with_no_matching_signature_is_vacuous() -> None:
    """MILESTONES.md M4 EC4: a probe that fails for a non-policy reason
    (command not found) lands VACUOUS, never PASS."""
    outcome = classify(
        _DENIAL_PROBE,
        returncode=127,
        stdout="",
        stderr="sh: nope: command not found",
        claim=_RLIMITS_CLAIM,
    )
    assert outcome.verdict is Verdict.VACUOUS


@pytest.mark.unit
def test_a_failure_matching_the_declared_signature_is_pass() -> None:
    """Control for the test above (MILESTONES.md M4 EC4, both directions):
    the SAME call, but a failure that actually carries the declared denial
    signature (SIGXCPU), is PASS with a matched_signature -- proving the
    VACUOUS above is about the missing match, not something else about the
    call."""
    outcome = classify(
        _DENIAL_PROBE,
        returncode=-signal.SIGXCPU,
        stdout="",
        stderr="",
        claim=_RLIMITS_CLAIM,
    )
    assert outcome.verdict is Verdict.PASS
    assert outcome.matched_signature is not None


_RETURNCODES = (1, 2, 127, 137, -signal.SIGXCPU, -signal.SIGKILL)
_STDERRS = ("", "Operation not permitted")


@pytest.mark.unit
def test_an_empty_signature_tuple_can_never_reach_pass() -> None:
    """decision-067 / SPEC.md §12: the empty tuple is a routing fact, not a
    gap -- a mechanism declaring it has NO way to reach PASS by signature,
    for any returncode or stderr shape in the enumerated set."""
    for returncode in _RETURNCODES:
        for stderr in _STDERRS:
            outcome = classify(
                _DENIAL_PROBE,
                returncode=returncode,
                stdout="",
                stderr=stderr,
                claim=_NO_SIGNATURE_CLAIM,
            )
            assert outcome.verdict is Verdict.VACUOUS, (returncode, stderr)

    # The Deliverable's own wording ("detail naming that this mechanism
    # declares no signature by design") pinned on one representative case.
    named_outcome = classify(
        _DENIAL_PROBE,
        returncode=127,
        stdout="",
        stderr="",
        claim=_NO_SIGNATURE_CLAIM,
    )
    assert "by design" in named_outcome.detail

    # Control: the identical probe, with a claim carrying a matching
    # pattern instead of the empty tuple, reaches PASS for the
    # signal-shaped case.
    control_outcome = classify(
        _DENIAL_PROBE,
        returncode=-signal.SIGXCPU,
        stdout="",
        stderr="",
        claim=_RLIMITS_CLAIM,
    )
    assert control_outcome.verdict is Verdict.PASS


@pytest.mark.unit
def test_an_attempt_that_succeeded_is_fail_not_pass() -> None:
    """A jail that permits the violation can never be reported as enforcing
    it: returncode==0 is FAIL regardless of what claim is on file, including
    no claim at all."""
    outcome_with_claim = classify(
        _DENIAL_PROBE, returncode=0, stdout="", stderr="", claim=_RLIMITS_CLAIM
    )
    assert outcome_with_claim.verdict is Verdict.FAIL

    outcome_without_claim = classify(_DENIAL_PROBE, returncode=0, stdout="", stderr="", claim=None)
    assert outcome_without_claim.verdict is Verdict.FAIL


@pytest.mark.unit
@pytest.mark.parametrize(
    ("probe", "returncode", "stdout", "stderr", "claim", "expected"),
    [
        pytest.param(
            _DENIAL_PROBE,
            0,
            "",
            "",
            _RLIMITS_CLAIM,
            Verdict.FAIL,
            id="denial_succeeded_is_fail",
        ),
        pytest.param(
            _DENIAL_PROBE,
            127,
            "",
            "sh: nope: command not found",
            None,
            Verdict.VACUOUS,
            id="denial_failed_no_claim_is_vacuous",
        ),
        pytest.param(
            _DENIAL_PROBE,
            127,
            "",
            "sh: nope: command not found",
            _NO_SIGNATURE_CLAIM,
            Verdict.VACUOUS,
            id="denial_failed_empty_signatures_is_vacuous",
        ),
        pytest.param(
            _DENIAL_PROBE,
            -signal.SIGXCPU,
            "",
            "",
            _RLIMITS_CLAIM,
            Verdict.PASS,
            id="denial_failed_signature_matches_is_pass",
        ),
        pytest.param(
            _DENIAL_PROBE,
            127,
            "",
            "sh: nope: command not found",
            _RLIMITS_CLAIM,
            Verdict.VACUOUS,
            id="denial_failed_no_signature_matches_is_vacuous",
        ),
        pytest.param(
            _ABSENCE_PROBE,
            1,
            "",
            "",
            None,
            Verdict.VACUOUS,
            id="absence_nonzero_exit_is_vacuous",
        ),
        pytest.param(
            _ABSENCE_PROBE,
            0,
            "PATH=/usr/bin",
            "",
            None,
            Verdict.PASS,
            id="absence_token_absent_is_pass",
        ),
        pytest.param(
            _ABSENCE_PROBE,
            0,
            "SECRET_TOKEN=xyz",
            "",
            None,
            Verdict.FAIL,
            id="absence_token_present_is_fail",
        ),
        pytest.param(
            _CONTROL_PROBE,
            0,
            "ok",
            "",
            None,
            Verdict.PASS,
            id="control_succeeded_token_present_is_pass",
        ),
        pytest.param(
            _CONTROL_PROBE,
            1,
            "",
            "",
            None,
            Verdict.FAIL,
            id="control_anything_else_is_fail",
        ),
    ],
)
def test_classify_table(
    probe: Probe,
    returncode: int,
    stdout: str,
    stderr: str,
    claim: AxisClaim | None,
    expected: Verdict,
) -> None:
    """Every row of the ten-row table in task-048's Deliverable, one
    parametrized case per row, the case id naming the row."""
    outcome = classify(probe, returncode=returncode, stdout=stdout, stderr=stderr, claim=claim)
    assert outcome.verdict is expected


@pytest.mark.unit
def test_classify_is_pure() -> None:
    """classify performs no I/O: called twice with identical arguments it
    returns equal ProbeOutcomes. The companion grep pin (task-048 AC #7)
    checks the module text itself for a subprocess/file/socket/clock call."""
    first = classify(
        _DENIAL_PROBE,
        returncode=-signal.SIGXCPU,
        stdout="",
        stderr="",
        claim=_RLIMITS_CLAIM,
    )
    second = classify(
        _DENIAL_PROBE,
        returncode=-signal.SIGXCPU,
        stdout="",
        stderr="",
        claim=_RLIMITS_CLAIM,
    )
    assert first == second
