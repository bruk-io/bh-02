"""Unit tests for `brig.mech.rlimits`: the render function's exact argv,
the `limits` axis grade, the denial signature, the axes claim, and the
`EventSource` exit classification -- all pure, all here per the unit-tier
rules' "render functions are the unit-test goldmine."

task-036 AC #1's three named cases live in the three
`test_render_*_exact_argv` functions below; AC #4's mutation pairing names
`test_render_cpu_seconds_one_exact_argv` specifically (see that test's own
docstring) as the deterministic pairing, per decision-026 rule 3.
"""

from __future__ import annotations

import signal
import sys

import pytest

from brig.core import Axis, EventKind, Grade, Limits, Spec
from brig.mech import CompileCtx, EventSource, ExitOutcome
from brig.mech.rlimits import rlimits

_CTX = CompileCtx(jail_dir="/unused/rlimits-unit-test", platform=sys.platform)


@pytest.mark.unit
def test_axes_is_exactly_limits() -> None:
    """AC #10: axes == frozenset({Axis.LIMITS}) by set equality, nothing
    else. Mutation pairing (manual, task notes): add Axis.ENV to
    `Rlimits.axes`, re-run this test by name, watch it fail; revert."""
    assert rlimits.axes == frozenset({Axis.LIMITS})


@pytest.mark.unit
def test_render_cpu_seconds_one_exact_argv() -> None:
    """AC #1, case 1. THE NAMED RENDER TEST for AC #4's mutation pairing:
    make `compile` emit no `--cpu` flag for a non-zero `cpu_seconds` and
    re-run exactly this test by name -- it must go red on the missing
    `'--cpu', '1'` segment."""
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=1)), _CTX)
    result = step.wrap(("/bin/echo", "hi"))
    assert result == (
        sys.executable,
        "-m",
        "brig.mech.trampoline",
        "--cpu",
        "1",
        "--",
        "/bin/echo",
        "hi",
    )


@pytest.mark.unit
def test_render_cpu_seconds_zero_emits_no_cpu_flag() -> None:
    """AC #1, case 2 -- the load-bearing one: SPEC.md §5, "0 = uncapped",
    so `cpu_seconds=0` must render with NO `--cpu` flag at all. Rendering
    `--cpu 0` instead would be a silent instant kill (`RLIMIT_CPU` of 0
    trips on the workload's very first tick), the opposite of "uncapped."
    """
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=0)), _CTX)
    result = step.wrap(("/bin/echo", "hi"))
    assert result == (
        sys.executable,
        "-m",
        "brig.mech.trampoline",
        "--",
        "/bin/echo",
        "hi",
    )
    assert "--cpu" not in result


@pytest.mark.unit
def test_render_multiword_workload_argv_exact_tuple() -> None:
    """AC #1, case 3: a multi-word workload argv passes through `wrap`
    unmodified, after the trampoline's own flags and separator."""
    step = rlimits.compile(Spec(limits=Limits(cpu_seconds=5)), _CTX)
    workload = ("python3", "-c", "import os; print(os.getpid())", "--flag", "value")
    result = step.wrap(workload)
    assert result == (
        sys.executable,
        "-m",
        "brig.mech.trampoline",
        "--cpu",
        "5",
        "--",
        "python3",
        "-c",
        "import os; print(os.getpid())",
        "--flag",
        "value",
    )


@pytest.mark.unit
def test_compile_is_pure_same_spec_same_ctx_same_argv() -> None:
    """Control for AC #1: two independent `compile` calls against
    equivalent inputs render byte-identical argv -- `compile` reads nothing
    but its own arguments."""
    spec = Spec(limits=Limits(cpu_seconds=1))
    step_a = rlimits.compile(spec, _CTX)
    step_b = rlimits.compile(
        Spec(limits=Limits(cpu_seconds=1)),
        CompileCtx(jail_dir="/unused/rlimits-unit-test", platform=sys.platform),
    )
    assert step_a.wrap(("x",)) == step_b.wrap(("x",))


