"""Test brig.stack.Stack.compile: claims, coverage, compatibility, floors, composition.

SPEC.md §7 (verbatim, the whole validation contract):

    `Stack(mechanisms).compile(spec, floors) -> CompiledJail`

    Validation, in order:

    1. Claims -- every axis claimed by at most one mechanism. Overlap is a
       compile error, not a grading question.
    2. Coverage -- every axis either claimed or entering the aggregate report
       as `unenforced`. No silent gaps.
    3. Compatibility & ordering -- a literal, versioned matrix of (mechanism,
       mechanism) pairs with an *ordering rationale* string per pair. ...
       Unknown pairs are refused.
    4. Floors -- aggregate grades meet the caller's `require(...)` or the
       compile refuses, naming the axis and the shortfall.

    Composition: argv wrappers compose inside-out per the matrix ordering;
    env merges with later-wins declared conflicts as errors; helpers and
    staged files union; `requires` union.

SPEC.md §3: "The empty stack is valid and grades every axis unenforced."

Test doubles (never real mechanisms) cover the generic validation-order
behaviour above; they predate M3's real mechanisms (brig/mech shipped zero
at the time this file was first written). task-037's matrix-specific tests
(below, marked with their own AC headers) use the two real mechanisms that
exist as of M3 -- `env_scrub` and `rlimits` -- because the compatibility
matrix itself is data about THOSE two names, not about test doubles.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from dataclasses import dataclass, field

import pytest

import brig.core
import brig.stack
from brig.core import AXES, Axis, Grade, Graded, Limits, Spec
from brig.mech import CompileCtx, Step
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits


def _identity(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


@dataclass(slots=True)
class DoubleMechanism:
    """A minimal test double satisfying the `Mechanism` protocol.

    Not frozen: `Mechanism.name`/`Mechanism.axes` are plain (settable)
    Protocol attributes (see test_mech_contract.py's `ConcreteMechanism`),
    and mypy strict rejects a frozen dataclass's read-only fields as a
    structural match for them.

    Grades exactly the axes it claims (never partially), so it never trips
    Stack.compile's "claims an axis its Step doesn't grade" defensive check.
    """

    name: str
    axes: frozenset[Axis]
    env: dict[str, str] = field(default_factory=dict)
    grade: Grade = Grade.ENFORCED

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        return Step(
            wrap=_identity,
            env=dict(self.env),
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={axis: Graded(self.grade) for axis in self.axes},
            denial_signatures=(),
        )


def _spec() -> Spec:
    return Spec()


# --------------------------------------------------------------------------
# AC#2: empty stack, exact grades
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_stack_grades_all_seven_axes_unenforced() -> None:
    """AC#2: Stack([]).compile(spec).report has all seven axes, all UNENFORCED.

    Asserts the axis SET equals core.AXES and the grade SET equals exactly
    {UNENFORCED} -- not "contains unenforced", which a stronger-graded
    report would also satisfy.
    """
    compiled = brig.stack.Stack([]).compile(_spec())
    report = compiled.report
    assert frozenset(report.axes) == frozenset(AXES)
    assert {graded.grade for graded in report.axes.values()} == {Grade.UNENFORCED}


# --------------------------------------------------------------------------
# AC#3 / AC#4: floors, EC5
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_floor_the_empty_stack_cannot_meet_refuses_naming_axis_and_shortfall() -> None:
    """AC#3 (EC5 half 1): require(fs_read=ENFORCED) against the empty stack
    raises FloorViolation naming fs_read and carrying the shortfall
    (required ENFORCED, actual UNENFORCED). Assert structured fields, not
    str(exc).
    """
    floors = brig.core.require(fs_read=Grade.ENFORCED)
    with pytest.raises(brig.core.FloorViolation) as exc_info:
        brig.stack.Stack([]).compile(_spec(), floors)
    shortfalls = exc_info.value.shortfalls
    assert len(shortfalls) == 1
    shortfall = shortfalls[0]
    assert shortfall.axis is Axis.FS_READ
    assert shortfall.required is Grade.ENFORCED
    assert shortfall.actual is Grade.UNENFORCED


@pytest.mark.unit
def test_floor_the_empty_stack_can_meet_compiles() -> None:
    """AC#4 (EC5 control): require(fs_read=UNENFORCED) against the empty
    stack compiles successfully. Without this control the refusal test
    cannot distinguish "the floor was checked" from "compile always raises".
    """
    floors = brig.core.require(fs_read=Grade.UNENFORCED)
    compiled = brig.stack.Stack([]).compile(_spec(), floors)
    assert compiled.report.axes[Axis.FS_READ].grade is Grade.UNENFORCED


# --------------------------------------------------------------------------
# AC#5: validation order is observable (claims before floors)
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_claims_error_raised_before_floors_error_when_both_violated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC#5: a stack that violates claims (two doubles claiming the same
    axis) AND would also fail a floor raises the CLAIMS error, not the
    floors one.

    The compatibility matrix is seeded for this pair so that, if the
    implementation's order were inverted (floors before claims), execution
    would actually reach the floor check via a real report -- rather than
    being intercepted by the (unrelated) compatibility gate, which would
    make an order-inversion mutation redden for the wrong reason. See the
    ATTEMPT 1 IMPLEMENTER note for the paired red/green mutation evidence
    this test was used to produce.
    """
    monkeypatch.setattr(
        brig.stack,
        "COMPATIBILITY_MATRIX",
        {
            frozenset({"double-a", "double-b"}): brig.stack.MatrixEntry(
                outer="double-a", rationale="test-seeded: order-of-validation probe"
            )
        },
    )
    a = DoubleMechanism(name="double-a", axes=frozenset({Axis.NETWORK}))
    b = DoubleMechanism(name="double-b", axes=frozenset({Axis.NETWORK}))
    stack = brig.stack.Stack([a, b])
    # Neither double claims fs_read, so the aggregate report grades it
    # UNENFORCED -- this floor would also fail, if reached.
    floors = brig.core.require(fs_read=Grade.ENFORCED)

    with pytest.raises(brig.stack.AxisClaimConflict) as exc_info:
        stack.compile(_spec(), floors)
    assert exc_info.value.axis is Axis.NETWORK


# --------------------------------------------------------------------------
# AC#6: claims overlap names both mechanisms; control on disjoint axes
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_claims_overlap_names_axis_and_both_mechanisms() -> None:
    """AC#6: two doubles claiming the axis `network` raise AxisClaimConflict
    naming the axis and both mechanism names."""
    a = DoubleMechanism(name="double-a", axes=frozenset({Axis.NETWORK}))
    b = DoubleMechanism(name="double-b", axes=frozenset({Axis.NETWORK}))
    stack = brig.stack.Stack([a, b])

    with pytest.raises(brig.stack.AxisClaimConflict) as exc_info:
        stack.compile(_spec())

    err = exc_info.value
    assert err.axis is Axis.NETWORK
    assert {err.mechanism_a, err.mechanism_b} == {"double-a", "double-b"}


@pytest.mark.unit
def test_claims_overlap_control_disjoint_axes_do_not_raise_claims_error() -> None:
    """AC#6 control: two doubles claiming DISJOINT axes do not raise the
    claims error.

    With M2's zero-pair compatibility matrix, a two-mechanism stack is
    refused at the compatibility step regardless -- so the discriminating
    assertion is that execution gets PAST claims: CompatibilityRefused is
    raised, not AxisClaimConflict.
    """
    a = DoubleMechanism(name="double-a", axes=frozenset({Axis.FS_READ}))
    b = DoubleMechanism(name="double-b", axes=frozenset({Axis.NETWORK}))
    stack = brig.stack.Stack([a, b])

    with pytest.raises(brig.stack.CompatibilityRefused):
        stack.compile(_spec())


# --------------------------------------------------------------------------
# AC#7: compatibility, zero-pair matrix
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_two_mechanism_stack_refused_as_unknown_pair_naming_both() -> None:
    """AC#7: a two-mechanism stack is refused as an unknown pair (M2's
    matrix has zero pairs), naming both mechanisms."""
    a = DoubleMechanism(name="double-a", axes=frozenset({Axis.FS_READ}))
    b = DoubleMechanism(name="double-b", axes=frozenset({Axis.NETWORK}))
    stack = brig.stack.Stack([a, b])

    with pytest.raises(brig.stack.CompatibilityRefused) as exc_info:
        stack.compile(_spec())

    err = exc_info.value
    assert {err.mechanism_a, err.mechanism_b} == {"double-a", "double-b"}
    assert err.matrix_version == brig.stack.MATRIX_VERSION


@pytest.mark.unit
def test_one_mechanism_stack_compiles_control() -> None:
    """AC#7 control: a one-mechanism stack compiles (no pair to check).

    Also covers step 2's "no silent gaps" claim for a NON-empty stack: the
    aggregate report carries all seven axes -- the one claimed axis graded
    by the mechanism's Step, and the six unclaimed axes filled UNENFORCED
    (not merely "the claimed axis is right"; AC#2 covers the all-UNENFORCED
    empty-stack case, this covers the mixed case M3 will actually depend
    on).
    """
    a = DoubleMechanism(name="double-a", axes=frozenset({Axis.FS_READ}))
    compiled = brig.stack.Stack([a]).compile(_spec())
    assert frozenset(compiled.report.axes) == frozenset(AXES)
    assert compiled.report.axes[Axis.FS_READ].grade is Grade.ENFORCED
    unclaimed = {axis: g.grade for axis, g in compiled.report.axes.items() if axis != Axis.FS_READ}
    assert set(unclaimed.values()) == {Grade.UNENFORCED}
    assert compiled.mechanism_names == ("double-a",)


@pytest.mark.unit
def test_empty_stack_compiles_control() -> None:
    """AC#7 control: the empty stack compiles (no pairs at all)."""
    compiled = brig.stack.Stack([]).compile(_spec())
    assert compiled.mechanism_names == ()


# --------------------------------------------------------------------------
# AC#8: composition with zero mechanisms is identity
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_zero_mechanism_composition_is_identity() -> None:
    """AC#8: compiled.wrap(("echo", "hi")) returns exactly ("echo", "hi"),
    compiled.env is empty, staged and helpers are empty tuples, requires is
    an empty frozenset."""
    compiled = brig.stack.Stack([]).compile(_spec())
    assert compiled.wrap(("echo", "hi")) == ("echo", "hi")
    assert dict(compiled.env) == {}
    assert compiled.staged == ()
    assert compiled.helpers == ()
    assert compiled.requires == frozenset()


# --------------------------------------------------------------------------
# AC#9: env conflict
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_env_conflict_raises_naming_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC#9: two doubles setting the same env name to different values
    raise EnvConflict naming the variable."""
    monkeypatch.setattr(
        brig.stack,
        "COMPATIBILITY_MATRIX",
        {
            frozenset({"double-a", "double-b"}): brig.stack.MatrixEntry(
                outer="double-a", rationale="test-seeded: env-merge probe"
            )
        },
    )
    a = DoubleMechanism(
        name="double-a", axes=frozenset({Axis.FS_READ}), env={"SAME_NAME": "value-a"}
    )
    b = DoubleMechanism(
        name="double-b", axes=frozenset({Axis.NETWORK}), env={"SAME_NAME": "value-b"}
    )
    stack = brig.stack.Stack([a, b])

    with pytest.raises(brig.stack.EnvConflict) as exc_info:
        stack.compile(_spec())

    err = exc_info.value
    assert err.name == "SAME_NAME"
    assert {err.mechanism_a, err.mechanism_b} == {"double-a", "double-b"}
    assert {err.value_a, err.value_b} == {"value-a", "value-b"}


@pytest.mark.unit
def test_env_same_name_same_value_control_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC#9 control: the same env name set to the same value by two
    mechanisms does not raise."""
    monkeypatch.setattr(
        brig.stack,
        "COMPATIBILITY_MATRIX",
        {
            frozenset({"double-a", "double-b"}): brig.stack.MatrixEntry(
                outer="double-a", rationale="test-seeded: env-merge probe"
            )
        },
    )
    a = DoubleMechanism(
        name="double-a", axes=frozenset({Axis.FS_READ}), env={"SAME_NAME": "shared-value"}
    )
    b = DoubleMechanism(
        name="double-b", axes=frozenset({Axis.NETWORK}), env={"SAME_NAME": "shared-value"}
    )
    stack = brig.stack.Stack([a, b])

    compiled = stack.compile(_spec())
    assert dict(compiled.env) == {"SAME_NAME": "shared-value"}


# --------------------------------------------------------------------------
# Stack construction: duplicate mechanism name
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_duplicate_mechanism_name_raises_value_error_at_construction() -> None:
    """Deliverable: duplicate mechanism *name* is a ValueError, raised at
    Stack construction (not deferred to compile)."""
    a = DoubleMechanism(name="dup", axes=frozenset({Axis.FS_READ}))
    b = DoubleMechanism(name="dup", axes=frozenset({Axis.NETWORK}))
    with pytest.raises(ValueError, match="dup"):
        brig.stack.Stack([a, b])


@pytest.mark.unit
def test_distinct_mechanism_names_construct_fine_control() -> None:
    """Control: distinct mechanism names construct without error."""
    a = DoubleMechanism(name="a", axes=frozenset({Axis.FS_READ}))
    b = DoubleMechanism(name="b", axes=frozenset({Axis.NETWORK}))
    stack = brig.stack.Stack([a, b])
    assert len(stack.mechanisms) == 2


# --------------------------------------------------------------------------
# task-044 AC #4: the axes ceiling. SPEC.md §6 / decision-092 (P-12): "a
# Step may not grade an axis outside its mechanism's declared axes (the
# declaration is a ceiling, not a hint)."
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_step_may_not_grade_an_axis_outside_the_declared_ceiling() -> None:
    """AC #4: a mechanism declaring `axes={FS_READ}` whose compiled Step
    also grades `NETWORK` raises ValueError naming the mechanism, the
    offending axis, and the declared axes. Control, same test: a Step
    grading a SUBSET of its declared axes compiles without raising (the
    unclaimed member of the declared set simply falls through to the
    coverage fill as UNENFORCED -- SPEC.md §6's own env_scrub-under-PASS
    case, reproduced here with a double so this test needs no real
    mechanism)."""

    @dataclass(slots=True)
    class OverclaimingStub:
        name: str = "overclaiming-stub"
        axes: frozenset[Axis] = frozenset({Axis.FS_READ})

        def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
            return Step(
                wrap=_identity,
                env={},
                staged=(),
                helpers=(),
                requires=frozenset(),
                grades={
                    Axis.FS_READ: Graded(Grade.ENFORCED),
                    Axis.NETWORK: Graded(Grade.ENFORCED),
                },
                denial_signatures=(),
            )

    stub = OverclaimingStub()
    with pytest.raises(ValueError) as exc_info:
        brig.stack.Stack([stub]).compile(_spec())

    message = str(exc_info.value)
    assert stub.name in message
    assert Axis.NETWORK.value in message
    for axis in stub.axes:
        assert axis.value in message

    # Control: a Step grading a SUBSET of the declared axes compiles fine,
    # and the unclaimed declared axis (NETWORK) falls through UNENFORCED.
    @dataclass(slots=True)
    class UnderclaimingStub:
        name: str = "underclaiming-stub"
        axes: frozenset[Axis] = frozenset({Axis.FS_READ, Axis.NETWORK})

        def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
            return Step(
                wrap=_identity,
                env={},
                staged=(),
                helpers=(),
                requires=frozenset(),
                grades={Axis.FS_READ: Graded(Grade.ENFORCED)},
                denial_signatures=(),
            )

    under = UnderclaimingStub()
    compiled = brig.stack.Stack([under]).compile(_spec())
    assert compiled.report.axes[Axis.FS_READ].grade is Grade.ENFORCED
    assert compiled.report.axes[Axis.NETWORK].grade is Grade.UNENFORCED


# --------------------------------------------------------------------------
# Denial-signature / CompiledJail field sanity (not a numbered AC, but
# exercises fields the launcher depends on)
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_compiled_jail_env_is_defensively_copied() -> None:
    """CompiledJail.env survives mutation of the dict passed through
    composition (defensive-copy idiom, matching mech.Step.env)."""
    a = DoubleMechanism(name="a", axes=frozenset({Axis.FS_READ}), env={"X": "1"})
    compiled = brig.stack.Stack([a]).compile(_spec())
    # There is no live source dict to mutate post-construction here (env is
    # built fresh during compile), so this asserts the type contract
    # instead: env is read-only.
    with pytest.raises(TypeError):
        compiled.env["X"] = "mutated"  # type: ignore[index]


@pytest.mark.unit
def test_compiled_jail_has_exactly_eleven_fields() -> None:
    """Deliverable: CompiledJail's field set is pinned to the named fields
    -- "exactly what the launcher and the report need, and no more." A
    missing or invented field is red (same idiom as
    test_mech_contract.py's test_step_has_exactly_seven_fields).

    Nine fields through M3; task-047 (M4) adds `signatures` -- the
    `SignatureBook` assembled alongside `report` in the same pass over
    `steps`, so a rehydrated `Handle` can still name which mechanism claims
    an axis and what its denial looks like (SPEC.md §6, §12). decision-152
    (2026-09-08) adds `sensors` -- every non-`None` `Step.events` from the
    same pass, because `run` is the only layer permitted to CALL a sensor
    and had no way to reach one: `Step.events` was assembled by every
    mechanism that had one and then dropped on the floor here."""
    expected_fields = {
        "spec",
        "report",
        "wrap",
        "env",
        "staged",
        "helpers",
        "requires",
        "mechanism_names",
        "matrix_version",
        "signatures",
        "sensors",
    }
    actual_fields = {f.name for f in dataclasses.fields(brig.stack.CompiledJail)}
    assert actual_fields == expected_fields, (
        f"CompiledJail field mismatch. Missing: {expected_fields - actual_fields}. "
        f"Extra: {actual_fields - expected_fields}."
    )


@pytest.mark.unit
def test_matrix_is_versioned_and_zero_pairs_control(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control, kept from M2: with the matrix EMPTIED (monkeypatched back
    to zero pairs, M2's own shipped state), a two-mechanism stack is
    refused as unknown -- proves the "zero pairs -> everything unknown"
    property this task's own one-pair matrix (test below) has moved past,
    without asserting it against the now-populated live matrix (which
    would just be wrong, not merely stale)."""
    monkeypatch.setattr(brig.stack, "COMPATIBILITY_MATRIX", {})
    a = DoubleMechanism(name="double-a", axes=frozenset({Axis.FS_READ}))
    b = DoubleMechanism(name="double-b", axes=frozenset({Axis.NETWORK}))
    with pytest.raises(brig.stack.CompatibilityRefused):
        brig.stack.Stack([a, b]).compile(_spec())


# --------------------------------------------------------------------------
# task-037: the compatibility matrix's first real pair, {env_scrub,
# rlimits}, rlimits outermost.
#
# task-059 FORCED EDIT (flagged as a decision-113b candidate, same shape as
# task-058's own ratified deviation 2a on this file's sibling,
# test_mech_events_purity.py -- "extending this pin is not scope creep, it
# is what the pin exists to force a reviewer of the diff to notice", and
# decision-124's later ratification of that exact precedent). task-059's
# Deliverable requires two NEW `COMPATIBILITY_MATRIX` rows
# (`{rlimits, seatbelt}`, `{seatbelt, env_scrub}`) and a bumped
# `MATRIX_VERSION` (2 -> 3) in `brig/stack/__init__.py` -- a file this task
# does not own the tests for, but this file's own
# `test_matrix_has_exactly_one_pair_...`/`test_matrix_version_incremented_
# to_two`/`test_compiled_jail_carries_the_new_matrix_version` hard-code
# task-037's THEN-current "exactly one pair" / "version 2" facts, which
# task-059's own required Deliverable makes false. Leaving them
# hard-coded is `./scripts/verify.sh` (both tiers) failing outright --
# task-059 AC #12 -- the same "no authorized role could satisfy both" shape
# decision-079 names. The three edits below are the MINIMAL ones that keep
# each test's original claim true of ITS OWN pair/row (task-037's
# `{env_scrub, rlimits}` entry, unchanged in value) while updating only the
# now-stale cardinality/version numbers a later mechanism was always going
# to move.
# --------------------------------------------------------------------------

_CTX = CompileCtx(jail_dir="/unused/test-stack-matrix", platform=sys.platform)


@pytest.mark.unit
def test_matrix_has_the_env_scrub_rlimits_pair_with_rationale() -> None:
    """task-037 AC #1, narrowed to its own pair (task-059 forced edit, see
    this section's banner comment): the matrix's `{env_scrub, rlimits}`
    entry exists, unchanged, among however many rows the live matrix
    carries -- its rationale string is non-empty and names which mechanism
    is outermost. Cardinality itself (how many rows total) is NOT this
    test's claim; `brig/stack/__init__.py`'s own module docstring is where
    that is tracked."""
    matrix = dict(brig.stack.COMPATIBILITY_MATRIX)
    entry = matrix[frozenset({"env_scrub", "rlimits"})]
    assert entry.rationale.strip() != ""
    assert entry.outer == "rlimits"
    assert "rlimits" in entry.rationale
    assert "outermost" in entry.rationale.lower()


@pytest.mark.unit
def test_matrix_version_is_the_current_one() -> None:
    """task-037 Deliverable: MATRIX_VERSION incremented from M2's `1` now
    that the matrix carries content (auditability, SPEC.md §7:
    `CompiledJail.matrix_version` exists so grades can be re-derived
    against the matrix version that produced them). task-059 (forced edit,
    see this section's banner comment) bumps it again, 2 -> 3, for its own
    two new rows. task-080/decision-135 bumps it again, 3 -> 4, for
    connect_proxy's three new rows. decision-159 bumps it again, 4 -> 5,
    for bwrap's four."""
    assert brig.stack.MATRIX_VERSION == 5


@pytest.mark.unit
def test_compiled_jail_carries_the_new_matrix_version() -> None:
    """task-037 AC #6: `compiled.matrix_version` equals the new constant.
    task-059 (forced edit, see this section's banner comment) updates the
    literal `2` this test originally pinned to `3`.

    Mutation pairing (AC #6, deterministic, scratch-copy-plus-sha256
    restoration per WORKFLOW.md decision-074 -- see the task's Evidence
    section for the round trip): temporarily set `MATRIX_VERSION = 1` in
    `brig/stack/__init__.py`, re-run this exact test --
    `compiled.matrix_version == 5` reddens (it becomes `1`), then revert.
    task-080/decision-135 updates the literal `3` to `4`; decision-159
    updates it to `5` for bwrap's four rows.
    """
    compiled = brig.stack.Stack([env_scrub, rlimits]).compile(Spec(), ctx=_CTX)
    assert compiled.matrix_version == 5
    assert compiled.matrix_version == brig.stack.MATRIX_VERSION


@pytest.mark.unit
def test_ordering_rlimits_outermost_regardless_of_construction_order() -> None:
    """task-037 AC #2: ordering is observable in the composed argv, not
    just declared. `Stack([env_scrub, rlimits])` and the REVERSE
    construction, `Stack([rlimits, env_scrub])`, compile to the identical
    composed argv, and its prefix is EXACTLY the trampoline invocation --
    `rlimits` outermost -- proving the matrix decides ordering, not the
    list order Stack() was constructed with.

    Mutation pairing (AC #3, deterministic): flip `_ENV_SCRUB_RLIMITS_
    RATIONALE`'s pair to `MatrixEntry(outer="env_scrub", ...)` in
    `brig/stack/__init__.py`, re-run this exact test -- both asserted
    prefixes go red (the trampoline is no longer first; `/bin/sh` is), then
    revert. See the task's Evidence section for the scratch-copy-plus-
    sha256 round trip.
    """
    workload = ("python3", "-c", "pass")
    forward = brig.stack.Stack([env_scrub, rlimits]).compile(Spec(), ctx=_CTX)
    reverse = brig.stack.Stack([rlimits, env_scrub]).compile(Spec(), ctx=_CTX)

    forward_argv = forward.wrap(workload)
    reverse_argv = reverse.wrap(workload)

    # Both construction orders produce the IDENTICAL composed argv: the
    # matrix, not Stack()'s own argument order, decided this.
    assert forward_argv == reverse_argv

    # The exact prefix `rlimits.compile`'s own render emits for an
    # uncapped (`cpu_seconds=0`, Spec()'s default) limit -- see
    # `brig/mech/rlimits.py::_render_wrap`. Asserted as an exact tuple
    # slice, never a substring: `rlimits` (the trampoline) is OUTERMOST.
    expected_prefix = (sys.executable, "-m", "brig.mech.trampoline", "--")
    assert forward_argv[: len(expected_prefix)] == expected_prefix
    assert reverse_argv[: len(expected_prefix)] == expected_prefix

    # Everything after the trampoline's own prefix is env_scrub's SCRUB-mode
    # shell wrapper (Spec()'s default EnvPolicy is SCRUB, empty allow-list)
    # -- confirms env_scrub is nested INSIDE the trampoline, not the other
    # way around, and pins the full composed shape, not just its prefix.
    assert forward_argv[len(expected_prefix) :] == (
        "/bin/sh",
        "-c",
        'exec /usr/bin/env -i "$@"',
        "sh",
        *workload,
    )


@pytest.mark.unit
def test_unknown_pair_refused_naming_both_members_and_matrix_version_control_known_pair() -> None:
    """task-037 AC #4: unknown pairs are still refused. A stack containing
    `rlimits`, `env_scrub`, and a third stub mechanism (claiming a
    disjoint axis) is refused as an unknown pair -- naming the two
    unrecognized members and the matrix version. Control, same test: the
    known `{env_scrub, rlimits}` pair alone still compiles."""

    @dataclass(slots=True)
    class ThirdStub:
        name: str = "third-stub"
        axes: frozenset[Axis] = frozenset({Axis.CHANNEL_EXCLUSIVITY})

        def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
            return Step(
                wrap=lambda argv: argv,
                env={},
                staged=(),
                helpers=(),
                requires=frozenset(),
                grades={Axis.CHANNEL_EXCLUSIVITY: Graded(Grade.ENFORCED)},
                denial_signatures=(),
            )

    stub = ThirdStub()
    stack = brig.stack.Stack([env_scrub, rlimits, stub])

    with pytest.raises(brig.stack.CompatibilityRefused) as exc_info:
        stack.compile(Spec(), ctx=_CTX)

    err = exc_info.value
    # Stack.compile's pairwise scan is `i<j` over `self.mechanisms` in ITS
    # OWN construction order `(env_scrub, rlimits, stub)`: (0,1) is the
    # known {env_scrub, rlimits} pair (no raise), so (0,2) -- env_scrub
    # paired with the stub -- is the first unknown pair reached and raises
    # deterministically. Pinned exactly, not "either name": a looser
    # assertion here would pass even if the scan order regressed.
    assert err.mechanism_a == "env_scrub"
    assert err.mechanism_b == "third-stub"
    assert err.matrix_version == brig.stack.MATRIX_VERSION

    # Control: the known pair alone (stub removed) compiles.
    known_pair = brig.stack.Stack([env_scrub, rlimits]).compile(Spec(), ctx=_CTX)
    assert known_pair.mechanism_names == ("env_scrub", "rlimits")


@pytest.mark.unit
def test_two_mechanisms_claiming_env_axis_raise_conflict_control_real_disjoint_pair() -> None:
    """task-037 AC #5: single-claim validation is live, testable now that
    two real mechanisms exist. A stub claiming `Axis.ENV` alongside the
    real `env_scrub` (same axis) raises `AxisClaimConflict` naming the
    axis and both mechanism names. Control, same test: the real
    `env_scrub` + `rlimits` pair (disjoint axes -- `env` vs `limits`)
    compiles without it."""

    @dataclass(slots=True)
    class EnvClaimingStub:
        name: str = "env-claiming-stub"
        axes: frozenset[Axis] = frozenset({Axis.ENV})

        def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
            return Step(
                wrap=lambda argv: argv,
                env={},
                staged=(),
                helpers=(),
                requires=frozenset(),
                grades={Axis.ENV: Graded(Grade.ENFORCED)},
                denial_signatures=(),
            )

    stub = EnvClaimingStub()
    stack = brig.stack.Stack([env_scrub, stub])

    with pytest.raises(brig.stack.AxisClaimConflict) as exc_info:
        stack.compile(Spec(), ctx=_CTX)

    err = exc_info.value
    assert err.axis is Axis.ENV
    assert {err.mechanism_a, err.mechanism_b} == {"env_scrub", "env-claiming-stub"}

    # Control: the real disjoint-axes pair compiles fine.
    compiled = brig.stack.Stack([env_scrub, rlimits]).compile(Spec(), ctx=_CTX)
    assert compiled.report.axes[Axis.ENV].grade is Grade.ENFORCED
    assert compiled.report.axes[Axis.LIMITS].grade is Grade.BEST_EFFORT


@pytest.mark.unit
def test_real_pair_compiles_with_a_cpu_limit_and_scrub_env() -> None:
    """Smoke test using both mechanisms with a non-default Spec (a real
    cpu limit and a real allow-listed SCRUB policy), confirming compile
    succeeds end-to-end and the resulting argv still has the trampoline
    outermost, `--cpu` flag and all."""
    spec = Spec(
        limits=Limits(cpu_seconds=5),
        env=brig.core.EnvPolicy(mode=brig.core.EnvMode.SCRUB, allow_names=("PATH",)),
    )
    compiled = brig.stack.Stack([env_scrub, rlimits]).compile(spec, ctx=_CTX)
    argv = compiled.wrap(("true",))
    assert argv[:6] == (
        sys.executable,
        "-m",
        "brig.mech.trampoline",
        "--cpu",
        "5",
        "--",
    )
    assert argv[6:10] == ("/bin/sh", "-c", 'exec /usr/bin/env -i ${PATH:+"PATH=$PATH"} "$@"', "sh")
    assert argv[10:] == ("true",)


@pytest.mark.unit
def test_compiled_jail_denial_signature_pattern_smoke() -> None:
    """Smoke test: a mechanism's declared denial_signatures survive compile
    (not part of CompiledJail's own fields, but confirms Step compilation
    is exercised faithfully by Stack.compile). Uses re.Pattern directly, as
    mech.Step does."""

    @dataclass(slots=True)
    class WithDenial:
        name: str
        axes: frozenset[Axis]

        def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
            return Step(
                wrap=_identity,
                env={},
                staged=(),
                helpers=(),
                requires=frozenset(),
                grades={axis: Graded(Grade.ENFORCED) for axis in self.axes},
                denial_signatures=(re.compile(r"Operation not permitted"),),
            )

    m = WithDenial(name="denial-double", axes=frozenset({Axis.FS_WRITE}))
    compiled = brig.stack.Stack([m]).compile(_spec())
    assert compiled.report.axes[Axis.FS_WRITE].grade is Grade.ENFORCED
