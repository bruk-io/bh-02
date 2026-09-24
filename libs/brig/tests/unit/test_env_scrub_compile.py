"""Unit tests for `brig.mech.env_scrub`: the render function's exact argv,
the `env` axis grade, the empty denial-signature tuple (asserted as intent,
not left implicit), the axes claim, and the `EventSource` compile-time-fact
case -- all pure, all here per the unit-tier rules' "render functions are
the unit-test goldmine."

task-034 AC #1's four named cases live in the four `test_render_*_exact_argv`
functions below. AC #4's mutation pairing (rlimits' own precedent, decision-
026 rule 3) names `test_render_scrub_two_allow_names_exact_argv` as the
deterministic pairing for AC #7's axes mutation check -- see that test's own
docstring.
"""

from __future__ import annotations

import sys

import pytest

from brig.core import Axis, EnvMode, EnvPolicy, EventKind, Grade, Spec
from brig.mech import CompileCtx, EventSource, ExitOutcome
from brig.mech.env_scrub import env_scrub

_CTX = CompileCtx(jail_dir="/unused/env-scrub-unit-test", platform=sys.platform)


@pytest.mark.unit
def test_axes_is_exactly_env() -> None:
    """AC #7: axes == frozenset({Axis.ENV}) by set equality, nothing else.

    Mutation pairing (manual, task notes, decision-026 rule 3 -- named
    here so the pairing is deterministic): add `Axis.FS_READ` to
    `EnvScrub.axes`, re-run THIS test by name
    (`test_axes_is_exactly_env`), watch it fail; revert."""
    assert env_scrub.axes == frozenset({Axis.ENV})


@pytest.mark.unit
def test_render_scrub_two_allow_names_exact_argv() -> None:
    """AC #1, case (i): SCRUB with two allow_names, no `set` pairs. The
    NAMED RENDER TEST for AC #7's mutation pairing above. `EnvPolicy`
    normalizes `allow_names` to a sorted tuple, so "A", "B" arrive in that
    order regardless of construction order -- asserted here via the
    caller's own choice of already-sorted names, not relied on silently."""
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("B", "A"))
    step = env_scrub.compile(Spec(env=policy), _CTX)
    result = step.wrap(("/bin/echo", "hi"))
    assert result == (
        "/bin/sh",
        "-c",
        'exec /usr/bin/env -i ${A:+"A=$A"} ${B:+"B=$B"} "$@"',
        "sh",
        "/bin/echo",
        "hi",
    )


@pytest.mark.unit
def test_render_scrub_no_allow_names_exact_argv() -> None:
    """AC #1, case (ii): SCRUB with no allow_names and no `set` pairs --
    the load-bearing minimal case: `env -i` still runs, forwarding
    nothing, with no dangling assignment tokens before `"$@"`."""
    policy = EnvPolicy(mode=EnvMode.SCRUB)
    step = env_scrub.compile(Spec(env=policy), _CTX)
    result = step.wrap(("/bin/echo", "hi"))
    assert result == (
        "/bin/sh",
        "-c",
        'exec /usr/bin/env -i "$@"',
        "sh",
        "/bin/echo",
        "hi",
    )


@pytest.mark.unit
def test_render_scrub_two_set_pairs_exact_argv() -> None:
    """AC #1, case (iii): SCRUB with no allow_names, two `set` pairs.
    `set` values are compile-time-known literals, so they are single-quoted
    directly into the script text -- no shell substitution needed for
    them, unlike `allow_names`."""
    policy = EnvPolicy(mode=EnvMode.SCRUB, set=(("K2", "v2"), ("K1", "v1")))
    step = env_scrub.compile(Spec(env=policy), _CTX)
    result = step.wrap(("/bin/echo", "hi"))
    assert result == (
        "/bin/sh",
        "-c",
        "exec /usr/bin/env -i K1='v1' K2='v2' \"$@\"",
        "sh",
        "/bin/echo",
        "hi",
    )