@pytest.mark.unit
def test_grade_is_best_effort_with_four_uncovered_fields_named() -> None:
    """AC #8: `grades[Axis.LIMITS].grade is Grade.BEST_EFFORT`, and
    `detail` names memory/tasks/wall/output by PARSED TOKEN SET (not
    substring): the segment after the `"uncovered:"` marker, split on
    commas, must equal exactly that four-name set -- so an invented fifth
    field, or a missing one, is loud rather than silently passing a
    substring check.

    THE NAMED GOLDEN GRADE TEST for AC #9's mutation pairing (see that
    AC's evidence in the task notes for why AC #9's own wording needed a
    correction)."""
    step = rlimits.compile(Spec(), _CTX)
    graded = step.grades[Axis.LIMITS]
    assert graded.grade is Grade.BEST_EFFORT

    marker = "uncovered:"
    assert marker in graded.detail
    uncovered_segment = graded.detail.split(marker, 1)[1]
    tokens = {token.strip() for token in uncovered_segment.split(",")}
    assert tokens == {"memory", "tasks", "wall", "output"}


@pytest.mark.unit
def test_denial_signature_matches_the_sigxcpu_termination_token() -> None:
    """AC #7, positive half: the declared denial signature matches
    SPEC.md §6/§12's canonical termination token, `signal:SIGXCPU`."""
    step = rlimits.compile(Spec(), _CTX)
    assert len(step.denial_signatures) == 1
    pattern = step.denial_signatures[0]
    assert pattern.search("signal:SIGXCPU") is not None


@pytest.mark.unit
def test_denial_signature_does_not_match_generic_failures() -> None:
    """AC #7, negative half -- the one that prevents vacuous probe passes
    at M4: the signature must NOT match a generic failure that merely
    happens to occur near a denial attempt."""
    step = rlimits.compile(Spec(), _CTX)
    pattern = step.denial_signatures[0]
    assert pattern.search("bash: spin: command not found") is None
    assert pattern.search("No such file or directory") is None


@pytest.mark.unit
def test_events_is_a_structurally_matching_event_source() -> None:
    """`Step.events` is populated and structurally satisfies `EventSource`
    (control for the classification tests below: isinstance actually
    discriminates, per test_mech_events_purity.py's own precedent)."""
    step = rlimits.compile(Spec(), _CTX)
    assert step.events is not None
    assert isinstance(step.events, EventSource)


@pytest.mark.unit
def test_event_source_classifies_sigxcpu_naming_field_and_signal() -> None:
    """AC #5's pure half: `classify_exit` recognizes a SIGXCPU termination
    (Python's own encoding: `returncode == -signal.SIGXCPU`) and names
    both the limit field (`cpu`) and the signal in the returned payload's
    data -- the same shape `run` will stamp `ts`/`jail_id` onto and
    append."""
    step = rlimits.compile(Spec(), _CTX)
    assert step.events is not None

    payload = step.events.classify_exit(ExitOutcome(returncode=-signal.SIGXCPU))
    assert payload is not None
    assert payload.kind is EventKind.LIMIT_TRIP
    assert payload.data == {"field": "cpu", "signal": int(signal.SIGXCPU)}
    # decision-069 constraint 2, mechanical form: no self-stamping.
    assert "ts" not in payload.data
    assert "jail_id" not in payload.data


@pytest.mark.unit
def test_event_source_ignores_endings_it_does_not_recognize() -> None:
    """Control for the classification test above: a clean exit (and an
    unrelated signal) are not misclassified as a cpu trip."""
    step = rlimits.compile(Spec(), _CTX)
    assert step.events is not None

    assert step.events.classify_exit(ExitOutcome(returncode=0)) is None
    assert step.events.classify_exit(ExitOutcome(returncode=1)) is None
    assert step.events.classify_exit(ExitOutcome(returncode=-signal.SIGTERM)) is None
    assert step.events.known_at_compile() == ()