@pytest.mark.unit
def test_render_set_empty_value_still_defines_the_binding() -> None:
    """Pins the deliberate asymmetry `env_scrub.py`'s `_assignment_tokens`
    docstring names: `allow_names` treats "empty" as "absent" (see
    `test_render_scrub_two_allow_names_exact_argv`'s `${NAME:+...}` form),
    but `set` does NOT -- a `set` pair with an empty VALUE still renders a
    real `KEY=''` binding, because `set` carries a literal the spec author
    chose (an empty string is a chosen value, not an absence), unlike
    `allow_names`, which only ever forwards what the parent actually had.
    A later refactor toward symmetry would have to change this literal."""
    policy = EnvPolicy(mode=EnvMode.SCRUB, set=(("KEY", ""),))
    step = env_scrub.compile(Spec(env=policy), _CTX)
    result = step.wrap(("/bin/echo", "hi"))
    assert result == (
        "/bin/sh",
        "-c",
        "exec /usr/bin/env -i KEY='' \"$@\"",
        "sh",
        "/bin/echo",
        "hi",
    )


@pytest.mark.unit
def test_render_pass_is_identity_exact_argv() -> None:
    """AC #1, case (iv): PASS. Nothing to scrub -- `wrap` is the identity
    transform, byte-identical input and output, no `/bin/sh`, no `env`."""
    policy = EnvPolicy(mode=EnvMode.PASS)
    step = env_scrub.compile(Spec(env=policy), _CTX)
    workload = ("/bin/echo", "hi", "--flag", "value")
    result = step.wrap(workload)
    assert result == workload
    assert result is workload  # the identity closure returns its argument object as-is


@pytest.mark.unit
def test_compile_is_pure_same_spec_same_ctx_same_argv() -> None:
    """Control for AC #1: two independent `compile` calls against
    equivalent inputs render byte-identical argv -- `compile` reads
    nothing but its own arguments (in particular: no environment read)."""
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("HOME",))
    step_a = env_scrub.compile(Spec(env=policy), _CTX)
    step_b = env_scrub.compile(
        Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("HOME",))),
        CompileCtx(jail_dir="/unused/env-scrub-unit-test", platform=sys.platform),
    )
    assert step_a.wrap(("x",)) == step_b.wrap(("x",))


@pytest.mark.unit
def test_grade_is_enforced_for_scrub() -> None:
    """AC #5's shipped-grade half: `grades[Axis.ENV]` is ENFORCED for SCRUB.

    The detail was `""` until decision-143, which left a report reader seeing
    ENFORCED with no scope while the caveat lived in a module docstring they
    never see. The GRADE is unchanged -- it is correct, scoped to the child;
    the detail now says so, and names the host-side argv transit window."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB)), _CTX)
    graded = step.grades[Axis.ENV]
    assert graded.grade is Grade.ENFORCED
    assert "AGAINST THE CHILD" in graded.detail
    assert "argv" in graded.detail


@pytest.mark.unit
def test_pass_mode_claims_no_axis() -> None:
    """AC #2 / task-044: SPEC.md §6, decision-092 (P-12) -- a mechanism
    claims an axis only when the spec gives it work to do on that axis.
    PASS forwards the parent environment untouched, byte-identical to what
    the empty stack already does, so there is nothing being enforced and
    `EnvScrub.compile` claims NOTHING on the env axis: `step.grades` is the
    empty mapping, not `{Axis.ENV: Graded(ENFORCED, "")}`.

    This test RETIRES `test_grade_is_enforced_for_pass_too` (this file, as
    it stood before task-044): that test asserted PASS grades
    `Axis.ENV: ENFORCED`, which is exactly the claim this task's spec fold
    (decision-092) makes false. task-044's own dispatch enumerated only
    the spec-invariance COMMENT block (test_stack_degraded_preset.py) as
    retired text; it did not name this test, which is an omission in that
    enumeration rather than license to leave a now-false assertion in a
    green suite (CLAUDE.md: never write a test that doesn't test the real
    implementation). WORKFLOW.md rule 4's remedy is followed here: the
    stale assertion is not deleted outright, it is renamed and rewritten
    to assert the positive fact that replaced it -- same test identity,
    corrected body -- and the named control immediately below
    (`test_scrub_mode_still_grades_env_enforced`) is AC #2's second half.
    See this task's ATTEMPT 1 IMPLEMENTER note for the full accounting."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.PASS)), _CTX)
    assert step.grades == {}


@pytest.mark.unit
def test_scrub_mode_still_grades_env_enforced() -> None:
    """AC #2's named control: SCRUB is a real policy being applied (names
    are filtered, `env -i` actually runs), so it still claims and grades
    the env axis -- `step.grades` has exactly the ENV key, graded ENFORCED,
    proving the PASS case above is a genuine branch on `EnvPolicy.mode`, not
    a change to what SCRUB does. The detail's content is pinned by
    `test_grade_is_enforced_for_scrub` (decision-143); the claim here is the
    KEY SET, which is what distinguishes the two modes."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB)), _CTX)
    assert set(step.grades) == {Axis.ENV}
    assert step.grades[Axis.ENV].grade is Grade.ENFORCED


@pytest.mark.unit
def test_denial_signatures_is_the_empty_tuple() -> None:
    """AC #6: `denial_signatures == ()`, asserted as intent (this module's
    own docstring states why: scrubbing produces absence, not denial, and
    any signature here would risk matching a workload's own generic
    "variable missing" failure text, converting an M4 probe's honest
    absence-check into a false PASS -- SPEC.md §6, decision-068/067)."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=("HOME",))), _CTX)
    assert step.denial_signatures == ()

    step_pass = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.PASS)), _CTX)
    assert step_pass.denial_signatures == ()

    # `importlib.import_module`, not `import brig.mech.env_scrub as x`: this
    # package's own `__init__.py` rebinds the attribute `brig.mech.env_scrub`
    # from the submodule to the `env_scrub` INSTANCE (same name, deliberately
    # -- `brig.mech.rlimits` has the identical shape), so a plain dotted
    # `import ... as x` would resolve `x` to the instance and its `__doc__`
    # would silently fall back to the CLASS's docstring instead of the
    # MODULE's -- exactly the kind of true-as-tested-but-wrong result
    # CLAUDE.md warns about. `importlib.import_module` reads `sys.modules`
    # directly, sidestepping that attribute rebind.
    import importlib

    module = importlib.import_module("brig.mech.env_scrub")
    assert module.__doc__ is not None
    assert "ABSENCE, not a denial" in module.__doc__


@pytest.mark.unit
def test_events_is_a_structurally_matching_event_source() -> None:
    """`Step.events` is populated and structurally satisfies `EventSource`
    (control for the classification tests below: isinstance actually
    discriminates, per test_mech_events_purity.py's own precedent)."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB)), _CTX)
    assert step.events is not None
    assert isinstance(step.events, EventSource)


@pytest.mark.unit
def test_event_source_reports_the_applied_scrub_policy_at_compile_time() -> None:
    """The compile-time-fact case (mirrors `rlimits`' exit-classification
    case, task-031 AC #8's shape): `known_at_compile` names what this
    mechanism actually knows -- the forwarded and set names -- never a
    claim about which OTHER names got scrubbed away, which a pure compile
    with no environment read cannot enumerate (see this module's own
    docstring's paragraph on that distinction)."""
    policy = EnvPolicy(mode=EnvMode.SCRUB, allow_names=("GH_TOKEN", "HOME"), set=(("FOO", "bar"),))
    step = env_scrub.compile(Spec(env=policy), _CTX)
    assert step.events is not None

    payloads = step.events.known_at_compile()
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload.kind is EventKind.SPAWN
    assert payload.data == {
        "env_policy": "scrub",
        "allowed_names": "GH_TOKEN,HOME",
        "set_names": "FOO",
    }
    assert "ts" not in payload.data
    assert "jail_id" not in payload.data


@pytest.mark.unit
def test_event_source_reports_pass_at_compile_time() -> None:
    """PASS's compile-time fact is just the mode -- nothing forwarded or
    set to name, since PASS confers everything already."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.PASS)), _CTX)
    assert step.events is not None
    payloads = step.events.known_at_compile()
    assert len(payloads) == 1
    assert payloads[0].kind is EventKind.SPAWN
    assert payloads[0].data == {"env_policy": "pass"}


@pytest.mark.unit
def test_event_source_never_classifies_an_exit() -> None:
    """Control / mirror of `rlimits`' own `known_at_compile() == ()`
    control: `env_scrub`'s interesting case is compile-time, not exit-time,
    so `classify_exit` always returns `None` regardless of how the
    workload ended."""
    step = env_scrub.compile(Spec(env=EnvPolicy(mode=EnvMode.SCRUB)), _CTX)
    assert step.events is not None
    assert step.events.classify_exit(ExitOutcome(returncode=0)) is None
    assert step.events.classify_exit(ExitOutcome(returncode=1)) is None
    assert step.events.classify_exit(ExitOutcome(returncode=-9)) is None
